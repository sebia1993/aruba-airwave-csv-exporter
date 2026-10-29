"""민감정보를 포함하지 않는 JSONL 실행 이력."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

# 외부 예외 메시지/URL/페이지 HTML/다운로드 데이터는 로그에 기록하지 않습니다.
ALLOWED_KEYS = {"stage", "status", "code", "rows", "bytes", "attempt", "filename", "elapsed_s", "run_id", "server_id"}


def record(home: Path, **values: Any) -> None:
    safe = {k: v for k, v in values.items() if k in ALLOWED_KEYS}
    safe["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
    directory = home / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (datetime.now().strftime("%Y-%m-%d") + ".jsonl")).open(
        "a", encoding="utf-8"
    ) as file:
        file.write(json.dumps(safe, ensure_ascii=False) + "\n")


def last_event(home: Path) -> dict[str, Any] | None:
    files = sorted((home / "logs").glob("*.jsonl"), reverse=True)
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines:
            return json.loads(lines[-1])
    return None


def record_server_event(
    home: Path, *, run_id: str, server_id: str, stage: str, status: str,
    code: int, attempt: int = 1, rows: int | None = None,
    filename: str | None = None,
) -> None:
    record(home, run_id=run_id, server_id=server_id, stage=stage,
           status=status, code=code, attempt=attempt, rows=rows, filename=filename)


def _write_json_atomic(path: Path, data: dict) -> None:
    import os
    from uuid import uuid4

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + uuid4().hex + ".part")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_batch_summary(home: Path, summary, server_results: dict) -> None:
    from dataclasses import asdict

    data = asdict(summary)
    data["servers"] = {sid: asdict(result) for sid, result in server_results.items()}
    _write_json_atomic(home / "state" / "last_batch.json", data)
    _write_json_atomic(home / "runs" / summary.run_id / "summary.json", data)


def read_last_batch(home: Path) -> dict:
    path = home / "state" / "last_batch.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mark_batch_active(home: Path, run_id: str) -> None:
    _write_json_atomic(home / "state" / "active_batch.json", {"run_id": run_id})


def clear_batch_active(home: Path) -> None:
    (home / "state" / "active_batch.json").unlink(missing_ok=True)


def reconcile_interrupted_batch(home: Path) -> None:
    active = home / "state" / "active_batch.json"
    if active.exists():
        try:
            info = json.loads(active.read_text(encoding="utf-8"))
            _write_json_atomic(home / "state" / "last_interrupted.json",
                               {"run_id": info.get("run_id"), "status": "INTERRUPTED"})
        except (OSError, json.JSONDecodeError):
            pass
        clear_batch_active(home)


def write_batch_progress(home: Path, run_id: str, statuses: dict[str, str]) -> None:
    _write_json_atomic(
        home / "state" / "progress.json", {"run_id": run_id, "servers": statuses}
    )
