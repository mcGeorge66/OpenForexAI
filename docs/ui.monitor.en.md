[Back to UI Handbook](ui.en.md)

# Monitor — Handbook

The **Monitor** is the live event stream viewer for OpenForexAI. It shows every event that passes through the system's event bus in real time, making it the primary tool for runtime observation, debugging, and understanding system behavior at any level of detail.

The Monitor does not control anything — it only observes. Think of it as an always-on log viewer with intelligent filtering, rich event metadata, and a structured detail window for any event of interest.

---

## 1. Core Concept

### 1.1 Single Subscription, Client-Side Filtering

The UI subscribes to the **full event stream exactly once** via WebSocket. All events flow into a shared ring buffer. The tabs you see are **client-side filters** — switching tabs does not create a new subscription or reload data. It simply changes the filter applied to the buffered events.

This means:
- Switching tabs is instant (no network round-trip).
- You never miss events while reading a different tab.
- The ring buffer always holds the last 1,000 events across all categories.

### 1.2 Ring Buffer

The Monitor stores the **last 1,000 events** in memory. When the buffer is full, the oldest event is dropped to make room for the newest. This is the sliding window of system activity.

Practical implications:
- In active systems with many agents, the buffer may fill within minutes.
- For quiet systems or during debugging, events can persist in the buffer for hours.
- Clicking **Clear** empties the display but does not affect the ring buffer — new events continue to arrive.

### 1.3 Live Indicator

The **live indicator** (green dot in the top-right of the Monitor panel) shows the WebSocket connection status:

| State | Meaning |
|-------|---------|
| Green dot, pulsing | WebSocket active, events are streaming |
| Grey/red dot | WebSocket disconnected — events are not being received |

If the live indicator is not green, refresh the page or check if the backend is running.

---

## 2. Event Row Format

Each event appears as a single row in the Monitor table. Rows are color-coded by event category for fast visual scanning.

### 2.1 Row Columns

| Column | Content |
|--------|---------|
| **Timestamp** | HH:MM:SS.mmm — time of the event with millisecond precision |
| **Arrow indicator** | Direction marker — see below |
| **Event type** | The event name (e.g. `llm_request`, `m5_candle_update`) |
| **Source module** | Which component emitted this event |
| **Payload preview** | First ~80 characters of the JSON payload, truncated |

### 2.2 Arrow Indicators

| Arrow | Meaning |
|-------|---------|
| `<` (left, blue) | **Incoming data** — data arriving from an external source (broker, LLM response) |
| `>` (right, green) | **Outgoing action** — action or signal sent outward (LLM request, order to broker) |
| `!` (exclamation, red/orange) | **Error or warning** — something went wrong or needs attention |

### 2.3 Color Coding by Category

Rows are colored to match their event category:
- **LLM events** — purple/violet tones
- **Tool events** — blue tones
- **Broker events** — orange tones
- **Data events** — teal/cyan tones
- **Core events** — grey/white
- **Bus events** — yellow/gold tones
- **Agent events** — green tones
- **Entity events** — indigo/dark blue

---

## 3. Event Tabs — All Nine Explained

### 3.1 All Events

**Filter:** No filter — shows every event from every component.

The **All Events** tab is the unfiltered fire hose. Use it when you want to see the complete picture of what the system is doing, without restricting to a specific category.

**Best used for:**
- Getting a first impression of system activity.
- Watching a complete analysis cycle unfold from trigger to signal.
- Identifying unexpected event patterns.
- Following a chain of events that spans multiple categories.

**Caution:** In active systems with multiple agents, All Events can scroll very fast. Use the other tabs for focused investigation.

### 3.2 LLM Events

**Filter:** `llm_request`, `llm_response`, `llm_turn_started`, `llm_turn_completed`, `llm_turn_failed`, `llm_error`

The **LLM Events** tab shows all communication with the LLM service.

#### llm_request

Emitted when an agent sends a request to the LLM via the event bus. The event is routed to the LLMService module (e.g. `llm:azure_azmin`).

Payload includes:
- `agent_id` — which agent initiated the request
- `prompt_length` — approximate size of the prompt in tokens
- `model` — which LLM model is targeted
- `request_id` — unique identifier for this request

