#!/usr/bin/env python3
"""OpenForexAI Console Monitor.

Polls the management API monitoring endpoint and displays events
in a human-readable format on the terminal.

Usage::

    python tools/monitor.py
    python tools/monitor.py --host 127.0.0.1 --port 8765
    python tools/monitor.py --filter broker_connected,llm_response
    python tools/monitor.py --pair EURUSD
    python tools/monitor.py --limit 50 --interval 1.0
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ── ANSI colours ──────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_BLUE   = "\033[34m"
_CYAN   = "\033[36m"
_WHITE  = "\033[37m"

_TYPE_COLOUR = {
    "broker_connected":    _GREEN,
    "broker_disconnected": _RED,
    "broker_reconnecting": _YELLOW,
    "broker_error":        _RED,
    "llm_request":         _CYAN,
    "llm_response":        _CYAN,
    "llm_error":           _RED,
    "tool_call_started":   _BLUE,
    "tool_call_completed": _BLUE,
    "tool_call_failed":    _RED,
    "agent_signal_generated": _YELLOW,
    "agent_decision_made":    _YELLOW,
    "agent_alarm":            _RED,
    "system_error":        _RED,
    "system_warning":      _YELLOW,
    "system_info":         _WHITE,
    "m5_candle_fetched":   _DIM,
    "m5_candle_queued":    _DIM,
    "account_status_updated": _GREEN,
    "agent_queue_full":    _YELLOW,
    "routing_reloaded":    _WHITE,
}

_NO_COLOUR = not sys.stdout.isatty()


def _c(colour: str, text: str) -> str:
    if _NO_COLOUR:
        return text
    return f"{colour}{text}{_RESET}"


def _format_event(evt: dict) -> str:
    ts    = evt.get("timestamp", "")[:19].replace("T", " ")
    etype = evt.get("event_type", "unknown")
    src   = evt.get("source", "")
    pair  = evt.get("pair") or ""
    broker = evt.get("broker") or ""
    payload = evt.get("payload", {})

    colour = _TYPE_COLOUR.get(etype, _WHITE)

    # Build context tag
    ctx_parts = [p for p in [broker, pair] if p]
    ctx = f"[{'/'.join(ctx_parts)}] " if ctx_parts else ""

    # Shorten payload to most relevant fields
    payload_str = ""
    if payload:
        # pick most informative keys
        interesting = [
            "model", "input_tokens", "output_tokens", "tool_calls",
            "stop_reason", "turn",
            "error", "message", "severity",
            "pair", "direction", "units", "price",
        ]
        parts = []
        for k in interesting:
            if k in payload:
                parts.append(f"{k}={payload[k]!r}")
        if not parts:
            raw = json.dumps(payload, default=str)
            parts = [raw[:120] + ("..." if len(raw) > 120 else "")]
        payload_str = "  " + _c(_DIM, "  ".join(parts))

    src_short = src.split(":")[-1] if ":" in src else src

    line = (
        f"{_c(_DIM, ts)}  "
        f"{_c(colour, f'{etype:<32}')}"
        f"{_c(_DIM, ctx)}"
        f"{_c(_DIM, src_short)}"
        f"{payload_str}"
    )
    return line


def _fetch(url: str) -> list | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenForexAI console monitor — polls /monitoring/events"
    )
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=8765)
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Poll interval in seconds (default: 2.0)")
    parser.add_argument("--limit",    type=int, default=100,
                        help="Max events per poll (default: 100)")
    parser.add_argument("--filter",   default="",
                        help="Comma-separated event_type filter (e.g. llm_response,tool_call_started)")
    parser.add_argument("--pair",     default="",
                        help="Filter by currency pair (e.g. EURUSD)")
    parser.add_argument("--no-colour", action="store_true")
    args = parser.parse_args()

    global _NO_COLOUR
    if args.no_colour:
        _NO_COLOUR = True

    base_url   = f"http://{args.host}:{args.port}"
    events_url = f"{base_url}/monitoring/events?limit={args.limit}"
    type_filter = {t.strip() for t in args.filter.split(",") if t.strip()}
    pair_filter  = args.pair.strip().upper()

    print(_c(_BOLD, f"OpenForexAI Monitor — {base_url}"))
    print(_c(_DIM,  f"Poll interval: {args.interval}s  |  Ctrl+C to exit"))
    if type_filter:
        print(_c(_DIM, f"Filter: {', '.join(sorted(type_filter))}"))
    if pair_filter:
        print(_c(_DIM, f"Pair filter: {pair_filter}"))
    print("-" * 80)

    last_ts: str | None = None
    connected = False

    while True:
        url = events_url
        if last_ts:
            url += f"&since={last_ts}"

        events = _fetch(url)

        if events is None:
            if connected:
                print(_c(_YELLOW, f"[{_ts_now()}] Connection lost — retrying..."))
                connected = False
        else:
            if not connected:
                print(_c(_GREEN, f"[{_ts_now()}] Connected to {base_url}"))
                connected = True

            for evt in events:
                if type_filter and evt.get("event_type") not in type_filter:
                    continue
                if pair_filter and evt.get("pair") != pair_filter:
                    continue
                print(_format_event(evt))
                ts = evt.get("timestamp")
                if ts and (last_ts is None or ts > last_ts):
                    last_ts = ts

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print(_c(_DIM, "\nMonitor stopped."))
            break


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
