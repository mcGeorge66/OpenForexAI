#!/usr/bin/env python3
"""OpenForexAI Event Logger — rotating JSONL file writer.

Polls the management API ``GET /monitoring/events`` endpoint and writes every
event as a JSON line (JSONL) to automatically rotating log files.

File naming
-----------
Active file:   ``fai_YYYYMMDDHHMM.log``          (start timestamp in name)
Closed file:   ``fai_YYYYMMDDHHMM_YYYYMMDDHHMM.log``  (start + end timestamp)

The start/end timestamps are always in UTC so the time window is immediately
readable from the filename alone.

Rotation
--------
A new file is started when the active file reaches ``--max-size`` megabytes.
At that point:
1. The active file is closed and renamed to the ``start_end`` format.
2. A new active file is opened with the current UTC timestamp as start.
3. If the total number of log files in ``--dir`` exceeds ``--max-files``,
   the oldest files are deleted until the count is within the limit.
   Set ``--max-files 0`` to keep all files indefinitely.

Format
------
Each line is a standalone JSON object (JSONL / ndjson).  This makes files
grep-able and allows streaming parsers to process individual events without
loading the entire file.

Example line::

    {"id": "…", "timestamp": "2026-03-03T08:12:34.123+00:00", "event_type": "llm_response", …}

Usage
-----
::

    python tools/logging.py
    python tools/logging.py --dir ./logs
    python tools/logging.py --dir ./logs --max-size 10 --max-files 20
    python tools/logging.py --host 127.0.0.1 --port 8765 --interval 2.0
    python tools/logging.py --max-size 50 --max-files 0   # unlimited retention
    python tools/logging.py --api-key secret --dir /var/log/fai

Stop with Ctrl+C — the active file is closed and renamed before exit.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# ── Timestamp helpers ─────────────────────────────────────────────────────────

_TS_FMT = "%Y%m%d%H%M"   # compact UTC timestamp used in filenames


def _ts_now() -> datetime:
    return datetime.now(UTC)


def _ts_str(dt: datetime) -> str:
    return dt.strftime(_TS_FMT)


def _ts_display(dt: datetime | None = None) -> str:
    if dt is None:
        dt = _ts_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ── Rotating file writer ──────────────────────────────────────────────────────

class _RotatingWriter:
    """Background JSONL writer with size-based rotation and file count limit.

    Thread-safe: all public methods acquire ``_lock`` so the poll thread and
    the writer thread can interact without races.

    All file operations run on the *caller's* thread (the writer thread in
    normal operation).  Rotation is triggered inside ``write()`` so it always
    happens at a well-defined point between two events.
    """

    def __init__(
        self,
        log_dir: Path,
        max_size_mb: float,
        max_files: int,
    ) -> None:
        self._dir = log_dir
        self._dir.mkdir(parents=True, exist_ok=True)

        # 0 means unlimited
        self._max_bytes: int = int(max_size_mb * 1024 * 1024) if max_size_mb > 0 else 0
        self._max_files: int = max_files

        self._lock = threading.Lock()
        self._start_time: datetime = _ts_now()
        self._current_path: Path = self._active_path(self._start_time)
        self._fh = self._current_path.open("a", encoding="utf-8")
        self._bytes_written: int = 0

        print(f"[logger] Active log: {self._current_path}")

    # ── Path helpers ──────────────────────────────────────────────────────────

    def _active_path(self, start: datetime) -> Path:
        """Path for an active (not yet rotated) log file."""
        return self._dir / f"fai_{_ts_str(start)}.log"

    def _closed_path(self, start: datetime, end: datetime) -> Path:
        """Path for a closed (rotated) log file."""
        return self._dir / f"fai_{_ts_str(start)}_{_ts_str(end)}.log"

    # ── Write & rotation ──────────────────────────────────────────────────────

    def write(self, event: dict) -> None:
        """Serialise *event* as a JSON line and write it.  Rotates if needed."""
        # Ensure each line starts with a clear log timestamp for quick human
        # interpretation while keeping strict JSONL format.
        event_with_log_ts = {
            "logged_at_utc": _ts_now().isoformat(),
            **event,
        }
        line = json.dumps(event_with_log_ts, default=str, ensure_ascii=False) + "\n"
        encoded = line.encode("utf-8")

        with self._lock:
            # Rotate BEFORE writing if the file would exceed the limit
            if self._max_bytes > 0 and self._bytes_written + len(encoded) > self._max_bytes:
                self._rotate()

            self._fh.write(line)
            self._fh.flush()
            self._bytes_written += len(encoded)

    def _rotate(self) -> None:
        """Close the current file, rename it, open a new one, prune old files.

        Must be called while holding ``_lock``.
        """
        end_time = _ts_now()

        self._fh.flush()
        self._fh.close()

        closed = self._closed_path(self._start_time, end_time)
        try:
            self._current_path.rename(closed)
        except OSError as exc:
            # Non-fatal — continue with a new file even if rename failed
            print(f"[logger] WARNING: could not rename log file: {exc}", file=sys.stderr)

        # Open the new active file
        self._start_time = _ts_now()
        self._current_path = self._active_path(self._start_time)
        self._fh = self._current_path.open("a", encoding="utf-8")
        self._bytes_written = 0

        print(
            f"[logger] Rotated  → {closed.name}\n"
            f"[logger] New file → {self._current_path.name}"
        )

        self._prune_old_files()

    def _prune_old_files(self) -> None:
        """Delete the oldest log files if the total count exceeds ``max_files``.

        Must be called while holding ``_lock``.
        Counts ALL ``fai_*.log`` files in the directory (active + closed).
        The currently-active file is never deleted.
        """
        if self._max_files <= 0:
            return  # unlimited

        # Gather all log files sorted by modification time (oldest first)
        all_files: list[Path] = sorted(
            self._dir.glob("fai_*.log"),
            key=lambda p: p.stat().st_mtime,
        )

        excess = len(all_files) - self._max_files
        if excess <= 0:
            return

        deleted = 0
        for f in all_files:
            if excess <= 0:
                break
            if f == self._current_path:
                continue   # never delete the active file
            try:
                f.unlink()
                print(f"[logger] Deleted old log: {f.name}")
                deleted += 1
                excess -= 1
            except OSError as exc:
                print(f"[logger] WARNING: could not delete {f.name}: {exc}", file=sys.stderr)

    # ── Clean shutdown ────────────────────────────────────────────────────────

    def close(self) -> None:
        """Flush, close and rename the active file with end timestamp."""
        with self._lock:
            end_time = _ts_now()
            self._fh.flush()
            self._fh.close()

            closed = self._closed_path(self._start_time, end_time)
            try:
                self._current_path.rename(closed)
                print(f"[logger] Closed   → {closed.name}")
            except OSError as exc:
                print(
                    f"[logger] WARNING: could not rename on close: {exc}\n"
                    f"[logger] Active file remains as: {self._current_path.name}",
                    file=sys.stderr,
                )

    @property
    def active_filename(self) -> str:
        return self._current_path.name

    @property
    def bytes_written(self) -> int:
        return self._bytes_written


# ── Writer thread ─────────────────────────────────────────────────────────────

def _writer_thread(writer: _RotatingWriter, q: queue.Queue[dict | None]) -> None:
    """Dequeue events and write them.  ``None`` is the shutdown sentinel."""
    while True:
        item = q.get()
        if item is None:
            writer.close()
            break
        try:
            writer.write(item)
        except Exception as exc:
            print(f"[logger] Write error: {exc}", file=sys.stderr)


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def _fetch_events(url: str, api_key: str | None) -> list | None:
    """Fetch monitoring events from the management API.  Returns None on error."""
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, Exception):
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "OpenForexAI Event Logger — polls /monitoring/events and writes "
            "rotating JSONL log files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "File naming:\n"
            "  Active:  fai_YYYYMMDDHHMM.log\n"
            "  Closed:  fai_YYYYMMDDHHMM_YYYYMMDDHHMM.log\n\n"
            "Examples:\n"
            "  python tools/logging.py\n"
            "  python tools/logging.py --dir ./logs --max-size 10 --max-files 20\n"
            "  python tools/logging.py --max-size 50 --max-files 0   # unlimited\n"
        ),
    )

    parser.add_argument(
        "--host", default="127.0.0.1", metavar="HOST",
        help="Management API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8765, metavar="PORT",
        help="Management API port (default: 8765)",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0, metavar="SECONDS",
        help="Poll interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--limit", type=int, default=200, metavar="N",
        help="Max events fetched per poll (default: 200)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MANAGEMENT_API_KEY", ""),
        metavar="KEY",
        help="X-API-Key header value (or set MANAGEMENT_API_KEY env var)",
    )
    parser.add_argument(
        "--dir", default=".", metavar="DIR",
        help="Directory to write log files into (default: current directory)",
    )
    parser.add_argument(
        "--max-size", type=float, default=10.0, metavar="MB",
        help=(
            "Maximum log file size in megabytes before rotation (default: 10.0). "
            "Set to 0 for no size limit."
        ),
    )
    parser.add_argument(
        "--max-files", type=int, default=20, metavar="N",
        help=(
            "Maximum total number of log files to keep (default: 20). "
            "0 = keep all files indefinitely."
        ),
    )

    args = parser.parse_args()

    # ── Validate ──────────────────────────────────────────────────────────────
    if args.max_size < 0:
        parser.error("--max-size must be >= 0")
    if args.max_files < 0:
        parser.error("--max-files must be >= 0")
    if args.interval <= 0:
        parser.error("--interval must be > 0")

    log_dir = Path(args.dir).expanduser().resolve()
    base_url = f"http://{args.host}:{args.port}"
    events_url = f"{base_url}/monitoring/events?limit={args.limit}"
    api_key: str | None = args.api_key or None

    # ── Banner ────────────────────────────────────────────────────────────────
    print("OpenForexAI Event Logger")
    print(f"  API:       {base_url}")
    print(f"  Directory: {log_dir}")
    if args.max_size > 0:
        print(f"  Max size:  {args.max_size:.1f} MB per file")
    else:
        print("  Max size:  unlimited")
    if args.max_files > 0:
        print(f"  Max files: {args.max_files} total")
    else:
        print("  Max files: unlimited")
    print(f"  Interval:  {args.interval}s  |  Ctrl+C to stop")
    print("─" * 60)

    # ── Start writer thread ───────────────────────────────────────────────────
    writer = _RotatingWriter(
        log_dir=log_dir,
        max_size_mb=args.max_size,
        max_files=args.max_files,
    )
    write_queue: queue.Queue[dict | None] = queue.Queue(maxsize=50_000)
    wt = threading.Thread(
        target=_writer_thread,
        args=(writer, write_queue),
        daemon=True,
        name="fai-log-writer",
    )
    wt.start()

    # ── Poll loop ─────────────────────────────────────────────────────────────
    last_ts: str | None = None
    connected = False
    total_events = 0

    try:
        while True:
            url = events_url
            if last_ts:
                url += "&" + urllib.parse.urlencode({"since": last_ts})

            events = _fetch_events(url, api_key)

            if events is None:
                if connected:
                    print(f"[{_ts_display()}] Connection lost — retrying…")
                    connected = False
            else:
                if not connected:
                    print(f"[{_ts_display()}] Connected to {base_url}")
                    connected = True

                for evt in events:
                    try:
                        write_queue.put_nowait(evt)
                        total_events += 1
                    except queue.Full:
                        print(
                            "[logger] WARNING: write queue full — event dropped",
                            file=sys.stderr,
                        )

                    ts = evt.get("timestamp")
                    if ts and (last_ts is None or ts > last_ts):
                        last_ts = ts

                if events:
                    # Print a brief status line after each batch
                    print(
                        f"[{_ts_display()}] +{len(events):>4} events "
                        f"(total: {total_events:,})  "
                        f"active: {writer.active_filename}  "
                        f"({writer.bytes_written / 1024:.1f} KB)"
                    )

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n[{_ts_display()}] Stopping…")

    finally:
        # Graceful shutdown: send sentinel, wait for writer to flush and close
        write_queue.put(None)
        wt.join(timeout=10)
        print(
            f"[{_ts_display()}] Logger stopped.  "
            f"{total_events:,} events written."
        )


if __name__ == "__main__":
    main()

