"""Windows 작업 스케줄러: 로그인된 사용자 세션에서만 실행하는 안전한 기본 설정."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


class ScheduleError(Exception):
    pass


def _powershell(script: str, *, env_extra: dict[str, str] | None = None) -> str:
    if os.name != "nt":
        raise ScheduleError("Windows 11에서만 예약 작업을 등록할 수 있습니다.")
    env = os.environ.copy()
    env.update(env_extra or {})
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=45, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScheduleError("Windows 작업 스케줄러를 실행할 수 없습니다.") from exc
    if result.returncode:
        # PowerShell 메시지에는 사용자 경로가 포함될 수 있으므로 노출하지 않습니다.
        raise ScheduleError("작업 스케줄러 요청이 거부되었습니다. 계정 권한과 정책을 확인하세요.")
    return result.stdout.strip()


def executable_action() -> tuple[Path, str]:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve(), "--run --headless"
    # 개발 환경에서만 Python 경로를 사용합니다.
    return Path(sys.executable).resolve(), "-m airwave_csv --run --headless"


def register_daily(time_hhmm: str) -> None:
    import re

    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_hhmm):
        raise ScheduleError("예약 시간은 HH:MM 형식이어야 합니다.")
    executable, arguments = executable_action()
    script = r"""
$ErrorActionPreference = 'Stop'
$who = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $env:AW_EXEC -Argument $env:AW_ARGS -WorkingDirectory $env:AW_WORKDIR
$trigger = New-ScheduledTaskTrigger -Daily -At $env:AW_TIME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'AirWave CSV Exporter - Daily' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
"""
    # Interactive LogonType: 로그인하지 않은 상태에서 실행을 보장하지 않습니다.
    _powershell(script, env_extra={
        "AW_EXEC": str(executable), "AW_ARGS": arguments,
        "AW_WORKDIR": str(executable.parent), "AW_TIME": time_hhmm,
    })


def unregister_daily() -> None:
    script = r"""
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'AirWave CSV Exporter - Daily' -ErrorAction SilentlyContinue
if ($null -ne $task) { Unregister-ScheduledTask -TaskName 'AirWave CSV Exporter - Daily' -Confirm:$false }
"""
    _powershell(script)


def task_status() -> str:
    script = r"""
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'AirWave CSV Exporter - Daily' -ErrorAction SilentlyContinue
if ($null -eq $task) { 'not_registered' } else { $task.State.ToString() }
"""
    return _powershell(script)
