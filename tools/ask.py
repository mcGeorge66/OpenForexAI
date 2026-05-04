"""ask.py — Query any OpenForexAI agent from the command line.

Communicates with the Management API (default http://127.0.0.1:8765).
No package installation required — uses only Python stdlib.

Usage
-----
List all currently registered agents::

    python tools/ask.py --list

Send a question to a specific agent and wait for its response::

    python tools/ask.py --agent OAPR1_EURUSD_AA_ANLYS --request "What is the current EURUSD trend?"

With custom host / port / timeout::

    python tools/ask.py --host 127.0.0.1 --port 8765 --timeout 120 \\
        --agent OAPR1_ALL..._BA_TRADE --request "Show me all open positions."

With API key (set MANAGEMENT_API_KEY or pass --api-key)::

    python tools/ask.py --api-key secret --agent OAPR1_EURUSD_AA_ANLYS --request "Trend?"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from datetime import UTC, datetime

# ── ANSI colour helpers ────────────────────────────────────────────────────────

_NO_COLOUR = not sys.stdout.isatty()

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_BGREEN = "\033[92m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_BRED   = "\033[91m"
_WHITE  = "\033[97m"


def _c(code: str, text: str) -> str:
    return text if _NO_COLOUR else f"{code}{text}{_RESET}"


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _request(
    method: str,
    url: str,
    body: dict | None = None,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> dict:
    """Perform a JSON HTTP request; raise on non-2xx."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("detail", str(exc))
        except Exception:
            detail = str(exc)
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to {url}: {exc.reason}") from exc


# ── Sub-commands ───────────────────────────────────────────────────────────────

def cmd_list(base_url: str, api_key: str | None) -> None:
    """Print all currently registered agents."""
    try:
        agents = _request("GET", f"{base_url}/agents", api_key=api_key)
    except RuntimeError as exc:
        print(_c(_BRED, f"Error: {exc}"), file=sys.stderr)
        sys.exit(1)

    if not agents:
        print(_c(_YELLOW, "No agents currently registered."))
        return

    print(_c(_BOLD, f"\n{'Agent ID':<40}  {'Queue':>6}  {'MaxQueue':>9}"))
    print("─" * 60)
    for a in agents:
        aid  = a.get("agent_id", "?")
        qs   = a.get("queue_size", 0)
        qmax = a.get("queue_maxsize", 0)
        # Colour-code by type segment (AA / BA / GA)
        if "_AA_" in aid:
            colour = _CYAN
        elif "_BA_" in aid:
            colour = _GREEN
        elif "_GA_" in aid:
            colour = _YELLOW
        else:
            colour = _WHITE
        print(f"  {_c(colour, f'{aid:<38}')}  {qs:>6}  {qmax:>9}")

    print()


def cmd_ask(
    base_url: str,
    agent_id: str,
    question: str,
    timeout: float,
    api_key: str | None,
) -> None:
    """Send a question to an agent and print its response."""

    # ── Verify the agent exists ────────────────────────────────────────────────
    try:
        agents = _request("GET", f"{base_url}/agents", api_key=api_key)
        known = {a["agent_id"] for a in agents}
    except RuntimeError as exc:
        print(_c(_BRED, f"Error fetching agents: {exc}"), file=sys.stderr)
        sys.exit(1)

    if agent_id not in known:
        print(_c(_BRED, f"Agent {agent_id!r} is not registered."), file=sys.stderr)
        print(_c(_YELLOW, "Registered agents:"))
        for a in sorted(known):
            print(f"  {a}")
        sys.exit(1)

    # ── Send the query ─────────────────────────────────────────────────────────
    ts = datetime.now(UTC).strftime("%H:%M:%S UTC")
    print()
    print(_c(_DIM, f"[{ts}] Sending query to ") + _c(_CYAN, agent_id))
    print(_c(_DIM, "─" * 60))
    for line in textwrap.wrap(question, width=70):
        print(f"  {_c(_WHITE, line)}")
    print(_c(_DIM, "─" * 60))
    print(_c(_DIM, f"Waiting up to {timeout:.0f}s for response…"))
    print()

    try:
        result = _request(
            "POST",
            f"{base_url}/agents/{agent_id}/ask",
            body={"question": question, "timeout": timeout},
            api_key=api_key,
            # HTTP timeout must be > agent timeout so the server can reply cleanly
            timeout=timeout + 15,
        )
    except RuntimeError as exc:
        err = str(exc)
        if "504" in err or "did not respond" in err.lower():
            print(_c(_BRED, f"Timeout: the agent did not respond within {timeout:.0f}s."))
        else:
            print(_c(_BRED, f"Error: {err}"), file=sys.stderr)
        sys.exit(1)

    # ── Print the response ─────────────────────────────────────────────────────
    ts2 = datetime.now(UTC).strftime("%H:%M:%S UTC")
    response_text  = result.get("response", "")
    correlation_id = result.get("correlation_id", "")
    responding_id  = result.get("agent_id", agent_id)

    print(_c(_BGREEN, f"[{ts2}] Response from {responding_id}"))
    print(_c(_DIM, "─" * 60))

    # Try to pretty-print JSON responses; fall back to plain text
    try:
        parsed = json.loads(response_text)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        for line in pretty.splitlines():
            print(f"  {line}")
    except (json.JSONDecodeError, TypeError):
        for line in response_text.splitlines():
            print(f"  {line}")

    print(_c(_DIM, "─" * 60))
    print(_c(_DIM, f"correlation_id: {correlation_id}"))
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    global _NO_COLOUR

    parser = argparse.ArgumentParser(
        prog="ask.py",
        description="Query any OpenForexAI agent from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python tools/ask.py --list
              python tools/ask.py --agent OAPR1_EURUSD_AA_ANLYS --request "Current EURUSD trend?"
              python tools/ask.py --agent OAPR1_ALL..._BA_TRADE  --request "Open positions?" --timeout 60
        """),
    )

    parser.add_argument("--host",     default="127.0.0.1", metavar="HOST")
    parser.add_argument("--port",     default=8765, type=int, metavar="PORT")
    parser.add_argument("--api-key",  default=os.environ.get("MANAGEMENT_API_KEY", ""),
                        metavar="KEY", help="X-API-Key header (or set MANAGEMENT_API_KEY env var)")
    parser.add_argument("--no-colour", action="store_true")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list",    action="store_true",
                       help="List all currently registered agents")
    group.add_argument("--agent",   metavar="AGENT_ID",
                       help="Agent ID to query (use --list to see available agents)")

    parser.add_argument("--request", metavar="QUESTION",
                        help="Question or instruction to send to the agent (required with --agent)")
    parser.add_argument("--timeout", default=120.0, type=float, metavar="SECONDS",
                        help="Seconds to wait for the agent's response (default: 120)")

    args = parser.parse_args()

    if args.no_colour:
        _NO_COLOUR = True

    if args.agent and not args.request:
        parser.error("--request is required when --agent is specified")

    base_url = f"http://{args.host}:{args.port}"
    api_key  = args.api_key or None

    if args.list:
        cmd_list(base_url, api_key)
    else:
        cmd_ask(base_url, args.agent, args.request, args.timeout, api_key)


if __name__ == "__main__":
    main()
