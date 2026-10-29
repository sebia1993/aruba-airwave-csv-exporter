"""민감정보를 포함하지 않는 JSONL 실행 이력."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

# 외부 예외 메시지/URL/페이지 HTML/다운로드 데이터는 로그에 기록하지 않습니다.
ALLOWED_KEYS = {"stage", "status", "code", "rows", "bytes", "attempt", "filename", "elapsed_s"}


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
