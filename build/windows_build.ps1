$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m pip install --upgrade pip
python -m pip install ".[build]"
python -m PyInstaller --noconfirm --clean --onedir --windowed --name AirWaveCsvExporter `
    --collect-all playwright --collect-submodules keyring `
    launcher.py
Write-Host "빌드 완료: dist\AirWaveCsvExporter\AirWaveCsvExporter.exe"
