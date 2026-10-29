"""GUI에서 사용하는 서버 등록 항목 변경: 고유 ID 보존, 저장 전 검증."""

from __future__ import annotations

from dataclasses import replace

from .multi_config import (
    MultiConfig, ServerProfile, normalize_server_url,
    validate_server_profile, validate_settings,
)


def _find(cfg: MultiConfig, sid: str) -> int:
    for i, server in enumerate(cfg.servers):
        if server.id == sid:
            return i
    raise ValueError("등록된 서버가 아닙니다.")


def change_server(cfg: MultiConfig, sid: str, *, name: str, url: str,
                  username: str) -> ServerProfile:
    index = _find(cfg, sid)
    old = cfg.servers[index]
    candidate = replace(
        old, display_name=name.strip(),
        server_url=normalize_server_url(url), username=username.strip(),
    )
    validate_server_profile(candidate)
    cfg.servers[index] = candidate
    try:
        validate_settings(cfg)
    except ValueError:
        cfg.servers[index] = old
        raise
    return candidate


def set_enabled(cfg: MultiConfig, sid: str, value: bool) -> None:
    index = _find(cfg, sid)
    cfg.servers[index] = replace(cfg.servers[index], enabled=bool(value))
    validate_settings(cfg)


def remove_server(cfg: MultiConfig, sid: str) -> None:
    del cfg.servers[_find(cfg, sid)]
    validate_settings(cfg)

def schedule_check_due(*, now: float, last: float | None, interval: float = 60.0) -> bool:
    """Windows 작업 스케줄러 호출은 GUI의 2초 갱신과 분리합니다."""
    return last is None or now - last >= interval
