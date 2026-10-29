# 워커 프로세스 E2E 및 장시간 안정성 구현계획

**Goal:** 실제 운영 코드 변경 없이 3~5개 워커 프로세스의 큐·CSV 분리·실패를 검증하고 반복 안정성/누수 측정을 CI에 추가.

**Spec:** `docs/superpowers/specs/2026-10-29-real-worker-soak-design.md`.

## 파일 책임

| File | 책임 |
|--|--|
| `tests/support/synthetic_worker.py` | 테스트 전용 워커(프로세스, 독립 파일, 모의 실패/재시도) |
| `tests/support/process_harness.py` | 실제 WorkerLauncher 실행·활성 슬롯 계측·검증 |
| `tests/test_process_pool_integration.py` | 3·5개 OS 워커 동시 실행·FIFO·독립 CSV·재시도 회귀 |
| `tests/support/frozen_worker_smoke.py` | Windows 빌드 EXE 실제 `--worker` 3·5개 fail-closed 기동 |
| `tests/support/soak_process_pool.py` | 반복 실행, pid/핸들·RSS 변화·CSV 무결성 집계 및 JSON 보고 |
| `.github/workflows/windows.yml` | PR/푸시에서 빠른 워커 검증·2분 소크 테스트·아티팩트 생성 |
| `.github/workflows/windows-soak.yml` | 수동 5·30·120·240분 소크 실행, 결과 업로드 |
| `README.md`, `docs/현장_연동_가이드.md` | 시험 방법·현장 검증 제외 범위 기록 |

## 작업 순서

### Task 1: 독립 프로세스 모의 워커 검증
- [ ] 실패/재시도/경쟁/CSV 교차 파일명을 검증하는 테스트 정의(RED).
- [ ] 테스트 전용 워커와 계측 래퍼 구현. 실제 `run_batch` 및 `WorkerLauncher`를 수정 없이 사용.
- [ ] Linux, Windows `pytest` GREEN, 기존 5대 제한·FIFO·CSV 원본 보호 테스트 GREEN.
- [ ] 커밋.

### Task 2: Windows EXE 3·5개 실행 경로
- [ ] 패키징된 동일 EXE를 실제 작업 워커로 실행하는 fail-closed 검증 작성.
- [ ] `--worker` 결과 오류 44, 빈 CSV 출력, 3개 슬롯 제한, 5개 완료 증명. 실제 장비 로그인 우회 금지.
- [ ] Windows EXE CI 빌드 후 검사, 실패 시 문제 원인 분석 및 제품 코드 최소 수정(테스트 먼저).
- [ ] 커밋.

### Task 3: 장시간·자원 누수 및 CI
- [ ] 수집 반복 실행 및 안정성 누수 검사(순간 활성 프로세스 수/종료된 PID/메모리/핸들) 작성.
- [ ] 실행 지속시간 상한과 누수 경고 기준/예외 처리를 명령행 인자로 제공(테스트 전용).
- [ ] 일반 CI 2분, 수동 Windows CI 5/30/120/240분, 현장 Windows 로컬 480분 지원.
- [ ] 결과 JSON 아티팩트로 보존(실서버·실계정·장비 데이터 불포함).
- [ ] 기존 파일 보존/보안/코드 품질·리뷰·전체 CI GREEN 후 PR 제출.
