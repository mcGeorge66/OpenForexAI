[Back to UI Handbook](ui.en.md)

# Action

The `Action` area is the operational work area of OpenForexAI. It is the primary interface used during live trading to monitor system activity, review positions, inspect AI decisions, and interact with agents directly.

## Sub-sections

- [Initial](ui.action.initial.en.md) — System status and runtime controls
- [Agent Chat](ui.action.chat.en.md) — Direct AI agent interaction and inspect runs
- [Orderbook](ui.action.orderbook.en.md) — Open positions, trade history, and P&L
- [Chart Analysis](ui.action.chart_analysis.en.md) — Visual chart with AI analysis overlay

---

## Initial

Use `Initial` as the runtime start and health view.

What you typically do here:

- check local version and update state
- check broker connectivity
- check LLM connectivity
- see whether the runtime is paused or active
- inspect enabled agents
- trigger update, pause, resume, or restart actions

The `Initial` page is your first stop after launching OpenForexAI. Before enabling live trading, confirm that all connectivity indicators are green:

- **Broker Status**: connected to MT5 or OANDA; receiving candle data
- **LLM Status**: connected to the configured LLM provider; responding to test calls
- **Agent Status**: all configured agents listed as active
- **Runtime State**: system shown as running (not paused)

If any indicator is red or yellow, resolve the issue before proceeding to live trading. Common causes:

- Broker connection lost: check network, broker server status, and API credentials in [Broker Modules](ui.config.broker_modules.en.md)
- LLM not responding: verify API key and endpoint in [LLM Modules](ui.config.llm_modules.en.md)
- No agents active: review [Agent Config](ui.config.agent_config.en.md)

### Runtime Controls

The `Initial` page provides buttons to control the runtime:

| Button | Effect |
|--------|--------|
| Pause | Halt all agent activity; no new analyses or trades will be triggered |
| Resume | Re-enable agent activity after a pause |
| Restart | Stop and restart the full runtime (useful after config changes) |
| Update | Pull the latest version and restart |

Pausing is useful when you want to make configuration changes without triggering trades during the transition. Always pause before making significant changes to Agent Config or Event Routing.

Suggested screenshot:
- [Initial page runtime status](image/ui-02-initial-runtime-status.png)

---

## Agent Chat

`Agent Chat` is both a normal agent chat view and a controlled execution surface for inspect runs.

What you can do:

- select an agent
- type a normal message and click `Send`
- click `Execute` to run the selected agent in inspect mode
- export the full visible chat history as Markdown
- clear the current chat history

### Chat Mode vs. Execute Mode

**Chat Mode** (`Send`): sends your message to the agent as a standard user message. The agent responds using its configured system prompt. This is useful for asking the agent questions, querying its current state, or having a conversation about market conditions.

**Execute Mode** (`Execute`): runs a full structured agent cycle in inspect mode. For AA agents, this triggers a complete snapshot build, LLM call, and analysis — exactly as it would run in live trading, but with full visibility into every step. The right panel fills with technical inspection data.

Typical usage:

1. Open `Agent Chat`.
2. Select the agent you want to test.
3. Enter text into the chat input field.
4. Use `Send` for a regular message or `Execute` for a structured test run.
5. Read the visible conversation on the left side.
6. Inspect technical details on the right side and below the chart.

For BA agents you can paste an AA analysis into the input field and then use `Execute` to see how the BA reacts to that analysis.

### When to Use Agent Chat

- Before going live: use Execute on your AA agent to verify the snapshot and LLM response look correct
- Debugging a trade: use Execute to reproduce the conditions that led to a signal
- Testing prompt changes: after updating a Decision Prompt profile, run Execute to verify the LLM receives the new prompt and responds appropriately
- BA agent verification: paste a sample analysis JSON and Execute to confirm the BA agent would place the trade correctly

Suggested screenshots:
- [Agent Chat overview](image/ui-03-agent-chat-overview.png)
- [Agent Chat execute run with visible chat history](image/ui-04-agent-chat-execute-run.png)

---

## Agent Chat Inspector

When the selected agent is an AA, the right side shows a chart and a technical inspection area.

What appears there:

- a candle chart
- optional persisted analysis markers
- timeframe buttons such as `M5`, `M15`, `M30`, `H1`
- an inspector below the chart

The inspector tabs currently are:

- `Overview`
- `Snapshot`
- `LLM`
- `Tools`
- `Runtime`

