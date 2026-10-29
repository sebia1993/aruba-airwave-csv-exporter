# 2차 안정성 검증 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Maintain TDD RED→GREEN and review.

**Goal:** 다중 AirWave 수집기의 기능을 바꾸지 않고 운영 코드의 실제 프로세스 장해 격리, GUI 상태 유지, CI 재현성을 검증한다.

**Architecture:** 기존 `tests/support` 모의 워커/하네스에만 결함 주입 데이터를 추가하고, 운영 `run_batch`·`WorkerLauncher`·GUI 코드의 공개 동작은 건드리지 않는다. Windows의 실제 Tk 및 CI 의존성 고정은 테스트/워크플로 전용이다.

**Tech Stack:** Windows 11 CI Python 3.12, pytest, psutil, tkinter, GitHub Actions, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-29-chaos-gui-repro-design.md`

## Global Constraints

- 사용자 기능/버튼/CLI/CSV/예약/로그인 동작 변경 금지.
- 모의 장애 환경 변수는 `tests/support/synthetic_worker.py` 내부에서만 읽는다.
- 최소 3개/최대 5개 작업, 기본 3대 병렬·FIFO, 기존 2분 CI 소크 동작 보존.
- 회사 URL·계정·CSV·스크린샷·비밀번호를 CI 아티팩트에 남기지 않는다.
- GitHub-hosted 6시간 제한으로 8시간(480분) 검증 완료를 주장하지 않는다.

## Review Focus

- 워커 프로세스가 결과 JSON 없이 죽으면 오류 코드 98로 간주하고 B~E 서버 진행, 배치 잠금 정리.
- 가짜 워커가 완료 코드 0을 내도 결과 JSON이 손상되면 성공으로 판정하면 안 됨.
- CSV가 손상됐거나 쓰기 예외가 나면 이전 `latest.csv`는 보존하고 정상 서버 최신본은 갱신해야 함.
- 실제 Tk Treeview와 Entry에서 refresh 반복 중 선택/미저장 입력값이 바뀌지 않고 타이머가 중복되지 않음.
- CI 직접 의존성 버전이 수시 변경되더라도 테스트 결과 재현 및 설치 버전 기록 가능해야 함.

---

### Task 1: 실제 OS 워커 결함 주입

**Files:**
- Modify: `tests/support/synthetic_worker.py`
- Modify: `tests/support/process_harness.py`
- Create: `tests/test_fault_injection_process_pool.py`

**Interfaces:** `run_synthetic_batch(..., crash_server: str|None=None, corrupt_result_server: str|None=None, corrupt_csv_server: str|None=None, write_failure_server: str|None=None)` remains test-only.

- [ ] **Step 1 — RED:** Write `test_abrupt_worker_exit_is_isolated`, `test_corrupt_worker_result_is_fail_closed`, `test_corrupt_csv_preserves_last_good`, `test_injected_write_error_preserves_successful_peers`. Assertions: 4 success/1 failed for 5; failed server error code 98; others' `latest.csv` exist; no active marker; max_concurrent ≤3; old latest preserved.
- [ ] **Step 2 — RED command:** `python -m pytest -q tests/test_fault_injection_process_pool.py` must fail on missing fault args.
- [ ] **Step 3 — GREEN:** Implement isolated test-only env modes; worker crashes before writing timeline/result, corrupt worker-result writes an invalid JSON result, corrupt CSV and write-error paths leave `latest.csv` unchanged.
- [ ] **Step 4 — GREEN command:** `python -m pytest -q tests/test_fault_injection_process_pool.py tests/test_process_pool_integration.py` pass on Windows and Linux; full CI pass.
- [ ] **Step 5 — Commit:** `test(stability): inject isolated OS worker failures without production changes`.

### Task 2: Windows 실제 Tk GUI 자동 검증

**Files:**
- Create: `tests/test_windows_tk_gui_e2e.py`

**Interfaces:** Existing `ExporterWindow`, `migrate_if_needed`, and `save_v2`; no product API changes.

- [ ] **Step 1 — Test:** Windows-only `test_tk_keeps_form_fields_selected_during_periodic_refresh` (real Treeview + Entry), `test_tk_keeps_one_timer_across_manual_refresh` using temporary `AIRWAVE_CSV_HOME`; skip only on non-Windows.
- [ ] **Step 2 — Run:** `python -m pytest -q tests/test_windows_tk_gui_e2e.py` on Windows; Linux skip.
- [ ] **Step 3 — GREEN:** Any defect found uses regression test first, minimal internal GUI fix; otherwise no product changes.
- [ ] **Step 4 — Commit:** `test(stability): exercise real Windows tkinter form state`.

### Task 3: CI reproducibility and provenance

**Files:**
- Create: `ci/constraints-py312.txt`
- Modify: `.github/workflows/windows.yml`
- Create: `tests/test_ci_constraints.py`
- Modify: `README.md` (only developer test instructions)

**Interfaces:** CI installs `python -m pip install -c ci/constraints-py312.txt ".[test,build]"` on Windows and corresponding `".[test]"` on Linux; `pip freeze` artifact includes no credentials or operational data.

- [ ] **Step 1 — RED:** Write `test_ci_constraints_cover_all_direct_deps` and `test_workflow_installs_with_constraints` to enforce pinned values. Run pytest and confirm failure before writing constraints.
- [ ] **Step 2 — GREEN:** Pin verified Python 3.12 versions of playwright/keyring/psutil/pytest/ruff/pyinstaller (and compatible transitive dependencies) in CI only, not pyproject runtime.
- [ ] **Step 3 — GREEN:** Linux & Windows CI package install, full tests, EXE build, frozen worker smoke, 2-min soak, and dependency-provenance artifact must succeed.
- [ ] **Step 4 — Commit:** `ci: pin tested Python 3.12 build environment and record provenance`.

## Final review

Compare PR to main before merge. Verify production `src/` and PyInstaller launcher unchanged unless red test exposed a pre-existing stability bug. Document any deferred risk and real AirWave access limitations.
