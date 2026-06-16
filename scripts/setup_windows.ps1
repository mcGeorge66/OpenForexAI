param()

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Write-Host 'OpenForexAI Windows Setup' -ForegroundColor Cyan
Write-Host "Root: $root"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'python not found in PATH' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git not found in PATH' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm not found in PATH' }

if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[all]"
& .\.venv\Scripts\python.exe -m pip install rich questionary

npm install --prefix ui
npm run build --prefix ui

& .\.venv\Scripts\python.exe scripts\initial_setup.py --platform windows
