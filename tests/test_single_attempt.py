from airwave_csv.config import Config, SelectorProfile, SELECTOR_TEMPLATE
from airwave_csv.engine import collect_attempt
from airwave_csv.portal import PortalError


class WrongView:
    def __init__(self, cfg, profile):
        pass
    def download(self, staged, password):
        raise PortalError(45, "wrong view")


class Busy:
    def __init__(self, cfg, profile):
        pass
    def download(self, staged, password):
        raise PortalError(47, "timed out")


class Good:
    def __init__(self, cfg, profile):
        pass
    def download(self, staged, password):
        staged.write_text("Name,Model\nAP1,535\n", encoding="utf-8")
        return 1


def cfg(tmp_path):
    return Config(server_url="https://aw.example.invalid", username="ops",
                  export_dir=str(tmp_path/"exports"))


def test_wrong_view_never_downloads(tmp_path):
    r=collect_attempt(cfg(tmp_path),SelectorProfile(dict(SELECTOR_TEMPLATE)),"fake",
                      portal_factory=WrongView,home=tmp_path)
    assert r.exit_code==45 and not r.retryable
    assert not (tmp_path/"exports"/"latest.csv").exists()


def test_loading_timeout_can_retry(tmp_path):
    r=collect_attempt(cfg(tmp_path),SelectorProfile(dict(SELECTOR_TEMPLATE)),"fake",
                      portal_factory=Busy,home=tmp_path)
    assert r.exit_code==47 and r.retryable


def test_attempt_saves_valid_csv_without_global_lock(tmp_path):
    r=collect_attempt(cfg(tmp_path),SelectorProfile(dict(SELECTOR_TEMPLATE)),"fake",
                      portal_factory=Good,home=tmp_path)
    assert r.exit_code==0
    assert r.saved.rows == 1
    assert (tmp_path/"exports"/"latest.csv").exists()
    assert not (tmp_path/"state"/"run.lock").exists()
