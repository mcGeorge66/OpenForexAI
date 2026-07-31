[Back to UI Handbook](ui.en.md)

# Monitor — Handbook

The **Monitor** is OpenForexAI's live event-stream viewer. It shows, in real time, every operation flowing through the system's event bus — the primary tool for runtime observation, troubleshooting, and understanding system behavior at any level of detail.

The Monitor controls nothing — it only observes. Unlike the [Event Log](ui.action.event_log.en.md) (a searchable, persistent database archive), the Monitor shows a **transient live stream**: its content is lost on page reload, but in exchange you see events the moment they happen, without waiting on a database query.

---

## 1. Core Concept

### 1.1 One Subscription, One Filter Builder

The UI subscribes to the full event stream **once** over WebSocket (`/ws/monitoring`) and keeps the last **500 events** in memory (a ring buffer). There are **no fixed category tabs** anymore — instead, a single, freely configurable **Filter Builder** right in the Monitor panel filters what's displayed. Switching or changing a filter is purely client-side: no network round-trip, no new subscription, no lost events.

### 1.2 Ring Buffer

The browser keeps the last 500 received events in memory; older events are evicted as new ones arrive. The backend additionally maintains its own separate 1,000-event ring buffer for polling purposes, independent of the WebSocket stream.

**Practical impact:** in active systems with multiple agents, the buffer can fill and start evicting the oldest events within minutes. If you want to keep a specific event permanently reachable, **pin it** (Section 5) instead of relying on the buffer.

**Example of when this bites you:** you're watching `agent_trigger_skipped` events for a specific agent, get pulled away for a minute (a call, another tab), and by the time you're back the event you wanted has already fallen out of the 500-event buffer because plenty of other agents kept running in the meantime. At that point only the persistent [Event Log](ui.action.event_log.en.md) helps — next time, pin the event the moment it reoccurs instead of trying to remember it "for later."

### 1.3 Live Indicator

Top left of the panel:

| Indicator | Meaning |
|-----------|---------|
| `● Live` (green) | WebSocket active, events are being received |
| `○ Disconnected` (red) | WebSocket disconnected — no events are being received |

If `Disconnected`: check backend status on the Initial page, reload the page if needed.

Next to it, two counters are shown: **shown** (how many events are currently in the list after filtering) and **primary** (how many of those are standalone request events, excluding their associated response events — see Section 4).

### 1.4 Auto-Scroll and Ordering

Newest events appear at the **top** of the list (not the bottom). The `Auto`/`Paused` button in the top right controls whether the list auto-scrolls up as new events arrive:

- **Auto** (green) — the list scrolls to the top automatically on every new event.
- **Paused** — auto-scroll is off, e.g. because you're reading further down the list. Scrolling back to the top re-enables Auto automatically.

**Clear** empties the list currently held in the browser (not the backend) — new events appear normally again right after.

---

## 2. Event Row Format

Each event appears as one row:

| Element | Content |
|---------|---------|
| **`[N]` button** (if present) | Number of correlated follow-on events (see Section 4); click to expand/collapse. |
| **Timestamp** | Time with millisecond precision. |
| **`orphan` marker** | Only on response events with no visible parent event in the current buffer (see Section 4). |
| **Event type** | Color-coded per event type (e.g. LLM events in blue tones, errors in red, broker events in green/orange). |
| **`bus`/`agent` badge** | Only on `llm_request`/`llm_response`: whether the event came from the event-bus transport or directly from agent monitoring. |
| **Source** | The triggering agent (e.g. `OXS_T-EURUSD-AA-ANLYS`), if available. |
| **Broker/Pair** | In brackets, if applicable. |
| **Payload preview** | A compact, event-type-specific summary (e.g. for `llm_response`: turn, stop reason, token counts, tool calls, model) instead of raw JSON. |
| **Pin icon** | Appears on hover; pins/unpins this event (Section 5). |

