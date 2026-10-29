"""PyInstaller 실행 진입점 (package 상대 import 문제 방지)."""

from airwave_csv.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
