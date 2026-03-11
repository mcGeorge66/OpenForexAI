[Back to Documentation Index](./README.md)

# OpenForexAI CLI Tools

## Table of Contents

- [OpenForexAI CLI Tools](#openforexai-cli-tools)
- [monitor.py — Console Monitor](#monitorpy--console-monitor)
- [ask.py — Agent Query Tool](#askpy--agent-query-tool)
- [logging.py — Rotating Event Logger](#loggingpy--rotating-event-logger)
- [test_llm.py — LLM Diagnostics](#test_llmpy--llm-diagnostics)
- [test_broker.py — Broker Module Test](#test_brokerpy--broker-module-test)
- [Folder Notes (/tools)](#folder-notes-tools)

---

Command-line utilities for monitoring, diagnostics, and direct interaction with a running OpenForexAI system.
Most tools communicate with the Management API (default `http://127.0.0.1:8765`).

**Prerequisites:**
- For `ask.py`, `monitor.py`, and `logging.py`: start the main system first.
- For `test_llm.py` and `test_broker.py`: project dependencies and valid module credentials are required.

```bash
python -m openforexai.main
```

| Tool | Purpose |
|---|---|
| [`monitor.py`](#monitorpy--console-monitor) | Real-time event stream in the terminal |
| [`ask.py`](#askpy--agent-query-tool) | Query any running agent directly |
| [`logging.py`](#loggingpy--rotating-event-logger) | Persistent rotating JSONL event logging |
| [`test_llm.py`](#test_llmpy--llm-diagnostics) | Deep diagnostics for configured LLM modules |
| [`test_broker.py`](#test_brokerpy--broker-module-test) | Live broker adapter smoke/integration test |

---

## monitor.py — Console Monitor

A terminal-based monitoring tool that polls the OpenForexAI management API and displays
everything that happens inside the running system in real time.

### Purpose

The monitor provides **full observability** into all internal system activity:

| What | Event type |
|---|---|
| LLM prompts sent (system prompt, user message, tool list) | `llm_request` |
| LLM responses received (full text, token counts, tool calls) | `llm_response` |
| Tool calls with all arguments | `tool_call_started` |
| Tool results (full response) | `tool_call_completed` |
| Tool failures | `tool_call_failed` |
| Agent-to-agent EventBus messages | `event_bus_message` |
| DataContainer access (candle reads, snapshots) | `data_container_access` |
| Incoming M5 candles (OHLCV + spread) | `m5_candle_fetched` |
| Account status updates | `account_status_updated` |
| Broker connection / disconnection | `broker_connected`, `broker_disconnected` |
| Candle gaps and repairs | `candle_gap_detected`, `candle_repair_*` |
| Sync discrepancies | `sync_discrepancy_found` |
| System errors and crashes | `system_error` |

The monitor works by polling `GET /monitoring/events` on the management API (default port 8765).
Events are stored in a ring buffer of 1 000 entries on the server side.

---

### Usage

```
python tools/monitor.py [OPTIONS]
```

---

### Parameters

#### Connection

| Parameter | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Management API host |
| `--port PORT` | `8765` | Management API port |
| `--interval SECS` | `2.0` | Poll interval in seconds |
| `--limit N` | `100` | Max events fetched per poll (ring buffer holds 1 000) |

#### Event filters (can be combined)

| Parameter | Shows |
|---|---|
| *(no filter)* | All events |
| `--all` | All events (explicit, overrides other filters) |
| `--errors` | Only errors and alarms (`system_error`, `broker_error`, `tool_call_failed`, etc.) |
| `--llm` | Only LLM communication (`llm_request`, `llm_response`, `llm_error`) |
| `--tools` | Only tool calls (`tool_call_started`, `tool_call_completed`, `tool_call_failed`) |
| `--bus` | Only agent-to-agent EventBus messages (`event_bus_message`) |
| `--data` | Only DataContainer accesses (`data_container_access`) |
| `--filter TYPE1,TYPE2` | Custom comma-separated list of event types |
| `--pair EURUSD` | Only events for a specific currency pair |

#### Display & logging

| Parameter | Description |
|---|---|
| `--no-colour` | Disable ANSI colours (useful for log files or non-TTY output) |
| `--log FILE` | Write **all** events as a JSON array to FILE (full payload, no truncation). Independent of display filters — every event is logged regardless of what the display shows. File is written on clean exit (Ctrl+C). |

---

### Audit log file (`--log`)

The `--log FILE` option collects every event received from the API and writes them
as a **single valid JSON array** when the monitor exits cleanly (Ctrl+C).  Key properties:

- **All events are logged** — the display filter (`--llm`, `--errors`, etc.) does NOT
  affect the log file.  Every event that arrives goes to the file.
- **Full payload, no truncation** — `messages`, `system_prompt`, `content`, `result`,
  `arguments`, `tool_call_details` etc. are written in their entirety.
- **Valid JSON** — the file is a proper JSON array `[...]`, readable by any JSON editor.
- **Write mode** — the file is overwritten on each monitor start.
- **Written on clean exit** — the file is saved when you press Ctrl+C. If the process
  is killed hard (e.g. `kill -9`), the file may not be written.

#### Log format

The file is a JSON array; each element is an event object:

```json
[
  {
    "id": "uuid",
    "timestamp": "2026-03-02T12:34:56.123456+00:00",
    "source": "agent:OAPR1_EURUSD_AA_ANLYS",
    "event_type": "llm_response",
    "broker": "OAPR1",
    "pair": "EURUSD",
    "payload": {
      "turn": 2,
      "content": "...full LLM response text without any truncation...",
      "messages": ["...complete conversation history..."],
      "tool_call_details": ["...complete tool call inputs..."]
    }
  }
]
```

#### Verifying completeness

To verify that payloads are truly stored without truncation:

```bash
# Start monitor with log file
python tools/monitor.py --llm --log audit.json

# In another terminal: inspect the log after Ctrl+C
python -c "
import json
with open('audit.json') as f:
    events = json.load(f)
    for e in events:
        if e['event_type'] == 'llm_response':
            content = e['payload'].get('content', '')
            print(f'content length: {len(content)} chars')
            msgs = e['payload'].get('messages', [])
            print(f'messages in request: {len(msgs)}')
"
```

---

### Examples

```bash
# Show everything
python tools/monitor.py

# Watch only what the LLM is thinking
python tools/monitor.py --llm

# Watch tool calls for EURUSD only
python tools/monitor.py --tools --pair EURUSD

# Watch only errors (ideal for debugging)
python tools/monitor.py --errors

# Watch agent communication
python tools/monitor.py --bus

# Watch DataContainer reads (what data agents are working with)
python tools/monitor.py --data

# Combine: LLM + tools (full agent decision cycle)
python tools/monitor.py --llm --tools

# Custom filter
python tools/monitor.py --filter llm_response,tool_call_completed,account_status_updated

# Fast polling for live trading monitoring
python tools/monitor.py --interval 0.5 --limit 200

# Write complete audit log (all events, full payload) while showing LLM events on screen
python tools/monitor.py --llm --log audit.json

# Save display output to file (no colour codes) AND write audit log
python tools/monitor.py --no-colour --log audit.json > display.log
```

---

### Display format

**Error events** (`system_error`, `broker_error`, `tool_call_failed`, etc.) are rendered as
a prominent multi-line block with all payload fields:

```
────────────────────────────────────────────────────────────────────────────────
!!! SYSTEM_ERROR !!!  2026-03-02 12:34:56  OAPR1_EURUSD_AA_ANLYS
  agent_id:             OAPR1_EURUSD_AA_ANLYS
  message:              Init failed: KeyError: 'azure_openai'
────────────────────────────────────────────────────────────────────────────────
```

**LLM and tool events** are shown as multi-line blocks.  Long text fields
(`content`, `system_prompt`, `result`) are display-truncated at 2 000 chars
with a note; **full data is always in the `--log` file**:

```
────────────────────────────────────────────────────────────────────────────────
▶ LLM_RESPONSE  2026-03-02 12:34:58  ANLYS  [OAPR1/EURUSD]
  turn:                 1
  stop_reason:          stop
  model:                gpt-5.2
  input_tokens:         3421
  output_tokens:        187
  tool_calls:           0
  content:              Based on the current M15 structure, I see a clear bear...
                        (display truncated at 2000 chars — full 4821 chars in --log file)
  messages:             [8 items — full data in --log file]
────────────────────────────────────────────────────────────────────────────────
```

Large list fields (`messages`, `tool_specs`, `tool_call_details`) are shown as
an item count only — the full JSON is always written to the `--log` file.

**All other events** appear as compact single lines:

```
2026-03-02 12:35:00  account_status_updated          [OAPR1]  balance='10000.00'  equity='10034.21'
2026-03-02 12:35:00  m5_candle_fetched               [OAPR1/EURUSD]  open='1.08210'  close='1.08234'
```

---

### Reconnect behaviour

If the connection to the management API is lost (e.g. system restart), the monitor:
1. Prints `Connection lost — retrying...` and keeps polling
2. On reconnect, scans the ring buffer for any **errors that occurred while disconnected**
   and displays them with a banner before resuming normal output

---

### Notes

- The ring buffer on the server holds **1 000 events**. At high activity (many tool calls,
  fast polling) older events may be overwritten. Use `--limit 500` or higher if needed.
- The monitor itself has **no impact** on system performance — all monitoring is
  fire-and-forget on the server side.
- This tool is the **first stage** of the observability stack. A graphical dashboard
  with agent timelines and decision traces is planned for a future release.

---

## ask.py — Agent Query Tool

A command-line tool for sending questions or instructions to any running agent and
receiving its response directly in the terminal.

### Purpose

`ask.py` lets you interact with any agent (AA, BA, GA) as if you were another agent
on the EventBus.  The question is delivered directly to the target agent's inbox,
the agent runs a full LLM + tool cycle to answer it, and the response is returned
to your terminal.

Useful for:
- Ad-hoc market analysis without waiting for the next timer cycle
- Querying agent state ("what are your open positions?")
- Testing agent behaviour and system prompt responses
- Debugging tool availability and data access

### How it works

```
ask.py  →  POST /agents/{id}/ask  →  Management API
                                           │
                                    AGENT_QUERY event
                                    (direct to agent inbox)
                                           │
                                        Agent
                                    (LLM + tool calls)
                                           │
                                    AGENT_QUERY_RESPONSE
                                           │
                                    Management API  →  ask.py
```

The Management API blocks until the agent publishes its response, then returns it
to `ask.py`.  The agent runs a complete decision cycle — it can use all its configured
tools (candles, indicators, account status, etc.) to answer the question.

---

### Usage

```
python tools/ask.py --list
python tools/ask.py --agent <AGENT_ID> --request "<question>"
```

---

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `--list` | — | List all currently registered agents |
| `--agent AGENT_ID` | — | Target agent ID (use `--list` to see available IDs) |
| `--request QUESTION` | — | Question or instruction to send to the agent |
| `--timeout SECS` | `120` | Seconds to wait for the agent's response (5–300) |
| `--host HOST` | `127.0.0.1` | Management API host |
| `--port PORT` | `8765` | Management API port |
| `--api-key KEY` | `$MANAGEMENT_API_KEY` | API key for authenticated deployments |
| `--no-colour` | — | Disable ANSI colours |

`--list` and `--agent` are mutually exclusive. `--request` is required when `--agent` is used.

---

### Examples

```bash
# See which agents are currently running
python tools/ask.py --list

# Ask the Analysis Agent for a market assessment
python tools/ask.py --agent OAPR1_EURUSD_AA_ANLYS \
    --request "What is the current EURUSD trend on H1?"

# Ask the Broker Agent for open positions
python tools/ask.py --agent OAPR1_ALL..._BA_TRADE \
    --request "Show me all open positions and their current P&L."

# Quick check with short timeout
python tools/ask.py --agent OAPR1_EURUSD_AA_ANLYS \
    --request "Give me a one-line directional bias for EURUSD." \
    --timeout 30

# With API key
python tools/ask.py --api-key mysecret \
    --agent OAPR1_EURUSD_AA_ANLYS --request "RSI status?"
```

---

### Output

**`--list`:**

```
Agent ID                                  Queue   MaxQueue
────────────────────────────────────────────────────────────
  OAPR1_EURUSD_AA_ANLYS                       0       1000
  OAPR1_ALL..._BA_TRADE                       0       1000
  SYSTM_ALL..._GA_CFGSV                       0       1000
```

Colour coding: cyan = AA (Analysis), green = BA (Broker), yellow = GA (Global).

**`--agent ... --request ...`:**

```
[12:34:56 UTC] Sending query to OAPR1_EURUSD_AA_ANLYS
────────────────────────────────────────────────────────────
  What is the current EURUSD trend on H1?
────────────────────────────────────────────────────────────
Waiting up to 120s for response…

[12:35:09 UTC] Response from OAPR1_EURUSD_AA_ANLYS
────────────────────────────────────────────────────────────
  {
    "bias": "BIAS_LONG",
    "reasoning": "EMA50 above EMA200, RSI at 61, H1 structure bullish",
    "trade_management": "HOLD"
  }
────────────────────────────────────────────────────────────
correlation_id: 3f2a1c8e-...
```

JSON responses are automatically pretty-printed. Plain-text responses are shown as-is.

---

### Notes

- **Any agent can be queried** — AA, BA, and GA agents all support `agent_query`.
- **Response time** = agent LLM latency + tool call time. Typically 3–20 seconds
  depending on how many tools the agent calls to formulate its answer.
- **Set `--timeout` generously** — if the agent needs to fetch candles, calculate
  indicators, and call the LLM multiple times, a 30s timeout may be too short.
- **The query is visible in `monitor.py`** — use `python tools/monitor.py --bus`
  or `--llm` in a second terminal to watch the agent process your question in real time.
- **The agent uses its full tool set** — it has access to all configured tools
  (market data, indicators, account info, etc.) when answering your question.

---

## logging.py — Rotating Event Logger

`logging.py` continuously polls `GET /monitoring/events` and writes each event as one JSON object per line (JSONL / ndjson).

### Key behavior

- Adds `logged_at_utc` timestamp to every written line.
- Rotates files by size (`--max-size` MB).
- Renames closed files to include start and end UTC timestamps.
- Enforces retention by file count (`--max-files`, `0` = unlimited).

### Usage

```bash
python tools/logging.py
python tools/logging.py --dir ./logs --max-size 10 --max-files 20
python tools/logging.py --host 127.0.0.1 --port 8765 --interval 2.0
```

### Important parameters

| Parameter | Default | Description |
|---|---|---|
| `--dir` | `tools` | Output directory for `fai_*.log` files |
| `--max-size` | `10` | Rotate when active file exceeds this size (MB) |
| `--max-files` | `20` | Keep at most N log files (`0` = unlimited) |
| `--interval` | `2.0` | Poll interval in seconds |
| `--host`, `--port`, `--api-key` | varies | Management API connection settings |

---

## test_llm.py — LLM Diagnostics

`test_llm.py` is a verbose diagnostic tool for one configured LLM module (`config/modules/llm/<name>.json5`).
It is designed to surface subtle failures (including adapter retry/fallback behavior).

### Usage

```bash
python tools/test_llm.py <llm_module_name>
# examples
python tools/test_llm.py azure_openai
python tools/test_llm.py azure_oai_mini
```

### What it checks

- Module config load and sanity hints.
- Adapter `complete()` call.
- Adapter `complete_with_tools()` behavior.
- Azure-specific raw API probes (when applicable).
- Error-chain inspection with status/code/response-body hints.

Exit codes:
- `0`: all checks passed
- `1`: at least one failure
- `2`: no failure, but warnings exist

---

## test_broker.py — Broker Module Test

`test_broker.py` validates one broker module (`config/modules/broker/<name>.json5`) end-to-end.

### Usage

```bash
python tools/test_broker.py <broker_module_name>
# examples
python tools/test_broker.py oanda
python tools/test_broker.py mt5
```

### What it tests

1. Connect/disconnect.
2. Account status retrieval.
3. Open positions retrieval.
4. Historical M5 candle retrieval.
5. Fast patched background M5 loop event emission.
6. Optional live M5 streaming window (Ctrl+C to stop).

Exit code:
- `0`: all tests passed
- `1`: at least one test failed

---

## Folder Notes (`/tools`)

Besides scripts, this folder may contain runtime artifacts generated by tooling sessions, for example:

- `audit.jsonl`, `audit_*.jsonl` (monitor/audit outputs)
- `fai_*.log` (rotating logger outputs)
- `__pycache__/` bytecode cache

These are operational artifacts, not documentation sources.

