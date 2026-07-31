[Back to Action](ui.action.en.md)

# Event Log — Handbook

The **Event Log** is the searchable, **persisted** archive of every event the system has ever written to the database. It is deliberately separate from the [Monitor](ui.monitor.en.md): the Monitor shows the **live stream** of the last few hundred events, loses its content on page reload, and only shows what's happening right now. The Event Log instead queries the database — it finds events from days or weeks ago and survives a browser restart.

**Rule of thumb for which tool to use:** watching something happen right now or about to happen → Monitor. Investigating something that already happened (yesterday's trade, last week's error) → Event Log.

---

## 1. Header and Filters

| Element | Function |
|---------|---------|
| **Roots / All** | `Roots` shows only **trace-root events** — the starting points of an event chain (e.g. `m5_candle_trigger`, `order_request`). `All` shows every persisted event, including ones that are part of a larger chain. |
| **event_type** | Filters on an exact or partial event type name. |
| **source agent** | Filters on the triggering agent/module. |
| **correlation id** | Filters on a specific correlation id, to find one connected chain. |
| **From time / To time** | Time-range filter (local date/time picker). |
| **min–max (Chain)** | Filters trace-root events by the size of their event chain. |
| **Search** | Applies the current filters and reloads. |
| **Clear** | Resets all filter fields. |
| **Refresh icon** (top right) | Reloads the current filter selection. |

**Recommendation:** almost always start in `Roots` mode. It shows exactly one entry per completed operation (e.g. one full analysis cycle) instead of dozens of individual events that all belong to the same operation — much faster to scan. Only switch to `All` once you're hunting for a specific intermediate step that isn't showing up in the trace view (Section 3).

**Using chain min/max effectively:** a very low chain value (e.g. max 2) typically finds failed or early-aborted cycles — the agent was triggered but barely did anything. A very high value finds unusually long, branching chains worth a closer look (e.g. because an EC queried repeatedly, or a tool failed and retried multiple times).

Results are loaded page by page (50 at a time); **Load more** at the bottom of the table fetches the next page.

---

## 2. Table Columns

| Column | Content |
|--------|---------|
| **Time** | Creation timestamp in the system-configured timezone. |
| **Event Type** | Color-coded by category. |
| **Source** | The triggering agent or module. |
| **Events / Chain** | In `Roots` mode: the number of follow-on events in this chain (`+N`). In `All` mode: ancestors/descendants (`↑N`/`↓N`). |
| **Trace** (branch icon) | Opens the trace view for this event. |

Clicking anywhere on a row also opens the trace view (clicking again closes it).

---

## 3. Trace View

Opens to the right of the table and shows the **full event chain** for an event as a vertical timeline — from the root event down to the clicked target event (the target additionally marked "← target").

For each entry: event type, timestamp, time relative to the root event (e.g. `+842ms`), source/target agent, correlation id. Clicking an entry expands it and additionally shows the full event id, the correlation chain, and the full JSON payload.

**Recommendation:** the relative time (`+842ms` etc.) is the fastest way to spot a performance anomaly — a jump from, say, `+120ms` to `+4200ms` between two consecutive steps immediately shows which sub-step (LLM call, tool call, broker response) slowed down the entire cycle, without manually subtracting timestamps.

**Export** button: downloads the entire chain as a `.json5` file. Useful for saving an incident before it becomes hard to find for practical reasons (e.g. database cleanup), or for sharing it outside the UI — with a colleague or in a ticket, without them needing access to the running instance.

---

## 4. Typical Workflows

### 4.1 Investigating a Rejected Trade

1. In `Roots` mode, filter by `event_type`, e.g. `order_result` or `signal_rejected`.
2. Narrow the time range to the day in question (`From time`/`To time`).
3. Click the matching event to open the trace view.
4. Step through the chain from the trigger to the rejection — each expanded step shows the full payload for that intermediate step. The actual reasoning is usually not in the root event but in an `ec_run_output` or `broker_http_response` entry further down the chain.
5. Click **Export** if you want to save the chain before discussing it with a colleague or support.

### 4.2 Finding Out Whether a Problem Was One-Off or a Pattern

A single incident is easy to over-interpret. Before making a configuration change, it's worth checking whether the same pattern shows up more than once:

1. Set `event_type` to the suspected failure type (e.g. `agent_trigger_skipped` or `order_result`).
2. Deliberately widen the time range (e.g. the last 7 days).
3. Scan the result list — does the failure happen regularly at the same time of day (suggests a session filter or market-hours issue), or only for one specific pair (suggests a configuration problem with that particular agent)?
4. Only make a change once you have this bigger picture — otherwise you risk "fixing" a one-off case that was actually normal, expected behavior.

**Warning:** the Event Log only shows what was actually published as an event. If an agent never triggered because of `runtime_paused`, you'd expect an `agent_trigger_skipped` event — but if the runtime wasn't running at all during that window, even those skip events may be entirely missing. An empty search result doesn't necessarily mean "nothing happened" — sometimes it means "the system wasn't running during that period." When in doubt, cross-check system status on the Initial page for the time range in question.
