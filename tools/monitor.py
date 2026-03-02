#!/usr/bin/env python3
"""OpenForexAI Console Monitor.

Polls the management API monitoring endpoint and displays events
in a human-readable format on the terminal.

Optionally writes ALL events as JSONL (full payload, no truncation) to a log
file in the background — useful for verifying that complete audit data is
being stored (use --log FILE to activate).

Usage::

    python tools/monitor.py
    python tools/monitor.py --host 127.0.0.1 --port 8765
    python tools/monitor.py --filter llm_request,llm_response,tool_call_started,tool_call_completed
    python tools/monitor.py --pair EURUSD
    python tools/monitor.py --limit 50 --interval 1.0
    python tools/monitor.py --errors          # show only error events
    python tools/monitor.py --llm             # show only LLM communication
    python tools/monitor.py --tools           # show only tool calls
    python tools/monitor.py --bus             # show only agent-to-agent messages
    python tools/monitor.py --log audit.jsonl # write full payloads to log file
    python tools/monitor.py --llm --log llm.jsonl  # display LLM events + log everything
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
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
_MAGENTA = "\033[35m"
_CYAN   = "\033[36m"
_WHITE  = "\033[37m"
_BRED   = "\033[91m"   # bright red — for error banners
_BGREEN = "\033[92m"   # bright green
_BYELLOW = "\033[93m"  # bright yellow
_BCYAN  = "\033[96m"   # bright cyan

_TYPE_COLOUR = {
    # Broker
    "broker_connected":    _GREEN,
    "broker_disconnected": _RED,
    "broker_reconnecting": _YELLOW,
    "broker_error":        _RED,
    # Candles
    "m5_candle_fetched":   _DIM,
    "m5_candle_queued":    _DIM,
    "candle_gap_detected": _YELLOW,
    "candle_repair_started":   _YELLOW,
    "candle_repair_completed": _GREEN,
    "candle_repair_failed":    _RED,
    "timeframe_calculated":    _DIM,
    # Account
    "account_status_updated": _GREEN,
    "account_poll_error":      _RED,
    # LLM
    "llm_request":         _BCYAN,
    "llm_response":        _CYAN,
    "llm_error":           _RED,
    # Tools
    "tool_call_started":   _BLUE,
    "tool_call_completed": _BGREEN,
    "tool_call_failed":    _RED,
    # Data container
    "data_container_access": _MAGENTA,
    # Agent decisions
    "agent_signal_generated": _YELLOW,
    "agent_decision_made":    _BYELLOW,
    "agent_alarm":            _RED,
    # EventBus
    "event_bus_message":   _DIM,
    # System
    "system_error":        _RED,
    "system_warning":      _YELLOW,
    "system_info":         _WHITE,
    "agent_queue_full":    _YELLOW,
    "routing_reloaded":    _WHITE,
    "sync_check_started":  _DIM,
    "sync_check_completed":_DIM,
    "sync_discrepancy_found": _YELLOW,
}

# Event types that indicate a crash / serious error — rendered with full payload
_ERROR_TYPES = {
    "system_error",
    "broker_error",
    "llm_error",
    "tool_call_failed",
    "agent_alarm",
    "broker_disconnected",
    "account_poll_error",
    "candle_repair_failed",
}

# Quick-filter sets for --llm, --tools, --bus flags
_LLM_TYPES   = {"llm_request", "llm_response", "llm_error"}
_TOOL_TYPES  = {"tool_call_started", "tool_call_completed", "tool_call_failed"}
_BUS_TYPES   = {"event_bus_message"}
_DATA_TYPES  = {"data_container_access"}

# ── Per-type payload field order ──────────────────────────────────────────────
# Keys listed here are shown first (in order); remaining keys are appended.
# NOTE: 'messages' and 'tool_specs' are intentionally last — they are displayed
#       as a compact summary on the terminal (full data always in --log file).
_TYPE_FIELDS: dict[str, list[str]] = {
    "llm_request":  [
        "turn", "tool_count", "tool_names", "message_count",
        "system_prompt",      # long text — display-truncated
        "content",            # last user message preview (legacy compat)
        "messages",           # complete history — summary only on terminal
        "tool_specs",         # complete definitions — summary only on terminal
    ],
    "llm_response": [
        "turn", "stop_reason", "model", "input_tokens", "output_tokens",
        "tool_calls", "tool_names",
        "tool_call_details",  # complete inputs — summary only on terminal
        "content",            # complete LLM text — display-truncated
    ],
    "tool_call_started":   ["tool_name", "agent", "arguments"],
    "tool_call_completed": ["tool_name", "agent", "result_length", "result"],
    "tool_call_failed":    ["tool_name", "agent", "error"],
    "event_bus_message":   ["event", "sender", "target", "correlation_id", "payload_keys"],
    "data_container_access": [
        "method", "timeframe", "candle_count", "bid", "ask",
        "m5_count", "m15_count", "m30_count", "h1_count", "h4_count", "d1_count",
        "session", "first_ts", "last_ts",
    ],
    "m5_candle_fetched":   ["timestamp", "open", "high", "low", "close", "spread", "tick_volume"],
    "account_status_updated": ["balance", "equity", "margin_level", "trade_allowed"],
}

# Fields that contain long free-text — use higher display limit
_LONG_TEXT_FIELDS = {
    "content",        # LLM response text / last user message
    "system_prompt",  # LLM request system prompt
    "result",         # Tool call result (can be large JSON)
    "arguments",      # Tool call arguments
    "error",          # Error messages (can be tracebacks)
}

# Fields that are lists-of-dicts — shown as a compact summary on the terminal
# (full data is always written to the --log file unmodified)
_LARGE_LIST_FIELDS = {
    "messages",          # complete LLM conversation history
    "tool_specs",        # complete tool definitions
    "tool_call_details", # complete tool call inputs
}

# Display limit for long text fields (terminal readability)
_DISPLAY_LIMIT_LONG = 2000

# Events that get a multi-line detailed block (not just single-line compact)
_MULTILINE_TYPES = {
    "llm_request", "llm_response",
    "tool_call_started", "tool_call_completed",
    "data_container_access",
} | _ERROR_TYPES

_NO_COLOUR = not sys.stdout.isatty()


def _c(colour: str, text: str) -> str:
    if _NO_COLOUR:
        return text
    return f"{colour}{text}{_RESET}"


def _val_preview(v, max_len: int = 200) -> str:
    """Convert a value to a display string, truncating if needed."""
    if isinstance(v, str):
        s = v
    elif isinstance(v, list):
        s = ", ".join(str(x) for x in v)
    else:
        s = json.dumps(v, default=str)
    if len(s) > max_len:
        s = s[:max_len] + " …"
    return s


def _format_multiline(evt: dict) -> str:
    """Render an event as a multi-line detailed block.

    Long text fields (system_prompt, content, result) are display-truncated
    with a note that the full data is available in the --log file.

    Large list fields (messages, tool_specs, tool_call_details) are shown as
    a compact summary — full data always in the --log file.
    """
    ts     = evt.get("timestamp", "")[:19].replace("T", " ")
    etype  = evt.get("event_type", "unknown")
    src    = evt.get("source", "")
    pair   = evt.get("pair") or ""
    broker = evt.get("broker") or ""
    payload = evt.get("payload", {})

    colour = _TYPE_COLOUR.get(etype, _WHITE)
    is_error = etype in _ERROR_TYPES
    bar_colour = _BRED if is_error else colour
    sep = _c(bar_colour, "─" * 80)

    ctx_parts = [p for p in [broker, pair] if p]
    ctx = f"[{'/'.join(ctx_parts)}]" if ctx_parts else ""
    src_short = src.split(":")[-1] if ":" in src else src

    prefix = "!!! " if is_error else "▶ "
    header = (
        f"{_c(bar_colour, _BOLD + prefix + etype.upper())}"
        f"  {_c(_DIM, ts)}"
        + (f"  {_c(_DIM, src_short)}" if src_short else "")
        + (f"  {_c(_DIM, ctx)}" if ctx else "")
    )

    lines = [sep, header]
    if payload:
        ordered_keys = _TYPE_FIELDS.get(etype, [])
        shown = set()

        def _render_field(k: str, v, is_priority: bool) -> None:
            label = f"{k}:"
            colour_fn = _YELLOW if is_priority else _DIM

            if k in _LARGE_LIST_FIELDS and isinstance(v, list):
                # Compact summary — full data in log file
                summary = f"[{len(v)} items — full data in --log file]"
                lines.append(f"  {_c(colour_fn, f'{label:<24}')}  {_c(_DIM, summary)}")
            elif k in _LONG_TEXT_FIELDS:
                # Display-truncated with note
                raw = v if isinstance(v, str) else json.dumps(v, default=str)
                if len(raw) > _DISPLAY_LIMIT_LONG:
                    val_str = raw[:_DISPLAY_LIMIT_LONG] + " …"
                    lines.append(f"  {_c(colour_fn, f'{label:<24}')}  {val_str}")
                    note = f"(display truncated at {_DISPLAY_LIMIT_LONG} chars — full {len(raw)} chars in --log file)"
                    lines.append(f"  {_c(_DIM, ' ' * 26)}  {_c(_DIM, note)}")
                else:
                    lines.append(f"  {_c(colour_fn, f'{label:<24}')}  {raw}")
            else:
                val_str = _val_preview(v, max_len=300)
                lines.append(f"  {_c(colour_fn, f'{label:<24}')}  {val_str}")

        for k in ordered_keys:
            if k in payload:
                _render_field(k, payload[k], is_priority=True)
                shown.add(k)
        for k, v in payload.items():
            if k not in shown:
                _render_field(k, v, is_priority=False)
    else:
        lines.append(_c(_DIM, "  (no payload)"))
    lines.append(sep)
    return "\n".join(lines)


def _format_compact(evt: dict) -> str:
    """Render an event as a compact single line."""
    ts     = evt.get("timestamp", "")[:19].replace("T", " ")
    etype  = evt.get("event_type", "unknown")
    src    = evt.get("source", "")
    pair   = evt.get("pair") or ""
    broker = evt.get("broker") or ""
    payload = evt.get("payload", {})

    colour = _TYPE_COLOUR.get(etype, _WHITE)
    ctx_parts = [p for p in [broker, pair] if p]
    ctx = f"[{'/'.join(ctx_parts)}] " if ctx_parts else ""
    src_short = src.split(":")[-1] if ":" in src else src

    payload_str = ""
    if payload:
        ordered_keys = _TYPE_FIELDS.get(etype, [
            "model", "input_tokens", "output_tokens", "tool_calls",
            "stop_reason", "turn", "error", "message",
            "pair", "direction", "units", "price",
            "balance", "equity", "rule_count",
            "broker_name", "timestamp", "close",
            "open", "high", "low", "spread",
            "positions_at_broker", "local_open", "discrepancies",
        ])
        parts = []
        for k in ordered_keys[:6]:   # show at most 6 fields on one line
            if k in payload:
                v = payload[k]
                if k in _LARGE_LIST_FIELDS and isinstance(v, list):
                    parts.append(f"{k}=[{len(v)} items]")
                else:
                    s = _val_preview(v, max_len=80)
                    parts.append(f"{k}={s!r}" if " " not in s else f"{k}={s}")
        if not parts:
            raw = json.dumps(payload, default=str)
            parts = [raw[:100] + ("…" if len(raw) > 100 else "")]
        payload_str = "  " + _c(_DIM, "  ".join(parts))

    return (
        f"{_c(_DIM, ts)}  "
        f"{_c(colour, f'{etype:<32}')}"
        f"{_c(_DIM, ctx)}"
        f"{_c(_DIM, src_short)}"
        f"{payload_str}"
    )


def _format_event(evt: dict) -> str:
    etype = evt.get("event_type", "unknown")
    if etype in _MULTILINE_TYPES:
        return _format_multiline(evt)
    return _format_compact(evt)


def _fetch(url: str) -> list | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError:
        return None
    except Exception:
        return None


def _show_missed_errors(base_url: str, limit: int, since_ts: str | None) -> None:
    """After a reconnect, fetch the ring buffer and print any errors we missed."""
    url = f"{base_url}/monitoring/events?limit={limit}"
    if since_ts:
        url += "&" + urllib.parse.urlencode({"since": since_ts})
    events = _fetch(url)
    if not events:
        return
    errors = [e for e in events if e.get("event_type") in _ERROR_TYPES]
    if not errors:
        return
    print(_c(_BRED, f"\n{'─'*80}"))
    print(_c(_BRED, _BOLD + f"  {len(errors)} ERROR(S) occurred while monitor was disconnected:"))
    print(_c(_BRED, f"{'─'*80}"))
    for evt in errors:
        print(_format_event(evt))
    print(_c(_BRED, f"{'─'*80}\n"))


# ── Background log writer ──────────────────────────────────────────────────────

def _log_writer_thread(log_path: str, q: "queue.Queue[str | None]") -> None:
    """Background thread: writes JSONL lines from the queue to the log file.

    Receives full event JSON strings (one per line).
    Stops when it receives None as a sentinel value.
    """
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            while True:
                item = q.get()
                if item is None:     # shutdown sentinel
                    break
                try:
                    f.write(item + "\n")
                    f.flush()        # flush after every event — no data loss on crash
                except Exception:
                    pass
    except Exception as exc:
        print(f"\n[monitor] Log file error: {exc}", file=sys.stderr)


def _start_log_writer(log_path: str) -> "queue.Queue[str | None]":
    """Start the background log writer and return its input queue."""
    q: queue.Queue[str | None] = queue.Queue(maxsize=10_000)
    t = threading.Thread(target=_log_writer_thread, args=(log_path, q), daemon=True)
    t.start()
    return q


def _log_event(q: "queue.Queue[str | None] | None", evt: dict) -> None:
    """Enqueue an event for logging (full JSON, no truncation)."""
    if q is None:
        return
    try:
        line = json.dumps(evt, default=str, ensure_ascii=False)
        q.put_nowait(line)
    except queue.Full:
        pass   # log queue full — drop rather than block the poll loop
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

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
                        help="Comma-separated event_type filter")
    parser.add_argument("--pair",     default="",
                        help="Filter by currency pair (e.g. EURUSD)")
    parser.add_argument("--errors",  action="store_true",
                        help="Show only error/alarm events")
    parser.add_argument("--llm",     action="store_true",
                        help="Show only LLM request/response events")
    parser.add_argument("--tools",   action="store_true",
                        help="Show only tool call events")
    parser.add_argument("--bus",     action="store_true",
                        help="Show only agent-to-agent EventBus messages")
    parser.add_argument("--data",    action="store_true",
                        help="Show only DataContainer access events")
    parser.add_argument("--all",     action="store_true",
                        help="Show all events (overrides other filters)")
    parser.add_argument("--no-colour", action="store_true")
    parser.add_argument("--log",     metavar="FILE", default="",
                        help="Append ALL events as JSONL to FILE (full payload, no truncation). "
                             "Runs in the background; independent of display filters.")
    args = parser.parse_args()

    global _NO_COLOUR
    if args.no_colour:
        _NO_COLOUR = True

    base_url   = f"http://{args.host}:{args.port}"
    events_url = f"{base_url}/monitoring/events?limit={args.limit}"

    type_filter: set[str] = {t.strip() for t in args.filter.split(",") if t.strip()}
    if args.errors:
        type_filter |= _ERROR_TYPES
    if args.llm:
        type_filter |= _LLM_TYPES
    if args.tools:
        type_filter |= _TOOL_TYPES
    if args.bus:
        type_filter |= _BUS_TYPES
    if args.data:
        type_filter |= _DATA_TYPES
    if args.all:
        type_filter = set()   # empty = no filter = show everything

    pair_filter = args.pair.strip().upper()

    # ── Start log writer ──────────────────────────────────────────────────────
    log_queue: queue.Queue | None = None
    if args.log:
        log_queue = _start_log_writer(args.log)

    # ── Banner ────────────────────────────────────────────────────────────────
    print(_c(_BOLD, f"OpenForexAI Monitor — {base_url}"))
    print(_c(_DIM,  f"Poll interval: {args.interval}s  |  Ctrl+C to exit"))
    active_flags = [f for f, v in [("--errors", args.errors), ("--llm", args.llm),
                                    ("--tools", args.tools), ("--bus", args.bus),
                                    ("--data", args.data)] if v]
    if args.all or not active_flags and not type_filter:
        print(_c(_DIM, "Showing ALL events"))
    elif active_flags:
        print(_c(_YELLOW, f"Filter: {', '.join(active_flags)}"))
    elif type_filter:
        print(_c(_DIM, f"Filter: {', '.join(sorted(type_filter))}"))
    if pair_filter:
        print(_c(_DIM, f"Pair filter: {pair_filter}"))
    if args.log:
        print(_c(_BGREEN, f"Log file: {args.log}  (ALL events, full payload, JSONL format)"))
    print("─" * 80)

    last_ts: str | None = None
    connected = False
    lost_at: str | None = None

    while True:
        url = events_url
        if last_ts:
            url += "&" + urllib.parse.urlencode({"since": last_ts})

        events = _fetch(url)

        if events is None:
            if connected:
                lost_at = last_ts
                print(_c(_YELLOW, f"[{_ts_now()}] Connection lost — retrying..."))
                connected = False
        else:
            if not connected:
                print(_c(_GREEN, f"[{_ts_now()}] Connected to {base_url}"))
                connected = True
                _show_missed_errors(base_url, args.limit, lost_at)
                lost_at = None

            for evt in events:
                # ── Log EVERY event (full payload, no filter) ─────────────────
                _log_event(log_queue, evt)

                # ── Display filter ────────────────────────────────────────────
                etype = evt.get("event_type")
                if type_filter and etype not in type_filter:
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
            if log_queue is not None:
                log_queue.put(None)   # shutdown sentinel
            print(_c(_DIM, "\nMonitor stopped."))
            break


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
