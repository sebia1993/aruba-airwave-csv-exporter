# Multi-AirWave 5-Server Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 단일 AirWave CSV Exporter를 보존하면서 최대 5대의 AirWave를 등록하고 기본 3대 병렬 프로세스와 FIFO 대기열을 통해 CSV를 독립 수집한다.

**Architecture:** Windows 11 EXE 하나가 글로벌 배치 잠금과 일일 예약 작업 하나를 유지하고, 독립 Playwright/Edge 워커 프로세스를 동시에 최대 3개 실행한다. 서버별 설정 스냅샷·자격 증명·CSS 선택자·다운로드 경로·결과를 격리한다. 먼저 기존 단일 서버 수집 로직을 재사용 가능한 단일 시도 함수로 추출한다.

**Tech Stack:** Python >=3.11, tkinter, Playwright >=1.55,<2, keyring >=25,<27, Windows Task Scheduler/PowerShell, Windows Job Object(ctypes), PyInstaller >=6.14,<7, pytest >=8,<10, GitHub Actions (Windows/Linux).

**Spec:** `docs/superpowers/specs/2026-10-29-multi-airwave-export-design.md` (승인된 2026-10-29 설계 문서)

## Global Constraints

- Windows 11 64비트와 AirWave 8.2.14.0 우선. **실 AirWave DOM/로그인은 미검증**; CSS 필수 선택자 미설정 시 CSV 다운로드 전 실패한다.
- 최대 등록 5대(신규 설치 0대 가능), 기본 동시 워커 3개, 1~5로 설정 가능, 초과 등록 금지. 실행 중 대기열은 미시작 서버 우선 FIFO.
- 각 워커는 `Devices > List`, `Default View = Devices`, 필터 해제, `Top`, `Expand folders to show all devices`, 최소 15~최대 30초 대기를 **다운로드 전 재검증**한다.
- 실패한 서버가 다른 서버를 중단하지 않는다. 서버별 CSV, `latest.csv`, 비교 기준, 자격 증명, 선택자, 로그를 분리한다.
- 다운로드/일시 로딩 오류는 서버별 기본 최대 2회 시도, 재시도 전 180초 **슬롯 미점유** 대기. 인증·보기 불일치·미확인 CSS는 재시도하지 않는다.
- 권장 한도: 서버별 첫 시도부터 12분(재시도 포함), 전체 배치 시작부터 30분. 타임아웃/종료 시 자식 Edge 프로세스 트리를 정리한다.
- Windows 예약 작업은 기존 `AirWave CSV Exporter - Daily` 하나와 현재 Interactive Windows 계정을 유지. 로그오프 중 실행은 보장하지 않는다.
- 공개 GitHub에는 실주소·ID·비밀번호·쿠키·CSV/장비 데이터/현장 CSS를 추가하지 않는다. 비밀번호는 Windows Credential Manager에서 워커가 직접 읽는다.
- GUI는 한국어 유지, 단일 서버 사용자는 기존 설정·선택자·과거 CSV·Windows 예약을 잃지 않는다. `main` 수정/Release는 별도 실행 단계에서 처리한다.

## File Map (작업 전 인터페이스 결정)

