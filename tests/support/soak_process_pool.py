"""Independent OS-worker repeat/soak validation. No AirWave connections or credentials.

Examples:
  python tests/support/soak_process_pool.py --minutes 2 --servers 5 --report test-results/soak.json
  python tests/support/soak_process_pool.py --minutes 480 --servers 5 --report soak-8h.json

In GitHub Actions, short checks run on normal commits; longer checks are workflow_dispatch.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import psutil

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support.process_harness import run_synthetic_batch


def _parent_metrics(process: psutil.Process) -> tuple[int, int]:
    rss = process.memory_info().rss
    if hasattr(process, "num_handles"):
        count = process.num_handles()
    else:
        count = process.num_fds()
    return rss, count


def _children(process: psutil.Process) -> set[int]:
    try:
        return {child.pid for child in process.children(recursive=True)}
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return set()


def _report_atomic(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + ".part")
    try:
        staging.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def run_soak(
    *, minutes: float, iterations: int = 0, servers: int = 5,
    delay_seconds: float = 0.65, report_path: Path,
    max_rss_growth_mb: float = 128.0, max_handle_growth: int = 64,
) -> dict:
    if minutes <= 0 and iterations <= 0:
        raise ValueError("minutes or iterations must be positive")
    if not 1 <= servers <= 5 or delay_seconds <= 0:
        raise ValueError("invalid synthetic test settings")
    if max_rss_growth_mb < 0 or max_handle_growth < 0:
        raise ValueError("invalid process resource limits")

    parent = psutil.Process(os.getpid())
    baseline_children = _children(parent)
    initial_rss, initial_handles = _parent_metrics(parent)
    started_at = time.monotonic()
    deadline = started_at + minutes * 60 if minutes > 0 else float("inf")
    count = 0
    attempts = 0
    peak_active = 0
    failed_batches = 0
    observed_growth_mb = 0.0
    observed_handle_growth = 0
    first_sample: tuple[int, int] | None = None
    leaked: set[int] = set()
    errors: list[str] = []
    status = "running"

    try:
        while time.monotonic() < deadline and (iterations == 0 or count < iterations):
            with tempfile.TemporaryDirectory(prefix="airwave-worker-soak-") as temp_dir:
                result = run_synthetic_batch(
                    Path(temp_dir), servers=servers, delay_seconds=delay_seconds
                )
                count += 1
                attempts += result.completed_count
                peak_active = max(peak_active, result.max_concurrent)
                if (result.summary.success != servers or result.summary.failed != 0
                        or result.summary.exit_code != 0
                        or result.completed_count != servers
                        or result.max_concurrent > 3
                        or not result.active_marker_removed):
                    failed_batches += 1
                    raise AssertionError("worker process batch integrity failed")
                for number in range(1, servers + 1):
                    sid = f"airwave-{number:02}"
                    path = result.export_root / sid / "latest.csv"
                    if not path.exists() or f"{sid},AP-535" not in path.read_text("utf-8"):
                        raise AssertionError("isolated synthetic CSV missing or incorrect")
            gc.collect()
            # In contrast to timeouts in production, these tests fail on orphan processes.
            extra = _children(parent) - baseline_children
            if extra:
                # Give the OS a short grace period for just-exited child reaping.
                time.sleep(0.1)
                extra = _children(parent) - baseline_children
            if extra:
                leaked.update(extra)
                raise AssertionError("synthetic worker process is still running")

            rss, handles = _parent_metrics(parent)
            if first_sample is None:
                first_sample = (rss, handles)
            baseline_rss, baseline_handles = first_sample
            observed_growth_mb = max(observed_growth_mb,
                                     (rss - baseline_rss) / (1024 * 1024))
            observed_handle_growth = max(observed_handle_growth,
                                         handles - baseline_handles)
            if (observed_growth_mb > max_rss_growth_mb
                    or observed_handle_growth > max_handle_growth):
                raise AssertionError("parent memory or handle growth exceeded limits")

        if count < 1:
            raise AssertionError("no synthetic worker batch was executed")
        status = "passed"
    except Exception as exc:
        status = "failed"
        errors.append(type(exc).__name__ + ": " + str(exc))
    finally:
        final_rss, final_handles = _parent_metrics(parent)
        report = {
            "status": status,
            "iterations": count,
            "servers_per_batch": servers,
            "worker_attempts": attempts,
            "failed_batches": failed_batches,
            "max_concurrent": peak_active,
            "elapsed_seconds": round(time.monotonic() - started_at, 2),
            "initial_rss_mb": round(initial_rss / (1024 * 1024), 2),
            "final_rss_mb": round(final_rss / (1024 * 1024), 2),
            "initial_handles": initial_handles,
            "final_handles": final_handles,
            "max_rss_growth_mb": round(max(0, observed_growth_mb), 2),
            "max_handle_growth": max(0, observed_handle_growth),
            "leaked_child_pids": sorted(leaked),
            "errors": errors,
            "uses_real_airwave": False,
            "uses_operational_credentials": False,
        }
        _report_atomic(report_path, report)
    if status != "passed":
        raise AssertionError("Synthetic process soak failed: " + json.dumps(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic multi-worker Windows stability soak")
    parser.add_argument("--minutes", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=0)
    parser.add_argument("--servers", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.65)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-rss-growth-mb", type=float, default=128.0)
    parser.add_argument("--max-handle-growth", type=int, default=64)
    args = parser.parse_args()
    output = run_soak(
        minutes=args.minutes, iterations=args.iterations, servers=args.servers,
        delay_seconds=args.delay, report_path=args.report,
        max_rss_growth_mb=args.max_rss_growth_mb,
        max_handle_growth=args.max_handle_growth,
    )
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
