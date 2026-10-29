"""실제 WorkerLauncher/작업 큐를 테스트 전용 OS 프로세스로 검증합니다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import sys
from unittest.mock import patch
from uuid import uuid4

from airwave_csv import process_control
from airwave_csv.multi_config import MultiConfig, add_server
from airwave_csv.orchestrator import BatchSummary, run_batch
from airwave_csv.run_snapshot import BatchSnapshot


WORKER = Path(__file__).with_name("synthetic_worker.py")


@dataclass(frozen=True)
class SyntheticRun:
    summary: BatchSummary
    export_root: Path
    run_root: Path
    started_order: list[str]
    max_concurrent: int
    completed_count: int
    active_marker_removed: bool
    worker_outcomes: dict[str, dict]
    worker_errors: dict[str, str]


class TrackedLauncher(process_control.WorkerLauncher):
    def __init__(self, run_id):
        super().__init__(run_id)
        self.all_handles = []
        self.started_order = []
        self.peak_live_handles = 0

    def start(self, snapshot_path, server_id, attempt, result_path):
        handle = super().start(snapshot_path, server_id, attempt, result_path)
        self.all_handles.append(handle)
        self.started_order.append(server_id)
        # The production scheduler releases finished worker handles before
        # scheduling more, so only running OS processes count here.
        count = sum(h.process.poll() is None for h in self.all_handles)
        self.peak_live_handles = max(self.peak_live_handles, count)
        return handle


def _interval_peak(events: list[dict]) -> int:
    markers = []
    for item in events:
        markers.append((item["start_ns"], +1))
        markers.append((item["end_ns"], -1))
    # Terminal events are ordered before starts for ties.
    markers.sort(key=lambda part: (part[0], part[1]))
    concurrent = peak = 0
    for _, delta in markers:
        concurrent += delta
        peak = max(peak, concurrent)
    return peak


def run_synthetic_batch(
    root: Path, *, servers: int = 5, delay_seconds: float = 0.5,
    fail_always: str | None = None, fail_once: str | None = None,
    retry_delay_seconds: int = 1,
) -> SyntheticRun:
    if not 1 <= servers <= 5:
        raise ValueError("Synthetic server count must be between 1 and 5")
    root.mkdir(parents=True, exist_ok=True)
    home = root / "home"
    export_root = root / "exports"
    config = MultiConfig(
        export_root=str(export_root), parallel_limit=3,
        retry_delay_seconds=retry_delay_seconds,
        server_timeout_seconds=60, batch_timeout_seconds=180,
    )
    for i in range(1, servers + 1):
        add_server(
            config, name=f"Synthetic AirWave {i}",
            url=f"https://synthetic-{i}.invalid", username="mock-operator",
        )
    run_id = str(uuid4())
    snapshot = BatchSnapshot(
        run_id, config, tuple(config.servers), {}, "2026-10-29T00:00:00Z"
    )
    launcher = TrackedLauncher(run_id)

    def command(snapshot_path, server_id, attempt, result_path):
        return [
            sys.executable, str(WORKER), "--snapshot", str(snapshot_path),
            "--server-id", server_id, "--attempt", str(attempt),
            "--result", str(result_path),
        ]

    env = {
        "AW_SYNTHETIC_DELAY_SECONDS": str(delay_seconds),
        "AW_SYNTHETIC_FAIL_ALWAYS": fail_always or "",
        "AW_SYNTHETIC_FAIL_ONCE": fail_once or "",
    }
    with patch.dict(os.environ, env), patch.object(process_control, "worker_command", command):
        summary = run_batch(snapshot, launcher=launcher, home=home)
    run_dir = home / "runs" / run_id
    timeline = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in run_dir.glob("result-*.timeline.json")
    ]
    batch_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    outcomes = {
        sid: {
            "status": result.get("status"),
            "code": result.get("exit_code"),
            "attempt": result.get("attempt"),
        }
        for sid, result in batch_summary.get("servers", {}).items()
    }
    errors = {
        item["server_id"]: item["error_type"]
        for item in timeline if item.get("error_type")
    }
    return SyntheticRun(
        summary=summary, export_root=export_root, run_root=home / "runs",
        started_order=launcher.started_order,
        max_concurrent=max(launcher.peak_live_handles, _interval_peak(timeline)),
        completed_count=len(timeline),
        active_marker_removed=not (home / "state" / "active_batch.json").exists(),
        worker_outcomes=outcomes,
        worker_errors=errors,
    )