| 경로 | 단일 책임 |
| --- | --- |
| `src/airwave_csv/multi_config.py` (Create) | `ServerProfile`/`MultiConfig`, 최대 5대 검증, URL 중복 제거, 불변 서버 ID |
| `src/airwave_csv/migration.py` (Create) | v1 설정/선택자/자격 증명 백업·원자적 v2 이행 |
| `src/airwave_csv/credentials.py` (Modify) | ID 단위 Windows Credential Manager 키와 구 키 호환 |
| `src/airwave_csv/paths.py` (Create) | 서버 ID별 CSV/선택자 디렉터리 안전 생성 |
| `src/airwave_csv/engine.py` (Modify) | 잠금 없는 **단일 시도** 수집 함수 추출 및 기존 `run_once` 호환 |
| `src/airwave_csv/run_snapshot.py` (Create) | 비밀정보 제외한 배치 입력 스냅샷·원자적 워커 결과 JSON |
| `src/airwave_csv/worker.py` (Create) | 한 서버의 한 시도만 수행하고 결과 기록하는 CLI 워커 |
| `src/airwave_csv/process_control.py` (Create) | Windows Job Object 기반 워커·Edge 프로세스 트리 종료 |
| `src/airwave_csv/orchestrator.py` (Create) | 최대 3개 실행 슬롯, FIFO, 재시도 공정성, 타임아웃, 배치 결과 집계 |
| `src/airwave_csv/events.py` (Modify) | 실행ID/서버ID 포함 이벤트·중단 복구용 요약 |
| `src/airwave_csv/__main__.py` (Modify) | 전체/선택/워커 실행 명령과 기존 `--run` 호환 |
| `src/airwave_csv/scheduler.py` (Modify) | 기존 Windows 예약 1개가 다중 서버 전체 실행 |
| `src/airwave_csv/gui.py` (Modify) | 서버 추가·수정·삭제/비활성, 전체/선택 실행, 상태표 |
| `src/airwave_csv/portal.py` (Reuse) | CSS/보기/폴더/15~30초 검증은 서버별 기존 코드 재사용 |
| `src/airwave_csv/csv_store.py` (Reuse) | 동일 서버 `latest.csv` 비교 및 파일 구조 검증 (호출 경로만 변경) |
| `tests/test_multi_config.py`, `test_migration.py`, `test_multi_credentials_paths.py` (Create) | 스키마·이행·격리 |
| `tests/test_single_attempt.py`, `test_worker.py`, `test_process_control.py` (Create) | 1회 시도·CLI 격리·프로세스 |
| `tests/test_orchestrator.py`, `test_batch_events.py`, `test_multi_cli.py`, `test_multi_gui.py` (Create) | 대기열·재시도·결과·UX |
| `tests/test_multi_airwave_e2e.py` (Create) | Windows 모의 AirWave 서버 3~5대 통합 검증 |
| `.github/workflows/windows.yml`, `README.md`, `docs/현장_연동_가이드.md` (Modify) | CI, 사용법, 현장 인수 절차 |

## Review Focus

- URL 표현 변형(대문자 호스트/기본 포트/끝 슬래시)과 ID 삭제 후 재등록 → 중복 서버 거부 및 절대 서버 ID 재사용 금지 (`Task 1`).
- v1 설정 손상·v2 쓰기 실패·Credential Manager 읽기 실패 → 백업 보존, 재실행 멱등성, 누락 비밀번호는 재입력 표시 (`Task 2`).
- 표시 이름에 경로 문자·서버 간 동일 CSV 파일명 → 경로 탈출/교차 덮어쓰기 불가, 기존 정상본 유지 (`Task 3`).
- 재시도 대기(180초)와 최초 대기열 D/E가 겹침 → A가 슬롯을 잡지 않고 D/E 우선 실행, 최대 3 슬롯 불변 (`Task 7`).
- 서버 하위 Edge 프로세스가 멈추거나 GUI/배치가 중단됨 → 자식 프로세스 트리 종료, 상태 INTERRUPTED, 유효한 다른 CSV 보존 (`Task 6`/`Task 8`).

---

### Task 1: v2 서버 설정 모델 및 등록 한도

**Files:**
- Create: `src/airwave_csv/multi_config.py`
- Test: `tests/test_multi_config.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) ServerProfile(id: str, display_name: str, server_url: str, username: str, enabled: bool=True, selector_profile: str="")`
- Produces: `@dataclass MultiConfig(schema_version: int=2, schedule_time: str="09:00", parallel_limit: int=3, export_root: str="", next_server_number: int=1, servers: list[ServerProfile]=..., retry_delay_seconds: int=180, max_attempts: int=2, min_wait_seconds: int=15, max_wait_seconds: int=30, server_timeout_seconds: int=720, batch_timeout_seconds: int=1800, drop_warning_percent: int=10)`
- Produces: `normalize_server_url(url: str) -> str`, `add_server(settings: MultiConfig, *, name: str, url: str, username: str) -> ServerProfile`, `validate_settings(settings: MultiConfig) -> None`, `validate_server_profile(profile: ServerProfile) -> None`, `load_v2(path: Path) -> MultiConfig`, `save_v2(settings: MultiConfig, path: Path) -> None`