#### llm_response

Emitted when the LLMService receives a completed response from the LLM provider and sends it back to the requesting agent.

Payload includes:
- `agent_id` — which agent receives the response
- `input_tokens` — tokens consumed by the prompt
- `output_tokens` — tokens in the response
- `latency_ms` — total LLM call duration in milliseconds
- `decision` — extracted decision object (if parsing succeeded)
- `request_id` — matches the originating `llm_request`

#### llm_turn_started

Emitted at the start of an LLM turn within an agent cycle. Useful for timing: this event marks when the agent actually begins waiting for an LLM response.

#### llm_turn_completed

Emitted when the LLM turn completes successfully. Pairs with `llm_turn_started` for duration calculation.

#### llm_turn_failed

Emitted when an LLM turn fails — timeout, API error, network error, or parsing failure. Payload includes:
- `reason` — the failure reason
- `error_code` — HTTP status or error category
- `retry_count` — how many retries were attempted

#### llm_error

Generic LLM error event for errors that occur outside of a specific turn (e.g. connection failures, authentication errors).

**LLM Events tab is best used for:**
- Diagnosing LLM connectivity issues.
- Checking token consumption per agent cycle.
- Verifying that requests are being sent and responses received.
- Investigating LLM latency (input/output timing visible in `llm_response`).
- Checking if decision parsing is succeeding or failing.

### 3.3 Tool Events

**Filter:** `tool_call_started`, `tool_call_completed`, `tool_call_failed`

The **Tool Events** tab tracks all tool invocations dispatched by the ToolDispatcher during agent cycles.

#### tool_call_started

Emitted immediately before a tool function is executed.

Payload includes:
- `tool_name` — which tool is being called (e.g. `get_candles`, `calculate_indicator`)
- `agent_id` — which agent initiated the tool call
- `parameters` — the input parameters passed to the tool
- `call_id` — unique identifier for this call

#### tool_call_completed

Emitted after a successful tool execution.

Payload includes:
- `tool_name`
- `agent_id`
- `call_id`
- `duration_ms` — execution time in milliseconds
- `result_summary` — brief description of the result (e.g. `"returned 200 candles"`)

#### tool_call_failed

Emitted when a tool execution fails.

Payload includes:
- `tool_name`
- `agent_id`
- `call_id`
- `error` — error description
- `duration_ms`

**Tool Events tab is best used for:**
- Verifying that all tool calls during a cycle completed successfully.
- Identifying slow tools that are increasing cycle duration.
- Diagnosing failed tool calls that may be causing empty or incomplete snapshots.
- Understanding which tools an agent calls and in what order.

### 3.4 Broker Events

**Filter:** Broker connectivity, HTTP traffic, sync events, account status events

The **Broker Events** tab shows all interactions between OpenForexAI and the connected broker adapters.

#### broker_connected

Emitted when a broker adapter successfully establishes connection. Payload includes the broker module ID and account details.

#### broker_disconnected

Emitted when a broker connection is lost. Payload includes the reason if known (e.g. timeout, HTTP error).

#### broker_reconnecting

Emitted when the broker adapter begins an automatic reconnection attempt. Payload includes the attempt number and backoff delay.

#### broker_http_request

Emitted for every HTTP request sent to the broker API. Payload includes:
- `method` (GET/POST/PUT/PATCH)
- `endpoint` — the API endpoint
- `broker_id` — which broker module
- `body` (for POST/PUT requests)

#### broker_http_response

Emitted for every HTTP response received from the broker API. Payload includes:
- `status_code` — HTTP status (200, 400, 401, 500 etc.)
- `broker_id`
- `response_time_ms` — how long the API call took
- `body_summary` — partial response body

#### sync_check_started

Emitted when a BA agent begins a sync check — verifying that locally tracked positions match what the broker has open.

#### sync_check_completed

Emitted when sync check completes. If a discrepancy was found:
- `sync_detected: true` — a position was found closed at the broker that was open locally
- `position_id` — which position
- `action_taken` — what OpenForexAI did (e.g. `"marked_closed_sync_detected"`)

