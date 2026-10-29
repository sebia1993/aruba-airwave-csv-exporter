"""비정상 종료 복구/GUI 응답성 안정화: 공개 기능은 변경하지 않습니다."""

from __future__ import annotations

import threading

from airwave_csv import events, gui
from airwave_csv.lock import single_instance

from test_gui_stability import make_window


def test_invalid_last_batch_json_does_not_crash_gui_reader(tmp_path):
    target = tmp_path / "state" / "last_batch.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken JSON", encoding="utf-8")
    assert events.read_last_batch(tmp_path) == {}


def test_failed_reconciliation_keeps_active_marker_for_later_recovery(tmp_path, monkeypatch):
    events.mark_batch_active(tmp_path, "failed-run")
    previous = events._write_json_atomic

    def fail_summary(path, data):
        if path.name == "last_batch.json":
            raise OSError("simulated storage error")
        return previous(path, data)

    monkeypatch.setattr(events, "_write_json_atomic", fail_summary)
    events.reconcile_interrupted_batch(tmp_path)
    assert (tmp_path / "state" / "active_batch.json").exists()


def test_idle_only_recovery_does_not_interrupt_running_batch(tmp_path):
    events.mark_batch_active(tmp_path, "crashed-run")
    lock_path = tmp_path / "state" / "run.lock"
    with single_instance(lock_path):
        assert events.reconcile_if_idle(tmp_path) is False
        assert (tmp_path / "state" / "active_batch.json").exists()
    assert events.reconcile_if_idle(tmp_path) is True
    assert not (tmp_path / "state" / "active_batch.json").exists()
    assert events.read_last_batch(tmp_path)["status"] == "INTERRUPTED"


def test_scheduler_status_is_not_queried_on_gui_thread(tmp_path, monkeypatch):
    window, _ = make_window(tmp_path, monkeypatch)
    main_thread = threading.get_ident()
    called = threading.Event()
    thread_ids = []

    def scheduler_status():
        thread_ids.append(threading.get_ident())
        called.set()
        return "Ready"

    monkeypatch.setattr(gui, "task_status", scheduler_status)
    window.refresh()
    assert called.wait(3), "기존 주기의 예약 상태 조회는 유지해야 합니다."
    assert thread_ids == [thread_ids[0]]
    assert thread_ids[0] != main_thread, "Windows PowerShell을 GUI 메인 스레드에서 호출하면 안 됩니다."


def test_unexpected_scheduler_thread_error_does_not_disable_future_checks(
    tmp_path, monkeypatch,
):
    import time

    w, _ = make_window(tmp_path, monkeypatch)
    entered = threading.Event()

    def fail_unexpectedly():
        entered.set()
        raise RuntimeError("unexpected PowerShell runtime failure")

    monkeypatch.setattr(gui, "task_status", fail_unexpectedly)
    w.refresh()
    assert entered.wait(2)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and w._schedule_status_results.empty():
        time.sleep(0.01)
    w.refresh()
    assert w._cached_schedule_status == "확인 불가"
    assert w._schedule_status_inflight is False