- [ ] **Step 1: Write failing tests.** `test_first_run_allows_zero_servers`, `test_five_allowed_sixth_rejected`, `test_normalized_duplicate_url_rejected`, `test_deleted_id_never_reused`, `test_parallel_default_is_three`, `test_invalid_url_or_time_rejected`, `test_one_bad_server_does_not_invalidate_other_profiles`. Assert new install has 0 registered, first ID airwave-01, fifth succeeds, sixth raises ValueError, delete then add gets a higher ID, mixed-case host/443/trailing slash are duplicate. An existing server with valid stable ID but invalid URL/username is loadable as a failed server while the other valid server profiles remain runnable.
    **대표 검증 테스트:**

```python
def test_five_allowed_sixth_rejected():
    settings = MultiConfig()
    for i in range(1, 6):
        add_server(settings, name=f"AW{i}", url=f"https://aw{i}.example.invalid",
                   username="operator")
    assert len(settings.servers) == 5
    assert settings.parallel_limit == 3
    with pytest.raises(ValueError):
        add_server(settings, name="AW6", url="https://aw6.example.invalid",
                   username="operator")
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_multi_config.py` → import or assertion failure expected.
- [ ] **Step 3: Implement minimal model and JSON atomic save.** Keep existing `config.Config` as legacy/single-attempt adapter; do not change `portal.py` behavior. Persist `next_server_number`; reject URL credentials, query and fragment **on add/edit**. Keep global structural validation (JSON schema, duplicate IDs/URLs, limits, non-dict entries) separate from **per-server readiness validation** (bad URL/account/CSS should fail only that server at dispatch time); syntactically unreadable JSON fails the batch.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_multi_config.py tests/test_config.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/multi_config.py tests/test_multi_config.py && git commit -m "feat: define multi-AirWave settings and server registry"`

### Task 2: 기존 v1 환경 안전 마이그레이션

**Files:**
- Create: `src/airwave_csv/migration.py`
- Modify: `src/airwave_csv/credentials.py`
- Test: `tests/test_migration.py`, existing `tests/test_config.py`

**Interfaces:**
- Consumes: `MultiConfig`/`load_v2`/`save_v2`/`ServerProfile` from Task 1 and existing `Config`/`SelectorProfile`.
- Produces: `migrate_if_needed(home: Path, vault: CredentialStore) -> MultiConfig`; `CredentialStore.set_for_server(server_id: str, password: str) -> None`; `get_for_server(server_id: str) -> str`; legacy `get(server,user)`/`set(server,user,password)` unchanged.

- [ ] **Step 1: Write failing tests.** `test_migrates_v1_once_and_preserves_original_csv`, `test_bad_v1_or_failed_write_rolls_back`, `test_missing_vault_password_requires_reentry_not_failure`, `test_migration_is_idempotent`. Assert backup of old config, selectors copied to per-server path, unchanged old CSV/latest.csv, no credential value in v2 JSON, duplicate startup yields one server.
    **대표 검증 테스트:**

```python
def test_migration_is_idempotent(tmp_path, fake_vault):
    Config(server_url="https://aw.example.invalid", username="ops",
           export_dir=str(tmp_path / "csv")).save(tmp_path / "config.json")
    first = migrate_if_needed(tmp_path, fake_vault)
    second = migrate_if_needed(tmp_path, fake_vault)
    assert [s.id for s in first.servers] == ["airwave-01"]
    assert [s.id for s in second.servers] == ["airwave-01"]
    assert (tmp_path / "config.v1.backup.json").exists()
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_migration.py` → FAIL.
- [ ] **Step 3: Implement migration.** Read legacy config, back it up before changing; create airwave-01; copy (not move) selectors; only migrate credentials if legacy vault access succeeds; write v2 via temporary file+replace. If credentials absent, mark setup needed without guessing. Keep old files intact, and do not treat unverified CSS as verified.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_migration.py tests/test_config.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/migration.py src/airwave_csv/credentials.py tests/test_migration.py && git commit -m "feat: migrate single-AirWave settings safely"`

