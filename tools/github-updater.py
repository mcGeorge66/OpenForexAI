#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import json5

REPO = "mcGeorge66/OpenForexAI"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "config.default.json5"


def _resolve_npm_command() -> str | None:
    candidates = ["npm.cmd", "npm", "npm.exe"] if os.name == "nt" else ["npm"]
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return None


def _parse_version(value: str) -> tuple[int, int, int, int, int] | None:
    raw = value.strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]

    stage = "final"
    stage_num = 0

    for marker in ("-alpha", "-beta", "-rc", "-dev", "-post", "_alpha", "_beta", "_rc", "_dev", "_post"):
        if marker in raw:
            head, tail = raw.split(marker, 1)
            raw = head
            stage = marker.strip("-_")
            stage_num = int(tail or "0") if (tail or "0").isdigit() else 0
            break

    parts = raw.split(".")
    if len(parts) < 2 or len(parts) > 3:
        return None
    if not all(p.isdigit() for p in parts):
        return None

    major = int(parts[0])
    minor = int(parts[1])
    patch = int(parts[2]) if len(parts) == 3 else 0

    order = {
        "dev": -3,
        "alpha": -2,
        "beta": -1,
        "rc": 0,
        "final": 1,
        "post": 2,
    }
    if stage not in order:
        return None
    return (major, minor, patch, order[stage], stage_num)


def _download_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status != 200:
                return None
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, PermissionError):
        return None


def _read_default_version_safe() -> str | None:
    try:
        cfg = json5.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8-sig"))
        ver = cfg.get("system", {}).get("version")
        return str(ver) if ver is not None else None
    except Exception:
        return None


def get_local_version() -> str:
    version = _read_default_version_safe()
    if version is None:
        raise RuntimeError(f"Could not read local version from {DEFAULT_CONFIG_PATH}")
    return version


def get_remote_version() -> str | None:
    body = _download_text(f"https://api.github.com/repos/{REPO}/releases")
    if body is None:
        return None

    try:
        releases = json.loads(body)
    except json.JSONDecodeError:
        return None

    if not isinstance(releases, list) or not releases:
        return None

    best: tuple[tuple[int, int, int, int, int], str] | None = None
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        if rel.get("draft"):
            continue
        tag_name = str(rel.get("tag_name", "")).strip()
        if not tag_name:
            continue
        parsed = _parse_version(tag_name)
        if parsed is None:
            continue
        normalized = tag_name[1:] if tag_name.lower().startswith("v") else tag_name
        if best is None or parsed > best[0]:
            best = (parsed, normalized)

    return best[1] if best else None


def _is_preserved(rel: Path) -> bool:
    rel_posix = rel.as_posix()
    if rel_posix == "config/system.json5":
        return True
    if rel_posix.startswith("config/modules/"):
        return True
    if rel_posix.startswith("config/RunTime/"):
        return True
    if rel_posix.startswith("data/"):
        return True
    if rel_posix.startswith("logs/"):
        return True
    if rel_posix.startswith(".venv/"):
        return True
    return False


def _copy_release_tree(src_root: Path, dst_root: Path) -> tuple[int, int, bool]:
    copied = 0
    skipped = 0
    replaced_default = False
    for src in src_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_root)
        if _is_preserved(rel):
            skipped += 1
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        if rel.as_posix() == "config/config.default.json5":
            replaced_default = True
    print(f"Applied release files: copied={copied}, preserved={skipped}, default_replaced={replaced_default}")
    return copied, skipped, replaced_default


def _update_from_release_archive(version: str) -> tuple[int, int, bool]:
    print("Updating from GitHub release archive...")

    candidates = [
        f"https://github.com/{REPO}/archive/refs/tags/v{version}.zip",
        f"https://github.com/{REPO}/archive/refs/tags/{version}.zip",
    ]

    archive_bytes: bytes | None = None
    for url in candidates:
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                if response.status == 200:
                    archive_bytes = response.read()
                    break
        except (urllib.error.URLError, TimeoutError, PermissionError):
            continue

    if archive_bytes is None:
        raise RuntimeError("Could not download release archive from GitHub.")

    with tempfile.TemporaryDirectory(prefix="ofai_update_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        zip_path = temp_dir / "release.zip"
        zip_path.write_bytes(archive_bytes)

        extract_dir = temp_dir / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        roots = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("Unexpected release archive structure.")

        return _copy_release_tree(roots[0], BASE_DIR)


def install_update(version: str) -> None:
    before = _read_default_version_safe()
    _copied, _skipped, replaced_default = _update_from_release_archive(version)
    after = _read_default_version_safe()

    print(f"Default config version before: {before}")
    print(f"Default config version after : {after}")
    if not replaced_default:
        print("WARNING: config/config.default.json5 was not part of the applied release files.")
    if before == after:
        print(
            "WARNING: Default version did not change after archive apply. "
            "Either the release uses the same default version or update content is unchanged."
        )

    print("Installing Python dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[all]"],
        check=True,
        cwd=BASE_DIR,
    )

    npm_cmd = _resolve_npm_command()
    if npm_cmd:
        print(f"Installing Node dependencies and building UI (using {npm_cmd})...")
        subprocess.run([npm_cmd, "install", "--prefix", "ui"], check=True, cwd=BASE_DIR)
        subprocess.run([npm_cmd, "run", "build", "--prefix", "ui"], check=True, cwd=BASE_DIR)
    else:
        print("WARNING: npm not found in PATH. Skipping UI build step.")
        print("Install Node.js + npm and run these manually if UI updates are required:")
        print("  npm install --prefix ui")
        print("  npm run build --prefix ui")

    print("\nUpdate complete. Please restart the application.")


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenForexAI GitHub updater")
    parser.add_argument("--yes", action="store_true", help="Run non-interactive; auto-confirm update")
    parser.add_argument("--version", help="Install this exact release version/tag (e.g. 0.6.0)")
    args = parser.parse_args()

    print("OpenForexAI GitHub Updater")
    print("==========================")

    local = get_local_version()
    print(f"Local version:  {local}")

    remote = args.version.strip() if isinstance(args.version, str) and args.version.strip() else get_remote_version()
    if remote is None:
        print("Error: GitHub unreachable or no valid releases found.")
        return 1

    print(f"Latest version: {remote} (includes prereleases)")

    if remote != local:
        print(f"\nUpdate available: {local} -> {remote}")
        do_update = True
        if not args.yes:
            answer = input("Update now? (y/n): ")
            do_update = answer.lower() == "y"
        if do_update:
            install_update(remote)
            return 0
        print("Update cancelled.")
        return 0

    print("\nAlready up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
