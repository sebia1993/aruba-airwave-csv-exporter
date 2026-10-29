"""서버별 독립 워커 시작/종료 및 Windows 자식 프로세스 트리 정리."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from .run_snapshot import WorkerResult, read_worker_result


def worker_command(snapshot_path: Path, server_id: str, attempt: int,
                   result_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        argv = [sys.executable]
    else:
        argv = [sys.executable, "-m", "airwave_csv"]
    return [*argv, "--worker", "--snapshot", str(snapshot_path),
            "--server-id", server_id, "--attempt", str(attempt),
            "--result", str(result_path)]


class _UnixProcess:
    def __init__(self, argv: list[str]):
        self.process = subprocess.Popen(argv, shell=False, start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def poll(self):
        return self.process.poll()

    def terminate(self):
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def close(self):
        self.process.poll()


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    SIZE_T = ctypes.c_size_t
    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    LARGE_INTEGER = ctypes.c_longlong

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", DWORD), ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
            ("dwX", DWORD), ("dwY", DWORD), ("dwXSize", DWORD),
            ("dwYSize", DWORD), ("dwXCountChars", DWORD), ("dwYCountChars", DWORD),
            ("dwFillAttribute", DWORD), ("dwFlags", DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", HANDLE), ("hStdOutput", HANDLE), ("hStdError", HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", HANDLE), ("hThread", HANDLE),
            ("dwProcessId", DWORD), ("dwThreadId", DWORD),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", LARGE_INTEGER),
            ("PerJobUserTimeLimit", LARGE_INTEGER),
            ("LimitFlags", DWORD), ("MinimumWorkingSetSize", SIZE_T),
            ("MaximumWorkingSetSize", SIZE_T), ("ActiveProcessLimit", DWORD),
            ("Affinity", SIZE_T), ("PriorityClass", DWORD), ("SchedulingClass", DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(key, ctypes.c_ulonglong) for key in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
            ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T),
        ]

    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.CreateJobObjectW.restype = HANDLE
    k32.SetInformationJobObject.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    k32.CreateProcessW.restype = wintypes.BOOL
    k32.ResumeThread.argtypes = [HANDLE]
    k32.ResumeThread.restype = DWORD
    k32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    k32.TerminateProcess.restype = wintypes.BOOL

    class _WindowsJobProcess:
        def __init__(self, argv: list[str]):
            self.job = None
            self.process = None
            self.closed = False
            job = k32.CreateJobObjectW(None, None)
            if not job:
                raise OSError("Windows Job Object를 생성할 수 없습니다.")
            self.job = job
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(
                job, 9, ctypes.byref(info), ctypes.sizeof(info)
            ):
                k32.CloseHandle(job)
                raise OSError("작업 프로세스 트리 제한을 설정할 수 없습니다.")
            startup = STARTUPINFOW()
            startup.cb = ctypes.sizeof(startup)
            pi = PROCESS_INFORMATION()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            ok = k32.CreateProcessW(
                None, command, None, None, False, 0x00000004 | 0x08000000,
                None, str(Path(argv[0]).resolve().parent),
                ctypes.byref(startup), ctypes.byref(pi),
            )
            if not ok:
                k32.CloseHandle(job)
                raise OSError("워커 프로세스를 생성할 수 없습니다.")
            self.process = pi.hProcess
            try:
                if not k32.AssignProcessToJobObject(job, pi.hProcess):
                    raise OSError("워커를 Windows Job Object에 연결할 수 없습니다.")
                if k32.ResumeThread(pi.hThread) == 0xFFFFFFFF:
                    raise OSError("워커 프로세스를 시작할 수 없습니다.")
            except BaseException:
                self.terminate()
                raise
            finally:
                k32.CloseHandle(pi.hThread)

        def poll(self) -> int | None:
            if self.closed or not self.process:
                return 1
            code = DWORD()
            if not k32.GetExitCodeProcess(self.process, ctypes.byref(code)):
                return 1
            return None if code.value == 259 else code.value

        def terminate(self) -> None:
            if self.closed:
                return
            self.closed = True
            if self.job:
                k32.CloseHandle(self.job)
                self.job = None
            if self.process:
                k32.TerminateProcess(self.process, 1)
                k32.CloseHandle(self.process)
                self.process = None

        def close(self) -> None:
            if self.closed:
                return
            self.closed = True
            if self.job:
                k32.CloseHandle(self.job)
                self.job = None
            if self.process:
                k32.CloseHandle(self.process)
                self.process = None


class WorkerHandle:
    def __init__(self, process, result_path: Path, run_id: str,
                 server_id: str, attempt: int):
        self.process = process
        self.result_path = result_path
        self.run_id = run_id
        self.server_id = server_id
        self.attempt = attempt
        self._finished = False

    def poll(self) -> WorkerResult | None:
        if self._finished:
            return None
        code = self.process.poll()
        if code is None:
            return None
        self._finished = True
        self.process.close()
        try:
            result = read_worker_result(self.result_path)
            if (result.run_id != self.run_id or result.server_id != self.server_id
                    or result.attempt != self.attempt):
                raise ValueError("다른 워커의 결과 파일입니다.")
            return result
        except (OSError, ValueError, TypeError, KeyError):
            return WorkerResult(
                self.run_id, self.server_id, self.attempt, "FAILED", 98, False
            )

    def terminate(self) -> None:
        if not self._finished:
            self.process.terminate()
            self._finished = True


class WorkerLauncher:
    def __init__(self, run_id: str):
        self.run_id = run_id

    def start(self, snapshot_path: Path, server_id: str, attempt: int,
              result_path: Path) -> WorkerHandle:
        args = worker_command(snapshot_path, server_id, attempt, result_path)
        process = _WindowsJobProcess(args) if os.name == "nt" else _UnixProcess(args)
        return WorkerHandle(process, result_path, self.run_id, server_id, attempt)
