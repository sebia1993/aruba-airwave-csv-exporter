"""실제 OS 워커 프로세스에서 비정상 종료·JSON/CSV 손상·쓰기 실패를 주입합니다.

운영용 AirWave 주소·계정·장비에는 접속하지 않습니다.
"""

from __future__ import annotations

from support.process_harness import run_synthetic_batch


def assert_peers_successful(result, *, bad_server="airwave-02"):
    assert result.summary.total == 5
    assert result.summary.success == 4
    assert result.summary.failed == 1
    assert result.summary.exit_code == 2
    assert result.max_concurrent <= 3
    assert result.active_marker_removed
    assert result.worker_outcomes[bad_server]["status"] == "FAILED"
    assert result.worker_outcomes[bad_server]["code"] == 98
    for number in (1, 3, 4, 5):
        sid = f"airwave-{number:02}"
        assert result.worker_outcomes[sid]["status"] == "SUCCESS"
        assert (result.export_root / sid / "latest.csv").is_file()


def test_abrupt_worker_exit_isolated_from_four_peer_servers(tmp_path):
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.35, crash_server="airwave-02"
    )
    assert_peers_successful(result)
    assert result.completed_count == 4  # 강제 종료한 워커의 완료 타임라인은 없음
    assert not (result.export_root / "airwave-02" / "latest.csv").exists()


def test_corrupt_worker_result_is_fail_closed_and_peers_continue(tmp_path):
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.35,
        corrupt_result_server="airwave-02",
    )
    assert_peers_successful(result)
    assert not (result.export_root / "airwave-02" / "latest.csv").exists()


def test_corrupt_csv_keeps_previous_latest_and_other_servers_succeed(tmp_path):
    before = run_synthetic_batch(tmp_path, servers=5, delay_seconds=0.25)
    assert before.summary.success == 5
    latest = before.export_root / "airwave-02" / "latest.csv"
    original = latest.read_bytes()
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.25, corrupt_csv_server="airwave-02"
    )
    assert_peers_successful(result)
    assert latest.read_bytes() == original
    assert len(list(latest.parent.glob("AirWave_Devices_*.csv"))) == 1
    for number in (1, 3, 4, 5):
        assert len(list(
            (result.export_root / f"airwave-{number:02}").glob("AirWave_Devices_*.csv")
        )) == 2


def test_injected_disk_write_error_keeps_latest_and_other_peers(tmp_path):
    before = run_synthetic_batch(tmp_path, servers=5, delay_seconds=0.25)
    assert before.summary.success == 5
    latest = before.export_root / "airwave-02" / "latest.csv"
    original = latest.read_bytes()
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.25, write_failure_server="airwave-02"
    )
    assert_peers_successful(result)
    assert latest.read_bytes() == original
    assert result.worker_errors["airwave-02"] == "OSError"