### Task 3: 서버별 경로·자격 증명·CSV 격리

**Files:**
- Create: `src/airwave_csv/paths.py`
- Modify: `src/airwave_csv/credentials.py` (Task 2의 새 키 API 사용)
- Test: `tests/test_multi_credentials_paths.py`, `tests/test_csv_store.py`

**Interfaces:**
- Consumes: `MultiConfig`, `ServerProfile`, `CredentialStore.get_for_server(server_id)`.
- Produces: `server_export_dir(settings: MultiConfig, server_id: str) -> Path`, `server_selectors_path(home: Path, server_id: str) -> Path`; both reject missing/invalid ID.
- Reuses: `store_export(staged, destination, expected_rows, drop_warning_percent) -> SavedExport`.

- [ ] **Step 1: Write failing tests.** `test_alias_path_characters_cannot_escape_export_root`, `test_two_servers_have_independent_latest_and_drop_baseline`, `test_same_filename_never_cross_overwrites`, `test_vault_server_ids_are_isolated`. Assert server display aliases containing `../` have no effect on path, A 감소 경고 does not change B latest, A/B credentials never interchange.
    **대표 검증 테스트:**

```python
def test_alias_does_not_change_server_path(tmp_path):
    settings = MultiConfig(export_root=str(tmp_path / "exports"))
    server = add_server(settings, name="../other-server",
                        url="https://aw1.example.invalid", username="ops")
    assert server_export_dir(settings, server.id) == tmp_path / "exports" / "airwave-01"
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_multi_credentials_paths.py` → FAIL.
- [ ] **Step 3: Implement ID-based paths and vault key validation.** Resolve paths beneath `export_root` using immutable ID only; no automatic deletion/move of historical CSV. First new success establishes new per-server latest baseline; legacy root latest stays untouched.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_multi_credentials_paths.py tests/test_csv_store.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/paths.py src/airwave_csv/credentials.py tests/test_multi_credentials_paths.py && git commit -m "feat: isolate CSV and credentials by server ID"`

### Task 4: 잠금 없는 1회 수집과 기존 기능 호환

**Files:**
- Modify: `src/airwave_csv/engine.py`
- Test: `tests/test_single_attempt.py`, existing `tests/test_engine.py`/`test_portal.py`

**Interfaces:**
- Produces: `collect_attempt(config: Config, profile: SelectorProfile, password: str, *, portal_factory=AirWavePortal, home: Path) -> RunResult`; add `RunResult.retryable: bool = False`.
- Maintains: existing `run_once(config=None, profile=None, *, portal_factory, credential_store, sleeper, home=None) -> RunResult` for legacy tests; global lock/retry remain in wrapper, **not** in `collect_attempt`.
- Retry classification: `PortalError` 47/48 and `CsvValidationError` → retryable; `PortalError` 31/45/46 and profile/vault errors → not retryable.

- [ ] **Step 1: Write failing tests.** `test_attempt_does_not_acquire_global_lock_or_sleep`, `test_retryable_timeout_47`, `test_nonretryable_wrong_view_45`, `test_legacy_run_once_still_retries_once`. Use fake Portal; assert no password appears in error/log and two different server destinations do not share latest.
    **대표 검증 테스트:**

```python
def test_nonretryable_wrong_view_45(config_for, profile_for, tmp_path):
    result = collect_attempt(config_for, profile_for, "dummy",
                             portal_factory=WrongViewPortal, home=tmp_path)
    assert result.exit_code == 45
    assert result.retryable is False
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_single_attempt.py` → FAIL.
- [ ] **Step 3: Extract one-attempt function.** Preserve existing CSV validation and fail-closed default view/Top/15~30s behavior; no Selenium bypass, TLS disable, or manual retry within worker.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_single_attempt.py tests/test_engine.py tests/test_portal.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/engine.py tests/test_single_attempt.py && git commit -m "refactor: extract isolated single AirWave export attempt"`

### Task 5: 비밀정보 없는 스냅샷과 독립 워커

