import pytest

from airwave_csv.credentials import CredentialStore
from airwave_csv.multi_config import MultiConfig, add_server
from airwave_csv.paths import server_export_dir, server_selectors_path
from airwave_csv.csv_store import store_export


def test_alias_does_not_change_path(tmp_path):
    cfg = MultiConfig(export_root=str(tmp_path / "exports"))
    s = add_server(cfg,name="../operator",url="https://aw.example.invalid",username="ops")
    assert server_export_dir(cfg,s.id) == tmp_path/"exports"/"airwave-01"
    with pytest.raises(ValueError):
        server_export_dir(cfg,"../escape")


def test_server_latest_isolation(tmp_path):
    cfg=MultiConfig(export_root=str(tmp_path))
    a=add_server(cfg,name="A",url="https://a.example.invalid",username="ops")
    b=add_server(cfg,name="B",url="https://b.example.invalid",username="ops")
    a_dir=server_export_dir(cfg,a.id)
    b_dir=server_export_dir(cfg,b.id)
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    for directory in (a_dir,b_dir):
        tmp=directory/"temp.part"
        tmp.write_text("Name,Model\nap1,AP-535\n", encoding="utf-8")
        store_export(tmp,directory,expected_rows=1)
    assert (a_dir/"latest.csv").exists() and (b_dir/"latest.csv").exists()
    assert a_dir!=b_dir


def test_selectors_path_rejects_escape(tmp_path):
    assert server_selectors_path(tmp_path, "airwave-01")==tmp_path/"selectors"/"airwave-01.json"
    with pytest.raises(ValueError):
        server_selectors_path(tmp_path, "other/name")


def test_vault_keys_are_independent(monkeypatch):
    calls = {}
    class Vault:
        def set_password(self, service, key, value):
            calls[(service,key)]=value
        def get_password(self, service, key):
            return calls.get((service,key))
    monkeypatch.setattr(CredentialStore,"_vault",staticmethod(lambda:Vault()))
    CredentialStore.set_for_server("airwave-01","first")
    CredentialStore.set_for_server("airwave-02","second")
    assert CredentialStore.get_for_server("airwave-01")=="first"
    assert CredentialStore.get_for_server("airwave-02")=="second"


def test_concurrent_first_export_root_creation_does_not_reject_valid_server(
    tmp_path, monkeypatch,
):
    """Windows에서는 미존재 경로가 생성되는 동안 resolve() 정규화가 달라질 수 있습니다.

    실제 symlink가 없는 정상 경로는 동시 폴더 생성 때문에 차단하면 안 됩니다.
    """
    from pathlib import Path

    root = tmp_path / "concurrent-exports"
    cfg = MultiConfig(export_root=str(root))
    server = add_server(
        cfg, name="AW", url="https://safe.example.invalid", username="operator"
    )
    original_resolve = Path.resolve

    def changing_path_resolution(self, *args, **kwargs):
        # The directory becomes visible to another process between the two
        # resolution calls; this imitates Windows canonicalization instability.
        if self == root / server.id and not root.exists():
            root.mkdir(parents=True, exist_ok=True)
            return tmp_path / "different-canonical-name" / server.id
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", changing_path_resolution)
    assert server_export_dir(cfg, server.id) == root / server.id
    assert root.is_dir()
