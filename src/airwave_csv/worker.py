"""워커 프로세스는 글로벌 잠금을 잡지 않고 서버 1대에서 딱 한 번 시도합니다."""

from __future__ import annotations

from pathlib import Path

from .config import Config, ProfileError, REQUIRED_SELECTORS, SelectorProfile
from .credentials import CredentialError, CredentialStore
from .engine import collect_attempt
from .multi_config import validate_server_profile
from .paths import server_export_dir
from .run_snapshot import WorkerResult, read_snapshot, write_worker_result


def run_worker(snapshot_path: Path, server_id: str, attempt: int, result_path: Path) -> int:
    snapshot = read_snapshot(snapshot_path)
    if attempt < 1 or server_id not in {s.id for s in snapshot.servers}:
        raise ValueError("등록되지 않은 서버 또는 잘못된 실행 번호입니다.")
    server = next(s for s in snapshot.servers if s.id == server_id)
    status, code, retry, rows, name = "FAILED", 99, False, None, None
    try:
        validate_server_profile(server)
        raw = snapshot.selectors.get(server_id)
        if not raw or any(not raw.get(key) for key in REQUIRED_SELECTORS):
            raise ProfileError("이 AirWave의 실제 화면 CSS 선택자가 미확인 상태입니다.")
        # 선택자 내용을 스냅샷에 고정해 실행 중 GUI 변경과 분리합니다.
        profile = SelectorProfile(dict(raw))
        password = CredentialStore.get_for_server(server_id)
        cfg = Config(
            server_url=server.server_url, username=server.username,
            export_dir=str(server_export_dir(snapshot.settings, server_id)),
            min_wait_seconds=snapshot.settings.min_wait_seconds,
            max_wait_seconds=snapshot.settings.max_wait_seconds,
            drop_warning_percent=snapshot.settings.drop_warning_percent,
            max_attempts=1,
            headless=snapshot.settings.headless,
        )
        result = collect_attempt(cfg, profile, password,
                                 home=snapshot_path.parent.parent.parent)
        code, retry = result.exit_code, result.retryable
        status = ("SUCCESS" if code == 0 else "WARNING" if code == 2 else "FAILED")
        if result.saved:
            rows, name = result.saved.rows, result.saved.path.name
    except CredentialError:
        code = 31
    except ProfileError:
        code = 44
    except (ValueError, OSError):
        code = 40
    except Exception:
        code = 99
    write_worker_result(result_path, WorkerResult(
        snapshot.run_id, server_id, attempt, status, code, retry, rows, name,
    ))
    return code