**Files:**
- Create: `src/airwave_csv/run_snapshot.py`, `src/airwave_csv/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) BatchSnapshot(run_id: str, settings: MultiConfig, servers: tuple[ServerProfile,...], selectors: dict[str, dict[str,str]], created_at: str)`.
- Produces: `write_snapshot(home: Path, snapshot: BatchSnapshot) -> Path`; `read_snapshot(path: Path) -> BatchSnapshot`; `write_worker_result(path: Path, result: WorkerResult) -> None` (atomic).
- Produces: `@dataclass(frozen=True) WorkerResult(run_id: str, server_id: str, attempt: int, status: str, exit_code: int, retryable: bool, rows: int|None, filename: str|None)` and `run_worker(snapshot_path: Path, server_id: str, attempt: int, result_path: Path) -> int`.
- Consumes: `collect_attempt` from Task 4, `server_export_dir` Task 3, `CredentialStore.get_for_server` Task 2. Worker **must not take parent global lock**.

- [ ] **Step 1: Write failing tests.** `test_snapshot_has_no_password_or_cookie`, `test_worker_one_attempt_reports_atomic_result`, `test_bad_css_fails_only_selected_server`, `test_snapshot_prevents_inflight_config_change`. Assert missing selectors or credential yields per-server failure not whole-batch startup crash.
    **대표 검증 테스트:**

```python
def test_snapshot_has_no_password_or_cookie(tmp_path, batch_snapshot):
    snapshot_path = write_snapshot(tmp_path, batch_snapshot)
    text = snapshot_path.read_text(encoding="utf-8")
    assert "my-secret-password" not in text
    assert "session-cookie" not in text
    assert read_snapshot(snapshot_path).run_id == batch_snapshot.run_id
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_worker.py` → FAIL.
- [ ] **Step 3: Implement JSON snapshot + one-attempt worker.** Parent snapshots validated server fields/selectors at batch start; worker gets only `--snapshot`/`--server-id`/`--attempt`/`--result` paths/IDs, reads current user's vault itself; no password in args/env/JSON. Write result to temporary file+replace; close Playwright in finally.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_worker.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/run_snapshot.py src/airwave_csv/worker.py tests/test_worker.py && git commit -m "feat: add isolated worker input and result protocol"`

### Task 6: Windows 워커 프로세스 트리 안전 종료

**Files:**
- Create: `src/airwave_csv/process_control.py`
- Test: `tests/test_process_control.py`

