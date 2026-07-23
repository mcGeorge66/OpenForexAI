from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env'
WRAPPER = ROOT / 'tools' / 'openforexai-wrapper.py'
VENV_PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main() -> int:
    os.chdir(ROOT)
    _load_env(ENV_FILE)
    if not VENV_PYTHON.exists():
        print(f'Missing .venv ({VENV_PYTHON}). Run scripts/setup_windows.ps1 first.', file=sys.stderr)
        return 1
    try:
        return subprocess.call([str(VENV_PYTHON), str(WRAPPER)], cwd=ROOT, env=os.environ.copy())
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
