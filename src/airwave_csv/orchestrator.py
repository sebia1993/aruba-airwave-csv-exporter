"""단일 배치 내부 3개 병렬 워커 + 미실행 우선 FIFO + 재시도 예약."""

from __future__ import annotations

import heapq
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .config import app_home
from .lock import single_instance
from .process_control import WorkerLauncher
from .run_snapshot import BatchSnapshot, WorkerResult, write_snapshot


@dataclass(frozen=True)
class BatchSummary:
    run_id: str
    total: int
    success: int
    warning: int
    failed: int
    skipped: int
    interrupted: int
    exit_code: int
    elapsed_s: float


def run_batch(
    snapshot: BatchSnapshot, *, launcher: WorkerLauncher | None = None,
    clock=None, home: Path | None = None,
) -> BatchSummary:
    clock = clock or time
    home = home or app_home()
    start = clock.monotonic()
    cfg = snapshot.settings
    pending = deque(s.id for s in snapshot.servers if s.enabled)
    skipped = len(snapshot.servers) - len(pending)
    if not pending:
        return BatchSummary(snapshot.run_id, len(snapshot.servers), 0, 0, 0,
                            skipped, 0, 3, 0.0)
    retry_heap: list[tuple[float, int, str, int]] = []
    sequence = 0
    active: dict[str, tuple[object, int]] = {}
    first_started: dict[str, float] = {}
    terminal: dict[str, str] = {}
    launcher = launcher or WorkerLauncher(snapshot.run_id)

    with single_instance(home / "state" / "run.lock"):
        snapshot_path = write_snapshot(home, snapshot)
        try:
            while pending or retry_heap or active:
                now = clock.monotonic()
                if now - start >= cfg.batch_timeout_seconds:
                    for sid, (handle, _) in active.items():
                        handle.terminate()
                        terminal[sid] = "INTERRUPTED"
                    active.clear()
                    for sid in pending:
                        terminal[sid] = "INTERRUPTED"
                    for _, _, sid, _ in retry_heap:
                        terminal[sid] = "INTERRUPTED"
                    pending.clear()
                    retry_heap.clear()
                    break

                # 초기 수집을 우선 수행해 느린 서버 재시도 때문에 D/E가 기다리지 않습니다.
                while len(active) < cfg.parallel_limit:
                    sid, attempt = None, 0
                    if pending:
                        sid, attempt = pending.popleft(), 1
                    elif retry_heap and retry_heap[0][0] <= now:
                        _, _, sid, attempt = heapq.heappop(retry_heap)
                    if sid is None:
                        break
                    if sid not in first_started:
                        first_started[sid] = now
                    if now - first_started[sid] >= cfg.server_timeout_seconds:
                        terminal[sid] = "FAILED"
                        continue
                    path = home / "runs" / snapshot.run_id / (
                        f"result-{sid}-{attempt}.json"
                    )
                    try:
                        handle = launcher.start(snapshot_path, sid, attempt, path)
                        active[sid] = (handle, attempt)
                    except (OSError, ValueError):
                        terminal[sid] = "FAILED"

                progress = False
                for sid, (handle, attempt) in list(active.items()):
                    now = clock.monotonic()
                    if now - first_started[sid] >= cfg.server_timeout_seconds:
                        handle.terminate()
                        del active[sid]
                        terminal[sid] = "FAILED"
                        progress = True
                        continue
                    result: WorkerResult | None = handle.poll()
                    if result is None:
                        continue
                    del active[sid]
                    progress = True
                    if (result.status == "FAILED" and result.retryable and
                            attempt < cfg.max_attempts and
                            now - first_started[sid] + cfg.retry_delay_seconds
                            < cfg.server_timeout_seconds):
                        sequence += 1
                        heapq.heappush(retry_heap, (
                            now + cfg.retry_delay_seconds, sequence, sid, attempt + 1
                        ))
                    else:
                        terminal[sid] = (
                            result.status if result.status in ("SUCCESS", "WARNING")
                            else "FAILED"
                        )
                if not progress and (active or pending or retry_heap):
                    delay = 0.2
                    if not active and not pending and retry_heap:
                        delay = min(0.5, max(0.01, retry_heap[0][0] - clock.monotonic()))
                    clock.sleep(delay)
        finally:
            for handle, _ in active.values():
                handle.terminate()

    good = sum(v == "SUCCESS" for v in terminal.values())
    warn = sum(v == "WARNING" for v in terminal.values())
    failed = sum(v == "FAILED" for v in terminal.values())
    interrupted = sum(v == "INTERRUPTED" for v in terminal.values())
    count = good + warn + failed + interrupted
    code = 0 if good == count else (1 if not good and not warn else 2)
    return BatchSummary(
        snapshot.run_id, len(snapshot.servers), good, warn, failed,
        skipped, interrupted, code, round(clock.monotonic() - start, 2),
    )
