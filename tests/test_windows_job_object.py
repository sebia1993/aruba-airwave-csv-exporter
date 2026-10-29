"""윈도우 워커와 그 자식 프로세스가 함께 정리되는지 확인합니다."""

import os
import sys
import time

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object 전용")
def test_job_close_terminates_worker_and_descendant(tmp_path):
    import ctypes
    from ctypes import wintypes

    from airwave_csv.process_control import _WindowsJobProcess

    child_file = tmp_path / "child.pid"
    script = (
        "import subprocess,sys,time,pathlib;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        f"pathlib.Path({str(child_file)!r}).write_text(str(p.pid));"
        "time.sleep(120)"
    )
    job=_WindowsJobProcess([sys.executable,"-c",script])
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and not child_file.exists():
            time.sleep(0.1)
        assert child_file.exists()
        child_pid=int(child_file.read_text(encoding="utf-8"))
    finally:
        job.terminate()
    time.sleep(0.5)
    ctypes.windll.kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    ]
    ctypes.windll.kernel32.OpenProcess.restype = wintypes.HANDLE
    handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,child_pid)
    if handle:
        code=wintypes.DWORD()
        assert ctypes.windll.kernel32.GetExitCodeProcess(handle,ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        assert code.value != 259  # STILL_ACTIVE
