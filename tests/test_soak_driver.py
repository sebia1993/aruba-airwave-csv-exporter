"""누수 측정 루프의 반복 횟수와 결과 보고 형식을 검증합니다."""

from __future__ import annotations

import json

from support.soak_process_pool import run_soak


def test_small_repeated_real_worker_soak_has_no_residual_batches(tmp_path):
    report_path = tmp_path / "test-soak.json"
    report = run_soak(
        minutes=0, iterations=2, servers=3,
        delay_seconds=0.2, report_path=report_path,
    )
    assert report["status"] == "passed"
    assert report["iterations"] == 2
    assert report["servers_per_batch"] == 3
    assert report["failed_batches"] == 0
    assert report["max_concurrent"] == 3
    assert report["worker_attempts"] == 6
    assert report["leaked_child_pids"] == []
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
