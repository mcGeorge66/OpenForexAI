$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-Not (Test-Path '.\.venv\Scripts\python.exe')) {
  Write-Host 'Missing .venv. Run scripts/setup_windows.ps1 first.' -ForegroundColor Red
  exit 1
}
& .\.venv\Scripts\python.exe tools\openforexai-start.py