**Broker Events tab is best used for:**
- Diagnosing broker connection problems.
- Watching API calls for a specific trade execution.
- Verifying that sync checks are running and completing.
- Investigating 4xx/5xx HTTP errors from the broker API.

### 3.5 Data Events

**Filter:** Candle pipeline events, indicator calculation events

The **Data Events** tab shows the flow of market data through the system.

#### m5_candle_update

Emitted every time a new M5 candle is received from the broker's candle polling service. This is the primary system heartbeat — all agent triggers originate from this event.

Payload includes:
- `pair` — which currency pair
- `broker_id`
- `candle` — the new candle data (timestamp, open, high, low, close, volume)
- `is_new` — whether this is a newly closed candle or a partial update

#### m5_candle_saved

Emitted after a new M5 candle has been persisted to the database.

#### candles_request

Emitted when an agent or tool requests candle data (e.g. during snapshot building). Payload includes the requested pair, timeframe, and count.

#### candles_response

Emitted when the candle data request is fulfilled. Payload includes count of candles returned and the timeframe.

#### indicator_request

Emitted when an indicator calculation is requested.

#### indicator_response

Emitted when indicator calculation completes. Payload includes the indicator type, period, and result values.

**Data Events tab is best used for:**
- Verifying that M5 candles are arriving consistently (system heartbeat check).
- Checking that candles are being saved to the database.
- Diagnosing data gaps or missing candles.
- Watching indicator calculations during agent cycles.

### 3.6 Core Events

**Filter:** Agent trigger events, snapshot build events, agent backlog events

The **Core Events** tab shows the lifecycle of agent cycles — from trigger to signal.

#### agent_trigger_received

Emitted when an agent's trigger condition is met and a cycle begins. This is the starting point of every analysis cycle.

Payload includes:
- `agent_id`
- `trigger_type` — what triggered the agent (e.g. `m5_candle`)
- `pair`
- `candle_timestamp` — the candle that triggered this cycle

#### agent_trigger_skipped

Emitted when a trigger was received but the agent did not start a cycle. **This is the key event for debugging why an agent is not running.**

Payload includes:
- `agent_id`
- `reason` — why the trigger was skipped. Possible values:
  - `"session_filter"` — current time is outside the agent's configured trading session
  - `"any_candle_divider"` — the agent is configured to only run every N candles, and this was not the Nth
  - `"runtime_paused"` — the system is in Suspend mode
  - `"already_running"` — a previous cycle has not yet completed
  - `"disabled"` — the agent is disabled in configuration

#### agent_backlog_detected

Emitted when an agent's trigger queue has more unprocessed triggers than a configured threshold. This indicates the agent is falling behind.

Payload includes:
- `agent_id`
- `backlog_size` — number of pending triggers
- `oldest_pending_ms` — how old the oldest pending trigger is

#### agent_input_built

Emitted when the full agent input (snapshot) has been assembled and is ready to be sent to the LLM. This marks the end of the data-gathering phase.

Payload includes:
- `agent_id`
- `snapshot_size_bytes` — size of the assembled snapshot
- `build_duration_ms` — how long it took to build the snapshot

#### agent_decision_snapshot_built

Emitted when the decision snapshot (structured output) has been successfully built from the LLM response.

#### agent_decision_snapshot_invalid

Emitted when the LLM response could not be parsed into a valid decision snapshot. This means the LLM returned something that did not match the expected JSON structure.

Payload includes:
- `agent_id`
- `reason` — why validation failed (e.g. missing required field, wrong value type)
- `raw_response_preview` — first 200 characters of the raw LLM response

**Core Events tab is best used for:**
- Confirming that agents are being triggered as expected.
- Diagnosing why an agent is not running (check `agent_trigger_skipped` and its `reason` field).
- Watching the snapshot build process.
- Identifying LLM response parsing failures.

### 3.7 Bus Events

**Filter:** All event bus routing events

The **Bus Events** tab shows every message routed through the internal event bus, with full sender and target information.

Bus events are the infrastructure layer: every llm_request, signal, trigger, and response is routed through the bus, and Bus Events shows the routing metadata.

