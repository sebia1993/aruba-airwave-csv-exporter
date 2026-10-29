"""불변 서버 ID에 기반한 파일 경로만 허용합니다."""

from __future__ import annotations

from pathlib import Path

from .multi_config import ID_PATTERN, MultiConfig


def _valid_id(server_id: str) -> str:
    if not isinstance(server_id, str) or not ID_PATTERN.fullmatch(server_id):
        raise ValueError("잘못된 서버 ID입니다.")
    return server_id


def server_export_dir(settings: MultiConfig, server_id: str) -> Path:
    _valid_id(server_id)
    if not any(s.id == server_id for s in settings.servers):
        raise ValueError("등록되지 않은 AirWave 서버입니다.")
    # 여러 워커의 첫 실행 때 아직 생성되지 않은 경로의 Windows 정규화가
    # 동시 mkdir 사이에서 바뀌지 않도록 상위 폴더부터 생성합니다.
    root_path = Path(settings.export_root).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)
    root = root_path.resolve()
    child = root / server_id
    # symlink 된 서버 폴더는 다른 서버 데이터 오염 위험이 있어 거부합니다.
    if child.is_symlink() or child.resolve() != (root / server_id):
        raise ValueError("CSV 서버 폴더가 다른 경로를 가리킵니다.")
    return child


def server_selectors_path(home: Path, server_id: str) -> Path:
    _valid_id(server_id)
    root = home / "selectors"
    child = root / (server_id + ".json")
    if child.is_symlink():
        raise ValueError("선택자 설정 파일이 다른 경로를 가리킵니다.")
    return child
