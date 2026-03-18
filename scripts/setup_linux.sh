#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "OpenForexAI Linux Setup"
echo "Root: $ROOT_DIR"

command -v python >/dev/null 2>&1 || { echo "python not found in PATH"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "git not found in PATH"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm not found in PATH"; exit 1; }

if [[ ! -f .venv/bin/python ]]; then
  python -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[all]"
.venv/bin/python -m pip install rich questionary

npm install --prefix ui
npm run build --prefix ui

.venv/bin/python scripts/initial_setup.py --platform linux
