"""Windows GUI / 전체 일일 배치 / 개별 서버 / 내부 워커 진입점."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from .config import ProfileError, SelectorProfile, app_home
from .migration import migrate_if_needed
from .multi_config import validate_settings
from .orchestrator import run_batch
from .paths import server_selectors_path
from .run_snapshot import BatchSnapshot
from .worker import run_worker


def run_all(only: str | None = None) -> int:
    home = app_home()
    try:
        settings = migrate_if_needed(home)
        validate_settings(settings)
        if only:
            servers = tuple(s for s in settings.servers if s.id == only)
            if len(servers) != 1:
                return 3
        else:
            servers = tuple(settings.servers)
        selectors = {}
        for s in servers:
            try:
                path = server_selectors_path(home, s.id)
                selectors[s.id] = SelectorProfile.load(path).values
            except (ProfileError, ValueError, OSError):
                selectors[s.id] = {}  # 다른 서버에는 영향을 미치지 않습니다.
        snap = BatchSnapshot(
            run_id=str(uuid4()), settings=settings, servers=servers,
            selectors=selectors,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return run_batch(snap, home=home).exit_code
    except Exception:
        # 실제 서버 계정·URL·로그 정보를 콘솔에 출력하지 않습니다.
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirWave CSV Exporter Windows 11")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", action="store_true", help="이전 버전 호환: 전체 수집")
    group.add_argument("--run-all", action="store_true", help="등록된 서버 모두 수집")
    group.add_argument("--run-one", metavar="SERVER_ID", help="한 서버만 수집")
    group.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--headless", action="store_true", help="GUI 없이 실행")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--server-id")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    if args.worker:
        if not all((args.snapshot, args.server_id, args.attempt, args.result)):
            parser.error("--worker requires --snapshot, --server-id, --attempt, --result")
        return run_worker(args.snapshot, args.server_id, args.attempt, args.result)
    if args.run or args.run_all or args.run_one:
        return run_all(args.run_one)
    from .gui import launch
    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
