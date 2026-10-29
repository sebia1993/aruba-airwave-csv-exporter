"""GUI 및 작업 스케줄러에서 호출하는 진입점."""

from __future__ import annotations

import argparse
import sys

from .engine import run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirWave CSV Exporter for Windows 11")
    parser.add_argument("--run", action="store_true", help="CSV를 한 번 다운로드합니다.")
    parser.add_argument("--headless", action="store_true", help="GUI 없이 실행합니다.")
    args = parser.parse_args(argv)
    if args.run:
        result = run_once()
        if not args.headless:
            print(result.message)
        return result.exit_code
    from .gui import launch

    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
