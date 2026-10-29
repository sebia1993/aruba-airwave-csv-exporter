"""Windows에서 실제 PyInstaller EXE 3대/5대 워커를 실행하는 음성(fail-closed) 검사.

사내 AirWave 접속이나 비밀번호 취득은 하지 않습니다.
빈 CSS 프로필을 넣어 제품이 정상적으로 오류 44를 반환하는지 검사합니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from airwave_csv import process_control
from airwave_csv.multi_config import MultiConfig, add_server
from airwave_csv.orchestrator import run_batch
from airwave_csv.run_snapshot import BatchSnapshot, read_worker_result


class CountLauncher(process_control.WorkerLauncher):
    def __init__(self, run_id: str):
        super().__init__(run_id)
        self.handles = []
        self.max_active = 0
        self.started = []

    def start(self, snapshot_path, server_id, attempt, result_path):
        handle = super().start(snapshot_path, server_id, attempt, result_path)
        self.handles.append(handle)
        self.started.append(server_id)
        live = sum(h.process.poll() is None for h in self.handles)
        self.max_active = max(live, self.max_active)
        return handle


def verify(exe: Path, servers: int, root: Path) -> dict:
    if not exe.is_file() or exe.suffix.lower() != ".exe":
        raise ValueError("실제 PyInstaller Windows EXE 파일 경로가 필요합니다.")
    config = MultiConfig(
        export_root=str(root / "exports"), parallel_limit=3,
        retry_delay_seconds=1, server_timeout_seconds=60, batch_timeout_seconds=180,
    )
    for index in range(1, servers + 1):
        add_server(
            config, name=f"Fake AirWave {index}",
            url=f"https://synthetic-{index}.invalid", username="fake-operator",
        )
    run_id = str(uuid4())
    snapshot = BatchSnapshot(
        run_id, config, tuple(config.servers), {}, "2026-10-29T00:00:00Z"
    )
    launcher = CountLauncher(run_id)

    def command(snapshot_path, server_id, attempt, result_path):
        return [
            str(exe), "--worker", "--snapshot", str(snapshot_path),
            "--server-id", server_id, "--attempt", str(attempt),
            "--result", str(result_path), "--headless",
        ]

    with patch.object(process_control, "worker_command", command):
        result = run_batch(snapshot, launcher=launcher, home=root / "home")
    if result.failed != servers or result.success != 0 or result.exit_code != 1:
        raise AssertionError(f"패키징 워커가 예상과 다르게 동작했습니다: {result}")
    if launcher.max_active > 3 or len(launcher.started) != servers:
        raise AssertionError("실제 EXE 워커의 3슬롯 또는 시작 개수에 오류가 있습니다.")
    for index in range(1, servers + 1):
        sid = f"airwave-{index:02}"
        result_file = root / "home" / "runs" / run_id / f"result-{sid}-1.json"
        worker_result = read_worker_result(result_file)
        if worker_result.exit_code != 44 or worker_result.status != "FAILED":
            raise AssertionError(f"실제 EXE fail-closed 경로 오류: {sid}/{worker_result}")
    if (root / "home" / "state" / "active_batch.json").exists():
        raise AssertionError("종료 후 active 배치 마커가 남았습니다.")
    if list((root / "exports").rglob("*.csv")) if (root / "exports").exists() else []:
        raise AssertionError("미확인 CSS 환경에서 CSV가 생성되었습니다.")
    return {
        "servers": servers, "max_active": launcher.max_active,
        "started": len(launcher.started), "errors_44": result.failed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    args = parser.parse_args()
    import os

    if os.name != "nt":
        raise SystemExit("이 검증은 Windows에서만 실행합니다.")
    with tempfile.TemporaryDirectory(prefix="airwave-frozen-test-") as temp:
        root = Path(temp)
        for count in (3, 5):
            print(verify(args.exe.resolve(), count, root / str(count)))
    print("Windows EXE 3/5 real worker processes: fail-closed verification passed")


if __name__ == "__main__":
    main()
