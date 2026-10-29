# AirWave 기능 동결 안정화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) task-by-task. Each task follows test RED → minimal code GREEN → regression verification → commit.

**Goal:** 기존 사용자 기능을 변경하지 않고 GUI/설정/실행 복구/프로세스/대용량 CSV의 안정성을 보강한다.

**Architecture:** 기능 모듈을 그대로 두고 GUI 트랜잭션·갱신/실행 이력·작업 종료·CSV 읽기를 작은 내부 변경으로 개선한다. 신규 사용자 기능, API 경로, 파일명, 예약 방식, 옵션 기본값은 추가/변경/삭제하지 않는다.

**Tech Stack:** 기존 Python>=3.11, tkinter, Windows Task Scheduler, Playwright, PyInstaller, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-feature-freeze-hardening.md`

## Global Constraints

- 현재 main `e5cdd090ea60822375abb044ea343fef7cb91e38` 기준 기능을 유지한다.
- AirWave 5대 등록, 기본 3개 동시/나머지 FIFO, 15~30초 전체 목록 대기, 기본 180초 재시도(최대 2회)는 변경하지 않는다.
- 파일명·CSV 열·UI 버튼·한국어 문구·Windows 예약 작업 이름·CLI 인수·Credential Manager 유지.
- 보안 변경으로 URL 변경 시 비밀번호 재입력을 요구하는 등의 **사용자 계약 변경 금지**.
- 실서버 검증 제외; Windows/Linux CI 및 Windows EXE smoke 포함.

## Review Focus

- GUI 저장 실패: 메모리 설정과 디스크가 이전 정상 상태 그대로 남고 비밀번호가 변경되지 않는지.
- GUI refresh: 2초 주기에도 서버 선택과 편집 입력이 덮이지 않고 예약 체크 작업이 1개만 실행되는지.
- 불완전 배치: 활성 배치가 실제 실행 중이면 그대로, 종료 후 재시작한 구배치는 INTERRUPTED; 기록 쓰기 실패 시 마커 보존.
- Windows Job Object: 워커·Edge 자식 프로세스 종료 확인 및 핸들 정리, 비정상 종료 시 기존 CSV 보호.
- 수십 MB CSV: 인코딩·quoted multiline·행 수·열 수·HTML 차단 결과 동일, 전체 바이트 메모리 적재 금지.

---

### Task 1: 설정 트랜잭션과 GUI 상태

**Files:** Modify `src/airwave_csv/gui.py`, `src/airwave_csv/gui_model.py`; Add `tests/test_gui_stability.py`.

**Interfaces:** `ExporterWindow.save()`/ `add()` / `edit()` / `delete()` 유지; 내부 후보 설정 복사 및 commit / rollback 도입. `refresh()`는 단일 after 타이머 보장 및 Treeview 현재 선택이 바뀌지 않을 때 selection_set 호출 생략.

- [ ] Write failing tests `test_failed_save_does_not_mutate_in_memory_config`, `test_edit_failure_rolls_back_config`, `test_no_duplicate_refresh_timer`, `test_refresh_preserves_unsaved_form_fields`.
- [ ] RED: `python -m pytest -q tests/test_gui_stability.py` expected failures.
- [ ] Implement smallest internal transaction and efficient list sync, no new controls or labels.
- [ ] GREEN: new tests + `tests/test_multi_gui.py`, `tests/test_multi_config.py` pass.
- [ ] Commit `fix: keep GUI configuration and refresh state consistent`.

### Task 2: 중단 복구와 GUI 무중단 스케줄 조회

**Files:** Modify `src/airwave_csv/events.py`, `src/airwave_csv/gui.py`; Add `tests/test_event_stability.py`.

**Interfaces:** `reconcile_interrupted_batch(home)`, `read_last_batch(home)`, `ExporterWindow.refresh()` 유지; 유휴상태 복구와 비동기 스케줄 조회 내부 함수 추가.

- [ ] Write failing tests `test_interrupted_marker_kept_when_summary_write_fails`, `test_corrupt_batch_json_is_nonfatal`, `test_skip_reconcile_if_batch_running`, `test_scheduler_status_cannot_block_gui_thread`.
- [ ] RED via `python -m pytest -q tests/test_event_stability.py`.
- [ ] Implement recover-if-idle with existing run.lock; exception-safe last_batch read; thread-safe queue/after integration for scheduler state, same 60s refresh interval.
- [ ] GREEN new tests + `tests/test_batch_events.py`, `tests/test_scheduler.py`.
- [ ] Commit `fix: recover interrupted runs without blocking GUI`.

### Task 3: Windows 작업 프로세스 종료 확인

**Files:** Modify `src/airwave_csv/process_control.py`; Add `tests/test_worker_termination_stability.py`; Update `tests/test_windows_job_object.py` only if needed.

- [ ] Add Windows-only test asserting worker and child have terminated immediately after `terminate()` returns, preserving existing Job Object behavior.
- [ ] RED: Windows CI test confirms old behavior gap or new mock WinAPI failure.
- [ ] Implement `WaitForSingleObject` with bounded wait and correct handle lifetime. Preserve no new CLI/timeout defaults.
- [ ] GREEN Windows CI + existing process-control tests.
- [ ] Commit `fix: confirm Windows worker termination before releasing handles`.

### Task 4: 대용량 CSV 검증 메모리 안정화

**Files:** Modify `src/airwave_csv/csv_store.py`; Add `tests/test_csv_streaming.py`.

- [ ] RED tests: reject `Path.read_bytes` by monkeypatch, parse large rows with unchanged count, preserve UTF-8 BOM/CP949/UTF-16 BOM/quoted multiline and invalid HTML behavior.
- [ ] GREEN implement streaming decoder and CSV parse with UTF-8/CP949 fallback, no change in accepted formats/columns or saved bytes.
- [ ] GREEN `tests/test_csv_store.py`, `tests/test_csv_streaming.py`.
- [ ] Commit `perf: bound CSV verification memory without changing format`.

### Task 5: repo 유출 예방·통합 검증

**Files:** Modify `.gitignore`; Add `tests/test_ignore_rules.py` (if useful); Optionally strengthen existing Windows tests without functional change. Update `README.md` with stability-only scope if needed.

- [ ] RED test that multi_config.json, server CSS/로그/실행 스냅샷 paths are ignored using `git check-ignore` or pattern test.
- [ ] Implement gitignore patterns (avoid excluding source code/tests/documents).
- [ ] GREEN baseline full suite `python -m pytest -q`, `python -m ruff check src tests --select E4,E7,E9,F`.
- [ ] Windows GitHub Actions: package EXE, smoke test, mock browser tests, worker process tree tests all green.
- [ ] Commit `chore: prevent local AirWave operational data from entering GitHub`.

## Final review gate

- diff against `e5cdd090` and replay existing tests for no default changes.
- Important/Critical findings get RED→GREEN fix pass; otherwise do not invent features.
- PR for user review; do not create GitHub Release or run real AirWave devices.