Each bus event row includes:
- `sender` — the agent or module that sent the message (e.g. `agent:OXS_T-EURUSD-AA-ANLYS`)
- `target` — the intended recipient (e.g. `llm:azure_azmin`, `agent:OXS_T-EURUSD-BA-TRADE`)
- `event_type` — the type of the routed message
- `routing_rule` — which routing rule matched (if applicable)

**Bus Events tab is best used for:**
- Verifying that signals are routed from AA to BA agents correctly.
- Watching the full LLM call chain (request from agent → LLMService → response back to agent).
- Diagnosing routing misconfigurations where signals are not reaching their targets.
- Understanding the message flow between system components.

### 3.8 Agent Events

**Filter:** Agent decision and signal events

The **Agent Events** tab shows events related to agent decision-making and signal generation.

#### agent_decision_made

Emitted when an agent has made a trading decision. This is the primary output event of an AA analysis cycle.

Payload includes:
- `agent_id`
- `decision` — BUY, SELL, or HOLD
- `confidence` — 0–100
- `entry`, `stop_loss`, `take_profit`
- `reasoning_summary` — brief text from the LLM
- `entry_quality`

#### agent_signal_generated

Emitted when a signal (BUY or SELL) is generated and sent to the BA agent. HOLD decisions do not generate signals.

Payload includes:
- `agent_id` (AA agent)
- `target_agent_id` (BA agent that will receive the signal)
- `signal_type` — BUY or SELL
- `signal_id` — unique identifier for this signal

#### agent_input_built

(Also visible in Core Events.) The assembled snapshot sent to the LLM.

**Agent Events tab is best used for:**
- Confirming that AA agents are generating decisions.
- Verifying that BUY/SELL signals are being sent to BA agents.
- Monitoring confidence levels and decision types over time.
- Checking whether the agent is consistently choosing HOLD (which means no trades will be placed).

### 3.9 Entity Events

**Filter:** EntityController (EC) run events

The **Entity Events** tab shows the lifecycle of EntityController runs — the structured execution units that process signals and manage trade state.

#### ec_run_started

Emitted when an EntityController run begins. This happens when the BA agent receives a signal and begins processing it.

#### ec_run_completed

Emitted when an EC run completes successfully.

Payload includes:
- `ec_id`
- `agent_id`
- `duration_ms`
- `output_summary` — brief description of what the EC run produced

#### ec_run_failed

Emitted when an EC run fails. Payload includes the error reason and stack trace summary.

#### ec_run_output

Emitted for the specific output of an EC run (e.g. order placed, order rejected). Payload includes:
- `output_type` — `order_placed`, `order_rejected`, `position_update`, etc.
- `details` — specific details of the output

**Entity Events tab is best used for:**
- Verifying that BA agent signals are being processed.
- Diagnosing why a trade was or was not executed.
- Watching the full execution chain for a specific signal.

---

## 4. Double-Click Event Detail Window

Double-clicking any event row opens the **Event Detail Window** — a floating, draggable, and resizable window that shows the full event data with context.

### 4.1 Window Layout

#### Title Bar

The title bar shows:
- **Event type** — the full event name (e.g. `llm_response`)
- **Timestamp** — HH:MM:SS.mmm
- **Broker/Pair** — if applicable to this event
- **Copy button** — copies the full JSON payload to clipboard
- **Close button** — closes the window (also: press **Escape**)

#### Context Strip

The context strip is located between the title bar and the JSON payload. It provides human-readable context for the event:

| Field | Content |
|-------|---------|
| **What** | Plain-English description of what this event type represents |
| **Why** | Why this event was emitted and what it triggers or signals next |
| **Source** | The `source_module` field — which component produced this event (e.g. `agent:OXS_T-EURUSD-AA-ANLYS`, `broker.OXS_T`, `eventbus`) |
| **Sender** | The bus sender agent ID (if routed via event bus) |
| **Target** | The bus target agent ID (if this event was directed to a specific agent) |
| **Broker/Pair** | The broker module and currency pair, if relevant |

The context strip turns raw technical events into understandable information — you don't need to know every event name by heart. The **What** and **Why** fields explain each event type in plain English.

#### JSON Payload

The full event payload is displayed as **pretty-printed JSON**:
- All fields are expanded (no collapsed objects)
- `\n` escape sequences are rendered as actual line breaks
- `\"` escape sequences are rendered as actual quotes
- Long strings are not truncated — the full payload is always shown
- Use the **Copy button** in the title bar to copy the entire payload

