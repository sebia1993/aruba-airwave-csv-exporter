import json

from airwave_csv.config import Config
from airwave_csv.migration import migrate_if_needed
from airwave_csv.multi_config import registry_path


class FakeVault:
    stored = {}

    @classmethod
    def get(cls, url, username):
        if (url, username) not in cls.stored:
            raise ValueError("missing")
        return cls.stored[url, username]

    @classmethod
    def set_for_server(cls, sid, password):
        cls.stored[sid] = password


def test_migration_is_idempotent_and_preserves_original(tmp_path):
    FakeVault.stored = {("https://aw.example.invalid", "ops"): "secret123"}
    old = Config(server_url="https://aw.example.invalid", username="ops",
                 export_dir=str(tmp_path / "exports"))
    old.save(tmp_path / "config.json")
    (tmp_path / "selectors.json").write_text('{"table_root_css":"#table"}',encoding="utf-8")
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "latest.csv").write_text("Name,Model\nap1,AP535\n")
    first = migrate_if_needed(tmp_path, FakeVault)
    second = migrate_if_needed(tmp_path, FakeVault)
    assert [x.id for x in first.servers] == ["airwave-01"]
    assert len(second.servers) == 1
    assert FakeVault.stored["airwave-01"] == "secret123"
    assert (tmp_path / "config.v1.backup.json").exists()
    assert (tmp_path / "selectors" / "airwave-01.json").exists()
    assert (tmp_path / "exports" / "latest.csv").exists()
    assert "secret123" not in registry_path(tmp_path).read_text(encoding="utf-8")


def test_empty_install_has_no_servers(tmp_path):
    assert migrate_if_needed(tmp_path, FakeVault).servers == []


def test_corrupt_legacy_stays_unchanged_and_is_not_migrated(tmp_path):
    old = tmp_path / "config.json"
    old.write_text("{bad", encoding="utf-8")
    try:
        migrate_if_needed(tmp_path, FakeVault)
    except (ValueError, json.JSONDecodeError):
        pass
    else:
        raise AssertionError("expected failure")
    assert old.read_text(encoding="utf-8") == "{bad"
    assert not registry_path(tmp_path).exists()


def test_missing_vault_does_not_block_migration(tmp_path):
    FakeVault.stored={}
    Config(server_url="https://aw.example.invalid", username="ops").save(
        tmp_path / "config.json"
    )
    result=migrate_if_needed(tmp_path, FakeVault)
    assert len(result.servers)==1
    assert "airwave-01" not in FakeVault.stored
