"""단일 서버 v1 설정을 읽어도 기존 파일을 변경/삭제하지 않는 v2 마이그레이션."""

from __future__ import annotations

from pathlib import Path
import shutil

from .config import Config
from .credentials import CredentialStore
from .multi_config import MultiConfig, add_server, load_v2, registry_path, save_v2
from .paths import server_selectors_path


def migrate_if_needed(home: Path, vault=CredentialStore) -> MultiConfig:
    target = registry_path(home)
    if target.exists():
        return load_v2(target)
    legacy_path = home / "config.json"
    if not legacy_path.exists():
        cfg = MultiConfig(export_root=str(home / "exports"))
        save_v2(cfg, target)
        return cfg
    original = Config.load(legacy_path)  # 손상 파일이면 v1 원본은 보존하고 오류
    backup = home / "config.v1.backup.json"
    if not backup.exists():
        shutil.copy2(legacy_path, backup)
    cfg = MultiConfig(export_root=original.export_dir,
                      schedule_time=original.schedule_time,
                      min_wait_seconds=original.min_wait_seconds,
                      max_wait_seconds=original.max_wait_seconds,
                      drop_warning_percent=original.drop_warning_percent,
                      max_attempts=original.max_attempts,
                      retry_delay_seconds=original.retry_delay_seconds,
                      headless=original.headless)
    if original.server_url and original.username:
        server = add_server(cfg, name="AirWave 1",
                            url=original.server_url, username=original.username)
        selectors = home / "selectors.json"
        destination = server_selectors_path(home, server.id)
        if selectors.exists() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(selectors, destination)
        try:
            password = vault.get(original.server_url, original.username)
        except Exception:
            password = None   # Vault 키 유실: UI에서 재입력 후 서버별 실패 처리
        if password:
            vault.set_for_server(server.id, password)
    save_v2(cfg, target)
    return cfg