**Interfaces:**
- Produces: `class WorkerHandle` with `poll() -> WorkerResult|None`, `terminate() -> None`; `class WorkerLauncher` with `start(snapshot_path: Path, server_id: str, attempt: int, result_path: Path) -> WorkerHandle`.
- Uses Windows `CreateProcessW(CREATE_SUSPENDED)` via ctypes, `AssignProcessToJobObject`, `ResumeThread` and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` to terminate worker plus Edge descendants without a pre-assignment race. Use `subprocess.list2cmdline(argv)` for safe argument quoting, not `shell=True`. On non-Windows, use a testable `subprocess.Popen(shell=False)` adapter. Source-run Python uses `python -m airwave_csv ...`; frozen EXE uses `sys.executable` with the internal CLI worker command.

- [ ] **Step 1: Write failing tests.** `test_worker_argv_contains_no_secret`, `test_timeout_terminates_worker_and_children_on_windows`, `test_missing_result_never_reports_success`. In Windows job, spawn synthetic worker that launches sleeping child and assert both are gone after terminate; Linux test uses fake process handle.
    **대표 검증 테스트:**

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")
def test_timeout_terminates_worker_and_children(running_worker_with_child):
    handle, worker_pid, edge_child_pid = running_worker_with_child
    handle.terminate()
    assert not process_exists(worker_pid)
    assert not process_exists(edge_child_pid)
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_process_control.py` → FAIL.
- [ ] **Step 3: Implement launcher/job object lifecycle.** Windows `ctypes` CreateProcessW returns handles for the suspended main thread and process; assign Job Object before ResumeThread, close thread handle after resuming, and close job/process handles on terminal outcome. Avoid assuming `subprocess.Popen` exposes a resumable thread handle. Allow fallback only if equivalent tested process-tree termination exists; otherwise fail safely. Do not log stdout/stderr or secrets.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_process_control.py` → PASS; Windows CI runs child cleanup test (Linux marks Windows-only).
- [ ] **Step 5: Commit.** `git add src/airwave_csv/process_control.py tests/test_process_control.py && git commit -m "feat: supervise Windows AirWave worker process trees"`

### Task 7: 최대 3대 병렬 FIFO·180초 재시도 대기열

**Files:**
- Create: `src/airwave_csv/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) BatchSummary(run_id: str, total: int, success: int, warning: int, failed: int, skipped: int, interrupted: int, exit_code: int, elapsed_s: float)`.
- Produces: `run_batch(snapshot: BatchSnapshot, *, launcher: WorkerLauncher, clock: Clock, home: Path) -> BatchSummary`.
- Clock interface: `monotonic() -> float` and `sleep(seconds: float) -> None` for deterministic fake-clock tests.
- Consumes: `WorkerHandle.poll()` and `WorkerResult.retryable`; ID-specific status updated from worker outcomes.

- [ ] **Step 1: Write failing tests.** `test_five_active_limits_max_running_to_three`, `test_three_active_start_without_wait_queue`, `test_first_attempt_D_E_precede_A_retry`, `test_A_failure_B_C_success_batch_partial`, `test_one_bad_server_fails_without_blocking_B_C`, `test_inactive_skipped_and_zero_active_exit_3`, `test_single_job_global_lock_prevents_second_batch`, `test_deadlines_12min_server_30min_batch`. Stub launcher and clock to simulate A retry_wait, D/E queued and hung workers without real sleeps; assert active slots never exceed 3. An existing A with invalid connection field or missing CSS fails only A while B/C succeed.
    **대표 검증 테스트:**

```python
def test_five_active_limits_max_running_to_three(five_server_snapshot,
                                                 fake_launcher, fake_clock, tmp_path):
    summary = run_batch(five_server_snapshot, launcher=fake_launcher,
                        clock=fake_clock, home=tmp_path)
    assert fake_launcher.max_active == 3
    assert fake_launcher.started_server_ids[:3] == [
        "airwave-01", "airwave-02", "airwave-03"
    ]
    assert summary.total == 5
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_orchestrator.py` → FAIL.
- [ ] **Step 3: Implement parent scheduler.** Use FIFO first-attempt queue plus retry-ready time min-heap; never block a slot during 180s delay, enforce per-server attempts ≤2. Validate each server for readiness without aborting other servers; global structural config failure prevents all. Take global `run.lock` only in parent; launch next eligible server when an active worker terminates. Cancel on deadlines via `WorkerHandle.terminate()`, aggregate independent results.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_orchestrator.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/orchestrator.py tests/test_orchestrator.py && git commit -m "feat: schedule up to three AirWave workers with fair retry queue"`

### Task 8: 서버별 실행 이력·중단 복구·결과 구분

**Files:**
- Modify: `src/airwave_csv/events.py`
- Modify: `src/airwave_csv/orchestrator.py` (Task 7의 완료 이벤트 연동)
- Test: `tests/test_batch_events.py`

**Interfaces:**
- Produces: `record_server_event(home: Path, *, run_id: str, server_id: str, stage: str, status: str, code: int, attempt: int=1, rows: int|None=None, filename: str|None=None) -> None`
- Produces: `write_batch_summary(home: Path, summary: BatchSummary, server_results: dict[str,WorkerResult]) -> None`; `read_last_batch(home: Path) -> dict`; `reconcile_interrupted_batch(home: Path) -> None`.
- Return codes: 0(all success), 2(partial/warning), 1(all active failed), 3(no active/invalid global config). Disabled servers SKIPPED.

- [ ] **Step 1: Write failing tests.** `test_summary_tracks_each_server`, `test_previous_crashed_batch_becomes_interrupted_not_replayed`, `test_log_whitelist_redacts_url_user_secret_and_csv_cells`, `test_exit_codes_distinguish_failure_modes`. Assert server_id/run_id in local logs; summary written atomically.
    **대표 검증 테스트:**

