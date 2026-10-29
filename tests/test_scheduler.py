import pytest

from airwave_csv import scheduler


def test_invalid_schedule_time_rejected():
    with pytest.raises(scheduler.ScheduleError):
        scheduler.register_daily("25:77")


def test_register_daily_passes_execution_path_without_shell_interpolation(monkeypatch, tmp_path):
    calls = []

    def fake_ps(script, *, env_extra=None):
        calls.append((script, env_extra))
        return ""

    monkeypatch.setattr(scheduler, "_powershell", fake_ps)
    monkeypatch.setattr(
        scheduler, "executable_action",
        lambda: (tmp_path / "Application Folder" / "AirWaveCsvExporter.exe", "--run --headless"),
    )
    scheduler.register_daily("09:05")
    script, env = calls[0]
    assert env["AW_TIME"] == "09:05"
    assert env["AW_ARGS"] == "--run --headless"
    assert "Application Folder" in env["AW_EXEC"]
    assert "New-ScheduledTaskPrincipal" in script
    assert "Interactive" in script
