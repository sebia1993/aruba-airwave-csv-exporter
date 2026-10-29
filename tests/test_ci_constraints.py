"""Python 3.12 CI 의존성의 버전 고정과 빌드 환경 이력 검증.

운영용 pyproject 의존성 범위는 변경하지 않습니다.
"""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "ci" / "constraints-py312.txt"
WORKFLOW = ROOT / ".github" / "workflows" / "windows.yml"

DIRECT = {
    "playwright", "keyring", "psutil", "pytest", "ruff", "pyinstaller",
}


def parse_pins(text: str) -> dict[str, str]:
    versions = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_.-]*)==([A-Za-z0-9.+_-]+)", line)
        assert match, f"CI 제약 파일에서 불확정 의존성 발견: {line!r}"
        name, version = match.groups()
        normalized = name.lower().replace("_", "-").replace(".", "-")
        assert normalized not in versions
        versions[normalized] = version
    return versions


def test_ci_constraints_pin_every_direct_build_and_test_dependency():
    pins = parse_pins(CONSTRAINTS.read_text(encoding="utf-8"))
    assert DIRECT <= pins.keys()
    assert len(pins) >= len(DIRECT)


def test_windows_and_linux_workflows_use_identical_py312_constraints():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert workflow.count("-c ci/constraints-py312.txt") >= 2
    assert "PIP_CONSTRAINT: ci/constraints-py312.txt" in workflow
    assert "AirWaveBuildDependencies-Windows" in workflow
    assert "AirWaveBuildDependencies-Linux" in workflow
    assert "pip freeze --all" in workflow


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS", "").lower() != "true",
    reason="GitHub Actions에 설치된 Python 3.12 패키지의 일치 여부만 검사",
)
def test_ci_installed_direct_packages_match_declared_pins():
    versions = parse_pins(CONSTRAINTS.read_text(encoding="utf-8"))
    for name in DIRECT:
        if name == "pyinstaller" and os.name != "nt":
            continue
        assert importlib.metadata.version(name) == versions[name]
