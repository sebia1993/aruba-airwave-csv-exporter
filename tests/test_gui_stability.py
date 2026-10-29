"""GUI 안정화 회귀 테스트. 실제 tkinter 디스플레이가 필요하지 않습니다."""

from __future__ import annotations

from airwave_csv import gui
from airwave_csv.multi_config import MultiConfig, add_server


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Table:
    def __init__(self):
        self.records = {}
        self.selected_id = None
        self.selection_set_calls = []
        self.insert_calls = []
        self.delete_calls = []

    def selection(self):
        return (self.selected_id,) if self.selected_id else ()

    def selection_set(self, sid):
        self.selection_set_calls.append(sid)
        self.selected_id = sid

    def selection_remove(self, *items):
        if self.selected_id in items:
            self.selected_id = None

    def get_children(self):
        return tuple(self.records)

    def delete(self, sid):
        self.delete_calls.append(sid)
        self.records.pop(sid, None)

    def insert(self, parent, index, iid, text, values):
        self.insert_calls.append(iid)
        self.records[iid] = tuple(values)

    def item(self, sid, **kwargs):
        if kwargs:
            self.records[sid] = tuple(kwargs["values"])
        return {"values": self.records[sid]}

    def exists(self, sid):
        return sid in self.records


def make_window(tmp_path, monkeypatch):
    w = gui.ExporterWindow.__new__(gui.ExporterWindow)
    settings = MultiConfig(export_root=str(tmp_path / "csv"))
    add_server(settings, name="AirWave A", url="https://aw1.example.invalid", username="operator")
    w.settings = settings
    w.time_var = Var("09:00")
    w.parallel_var = Var("3")
    w.dir_var = Var(str(tmp_path / "csv"))
    w.name_var = Var("AirWave A")
    w.url_var = Var("https://aw1.example.invalid")
    w.user_var = Var("operator")
    w.pass_var = Var("")
    w.enabled_var = Var(True)
    w.status_var = Var("old")
    w.table = Table()
    w._last_schedule_check = None
    w._cached_schedule_status = "확인 전"
    after_calls = []
    w.after = lambda delay, callback: after_calls.append((delay, callback)) or "timer-1"
    w.after_cancel = lambda token: None
    monkeypatch.setattr(gui, "app_home", lambda: tmp_path)
    monkeypatch.setattr(gui, "task_status", lambda: "Ready")
    monkeypatch.setattr(gui, "read_last_batch", lambda _: {})
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *args: None)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args: True)
    return w, after_calls


def test_failed_save_does_not_modify_current_settings(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    w.time_var.set("25:00")
    assert not w.save()
    assert w.settings.schedule_time == "09:00"
    assert w.settings.parallel_limit == 3


def test_failed_edit_rolls_back_server_and_credentials(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    w.table.selected_id = "airwave-01"
    w.name_var.set("Altered")
    old_server = w.settings.servers[0]
    monkeypatch.setattr(gui, "save_v2", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    assert w.edit() is None
    assert w.settings.servers[0] == old_server


def test_failed_add_does_not_consume_server_id(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    w.name_var.set("AirWave B")
    w.url_var.set("https://aw2.example.invalid")
    w.pass_var.set("demo-only")
    first_next = w.settings.next_server_number
    monkeypatch.setattr(gui.CredentialStore, "set_for_server", lambda *_: None)
    monkeypatch.setattr(gui, "save_v2", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    w.add()
    assert len(w.settings.servers) == 1
    assert w.settings.next_server_number == first_next


def test_failed_delete_preserves_server_registry(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    w.table.selected_id = "airwave-01"
    monkeypatch.setattr(gui, "save_v2", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    w.delete()
    assert len(w.settings.servers) == 1


def test_repeated_refresh_has_one_pending_timer(tmp_path, monkeypatch):
    w, timers = make_window(tmp_path, monkeypatch)
    w.refresh()
    w.refresh()
    w.refresh()
    assert len(timers) == 1


def test_refresh_keeps_current_selection_and_unsaved_input(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    w.refresh()
    w.table.selected_id = "airwave-01"
    w.name_var.set("아직 저장하지 않은 이름")
    w.refresh()
    w.refresh()
    assert w.name_var.get() == "아직 저장하지 않은 이름"
    assert w.table.selection_set_calls == []
    assert w.table.delete_calls == []
    assert w.table.insert_calls == ["airwave-01"]


def test_vault_failure_restores_original_config_without_allocating_rollback_bytes(
    tmp_path, monkeypatch,
):
    """파일 저장 후 보안 저장소가 실패해도 원본 설정을 보존합니다."""
    from pathlib import Path

    from airwave_csv.credentials import CredentialError
    from airwave_csv.multi_config import registry_path, save_v2

    w, _ = make_window(tmp_path, monkeypatch)
    config_path = registry_path(tmp_path)
    save_v2(w.settings, config_path)
    original = config_path.read_bytes()
    w.table.selected_id = "airwave-01"
    w.name_var.set("Changed before credential failure")
    w.pass_var.set("new-demo-secret")

    def fail_vault(*args):
        raise CredentialError("vault unavailable")

    original_write = Path.write_bytes

    def fail_rollback_allocation(self, data):
        if ".rollback." in self.name:
            raise OSError("no storage space for backup rewrite")
        return original_write(self, data)

    monkeypatch.setattr(gui.CredentialStore, "set_for_server", fail_vault)
    monkeypatch.setattr(Path, "write_bytes", fail_rollback_allocation)
    w.edit()
    assert w.settings.servers[0].display_name == "AirWave A"
    assert config_path.read_bytes() == original


def test_malformed_server_result_does_not_crash_refresh(tmp_path, monkeypatch):
    w, _ = make_window(tmp_path, monkeypatch)
    monkeypatch.setattr(gui, "read_last_batch", lambda _: {"servers": "damaged"})
    w.refresh()
    assert w.table.exists("airwave-01")