```python
def test_summary_tracks_each_server(tmp_path, batch_summary, server_results):
    write_batch_summary(tmp_path, batch_summary, server_results)
    result = read_last_batch(tmp_path)
    assert result["run_id"] == batch_summary.run_id
    assert set(result["servers"]) == set(server_results)
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_batch_events.py` → FAIL.
- [ ] **Step 3: Add structured event & crash recovery.** Reconciliation marks old incomplete batches INTERRUPTED on next start and does **not** retry them automatically. Retain original `record`/`last_event` for legacy tests.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_batch_events.py tests/test_engine.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/events.py src/airwave_csv/orchestrator.py tests/test_batch_events.py && git commit -m "feat: persist server-level results and recover interrupted runs"`

### Task 9: CLI/Windows 예약 하나 및 한국어 서버 관리 UI

**Files:**
- Modify: `src/airwave_csv/__main__.py`, `src/airwave_csv/scheduler.py`, `src/airwave_csv/gui.py`
- Test: `tests/test_multi_cli.py`, `tests/test_multi_gui.py`, existing `tests/test_scheduler.py`

**Interfaces:**
- CLI: `--run-all --headless` = all enabled; `--run --headless` = backwards compatible alias; `--run-one SERVER_ID` = manual one server; internal `--worker --snapshot PATH --server-id ID --attempt N --result PATH` = exactly one attempt.
- Scheduling: `register_daily(time_hhmm: str) -> None` retains Windows task name and Interactive credential context; GUI calls it after user saves.
- GUI: table view shows name, enabled, connection/CSS-ready, queued/running/retry/success/warning/failed/skipped/interrupted, rows, last download. Async subprocess launch + main-thread `after` poll only.

- [ ] **Step 1: Write failing tests.** `test_old_run_invokes_all`, `test_worker_mode_requires_compatible_flags`, `test_schedule_uses_one_existing_task`, `test_gui_add_edit_disable_delete_no_csv_deletion`, `test_gui_never_blocks_mainloop_during_batch`. Use mocks; guard against disabled server or nonexistent ID actions.
    **대표 검증 테스트:**

```python
def test_schedule_keeps_single_task(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_powershell",
                        lambda script, *, env_extra=None: calls.append(env_extra))
    scheduler.register_daily("09:05")
    assert len(calls) == 1
    assert "--run-all" in calls[0]["AW_ARGS"]
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_multi_cli.py tests/test_multi_gui.py` → FAIL.
- [ ] **Step 3: Implement CLI/GUI additions with existing tkinter.** Avoid editing `portal.py` and preserve current labels; add 5-server list and one-time server test, global execution progress. GUI does not manipulate tkinter from background workers; stop button only requests process cancellation through coordinator.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q tests/test_multi_cli.py tests/test_multi_gui.py tests/test_scheduler.py` → PASS.
- [ ] **Step 5: Commit.** `git add src/airwave_csv/__main__.py src/airwave_csv/scheduler.py src/airwave_csv/gui.py tests/test_multi_cli.py tests/test_multi_gui.py tests/test_scheduler.py && git commit -m "feat: manage and schedule multiple AirWave servers in Windows GUI"`

### Task 10: Windows EXE·모의 브라우저 통합 검증·현장 가이드

**Files:**
- Create: `tests/test_multi_airwave_e2e.py`
- Modify: `.github/workflows/windows.yml`, `README.md`, `docs/현장_연동_가이드.md`
- Optionally Modify: `build/windows_build.ps1` only if spawned frozen worker needs PyInstaller packaging adjustments.

**Interfaces:**
- Consumes: Tasks 1–9. No new product API.
- Produces: Windows CI artifact `AirWaveCsvExporter-Windows` and documented migration/rollback / real-server acceptance checklist.

