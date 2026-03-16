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


def _spawn_app() -> subprocess.Popen:
    env = dict(os.environ)
    env["OPENFOREXAI_WRAPPED"] = "1"
    env["OPENFOREXAI_RESTART_SIGNAL_PATH"] = str(RESTART_FLAG)
    return subprocess.Popen([sys.executable, "-m", "openforexai.main"], cwd=ROOT, env=env)


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[wrapper] root={ROOT}")
    print(f"[wrapper] restart flag={RESTART_FLAG}")

    while True:
        if RESTART_FLAG.exists():
            RESTART_FLAG.unlink(missing_ok=True)

        proc = _spawn_app()
        print(f"[wrapper] started pid={proc.pid}")

        restart_requested = False
        try:
            while True:
                code = proc.poll()
                if code is not None:
                    break
                if RESTART_FLAG.exists():
                    restart_requested = True
                    print("[wrapper] restart requested — stopping child")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
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

        if restart_requested:
            RESTART_FLAG.unlink(missing_ok=True)
            print("[wrapper] restarting OpenForexAI...")
            continue

        exit_code = proc.returncode or 0
        print(f"[wrapper] child exited with code {exit_code}")
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