### 4.2 Dragging and Resizing

The detail window is:
- **Draggable** — click and drag the title bar to reposition
- **Resizable** — drag any edge or corner to resize

This allows you to position the detail window alongside the event list so you can continue scanning events while reading the detail.

### 4.3 Selected Row Highlight

After you close the detail window, the row you double-clicked remains **highlighted in dark orange** in the event list. This makes it easy to find the event you were inspecting again, even if many new events have arrived.

The highlight persists until you click another row or explicitly clear it.

### 4.4 Keyboard Shortcut

Press **Escape** to close the detail window without using the mouse.

---

## 5. Controls

### 5.1 Clear Button

The **Clear** button empties the current display. The ring buffer continues to receive new events, and new events will appear immediately after clearing. Clear is useful to get a clean view before triggering a specific action you want to observe.

**Note:** Clear only affects the display. The 10,000-event ring buffer is not reset — it continues accumulating events. If you re-open a tab after clearing, you will not see the old events again.

### 5.2 Live Indicator

The live indicator shows the WebSocket connection status. If it is not green:
1. Check if the backend is running (Initial page — system status).
2. Refresh the page.
3. If the backend is running and the indicator stays grey: check browser console for WebSocket connection errors.

---

## 6. LLM Architecture — Event Bus Flow (since v0.7)

Since version 0.7, **all LLM calls are routed through the Event Bus**. This is a significant architectural change that makes the full LLM call chain visible in the Monitor.

### 6.1 The Complete LLM Call Chain

```
Agent Analysis Cycle
  → Snapshot built (agent_input_built)
  → llm_request emitted to Event Bus
  → Event Bus routes to LLMService (llm:azure_azmin)
  → LLMService: llm_turn_started
  → LLMService calls Azure OpenAI API (HTTP)
  → Azure OpenAI API responds
  → LLMService: llm_turn_completed
  → LLMService emits llm_response to Event Bus
  → Event Bus routes response back to originating Agent
  → Agent processes LLM response
  → agent_decision_made emitted
```

### 6.2 Where to See Each Step in the Monitor

| Step | Tab | Event |
|------|-----|-------|
| Snapshot assembled | Core Events | `agent_input_built` |
| LLM request sent from agent | Bus Events | `llm_request` (sender = agent, target = llm:...) |
| LLM turn begins | LLM Events | `llm_turn_started` |
| LLM turn ends | LLM Events | `llm_turn_completed` |
| LLM response routed back | Bus Events | `llm_response` (sender = llm:..., target = agent) |
| Decision extracted | Agent Events | `agent_decision_made` |

This means you can trace the **full round-trip** of an LLM call entirely within the Monitor, without needing to check server logs.

---

## 7. Practical Debugging Workflows

### 7.1 Watching a Complete EURUSD Analysis Cycle

Goal: Observe a full analysis cycle from M5 trigger to trade signal.

1. Open the Monitor. Switch to **All Events** tab.
2. Click **Clear** to start fresh.
3. Wait for the next M5 candle (visible in Data Events or All Events as `m5_candle_update`).
4. Watch for the following sequence:
   - `m5_candle_update` (pair: EUR_USD)
   - `agent_trigger_received` (agent: OXS_T-EURUSD-AA-ANLYS)
   - Tool calls: `candles_request` / `candles_response` for multiple timeframes
   - `agent_input_built` — snapshot ready
   - `llm_request` in Bus Events — sent to LLM
   - `llm_turn_started` in LLM Events
   - `llm_turn_completed` in LLM Events
   - `llm_response` in Bus Events — returned to agent
   - `agent_decision_made` in Agent Events
   - (If BUY/SELL:) `agent_signal_generated` → `ec_run_started` → `ec_run_completed`
5. Double-click `agent_decision_made` to see the full decision in the detail window.

### 7.2 Debugging Why an Agent Is Not Running

Goal: Find out why no agent cycles are occurring.

