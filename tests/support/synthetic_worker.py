"""테스트 전용 독립 워커: 실제 AirWave에 접속하지 않습니다.

의도적으로 운영 코드의 로그인/다운로드 기능을 수정하거나 우회하지 않습니다.
OS 워커 프로세스, CSV 검사, Atomic WorkerResult 프로토콜을 테스트합니다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from airwave_csv.csv_store import store_export
from airwave_csv.paths import server_export_dir
from airwave_csv.run_snapshot import WorkerResult, read_snapshot, write_worker_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.monotonic_ns()
    snapshot = read_snapshot(args.snapshot)
    if args.server_id not in {s.id for s in snapshot.servers}:
        raise SystemExit("unknown synthetic server")
    sleep_s = float(os.environ.get("AW_SYNTHETIC_DELAY_SECONDS", "0.6"))
    fail_always = os.environ.get("AW_SYNTHETIC_FAIL_ALWAYS")
    fail_once = os.environ.get("AW_SYNTHETIC_FAIL_ONCE")
    crash_server = os.environ.get("AW_SYNTHETIC_CRASH_SERVER")
    corrupt_result = os.environ.get("AW_SYNTHETIC_BAD_RESULT_SERVER")
    corrupt_csv = os.environ.get("AW_SYNTHETIC_BAD_CSV_SERVER")
    write_failure = os.environ.get("AW_SYNTHETIC_WRITE_FAILURE_SERVER")
    status = "SUCCESS"
    code = 0
    retryable = False
    rows = None
    filename = None
    error_type = ""
    staged = None
    try:
        time.sleep(sleep_s)
        if args.server_id == crash_server:
            # 실제 OS 비정상 종료. 결과 JSON과 타임라인은 남기지 않습니다.
            os._exit(78)
        if args.server_id == corrupt_result:
            status, code, retryable = "FAILED", 98, False
        elif args.server_id == write_failure:
            raise OSError("test-only simulated disk write failure")
        elif args.server_id == fail_always:
            status, code, retryable = "FAILED", 31, False
        elif args.server_id == fail_once and args.attempt == 1:
            status, code, retryable = "FAILED", 48, True
        else:
            folder = server_export_dir(snapshot.settings, args.server_id)
            folder.mkdir(parents=True, exist_ok=True)
            staged = folder / (".synthetic-" + uuid4().hex + ".part")
            if args.server_id == corrupt_csv:
                staged.write_text("Name,Model\nbroken-row\n", encoding="utf-8")
            else:
                staged.write_text(
                    "Name,Model\n" + args.server_id + ",AP-535\n", encoding="utf-8"
                )
            export = store_export(staged, folder, expected_rows=1)
            rows, filename = export.rows, export.path.name
    except Exception as exc:
        status, code, retryable = "FAILED", 98, False
        error_type = type(exc).__name__
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    ended = time.monotonic_ns()
    metric_path = args.result.with_suffix(".timeline.json")
    metric_path.parent.mkdir(parents=True, exist_ok=True)
    metric_path.write_text(json.dumps({
        "server_id": args.server_id,
        "attempt": args.attempt,
        "pid": os.getpid(),
        "start_ns": started,
        "end_ns": ended,
        "status": status,
        "error_type": error_type,
    }), encoding="utf-8")
    if args.server_id == corrupt_result:
        # 프로세스가 종료 코드 0을 반환해도 유효하지 않은 결과는 실패여야 합니다.
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text("{broken-json", encoding="utf-8")
        return 0
    write_worker_result(args.result, WorkerResult(
        snapshot.run_id, args.server_id, args.attempt,
        status, code, retryable, rows, filename
    ))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
