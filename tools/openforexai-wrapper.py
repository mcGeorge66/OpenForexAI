#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / ".runtime"
RESTART_FLAG = RUNTIME_DIR / "restart.requested"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _spawn_app() -> subprocess.Popen:
    env = dict(os.environ)
    env["OPENFOREXAI_WRAPPED"] = "1"
    env["OPENFOREXAI_RESTART_SIGNAL_PATH"] = str(RESTART_FLAG)
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    return subprocess.Popen([python, "-m", "openforexai.main"], cwd=ROOT, env=env)


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[wrapper] root={ROOT}")
    print(f"[wrapper] restart flag={RESTART_FLAG}")
    if not VENV_PYTHON.exists():
        print(f"[wrapper] WARNING: .venv not found at {VENV_PYTHON}, falling back to {sys.executable}")

    while True:
        if RESTART_FLAG.exists():
            RESTART_FLAG.unlink(missing_ok=True)

        proc = _spawn_app()
        print(f"[wrapper] started pid={proc.pid}")

        restart_requested = False
        try:
            while True:
                if RESTART_FLAG.exists():
                    restart_requested = True
                    print("[wrapper] restart requested — stopping child")
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
                    break
                code = proc.poll()
                if code is not None:
                    break
                time.sleep(0.6)
        except KeyboardInterrupt:
            print("[wrapper] Ctrl+C — stopping child")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 0

        if restart_requested or RESTART_FLAG.exists():
            RESTART_FLAG.unlink(missing_ok=True)
            print("[wrapper] restarting OpenForexAI...")
            continue

        exit_code = proc.returncode or 0
        print(f"[wrapper] child exited with code {exit_code}")
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

