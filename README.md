# Aruba AirWave CSV Exporter — Multi-AirWave v2

**Windows 11 EXE / Aruba AirWave 8.2.14.0 / Python 설치 없이 실행**

현재 AirWave 3대와 향후 최대 5대를 등록하고, 기본 **3개 독립 워커**가 동시에 CSV를 수집합니다. 추가 서버는 **FIFO 대기열**에서 기다립니다. 한 서버가 실패해도 나머지 서버는 계속 진행합니다.

> **실운영 검증 미완료:** 개발자/CI 환경에서는 사내 AirWave 장비에 접속하지 않았습니다. 각 AirWave 8.2.14.0 실제 DOM에 맞춘 CSS 선택자가 없으면 다운로드를 안전하게 차단합니다.

## 자동 수집 순서

1. 서버별 로그인 후 **Devices → List**
2. **Default View = Devices** (Default Expansion과 다른 항목)
3. 필터 해제, **Top** 폴더 선택
4. **Expand folders to show all devices** 실행
5. 최소 **15초**, 최대 **30초** 대기하며 전체 장비 건수와 로딩 확인
6. 다운로드 직전 보기/폴더/필터/확장/건수를 다시 검증
7. **Export as CSV**, 전체 행 수와 화면 건수 대조 후 저장

## Windows EXE 사용

1. GitHub Actions의 성공한 **Windows tests and EXE build** 실행을 열고 Artifacts에서 **AirWaveCsvExporter-Windows** ZIP을 다운로드합니다.
2. 압축 파일의 **폴더 전체**를 풀고 AirWaveCsvExporter.exe를 실행합니다. 대상 PC에 Microsoft Edge 및 정상적인 사내 HTTPS 인증서가 필요합니다.
3. 서버 이름, HTTPS 주소, 로그인 ID, 비밀번호 입력 후 **서버 추가**. 총 5대까지 등록 가능합니다.
4. 서버 선택 후 **선택자 파일 열기**를 눌러 실제 AirWave 화면에서 확인한 CSS를 입력합니다. 서버별로 별도의 CSS 파일을 사용합니다.
5. **선택 서버 테스트**로 실제 CSV/장비 수를 검증한 후 **전체 지금 실행**을 확인합니다.
6. 실행 시각과 동시 실행 수(기본 3)를 저장하고 **예약 등록/변경**을 누릅니다.

비밀번호는 Windows Credential Manager에만 저장합니다. 회사의 MFA/SSO/CAPTCHA를 우회하지 않습니다. Windows 예약은 **현재 로그인한 계정**으로 실행되며, 로그오프/전원 꺼짐 상태의 수집은 보장되지 않습니다.

## 병렬 실행 및 재시도

| 설정 | 기본값 |
| --- | --- |
| 최대 서버 등록 | 5대 |
| 기본 병렬 수 | 3대 (설정 범위 1~5대) |
| 대기열 | 미실행 서버 우선 FIFO |
| 일시 오류 재시도 | 기본 180초 후, 최대 2회 시도 |
| 재시도 대기 중 | 실행 슬롯 미점유 |
| 전체 폴더 확장 후 대기 | 15~30초 |
| 서버 작업 제한 | 12분 |
| 배치 작업 제한 | 30분 |
| 장비 수 급감 경고 | 서버별 최신본 대비 10% 이상 감소 |

서버 A/B/C가 시작되고 D/E는 대기합니다. A가 완료되거나 실패해 슬롯이 비면 D를 먼저 실행합니다. A가 180초 재시도를 기다려도 D/E가 먼저 실행됩니다.

## CSV 저장 위치 (예시)

    C:\AirWaveCSV\
      airwave-01\
        latest.csv
        AirWave_Devices_YYYYMMDD_HHMMSS_microseconds.csv
      airwave-02\
        latest.csv
        AirWave_Devices_YYYYMMDD_HHMMSS_microseconds.csv

같은 서버의 이전 정상본에 비해 장비 수가 10% 이상 감소하면 경고 후 그 서버의 latest.csv를 갱신하지 않습니다. 서버 이름 수정/등록 삭제로 이전 CSV를 지우지 않습니다.

## v1 설정에서 업그레이드

기존 config.json은 변경하지 않고 config.v1.backup.json을 복사해 보존합니다. 새 multi_config.json을 생성하면서 첫 번째 서버를 airwave-01로 등록하고, 기존 selectors.json을 selectors/airwave-01.json으로 복사합니다. 기존 CSV 및 latest.csv는 유지하고, 신규 버전은 서버 ID별 하위 폴더에 데이터를 저장합니다. 기존 작업 스케줄러 작업 1개를 유지하며 이전 --run 명령도 전체 수집에 대응합니다.

## 로컬 설정/로그

    %LOCALAPPDATA%\AirWaveCsvExporter\
      multi_config.json
      selectors\airwave-01.json
      selectors\airwave-02.json
      logs\YYYY-MM-DD.jsonl
      state\last_batch.json
      state\progress.json
      runs\<run-id>\snapshot.json

**실서버 URL, 운영 계정, 쿠키, 비밀번호, 실제 CSV, 장비 IP/MAC을 공개 GitHub에 업로드하지 마세요.** 로컬 파일은 회사 정책에 맞춰 관리하세요.

## 개발자 테스트

    python -m pip install -e ".[test,build]"
    python -m pytest -q
    python -m ruff check src tests --select E4,E7,E9,F
    powershell -ExecutionPolicy RemoteSigned -File build/windows_build.ps1

실제 AirWave 웹 DOM/인증 및 CSV 완전성은 CI 모의 테스트와 별개의 현장 인수 항목입니다.

설계/작업계획:
- docs/superpowers/specs/2026-10-29-multi-airwave-export-design.md
- docs/superpowers/plans/2026-10-29-multi-airwave-export-implementation.md

Aruba/HPE 공식 배포 프로그램은 아닙니다.