1. Open the Monitor. Switch to **Core Events** tab.
2. Wait 5–10 minutes (at least one M5 candle interval).
3. Look for `agent_trigger_skipped` events for the agent in question.
4. Double-click the event to open the detail window.
5. Read the **`reason`** field in the payload:
   - `"session_filter"` → Agent is outside its configured trading session. Check session configuration.
   - `"any_candle_divider"` → Agent is configured to run every N candles, and this was not the Nth.
   - `"runtime_paused"` → System is suspended. Click Continue on the Initial page.
   - `"already_running"` → Previous cycle is still in progress (slow LLM or many tools).
   - `"disabled"` → Agent is disabled in config. Check `system.json5`.
6. If there is no `agent_trigger_skipped` event either: check **Data Events** tab for `m5_candle_update`. Are candles arriving for this pair?

### 7.3 Verifying LLM Calls and Token Consumption

Goal: Confirm LLM calls are working and check token usage.

1. Switch to **LLM Events** tab.
2. Trigger an Execute run in Agent Chat (or wait for a natural cycle).
3. Watch for `llm_turn_started` followed by `llm_turn_completed`.
4. Double-click `llm_response` to see the detail window.
5. In the payload, check:
   - `input_tokens` and `output_tokens` — total token usage
   - `latency_ms` — how long the LLM call took
   - `decision` — was the decision successfully extracted?
6. If you see `llm_turn_failed` instead: check the `reason` field for the error.

### 7.4 Checking Broker Connection Health

Goal: Verify the broker is connected and responding correctly.

1. Switch to **Broker Events** tab.
2. Look for `broker_connected` (should have appeared at system startup).
3. Watch for `broker_http_request` / `broker_http_response` pairs — these occur during candle polling and sync checks.
4. In `broker_http_response`: check the `status_code` field.
   - `200` — all good
   - `4xx` — authentication or parameter error
   - `5xx` — broker-side server error
5. If you see `broker_disconnected` followed by `broker_reconnecting`: the system is attempting auto-recovery. Watch for `broker_connected` to confirm success.

### 7.5 Debugging Event Routing

Goal: Verify that signals are being routed from AA to BA agents correctly.

1. Switch to **Bus Events** tab.
2. Trigger an Execute run in Agent Chat for the AA agent.
3. Watch for `agent_signal_generated` in the bus event stream.
4. Double-click the event. In the context strip:
   - **Sender** should be the AA agent ID.
   - **Target** should be the BA agent ID.
5. If the target is wrong or missing: check the event routing configuration in Config → Event Routing.
6. After the signal: watch for `ec_run_started` in Entity Events to confirm the BA agent received it.

### 7.6 Investigating a Rejected Trade

Goal: Find out why a trade was rejected.

1. Switch to **Entity Events** tab.
2. Look for `ec_run_output` with `output_type: "order_rejected"`.
3. Double-click the event. The payload's `details` field explains the rejection reason:
   - Risk limit exceeded
   - Duplicate signal detected
   - Broker API rejection (with status code)
   - Invalid SL/TP values
4. Also check **Broker Events** for the `broker_http_response` around the same timestamp — if the broker rejected the order, the HTTP response will show a 4xx status with an error message.

---

## 8. Tips for Effective Monitor Use

**Use the right tab:** All Events is overwhelming in an active system. Use the specific tabs when investigating a particular area. Only fall back to All Events when you need to see cross-category sequences.

**Clear before triggering:** If you want to watch a specific action (like an Execute run), clear the display first, then trigger the action. You'll get a clean, focused event stream.

**Double-click liberally:** The context strip in the detail window explains every event type in plain English. Even if you don't know what an event means, double-clicking it will tell you.

**Keep detail window open:** The detail window doesn't auto-update. You can leave it open while new events arrive — it stays pinned to the event you opened. The dark orange highlight on the selected row ensures you can find it again.

**Ring buffer fills fast:** In active systems, 10,000 events can accumulate within a few minutes. For long debug sessions, check the most relevant tab frequently rather than relying on scrolling back far.

**Combine with Agent Chat:** For the deepest insight, run an Execute cycle in Agent Chat while monitoring the LLM Events and Core Events tabs. You'll see the snapshot being built (Core Events) and the LLM call being processed (LLM Events) in real time while the Execute result appears in the Chat panel.