Use this area when you need to understand what happened during an `Execute` run without cluttering the chat itself.

### Overview Tab

Shows a high-level summary of the last execute run:
- signal direction (BUY / SELL / NO SIGNAL)
- confidence score
- entry, stop-loss, take-profit levels
- reasoning summary from the LLM
- any validation errors

### Snapshot Tab

Shows the full snapshot dict that was assembled and passed to the LLM. This is the exact data structure the LLM received as its user message. Use this tab to:
- verify all expected data blocks are present
- check that values (ATR, swing levels, session context) are correct
- debug unexpected LLM behaviour by tracing it back to the data

### LLM Tab

Shows:
- the system prompt (after Decision Prompt substitution)
- the user message (assembled snapshot)
- the raw LLM response
- token usage (input tokens, output tokens, total cost estimate)

This is the definitive audit trail for what the LLM was asked and what it said.

### Tools Tab

Shows all tool calls made during the run, in order:
- tool name and input parameters
- tool response
- timing per call

Use this when snapshot assembly involves custom tools and you need to verify they returned expected data.

### Runtime Tab

Shows timing data for each stage of the execute cycle:
- snapshot assembly duration
- LLM call duration
- response parsing duration
- total cycle time

Use this to identify performance bottlenecks or unexpected slowness.

Typical things to inspect:

- the runtime-built snapshot
- the final LLM input and output
- tool calls and tool results
- timing data
- token usage
- validation errors

Suggested screenshots:
- [Agent Chat inspector overview tab](image/ui-05-agent-chat-inspector-overview.png)
- [Agent Chat snapshot tab](image/ui-06-agent-chat-snapshot-tab.png)
- [Agent Chat LLM tab](image/ui-07-agent-chat-llm-tab.png)
- [Agent Chat tools tab](image/ui-08-agent-chat-tools-tab.png)

---

## Orderbook

The `Orderbook` page is used to inspect operational trade entries together with analysis context.

What you can do here:

- review open, closed, and rejected entries
- compare start and end timestamps
- inspect close reason and linked analysis
- open the detail dialog for a specific entry

### Trade Entry States

| State | Meaning |
|-------|---------|
| Open | Position is active at the broker |
| Closed | Position has been closed; final P&L recorded |
| Rejected | Signal was generated but blocked by EC Relay filters |
| Pending | Order placed but not yet confirmed by broker |

### Timestamp Behaviour

Important current behavior:

- broker-confirmed timestamps are preferred in the UI
- if broker timestamps are not available yet, the local UTC fallback timestamp is shown
- unconfirmed broker data is marked visually with a warning indicator

This allows you to distinguish between:

- a broker-confirmed record
- a provisional local record that is still waiting for broker confirmation

### Detail Dialog

Click any entry to open the detail dialog. The dialog shows:

- full trade parameters (entry, SL, TP, lot size, direction)
- the analysis that triggered the trade (signal, confidence, reasoning)
- the snapshot context at the time of entry
- open/close timestamps and duration
- realised P&L in account currency and pips

The linked analysis view lets you see exactly what the LLM said when it generated the signal. This is essential for post-trade review: if a trade lost, you can examine whether the LLM reasoning was sound or whether the signal should have been filtered.

### Filtering the Orderbook

Use the filter controls at the top of the page to narrow the view:

- filter by state (open / closed / rejected / pending)
- filter by symbol (EURUSD, GBPUSD, etc.)
- filter by agent
- filter by date range
- filter by direction (BUY / SELL)

Suggested screenshots:
- [Orderbook overview with confirmed and provisional entries](image/ui-09-orderbook-overview.png)
- [Orderbook entry detail dialog](image/ui-10-orderbook-entry-detail.png)

---

## Chart Analysis

The `Chart Analysis` page provides a visual candlestick chart for any configured symbol with AI analysis results overlaid.

What you can see:

- live candlestick chart for the selected symbol and timeframe
- buy/sell signal markers at the candles where analyses were triggered
- swing high/low markers from the snapshot data
- trend direction overlay
- ATR bands or stop-loss visualisation

Use `Chart Analysis` to:

- visually review the quality of recent signals
- spot patterns in where the system enters and exits
- identify whether the system is aligning with or fighting the prevailing trend
- validate that swing level detection is working as expected

Suggested screenshots:
- [Chart Analysis with signal markers](image/ui-11-chart-analysis-signals.png)
- [Chart Analysis swing levels overlay](image/ui-12-chart-analysis-swing-levels.png)
