import json

import pytest

from airwave_csv.config import (
    Config, ProfileError, REQUIRED_SELECTORS, SELECTOR_TEMPLATE, SelectorProfile
)


def test_config_roundtrip_and_wait_range(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(
        server_url="https://airwave.example.invalid",
        username="operator", export_dir=str(tmp_path / "exports"),
    )
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.server_url == cfg.server_url
    assert loaded.min_wait_seconds == 15
    assert loaded.max_wait_seconds == 30
    assert loaded.schedule_time == "09:00"
    assert "password" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("url", [
    "http://airwave.example.invalid",
    "https://someone:secret@host.example.invalid",
    "https://host.example.invalid/?token=abc",
    "not-a-url",
])
def test_bad_server_urls_fail(url):
    cfg = Config(server_url=url, username="operator")
    with pytest.raises(ValueError):
        cfg.validate(require_connection=True)


@pytest.mark.parametrize("start,end", [(14, 30), (15, 31), (30, 15)])
def test_wait_is_restricted(start, end):
    with pytest.raises(ValueError):
        Config(min_wait_seconds=start, max_wait_seconds=end).validate()


def test_unverified_profile_fails_closed(tmp_path):
    file = tmp_path / "selectors.json"
    with pytest.raises(ProfileError, match="생성"):
        SelectorProfile.load(file)
    saved = json.loads(file.read_text(encoding="utf-8"))
    assert all(not saved[key] for key in REQUIRED_SELECTORS)
    with pytest.raises(ProfileError, match="미설정"):
        SelectorProfile.load(file)


def test_complete_profile_can_load(tmp_path):
    data = dict(SELECTOR_TEMPLATE)
    for key in REQUIRED_SELECTORS:
        data[key] = ".valid"
    data["total_count_pattern"] = r"of (\d+)"
    file = tmp_path / "selectors.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    assert SelectorProfile.load(file)["view_control_css"] == ".valid"
