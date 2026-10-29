"""실행 시작 시 고정하는 비밀정보 없는 스냅샷 및 워커 결과 프로토콜."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .multi_config import MultiConfig, ServerProfile, validate_settings


@dataclass(frozen=True)
class BatchSnapshot:
    run_id: str
    settings: MultiConfig
    servers: tuple[ServerProfile, ...]
    selectors: dict[str, dict[str, str]]
    created_at: str


@dataclass(frozen=True)
class WorkerResult:
    run_id: str
    server_id: str
    attempt: int
    status: str
    exit_code: int
    retryable: bool
    rows: int | None = None
    filename: str | None = None


def _atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + "." + uuid4().hex + ".part")
    try:
        staging.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def write_snapshot(home: Path, snapshot: BatchSnapshot) -> Path:
    validate_settings(snapshot.settings)
    path = home / "runs" / snapshot.run_id / "snapshot.json"
    if path.exists():
        raise FileExistsError("이미 생성된 실행 스냅샷입니다.")
    _atomic_json(path, asdict(snapshot))
    return path


def read_snapshot(path: Path) -> BatchSnapshot:
    obj = json.loads(path.read_text(encoding="utf-8"))
    settings = obj["settings"]
    settings["servers"] = [ServerProfile(**s) for s in settings["servers"]]
    config = MultiConfig(**settings)
    validate_settings(config)
    return BatchSnapshot(
        run_id=obj["run_id"],
        settings=config,
        servers=tuple(ServerProfile(**s) for s in obj["servers"]),
        selectors=obj["selectors"],
        created_at=obj["created_at"],
    )


def write_worker_result(path: Path, result: WorkerResult) -> None:
    _atomic_json(path, asdict(result))


def read_worker_result(path: Path) -> WorkerResult:
    result = json.loads(path.read_text(encoding="utf-8"))
    return WorkerResult(**result)
