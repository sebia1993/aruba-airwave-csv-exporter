"""비밀정보가 없는 사용자 설정 및 현장 확인된 CSS 선택자."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit

APP_NAME = "AirWaveCsvExporter"
TASK_NAME = "AirWave CSV Exporter - Daily"
REQUIRED_VIEW = "Devices"
ROOT_FOLDER = "Top"


def app_home() -> Path:
    override = os.environ.get("AIRWAVE_CSV_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


@dataclass
class Config:
    server_url: str = ""
    username: str = ""
    export_dir: str = ""
    schedule_time: str = "09:00"
    schedule_enabled: bool = False
    min_wait_seconds: int = 15
    max_wait_seconds: int = 30
    retry_delay_seconds: int = 180
    max_attempts: int = 2
    drop_warning_percent: int = 10
    headless: bool = True

    def __post_init__(self) -> None:
        if not self.export_dir:
            self.export_dir = str(app_home() / "exports")

    def validate(self, *, require_connection: bool = False) -> None:
        if require_connection or self.server_url:
            url = urlsplit(self.server_url)
            if (url.scheme != "https" or not url.hostname or url.username
                    or url.password or url.query or url.fragment):
                raise ValueError("AirWave 주소는 계정정보가 없는 HTTPS 서버 주소여야 합니다.")
        if require_connection and not self.username.strip():
            raise ValueError("AirWave 사용자 ID를 입력하세요.")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", self.schedule_time):
            raise ValueError("실행 시간은 HH:MM 형식이어야 합니다.")
        if not (15 <= self.min_wait_seconds <= self.max_wait_seconds <= 30):
            raise ValueError("전체 목록 대기는 15~30초 범위여야 합니다.")
        if not (1 <= self.max_attempts <= 3 and 0 <= self.retry_delay_seconds <= 3600):
            raise ValueError("재시도 설정이 올바르지 않습니다.")
        if not (0 <= self.drop_warning_percent <= 100):
            raise ValueError("장비 감소 경고 비율이 올바르지 않습니다.")
        if not self.export_dir.strip():
            raise ValueError("CSV 저장 폴더가 비어 있습니다.")

    @property
    def export_path(self) -> Path:
        return Path(os.path.expandvars(self.export_dir)).expanduser()

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or app_home() / "config.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = {field.name for field in fields(cls)}
        obj = cls(**{k: v for k, v in data.items() if k in valid})
        obj.validate()
        return obj

    def save(self, path: Path | None = None) -> None:
        self.validate()
        path = path or app_home() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)


# 초기에는 필수 CSS를 의도적으로 비워 둡니다. 추측한 선택자로 잘못된 CSV를 받지 않습니다.
SELECTOR_TEMPLATE: dict[str, str] = {
    "devices_nav_css": "",
    "list_nav_css": "",
    "login_user_css": "",
    "login_pass_css": "",
    "login_submit_css": "",
    "table_root_css": "",
    "view_control_css": "",
    "view_selected_css": "",
    "view_option_css": "",
    "folder_control_css": "",
    "folder_selected_css": "",
    "folder_option_css": "",
    "active_filters_css": "",
    "clear_filters_css": "",
    "expand_control_css": "",
    "expanded_marker_css": "",
    "loading_css": "",
    "rows_css": "",
    "total_count_css": "",
    "total_count_pattern": r"(?:of|총)\s*([\d,]+)",
    "export_control_css": "",
}

# 필수 선택자는 AirWave 8.2.14.0 실제 HTML 화면을 확인해 입력해야 합니다.
REQUIRED_SELECTORS = (
    "table_root_css",
    "view_control_css",
    "folder_control_css",
    "active_filters_css",
    "expand_control_css",
    "expanded_marker_css",
    "rows_css",
    "total_count_css",
    "export_control_css",
)


class ProfileError(Exception):
    pass


@dataclass(frozen=True)
class SelectorProfile:
    values: dict[str, str]

    @classmethod
    def load(cls, path: Path | None = None) -> "SelectorProfile":
        path = path or app_home() / "selectors.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(SELECTOR_TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raise ProfileError("선택자 파일을 생성했습니다. 현장 AirWave 화면에 맞게 설정하세요.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ProfileError("선택자 파일은 JSON 객체여야 합니다.")
        values = {k: raw.get(k, v) for k, v in SELECTOR_TEMPLATE.items()}
        if any(not isinstance(v, str) for v in values.values()):
            raise ProfileError("CSS 선택자는 문자열이어야 합니다.")
        missing = [key for key in REQUIRED_SELECTORS if not values[key].strip()]
        if missing:
            raise ProfileError("필수 화면 선택자가 미설정되었습니다: " + ", ".join(missing))
        try:
            re.compile(values["total_count_pattern"])
        except re.error as exc:
            raise ProfileError("장비 총건수 추출 정규식이 올바르지 않습니다.") from exc
        return cls(values)

    def __getitem__(self, key: str) -> str:
        return self.values[key]