Double-clicking a row opens the [event detail window](#6-event-detail-window) (Section 6).

---

## 3. Filter Builder

The Filter Builder replaces the former fixed category tabs with freely combinable rules.

### 3.1 Rules

Each rule consists of:

| Part | Options |
|------|---------|
| **Join** | `Start` (only on the first rule), `AND`, `AND NOT`, `OR`, `OR NOT` |
| **Field** | `Event Type`, `Source`, `Broker`, `Pair`, `Sender`, `Target`, `Message ID`, `Correlation ID`, `Payload Field` |
| **Operator** | `contains`, `equals`, `starts with`, `ends with`, `exists` |
| **Path** (only for `Payload Field`) | Dot-separated path into the payload JSON, e.g. `decision.confidence` |
| **Value** | Comparison value (not used with `exists`) |

Rules are evaluated **top to bottom**, in the order they were added — each rule's join applies to the running result so far. `+ Rule` adds a new rule, `Remove` deletes it, `New` resets the whole filter (no rules = all primary events shown).

**Example:** "all errors except for the test pair GBPUSD" — two rules: `Start: Event Type contains error`, then `AND NOT: Pair equals GBPUSD`. A common mistake is picking `OR NOT` instead — that would widen the result again (any event that *isn't* GBPUSD would also pass, regardless of the error criterion), since `OR` adds the rule independently of the running result so far.

### 3.2 Include responses / Show orphans

- **Include responses** — when enabled, a visible primary request also shows its correlated response events, even if those don't themselves match the filter rules (see Section 4).
- **Show orphans** — when enabled, response events are shown even if their associated request event is no longer in the buffer (e.g. because it was already evicted).

**Recommendation:** leave both enabled by default — otherwise, filtering on `llm_request` for example would show only the requests, not the matching responses, losing exactly the part that's usually most interesting (tokens, result, errors). Only disable `Include responses` when you deliberately want just the request side, e.g. to count how often a particular tool call happens per minute without the response rows cluttering the view.

### 3.3 Saved Filters

A configured filter can be saved under a name:

| Element | Function |
|---------|---------|
| **Name field + Save New** | Saves the current rule combination plus its `Include responses`/`Show orphans` setting under this name. |
| **Update** | Overwrites the currently loaded saved filter with the current state. |
| **Delete** | Deletes the currently loaded saved filter. |

Saved filters are stored centrally in `system.json5` (`system.ui.monitor.saved_filters`) — meaning they're **visible to everyone using the system**, not just locally in your own browser. Every saved filter automatically appears as an entry in the Monitor section's **left sidebar**; clicking it loads its rules into the Filter Builder. With no saved filters, the sidebar shows "No saved filters".

**Recommendation:** create a saved filter for every agent you watch regularly (e.g. "EURUSD AA" with the rule `Source contains OXS_T-EURUSD-AA`). Since these filters are visible to everyone, colleagues benefit immediately too — no need to re-explain how to filter down to a specific pair each time. Because the filters live in `system.json5`, check before deleting an unfamiliar saved filter someone else created — it might be actively in use.

---

## 4. Grouped/Correlated Events

Events carrying a `message_id` in their payload are considered **primary** (a standalone request). Events with a `correlation_id` pointing at another event's `message_id` are considered its **response** and are shown indented underneath it by default, once you click the `[N]` badge on the primary row.

- **`[N]`** next to a primary row — number of correlated response events; click to expand/collapse.
- **`orphan`** (highlighted orange) — a response event whose associated request event wasn't found in the current buffer (e.g. already evicted, or outside the current filter with `Include responses` disabled).

This grouping replaces the old, separate "Bus Events" concept: request/response pairs (e.g. an `llm_request` and its matching `llm_response`) now appear together in one place, instead of being split across separate tabs.

**Example:** an agent cycle with three tool calls produces one primary `agent_input_built` event with `[3]` next to it. Clicking it reveals the three matching `tool_call_completed` events indented underneath, in the order they executed — no need to manually hunt through the stream for related events.

**Warning — lots of `orphan` markers right after connecting is usually harmless:** right after opening the Monitor (freshly connected, buffer still empty), the first few response events will almost always show as `orphan`, because their request already happened earlier and isn't in the buffer anymore. That's normal, not a bug. If orphans keep piling up persistently during normal operation, though, that suggests very short gaps between request and eviction (the buffer is filling up very fast) — tighten your filter to push fewer irrelevant events through the buffer.

---

## 5. Pinned Events

A dedicated **"Pinned Events"** section appears above the event list whenever at least one event is pinned (collapsible).

- **Manual pinning:** click a row's pin icon. Pinned events are held in a protected buffer on the backend that is **not** subject to ring-buffer eviction — they stay reachable even after the browser's 500-event buffer has long since moved on. Clicking `PinOff` removes the pin.
- **Automatic pinning:** certain error/failure event types are auto-pinned by the system itself as soon as they occur — marked with an `auto` badge in the pinned list:
  - `system_error`
  - `llm_error`
  - `llm_turn_failed`
  - `ec_run_failed`
  - `tool_call_failed`
  - `broker_error`
  - `broker_disconnected`

The pinned section is re-fetched from the backend every 5 seconds (`GET /monitoring/pinned`), independent of the WebSocket stream — so it still shows content even if the live connection was briefly interrupted.

**Recommendation:** pinned events are shared, system-wide state (not just your own browser) — useful for pointing a colleague at a specific problem without exchanging screenshots: just pin it and say "check the Pinned section." Don't forget to unpin (`PinOff`) once resolved — otherwise the pinned section accumulates stale cases over time, unnecessarily burying the ones that actually matter (the auto-pinned failures).

---

## 6. Event Detail Window

Double-clicking a row (including in the pinned section) opens a floating, **draggable and resizable** window with the full event data.

### 6.1 Title Bar

- Event type (color-coded), timestamp, broker/pair (if applicable)
- **Copy icon** — copies the full JSON payload to the clipboard
- **Close icon** (also: **Escape** key)

### 6.2 Context Strip

| Field | Content |
|-------|---------|
| **What / Why** | Plain-language explanation of what this event type means and why it fired — from a built-in catalogue of the most common event types. Unknown types show a note that no description is available. |
| **Source** | The triggering module (e.g. `agent:OXS_T-EURUSD-AA-ANLYS`, `broker.OXS_T`). |
| **Sender / Target** | Bus routing metadata, if present in the payload. |
| **Broker** | Broker module and pair, if relevant. |
| **Msg / Corr** | The event's `message_id` or `correlation_id`, if present — useful for manually finding the same chain in the [Event Log](ui.action.event_log.en.md). |

### 6.3 Payload

Full JSON, with `\n` and `\"` escape sequences resolved for readability. Nothing is truncated.

### 6.4 Dragging, Resizing, Multiple Windows

Click and drag the title bar to move; drag any edge/corner to resize. The window does not auto-refresh — it stays fixed on the event you opened, even as new events keep arriving. The most recently double-clicked row stays highlighted dark orange until another row is clicked.

**Warning:** only **one** detail window can be open at a time — double-clicking another row replaces the currently open window instead of opening a second one alongside it. To directly compare two payloads (e.g. `llm_request` vs. its matching `llm_response`), your best bet is usually: copy the first payload via the copy icon, then open the second event.

---

## 7. Practical Debug Workflows

### 7.1 Watching a Full Analysis Cycle for a Pair

1. Filter Builder: add a rule `Source contains OXS_T-EURUSD-AA` (or use `Payload Field` with an appropriate path).
2. Click `Clear` to start clean.
3. Wait for the next M5 candle.
4. Follow the chain: `agent_trigger_received` → `candles_request`/`candles_response` → `agent_input_built` → `llm_request` → `llm_turn_started`/`llm_turn_completed` → `llm_response` → `agent_decision_made` → on BUY/SELL: `agent_signal_generated` → `ec_run_started`/`ec_run_completed`.
5. Double-click `llm_response` to see token usage and the decision in the detail window.
6. If you'll need this again, save the filter under a name (e.g. "EURUSD AA cycle").

### 7.2 Finding Out Why an Agent Isn't Running

1. Filter: `Event Type equals agent_trigger_skipped`, optionally `AND Source contains <agent_id>`.
2. Double-click a matching event and check the `reason` field in the payload:
   - `"session_filter"` → agent is outside its configured trading session.
   - `"any_candle_divider"` → the AnyCandle divider hasn't been reached yet.
   - `"runtime_paused"` → the system is paused.
   - `"already_running"` → a previous cycle hasn't finished yet.
   - `"disabled"` → the agent is disabled in configuration.
3. If no `agent_trigger_skipped` shows up at all: set the filter to `Event Type contains m5_candle` and check whether candles are arriving for this pair at all.

### 7.3 Checking LLM Calls and Token Usage

1. Filter: `Event Type starts with llm_`.
2. Start an Execute run in Agent Chat, or wait for a natural cycle.
3. Double-click `llm_response`; check `input_tokens`/`output_tokens`, `latency_ms`, and `decision` in the payload.
4. If `llm_turn_failed` appears instead: check the `reason` field for the failure cause — these failures are also auto-pinned (Section 5), so they won't be lost from the buffer.

### 7.4 Monitoring Broker Connectivity

1. Filter: `Event Type contains broker_`.
2. Watch for `broker_connected` at system startup.
3. Watch `broker_http_request`/`broker_http_response` pairs (expandable via the `[N]` badge) — check `status_code` in the response payload (`200` ok, `4xx` auth/parameter error, `5xx` server error).
4. `broker_disconnected` and `broker_error` are auto-pinned — still findable in the Pinned section even after a full ring buffer.

### 7.5 Investigating a Rejected Trade

1. Filter: `Event Type equals ec_run_output`, `Payload Field` with path `output_type` and value `order_rejected`.
2. Double-click the match; the `details` field in the payload explains the rejection reason.
3. For the full, permanent chain (including from the past), search the [Event Log](ui.action.event_log.en.md) with the same `correlation_id`/`message_id` instead — the Monitor only shows what has streamed through live since the page was last loaded.

---

## 8. Tips for Effective Monitor Use

**Filter instead of scrolling:** in an active system with multiple agents, the unfiltered stream gets unwieldy fast. A targeted rule combination is usually faster than manual scrolling.

**Save recurring filters:** a rule combination you need often (e.g. "errors only," "one specific pair") is worth saving under a name — it then appears permanently in the sidebar, for every user of the system.

**Pin important individual events instead of just copying them:** a pinned event stays reachable even after the buffer has long since moved on — better than copying the payload into an external note.

**Error events are already protected:** the auto-pinned failure types (Section 5) don't need to be manually pinned to avoid losing them.

**Monitor for "now," Event Log for "back then":** use the Monitor for anything happening now or about to happen. Use the [Event Log](ui.action.event_log.en.md) for anything that happened more than a few hundred events ago, or before the last page reload.
