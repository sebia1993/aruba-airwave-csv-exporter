"""CSV 1회 수집 실행 엔진. 스케줄러와 GUI는 동일한 함수를 사용합니다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from uuid import uuid4

from .config import Config, ProfileError, SelectorProfile, app_home
from .credentials import CredentialError, CredentialStore
from .csv_store import CsvValidationError, SavedExport, store_export
from .events import record
from .lock import AlreadyRunning, single_instance
from .portal import AirWavePortal, PortalError


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    status: str
    message: str
    saved: SavedExport | None = None
    retryable: bool = False


def run_once(
    config: Config | None = None, profile: SelectorProfile | None = None,
    *, portal_factory=AirWavePortal, credential_store=CredentialStore,
    sleeper=time.sleep, home: Path | None = None,
) -> RunResult:
    base = home or app_home()
    started = time.monotonic()
    try:
        with single_instance(base / "state" / "run.lock"):
            config = config or Config.load(base / "config.json")
            config.validate(require_connection=True)
            profile = profile or SelectorProfile.load(base / "selectors.json")
            password = credential_store.get(config.server_url, config.username)
            config.export_path.mkdir(parents=True, exist_ok=True)
            last_error: Exception | None = None
            for attempt in range(1, config.max_attempts + 1):
                staged = config.export_path / (".download-" + uuid4().hex + ".part")
                try:
                    portal = portal_factory(config, profile)
                    expected = portal.download(staged, password)
                    saved = store_export(
                        staged, config.export_path, expected_rows=expected,
                        drop_warning_percent=config.drop_warning_percent,
                    )
                    status = "warning" if saved.warning_drop else "success"
                    code = 2 if saved.warning_drop else 0
                    record(
                        base, stage="complete", status=status, code=code,
                        rows=saved.rows, bytes=saved.size, filename=saved.path.name,
                        attempt=attempt, elapsed_s=round(time.monotonic() - started, 1),
                    )
                    return RunResult(
                        code, status,
                        ("장비 수가 급감하여 latest.csv 갱신을 보류했습니다."
                         if saved.warning_drop else "CSV 다운로드 및 검증에 성공했습니다."),
                        saved,
                    )
                except (CsvValidationError, PortalError) as exc:
                    last_error = exc
                    # 빈 파일/일시적 다운로드 실패만 재시도합니다. 45=보기 오류는 즉시 실패.
                    eligible = isinstance(exc, CsvValidationError) or (
                        isinstance(exc, PortalError) and exc.code == 48
                    )
                    if not eligible or attempt == config.max_attempts:
                        break
                    record(base, stage="retry", status="retry", code=51,
                           attempt=attempt)
                    sleeper(config.retry_delay_seconds)
                finally:
                    staged.unlink(missing_ok=True)
            if isinstance(last_error, PortalError):
                code = last_error.code
            else:
                code = 52
            message = str(last_error) if last_error else "알 수 없는 다운로드 오류입니다."
            record(base, stage="complete", status="failed", code=code,
                   attempt=attempt, elapsed_s=round(time.monotonic() - started, 1))
            return RunResult(code, "failed", message)
    except AlreadyRunning:
        return RunResult(60, "failed", "다른 CSV 내보내기 작업이 실행 중입니다.")
    except (ProfileError, ValueError, OSError) as exc:
        code = 44 if isinstance(exc, ProfileError) else 40
        record(base, stage="configuration", status="failed", code=code)
        return RunResult(code, "failed", str(exc))
    except CredentialError as exc:
        record(base, stage="authentication", status="failed", code=31)
        return RunResult(31, "failed", str(exc))
    except Exception:
        record(base, stage="unexpected", status="failed", code=99)
        return RunResult(99, "failed", "처리되지 않은 오류가 발생했습니다. 실행 로그를 확인하세요.")


def collect_attempt(
    config: Config, profile: SelectorProfile, password: str,
    *, portal_factory=AirWavePortal, home: Path,
) -> RunResult:
    """잠금/재시도/비밀정보 로그 없는 단일 AirWave 다운로드 시도."""
    config.validate(require_connection=True)
    config.export_path.mkdir(parents=True, exist_ok=True)
    staged = config.export_path / (".download-" + uuid4().hex + ".part")
    try:
        expected_rows = portal_factory(config, profile).download(staged, password)
        saved = store_export(
            staged, config.export_path, expected_rows=expected_rows,
            drop_warning_percent=config.drop_warning_percent,
        )
        if saved.warning_drop:
            return RunResult(2, "warning", "장비 수 감소로 latest.csv 갱신을 보류했습니다.",
                             saved, False)
        return RunResult(0, "success", "CSV 검증 및 저장에 성공했습니다.", saved, False)
    except PortalError as exc:
        return RunResult(exc.code, "failed", str(exc), None, exc.code in (47, 48))
    except CsvValidationError as exc:
        return RunResult(52, "failed", str(exc), None, True)
    except (OSError, ValueError) as exc:
        return RunResult(40, "failed", "CSV 수집 경로 또는 설정에 오류가 있습니다.", None, False)
    finally:
        staged.unlink(missing_ok=True)
