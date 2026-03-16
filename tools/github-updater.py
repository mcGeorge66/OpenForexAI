#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import json5
import requests
from packaging.version import InvalidVersion, Version

REPO = "mcGeorge66/OpenForexAI"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "config.default.json5"


def get_local_version() -> str:
    config = json5.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    return str(config["system"]["version"])


def get_remote_version() -> str | None:
    try:
        res = requests.get(
            f"https://api.github.com/repos/{REPO}/releases",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if res.status_code != 200:
            return None
        releases = res.json()
        if not isinstance(releases, list) or not releases:
            return None

        candidates: list[tuple[Version, str]] = []
        for rel in releases:
            if not isinstance(rel, dict):
                continue
            if rel.get("draft"):
                continue
            tag_name = str(rel.get("tag_name", "")).strip()
            if not tag_name:
                continue
            normalized = tag_name[1:] if tag_name[:1].lower() == "v" else tag_name
            try:
                parsed = Version(normalized)
            except InvalidVersion:
                continue
            candidates.append((parsed, normalized))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[-1][1]
    except Exception:
        return None


def install_update() -> None:
    print("Pulling latest code from GitHub...")
    subprocess.run(["git", "pull"], check=True, cwd=BASE_DIR)

    print("Installing Python dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[all]"],
        check=True,
        cwd=BASE_DIR,
    )

    print("Installing Node dependencies and building UI...")
    subprocess.run(["npm", "install", "--prefix", "ui"], check=True, cwd=BASE_DIR)
    subprocess.run(["npm", "run", "build", "--prefix", "ui"], check=True, cwd=BASE_DIR)

    print("\nUpdate complete. Please restart the application.")


def main() -> None:
    print("OpenForexAI GitHub Updater")
    print("==========================")

    local = get_local_version()
    print(f"Local version:  {local}")

    remote = get_remote_version()
    if remote is None:
        print("Error: GitHub unreachable or no valid releases found.")
        sys.exit(1)

    print(f"Latest version: {remote} (includes prereleases)")

    if Version(remote) > Version(local):
        print(f"\nUpdate available: {local} -> {remote}")
        answer = input("Update now? (y/n): ")
        if answer.lower() == "y":
            install_update()
        else:
            print("Update cancelled.")
    else:
        print("\nAlready up to date.")


if __name__ == "__main__":
    main()
