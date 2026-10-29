"""다중 AirWave 설정 (비밀정보 제외). 첫 설치 시 서버 0대 허용."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ID_PATTERN = re.compile(r"airwave-\d{2,}")
MAX_SERVERS = 5
SCHEMA_VERSION = 2


def registry_path(home: Path) -> Path:
    return home / "multi_config.json"


@dataclass(frozen=True)
class ServerProfile:
    id: str
    display_name: str
    server_url: str
    username: str
    enabled: bool = True
    selector_profile: str = ""


@dataclass
class MultiConfig:
    schema_version: int = SCHEMA_VERSION
    schedule_time: str = "09:00"
    parallel_limit: int = 3
    export_root: str = ""
    next_server_number: int = 1
    servers: list[ServerProfile] = field(default_factory=list)
    retry_delay_seconds: int = 180
    max_attempts: int = 2
    min_wait_seconds: int = 15
    max_wait_seconds: int = 30
    server_timeout_seconds: int = 720
    batch_timeout_seconds: int = 1800
    drop_warning_percent: int = 10
    headless: bool = True

    def __post_init__(self):
        if not self.export_root:
            from .config import app_home
            self.export_root = str(app_home() / "exports")


def normalize_server_url(url: str) -> str:
    if not isinstance(url, str) or url != url.strip():
        raise ValueError("유효한 HTTPS 서버 주소가 필요합니다.")
    try:
        parts = urlsplit(url)
        if (parts.scheme.lower() != "https" or not parts.hostname or
                parts.username is not None or parts.password is not None or
                parts.query or parts.fragment or parts.port == 0):
            raise ValueError("HTTPS 전용이며 계정/쿼리/조각은 URL에 포함할 수 없습니다.")
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        authority = host + (f":{port}" if port and port != 443 else "")
        path = parts.path.rstrip("/")
        if path and (not path.startswith("/") or ".." in path.split("/")):
            raise ValueError("서버 경로가 유효하지 않습니다.")
        return urlunsplit(("https", authority, path, "", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError("유효한 HTTPS 서버 주소가 필요합니다.") from exc


def validate_server_profile(profile: ServerProfile) -> None:
    if not ID_PATTERN.fullmatch(profile.id):
        raise ValueError("서버 고유 ID 형식이 올바르지 않습니다.")
    if not isinstance(profile.display_name, str) or not profile.display_name.strip():
        raise ValueError("서버 이름이 비어 있습니다.")
    normalize_server_url(profile.server_url)
    if not isinstance(profile.username, str) or not profile.username.strip():
        raise ValueError("AirWave 사용자 ID가 비어 있습니다.")
    if not isinstance(profile.selector_profile, str):
        raise ValueError("선택자 설정이 올바르지 않습니다.")


def validate_settings(settings: MultiConfig) -> None:
    if settings.schema_version != 2:
        raise ValueError("알 수 없는 다중 서버 설정 버전입니다.")
    if len(settings.servers) > MAX_SERVERS:
        raise ValueError("서버는 최대 5대까지 등록할 수 있습니다.")
    if not (1 <= settings.parallel_limit <= 5):
        raise ValueError("동시 실행은 1~5대 범위입니다.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", settings.schedule_time):
        raise ValueError("예약 시간은 HH:MM이어야 합니다.")
    if not (15 <= settings.min_wait_seconds <= settings.max_wait_seconds <= 30):
        raise ValueError("전체 폴더 확장 대기는 15~30초여야 합니다.")
    if not (1 <= settings.max_attempts <= 3 and 0 <= settings.retry_delay_seconds <= 3600):
        raise ValueError("재시도 횟수 또는 대기시간이 잘못되었습니다.")
    if not (0 <= settings.drop_warning_percent <= 100):
        raise ValueError("장비 수 감소 기준이 잘못되었습니다.")
    if not (60 <= settings.server_timeout_seconds <= settings.batch_timeout_seconds
            and settings.batch_timeout_seconds <= 86400):
        raise ValueError("작업 타임아웃이 잘못되었습니다.")
    if not settings.export_root.strip() or settings.next_server_number < 1:
        raise ValueError("저장 경로 또는 서버 ID 순서가 잘못되었습니다.")
    ids = [s.id for s in settings.servers]
    if any(not ID_PATTERN.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("서버 고유 ID가 중복되거나 올바르지 않습니다.")
    if any(int(s.id.split("-")[-1]) >= settings.next_server_number for s in settings.servers):
        raise ValueError("다음 서버 ID가 이전 등록 번호보다 작습니다.")
    urls = []
    for s in settings.servers:
        try:
            urls.append(normalize_server_url(s.server_url))
        except ValueError:
            continue  # 서버 개별 오류: 다른 정상 서버를 수집할 수 있어야 합니다.
    if len(urls) != len(set(urls)):
        raise ValueError("AirWave 서버 URL이 중복됩니다.")


def add_server(settings: MultiConfig, *, name: str, url: str, username: str) -> ServerProfile:
    validate_settings(settings)
    if len(settings.servers) >= MAX_SERVERS:
        raise ValueError("서버는 최대 5대까지 등록할 수 있습니다.")
    normalized = normalize_server_url(url)
    profile = ServerProfile(
        id=f"airwave-{settings.next_server_number:02d}", display_name=name.strip(),
        server_url=normalized, username=username.strip(),
    )
    validate_server_profile(profile)
    if any(s.server_url and normalize_server_url(s.server_url) == normalized
           for s in settings.servers if _valid_url(s.server_url)):
        raise ValueError("중복된 AirWave 서버 URL입니다.")
    settings.servers.append(profile)
    settings.next_server_number += 1
    return profile


def _valid_url(url: str) -> bool:
    try:
        normalize_server_url(url)
        return True
    except ValueError:
        return False


def load_v2(path: Path) -> MultiConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        raise ValueError("다중 서버 설정 JSON 구조가 올바르지 않습니다.")
    allowed = set(MultiConfig.__dataclass_fields__)
    entries = []
    for item in data["servers"]:
        if not isinstance(item, dict):
            raise ValueError("서버 설정이 올바르지 않습니다.")
        entries.append(ServerProfile(**{
            k: value for k, value in item.items() if k in ServerProfile.__dataclass_fields__
        }))
    rest = {k: v for k, v in data.items() if k in allowed and k != "servers"}
    model = MultiConfig(**rest, servers=entries)
    validate_settings(model)
    return model


def save_v2(settings: MultiConfig, path: Path) -> None:
    validate_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".json.tmp")
    try:
        staging.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2),
                           encoding="utf-8")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
