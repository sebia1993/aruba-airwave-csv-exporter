"""실제 run_batch + WorkerLauncher + OS 자식 프로세스 통합 검증.

모의 워커는 AirWave와 통신하지 않습니다. 운영 코드는 수정하지 않습니다.
"""

from __future__ import annotations

import json

import pytest

from support.process_harness import run_synthetic_batch


@pytest.mark.parametrize("servers", [3, 5])
def test_real_subprocesses_respect_three_slots_and_write_isolated_csv(tmp_path, servers):
    result = run_synthetic_batch(tmp_path, servers=servers, delay_seconds=0.65)
    assert result.summary.total == servers
    assert result.summary.success == servers
    assert result.summary.exit_code == 0
    assert result.max_concurrent == 3
    assert result.started_order[:3] == ["airwave-01", "airwave-02", "airwave-03"]
    assert result.completed_count == servers
    assert result.active_marker_removed

    for index in range(1, servers + 1):
        server_id = f"airwave-{index:02}"
        folder = result.export_root / server_id
        csv_text = (folder / "latest.csv").read_text(encoding="utf-8")
        assert f"{server_id},AP-535" in csv_text
        assert csv_text.count("\n") == 2
        dated = list(folder.glob("AirWave_Devices_*.csv"))
        assert len(dated) == 1
        assert dated[0].read_bytes() == (folder / "latest.csv").read_bytes()


def test_real_subprocess_failure_isolated_from_other_servers(tmp_path):
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.5, fail_always="airwave-02"
    )
    assert result.summary.success == 4
    assert result.summary.failed == 1
    assert result.summary.exit_code == 2
    assert result.max_concurrent == 3
    assert not (result.export_root / "airwave-02" / "latest.csv").exists()
    for number in (1, 3, 4, 5):
        assert (result.export_root / f"airwave-{number:02}" / "latest.csv").exists()
    assert result.active_marker_removed


def test_real_subprocess_retry_releases_slot_and_waits_for_unstarted_servers(tmp_path):
    result = run_synthetic_batch(
        tmp_path, servers=5, delay_seconds=0.5, fail_once="airwave-01",
        retry_delay_seconds=1,
    )
    assert result.summary.success == 5
    assert result.summary.exit_code == 0
    first_retry_index = result.started_order.index("airwave-01", 1)
    assert result.started_order.index("airwave-04") < first_retry_index
    assert result.started_order.index("airwave-05") < first_retry_index
    assert result.max_concurrent == 3
    assert result.started_order.count("airwave-01") == 2
    assert result.active_marker_removed


def test_synthetic_test_workers_do_not_leak_credentials_into_snapshot(tmp_path):
    result = run_synthetic_batch(tmp_path, servers=3, delay_seconds=0.3)
    snapshot = next((result.run_root).glob("*/snapshot.json"))
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    assert "password" not in snapshot.read_text(encoding="utf-8").lower()
    assert len(data["servers"]) == 3
