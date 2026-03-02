# OpenForexAI Console Monitor

A terminal-based monitoring tool that polls the OpenForexAI management API and displays
everything that happens inside the running system in real time.

---

## Purpose

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

## Usage

```
python tools/monitor.py [OPTIONS]
```

**Prerequisites:** The main system must be running first:
```
python -m openforexai.main
```

---

## Parameters

### Connection

| Parameter | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Management API host |
| `--port PORT` | `8765` | Management API port |
| `--interval SECS` | `2.0` | Poll interval in seconds |
| `--limit N` | `100` | Max events fetched per poll (ring buffer holds 1 000) |

### Event filters (can be combined)

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

### Display & logging

| Parameter | Description |
|---|---|
| `--no-colour` | Disable ANSI colours (useful for log files or non-TTY output) |
| `--log FILE` | Append **all** events as JSONL to FILE (full payload, no truncation, runs in background). Independent of display filters — every event is logged regardless of what the display shows. |

---

## Audit log file (`--log`)

The `--log FILE` option writes every event received from the API to a JSONL file
(one JSON object per line).  Key properties:

- **All events are logged** — the display filter (`--llm`, `--errors`, etc.) does NOT
  affect the log file.  Every event that arrives goes to the file.
- **Full payload, no truncation** — `messages`, `system_prompt`, `content`, `result`,
  `arguments`, `tool_call_details` etc. are written in their entirety.
- **Runs in background** — a dedicated thread handles file writes; the polling loop
  is never blocked.
- **Append mode** — restarting the monitor appends to an existing log file.
- **Crash-safe** — `flush()` is called after every line.

### Log format

Each line is a JSON object:

```json
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
    "messages": [...complete conversation history...],
    "tool_call_details": [...complete tool call inputs...]
  }
}
```

### Verifying completeness

To verify that payloads are truly stored without truncation:

```bash
# Start monitor with log file
python tools/monitor.py --llm --log audit.jsonl

# In another terminal: inspect the log
python -c "
import json
with open('audit.jsonl') as f:
    for line in f:
        e = json.loads(line)
        if e['event_type'] == 'llm_response':
            content = e['payload'].get('content', '')
            print(f'content length: {len(content)} chars')
            msgs = e['payload'].get('messages', [])
            print(f'messages in request: {len(msgs)}')
"
```

---

## Examples

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
python tools/monitor.py --llm --log audit.jsonl

# Save display output to file (no colour codes) AND write audit log
python tools/monitor.py --no-colour --log audit.jsonl > display.log
```

---

## Display format

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

## Reconnect behaviour

If the connection to the management API is lost (e.g. system restart), the monitor:
1. Prints `Connection lost — retrying...` and keeps polling
2. On reconnect, scans the ring buffer for any **errors that occurred while disconnected**
   and displays them with a banner before resuming normal output

---

## Notes

- The ring buffer on the server holds **1 000 events**. At high activity (many tool calls,
  fast polling) older events may be overwritten. Use `--limit 500` or higher if needed.
- The monitor itself has **no impact** on system performance — all monitoring is
  fire-and-forget on the server side.
- This tool is the **first stage** of the observability stack. A graphical dashboard
  with agent timelines and decision traces is planned for a future release.
