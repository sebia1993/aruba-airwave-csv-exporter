"""Windows Job Object 종료는 프로세스 핸들을 닫기 전에 완료 확인이 필요합니다."""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object 전용")
def test_worker_termination_waits_for_exit_before_handle_disposal(monkeypatch):
    from airwave_csv import process_control

    events = []

    class FakeKernel:
        def CloseHandle(self, handle):
            events.append(("close", handle))
            return 1

        def TerminateProcess(self, handle, code):
            events.append(("terminate", handle))
            return 1

        def WaitForSingleObject(self, handle, timeout):
            events.append(("wait", handle))
            return 0  # WAIT_OBJECT_0

    monkeypatch.setattr(process_control, "k32", FakeKernel())
    worker = process_control._WindowsJobProcess.__new__(process_control._WindowsJobProcess)
    worker.job = 100
    worker.process = 200
    worker.closed = False
    worker.terminate()
    assert ("wait", 200) in events
    assert events.index(("wait", 200)) < events.index(("close", 200))
    assert worker.closed is True
