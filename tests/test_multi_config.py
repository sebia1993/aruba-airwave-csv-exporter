import json

import pytest

from airwave_csv.multi_config import (
    MultiConfig, ServerProfile, add_server, load_v2, normalize_server_url,
    save_v2, validate_server_profile, validate_settings,
)


def configured():
    return MultiConfig(export_root="C:/AirWaveCSV")


def test_new_install_allows_zero_servers_and_defaults():
    cfg = configured()
    assert cfg.parallel_limit == 3
    assert cfg.servers == []
    validate_settings(cfg)


def test_five_allowed_sixth_rejected():
    cfg = configured()
    for index in range(1, 6):
        add_server(cfg, name=f"AW{index}", url=f"https://aw{index}.example.invalid",
                   username="operator")
    assert len(cfg.servers) == 5
    assert cfg.servers[0].id == "airwave-01"
    with pytest.raises(ValueError, match="5"):
        add_server(cfg, name="AW6", url="https://aw6.example.invalid", username="operator")


def test_duplicate_url_normalized():
    cfg = configured()
    add_server(cfg, name="First", url="https://AW.EXAMPLE.INVALID:443/",
               username="operator")
    assert normalize_server_url("https://aw.example.invalid") == "https://aw.example.invalid"
    with pytest.raises(ValueError, match="중복"):
        add_server(cfg, name="Second", url="https://aw.example.invalid/",
                   username="someone")


def test_deleted_ids_not_reused():
    cfg = configured()
    one = add_server(cfg, name="A", url="https://a.example.invalid", username="ops")
    cfg.servers.remove(one)
    second = add_server(cfg, name="B", url="https://b.example.invalid", username="ops")
    assert second.id == "airwave-02"


def test_atomic_save_load_no_password(tmp_path):
    cfg = configured()
    add_server(cfg, name="A", url="https://a.example.invalid", username="operator")
    file = tmp_path / "multi_config.json"
    save_v2(cfg, file)
    assert json.loads(file.read_text(encoding="utf-8"))["schema_version"] == 2
    assert "password" not in file.read_text(encoding="utf-8")
    loaded = load_v2(file)
    assert loaded.servers == cfg.servers
    assert loaded.parallel_limit == 3


@pytest.mark.parametrize("bad", ["http://host", "https://someone:secret@host",
                                  "https://host/?token=abc", "no-scheme"])
def test_reject_insecure_urls(bad):
    with pytest.raises(ValueError):
        add_server(configured(), name="bad", url=bad, username="ops")


def test_per_server_readiness_isolated_from_global_structure():
    cfg = configured()
    good = add_server(cfg, name="B", url="https://good.example.invalid", username="ops")
    cfg.servers.insert(0, ServerProfile(
        id="airwave-00", display_name="A", server_url="invalid", username=""
    ))
    validate_settings(cfg)
    with pytest.raises(ValueError):
        validate_server_profile(cfg.servers[0])
    validate_server_profile(good)


def test_time_limit_validation():
    cfg = configured()
    cfg.parallel_limit = 6
    with pytest.raises(ValueError):
        validate_settings(cfg)
    cfg.parallel_limit = 3
    cfg.schedule_time = "25:90"
    with pytest.raises(ValueError):
        validate_settings(cfg)