- [ ] **Step 1: Write failing Windows E2E tests.** `test_three_mock_airwave_hosts_export_independently`, `test_five_servers_fifo_max_three`, `test_mock_B_failure_does_not_block_A_C_D_E`, `test_frozen_exe_worker_start_and_tree_shutdown`. Run multiple local mock HTTPS hosts or isolated fake workers where TLS mock is unnecessary; **do not disable certificate verification in production code**.
    **대표 검증 테스트:**

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows Edge CI")
def test_five_mock_servers_are_isolated(mock_five_server_batch):
    result = mock_five_server_batch()
    assert result.total == 5
    assert result.success == 5
    assert result.exit_code == 0
```

- [ ] **Step 2: Run RED.** `python -m pytest -q tests/test_multi_airwave_e2e.py` → FAIL before final wiring; Windows-only tests skip explicitly on Linux.
- [ ] **Step 3: Finish integration, docs and CI.** Windows workflow includes pytest, Ruff `--select E4,E7,E9,F`, compileall, Windows EXE build, `--help` startup, synthetic 3/5-host export, child process cleanup. README explains maximum 5, default 3, 180s retry, 15~30s wait, per-server output, v1 migration, no-login session restriction, selectors verification, local-only logs. Real AirWave 8.2.14.0 UI selectors and actual CSV completeness require operator verification.
- [ ] **Step 4: Run GREEN.** `python -m pytest -q`, `python -m ruff check src tests --select E4,E7,E9,F`; Windows CI all jobs PASS, built EXE startup check PASS and artifact exists.
- [ ] **Step 5: Commit.** `git add tests/test_multi_airwave_e2e.py .github/workflows/windows.yml README.md docs/현장_연동_가이드.md build/windows_build.ps1 && git commit -m "test/docs: validate multi-AirWave EXE and operator rollout"`

## Integration and Release Gate

1. 각 Task는 **RED → GREEN → 커밋 → 리뷰** 후 다음 작업으로 이동한다. 기존 `tests/test_engine.py`/`test_portal.py`/`test_csv_store.py`/`test_playwright_mock_ui.py`를 삭제하거나 건너뛰지 않는다.
2. Windows GitHub Actions에서 모든 테스트·EXE 빌드·프로세스 트리 종료 검증이 통과해야 한다.
3. 전체 변경의 PR을 만들어 `main`에 병합하기 전에 테스트 아티팩트, 불변 데이터 보존, credentials/CSV 비노출, 스케줄러 1개 유지 여부를 검토한다.
4. 사내 AirWave 3대 실연동은 사용자가 Windows PC에서 수행한다. DOM/CSS/인증/페이지네이션/총건수 불일치 가능성이 남아 있으며, 실제 테스트 전에는 '실서버 정상 작동'이라고 표시하지 않는다.
5. GitHub Release 또는 실제 운영 PC 배포는 별도 사용자 승인 없이는 실행하지 않는다.

## Superpowers Plan Self-Review

- **Coverage:** 설계 ``1–2`(목표/제외)→Global Constraints, `3`(코드 변경)→File Map, `4–5`(선택된 프로세스/큐)→Tasks 5–7, `6–7`(설정/CSV)→Tasks 1–3, `8–9`(재시도/예약)→Tasks 4–9, `10`(마이그레이션)→Task 2, `11–12`(GUI/로그)→Tasks 8–9, `13–14`(테스트/보안)→Review Focus/Task 10, `15–17`(게이트/빌더 체크)→Integration Gate.
- **Interface alignment:** `MultiConfig`·`ServerProfile` → `BatchSnapshot` → `WorkerResult` → `BatchSummary` 흐름, 전체 잠금은 부모만 보유. 워커는 정확히 **1회 시도**, 재시도 일정은 부모만 소유.
- **Risk checks:** Review Focus의 5개 위험 조건 각각 Task 1/2/3/6/7/8에서 명시적 테스트 지정.
- **Proportion:** 사양의 모든 프로토콜 이름·상태·시간값만 결정; 실제 함수 본문과 테스트 전체 구현은 실행 단계에 남겨둠.
- **Ready for execution:** **사용자의 본 구현 계획 검토 및 실행 방식 선택 대기.** 현재 문서는 구현 지시서이며 기능 코드가 아님.
