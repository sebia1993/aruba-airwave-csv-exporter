"""Git 저장소에 로컬 운영 설정·실행 상태가 실수로 포함되지 않아야 합니다."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("private_path", [
    "multi_config.json",
    "config.v1.backup.json",
    "selectors/airwave-01.json",
    "selectors/airwave-02.json",
    "state/last_batch.json",
    "state/active_batch.json",
    "runs/example-run/snapshot.json",
    "logs/2026-10-29.jsonl",
    ".superpowers/sdd/example/progress.md",
])
def test_local_airwave_files_are_gitignored(private_path):
    result = subprocess.run(
        ["git", "check-ignore", "-q", private_path],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, f"로컬 운영 파일이 Git 추적 대상이 될 위험: {private_path}"
