# Aruba AirWave CSV Exporter

Windows 11용 Aruba AirWave 8.2.14.0 장비 목록 CSV 자동 백업 프로그램 개발 저장소입니다.

> 개발 중: 실제 AirWave 웹 UI의 DOM과 사내 인증 방식은 아직 현장 검증되지 않았습니다. 안전을 위해 필수 선택자 또는 검증 정보가 없는 상태에서는 CSV 다운로드를 실행하지 않습니다.

최종 요구사항은 `Devices > List`, `Default View = Devices`, `Top` 폴더 및 하위 폴더 확장, **15~30초** 화면 표시 대기, `Export as CSV`입니다.

실행 코드는 `feat/initial-windows-exporter` 브랜치에서 개발합니다.
