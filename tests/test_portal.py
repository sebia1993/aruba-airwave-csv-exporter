import pytest

from airwave_csv.config import Config, SELECTOR_TEMPLATE, SelectorProfile
from airwave_csv.portal import AirWavePortal, PortalError


class Select:
    def count(self):
        return 1

    def __init__(self, selected):
        self.selected = selected

    def evaluate(self, expression):
        if "tagName" in expression:
            return "select"
        return self.selected

    def select_option(self, label):
        self.selected = label


class Scope:
    def __init__(self, controls):
        self.controls = controls

    def locator(self, css):
        return self.controls[css]

    def count(self):
        return 1


def profile():
    d = dict(SELECTOR_TEMPLATE)
    d["table_root_css"] = "#table"
    d["view_control_css"] = "#view"
    d["folder_control_css"] = "#folder"
    d["rows_css"] = ".row"
    d["total_count_css"] = "#count"
    return SelectorProfile(d)


def test_default_view_is_changed_to_devices_then_verified():
    control = Select("Down Devices")
    root = Scope({"#view": control})
    page = Scope({"#table": root})
    portal = AirWavePortal(Config(), profile())
    portal._set_view(page)
    portal._verify_view(page)
    assert control.selected == "Devices"


def test_default_view_mismatch_causes_error_45():
    control = Select("Down Devices")
    root = Scope({"#view": control})
    page = Scope({"#table": root})
    portal = AirWavePortal(Config(), profile())
    with pytest.raises(PortalError) as err:
        portal._verify_view(page)
    assert err.value.code == 45


def test_waits_15_seconds_but_not_more_than_30(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("airwave_csv.portal.time.monotonic", lambda: now[0])
    monkeypatch.setattr("airwave_csv.portal.time.sleep", lambda n: now.__setitem__(0, now[0] + n))

    class Rows:
        def count(self):
            return 2

        def nth(self, index):
            return self

        def is_visible(self):
            return True

    class Page:
        def locator(self, css):
            return Rows()

    portal = AirWavePortal(Config(), profile())
    monkeypatch.setattr(portal, "_verify_expanded", lambda page: True)
    monkeypatch.setattr(portal, "_total", lambda page: 2)
    result = portal._wait_for_all(Page())
    assert result == 2
    assert 15 <= now[0] - 100 <= 30


def test_timeout_when_spinner_never_disappears(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("airwave_csv.portal.time.monotonic", lambda: now[0])
    monkeypatch.setattr("airwave_csv.portal.time.sleep", lambda n: now.__setitem__(0, now[0] + n))

    class Busy:
        def count(self):
            return 1

        def nth(self, i):
            return self

        def is_visible(self):
            return True

    class Page:
        def locator(self, css):
            return Busy()

    p = profile()
    p.values["loading_css"] = "#busy"
    portal = AirWavePortal(Config(), p)
    monkeypatch.setattr(portal, "_verify_expanded", lambda page: True)
    with pytest.raises(PortalError) as error:
        portal._wait_for_all(Page())
    assert error.value.code == 47
    assert now[0] >= 30
