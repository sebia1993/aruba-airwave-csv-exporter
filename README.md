# Aruba AirWave CSV Exporter

Windows 11에서 Aruba AirWave 8.2.14.0의 Devices List 장비 목록을
매일 지정 시간에 CSV로 내보내는 GUI / EXE 프로그램입니다.

**개발 상태:** 소스와 모의 테스트를 구현했지만 사내 AirWave 웹 UI에서
실제 장비 다운로드는 아직 검증하지 않았습니다.

## 다운로드 전 필수 조건

1. AirWave 접속 및 Devices > List 화면으로 이동
2. Devices List의 Default View가 정확히 **Devices**인지 확인/변경
3. 상태/검색 필터 해제, **Top** 폴더 선택
4. **Expand folders to show all devices** 실행
5. 확장 후 **최소 15초, 최대 30초** 대기하고 로딩 완료/총건수 확인
6. Default View = Devices, Top, 필터 없음, 확장 상태를 **다운로드 직전 재검증**
7. Export as CSV, CSV 전체 행 수와 화면 총건수 비교
8. 검증 성공 시 날짜별 CSV 및 latest.csv 저장. 이상 급감 시 latest.csv 보존

현장 DOM/CSS를 알 수 없는 상태에서는 잘못된 목록을 내보내지 않도록
필수 CSS 선택자를 미설정 상태로 두고 **안전하게 실패(종료코드 44)**합니다.
처음 실행하면 %LOCALAPPDATA%\AirWaveCsvExporter\selectors.json 파일이 생성됩니다.
자세한 순서는 [현장 연동 가이드](docs/현장_연동_가이드.md)를 참고하세요.

## 설치 및 실행

**일반 사용자 (Windows 11):**

1. GitHub Actions의 성공한 "Windows tests and EXE build" 실행을 엽니다.
2. Artifacts 항목에서 AirWaveCsvExporter-Windows ZIP을 받습니다.
3. ZIP의 전체 폴더를 PC에 압축 해제합니다. exe 파일만 따로 꺼내지 마세요.
4. AirWaveCsvExporter.exe를 실행합니다.
5. HTTPS 주소 / 사용자 ID / 비밀번호 / CSV 저장 폴더 / 시간 입력 후 설정 저장.
   비밀번호는 Windows Credential Manager에 저장됩니다.
6. 현장 검증한 CSS 선택자를 selectors.json에 입력합니다.
7. **지금 테스트**로 실서버의 다운로드와 CSV 건수를 수동 검증합니다.
8. 성공하면 **매일 예약 등록/변경** 버튼으로 Windows 작업을 등록합니다.

**개발자:**

    python -m pip install -e ".[test,build]"
    python -m pytest -q
    python -m airwave_csv
    powershell -ExecutionPolicy RemoteSigned -File build/windows_build.ps1

배포 파일은 Windows에서만 빌드합니다. 대상 Windows PC에 Microsoft Edge가
설치되어 있어야 합니다. Python 설치는 필요 없습니다. 64비트 Windows 11을
대상으로 합니다. 별도의 AirWave 서비스/API 자격증명이나 브라우저 보안
우회 기능은 사용하지 않습니다.

## 파일과 보안

- 설정: %LOCALAPPDATA%\AirWaveCsvExporter\config.json (비밀번호 없음)
- 현장 CSS: %LOCALAPPDATA%\AirWaveCsvExporter\selectors.json
- CSV: 설정한 저장 폴더 / latest.csv / 날짜별 AirWave_Devices_*.csv
- 실행 로그: %LOCALAPPDATA%\AirWaveCsvExporter\logs\YYYY-MM-DD.jsonl
- Windows 작업명: AirWave CSV Exporter - Daily
- 예약 실행: AirWaveCsvExporter.exe --run --headless

CSV에는 조직 내부 자산정보가 포함될 수 있습니다. CSV, 실제 서버 주소,
쿠키, 비밀번호, 사내 설정 파일을 공개 GitHub에 올리지 마세요. 스크린샷
또는 원격 오류 데이터는 자동 업로드되지 않습니다.

**Windows 작업 스케줄러 기본 등록은 사용자가 Windows에 로그인된 경우에
실행됩니다.** PC 전원 꺼짐/로그오프 상태 자동 동작은 보장하지 않습니다.
사내 정책 허용 범위에서 현장 검증이 필요합니다.

## 개발 범위 및 한계

* 최신 정상본만 자동 갱신합니다. 10% 이상 장비 수 감소 시 날짜별 파일만
  남기고 최신본을 보존하며 경고 상태(종료코드 2)를 기록합니다.
* Empty CSV / 다운로드 오류는 기본 180초 뒤 한 번 재시도합니다.
* 실제 DOM, 로그인, 내보내기 버튼, 페이지네이션별 CSV 포함 범위는
  실서버를 연결해야만 확인할 수 있습니다.
* 하위 폴더 확장과 표시 총건수만으로 권한 밖 장비까지 포함된다고
  보장하지 않습니다. 허용된 계정의 가시 범위만 수집합니다.
* 외부 알림, 네트워크 장비 변경, 릴리즈 자동 배포는 포함하지 않습니다.

본 프로젝트는 Aruba / HPE의 공식 도구가 아닌 독립적인 자동화 프로그램입니다.
