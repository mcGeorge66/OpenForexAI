[Back to Action](ui.action.en.md)

# Orderbook

The Orderbook is the **complete trade history and inspection page** for all positions managed by OpenForexAI. It gives you a structured view of every order the system has recorded — open, closed, rejected, and cancelled — with a linked interactive chart that shows the market context for any selected trade. Use the Orderbook to review performance, understand why trades succeeded or failed, audit the system's execution quality, drill into a specific order with an AI chat, jump into full Chart Analysis anchored on that order, print trade reports, and export trade write-ups to the Knowledgebase.

Orderbook is deliberately **read-only for trading**: you cannot close, modify, or place trades from this page. Everything here is inspection and analysis. To act on a position, use the broker platform directly or the Agent Chat / Initial pages.

---

## Table of Contents

1. [Page Layout Overview](#1-page-layout-overview)
2. [Filter Bar](#2-filter-bar)
3. [Trade Table — Columns Explained](#3-trade-table--columns-explained)
4. [Per-Row Actions: Open, Trace, AI, Chart](#4-per-row-actions-open-trace-ai-chart)
5. [Close Reasons Reference](#5-close-reasons-reference)
6. [Trade Detail Chart](#6-trade-detail-chart)
7. [Chart Controls](#7-chart-controls)
8. [AA Analysis and Recommendation Popups](#8-aa-analysis-and-recommendation-popups)
9. [Print and Knowledgebase Export](#9-print-and-knowledgebase-export)
10. [Practical Workflows](#10-practical-workflows)
11. [Scenarios and Examples](#11-scenarios-and-examples)
12. [Quick Reference](#12-quick-reference)

---

## 1. Page Layout Overview

The Orderbook page is divided into two vertically stacked sections separated by a resizable divider:

```
┌─────────────────────────────────────────────────────────────────┐
│  FILTER BAR: [all] [open] [closed] [rejected]   Max: [__]       │
│              [Refresh] [Print] [→ KB]                           │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  TRADE TABLE                                                     │
│  Pair | From | To | HH:MM | Id | Units | Stake | Result |       │
│  Close | Analysis: [Open] [Trace] [AI] [Chart]                   │
│                                                                   │
├══════════════════════ RESIZE DIVIDER ═══════════════════════════╡
│                                                                   │
│  TRADE DETAIL CHART                                              │
│  Info boxes: Entry/Exit · SL/TP · Support/Resistance · Indicators│
│  [Show the Analyses] [M5] [M15] [M30] [H1]                       │
│  Chart with candles + Entry/Exit/SL/TP lines + Start/End markers │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

The table occupies the top portion and the chart occupies the bottom. The divider between them is draggable — you can set the split between 28% and 72% of the total page height depending on how much chart space you need. Drag the small handle bar in the middle of the divider; the split is not persisted across reloads, so it resets to roughly half-and-half each time you open the page.

Clicking any row in the table selects that trade and loads its associated chart below. The table and chart remain in sync: clicking different rows updates the chart immediately. Selecting a row does **not** navigate away from the Orderbook — the embedded chart at the bottom is a lightweight, read-only preview. For deeper technical analysis of an order (adding your own indicators, swing levels, drawing tools), use the **Chart** button described in [Section 4](#4-per-row-actions-open-trace-ai-chart) to jump to the full Chart Analysis page instead.

---

## 2. Filter Bar

The filter bar sits at the top of the page and controls which trades are loaded and displayed in the table.

### Status Filter Buttons

Exactly four toggle buttons control the status filter — there is no separate button for cancelled trades (see below):

**all**
Shows every trade in the database regardless of status. This is the default state. With large trade histories, use Max Orders to limit the result set.

**open**
Shows positions that are still live in the broker's sense: this includes orders that are `PENDING` (submitted but not yet confirmed), fully `OPEN`, and `PARTIALLY_FILLED`. The To column will be empty for all of these. Use this filter to review active risk exposure.

**closed**
Shows only completed trades — positions that were opened and subsequently closed for any reason (SL, TP, trailing stop, agent-initiated close, broker-forced close, or a sync-detected close). This is the most commonly used filter for performance review.

**rejected**
Shows only trades that were attempted but rejected at the point of order submission. The trade was evaluated by the BA agent, an order was constructed, but the broker (or a pre-submission validation) rejected it before it ever opened. Rejected trades have no entry price, no broker-confirmed From timestamp, and no Result. Use this filter to identify systemic rejection patterns.

### There is no dedicated "Cancelled" button

Trades that were cancelled before submission (decision made, order object built, but never sent to the broker — for example because the system was suspended between decision and execution, or a duplicate-position guard fired) get status `CANCELLED`. **There is no filter button for this status specifically.** The only way to see cancelled entries in the table today is to select **all** and scan for `CANCELLED` in the Close column. If you're troubleshooting "why didn't this trade happen," check **rejected** first, then **all** — don't assume a missing cancelled-only filter means there's nothing to find.

### Max Orders

A numeric input field that limits how many trade entries are loaded from the database. Applied when you leave the field (blur) or press Enter — typing a new number does nothing until you tab/click away or hit Enter.

- **Minimum:** 1 (values below 1 are clamped up)
- **No explicit maximum**, but very high values slow loading noticeably since the chart's candle fetch is done per selected order, not per row
- **Default on page load: 7.** This is a small number by design — the page opens fast and shows only your most recent handful of trades. Raise it immediately if you're doing a review session rather than a quick recent-activity check.

Reduce this number when reviewing recent activity (leave it at 7, or set to 20 for a slightly wider recent view). Increase it when doing a full performance audit across many trades — e.g. 200–500 for a monthly review.

### Refresh Button

Reloads the trade table from the database using the current filter and Max Orders settings, and additionally **forces a broker sync** for every unique broker+pair combination currently shown in the table before re-reading the local database. This means Refresh can take noticeably longer than a simple reload — it's actively asking each relevant broker connection for the latest state, not just re-querying local data. Shows a spinner icon while loading.

Click Refresh after a BA agent is expected to have placed a new trade and it has not appeared in the table yet, or when you suspect a position's local status is stale relative to the broker.

### Print Button

Generates and opens a print-ready report for the currently selected trade. This button is only active when a trade is selected in the table. Unlike Chart Analysis's print feature, there is **no options dialog** here — clicking Print always includes everything (metadata, execution details, AA context, a snapshot of the current chart view, and the full AA analysis text) in one go. See [Section 9](#9-print-and-knowledgebase-export) for details.

### → KB Button

Exports the currently selected trade as a formatted Markdown report directly into the Knowledgebase, under an auto-managed "Import" folder, with a title like `Orderbook_2026-08-21T14-32-10`. Also only active when a trade is selected. See [Section 9](#9-print-and-knowledgebase-export).

---

## 3. Trade Table — Columns Explained

Each row in the table represents one trade record. Clicking a row selects it and loads its chart context below.

### Pair

The currency pair (instrument) of the trade, the direction of the trade, and the current status, displayed together in this column.

**Format:** `EUR_USD` on the first line, `BUY · CLOSED` on the second line.

Direction is either **BUY** (long position) or **SELL** (short position).

If the trade has not yet been confirmed by the broker — meaning the order was submitted but the broker's acknowledgment has not been received and synced — a **warning icon** appears next to the pair. This is a temporary state that should resolve within a few seconds of order submission. If it persists for more than a minute, check broker connectivity on the Initial page.

### From (Entry Time)

The timestamp when the trade was opened — the broker-confirmed open time (`opened_at`) when available, falling back to the locally recorded request time (`requested_at`) otherwise.

- **Amber/yellow color:** The timestamp is local only (there is no `opened_at` yet, just `requested_at`) — broker confirmation has not yet been received. Once the broker confirms, the timestamp switches to the broker's official open time and the color reverts to normal.
- **Normal color:** The timestamp has been confirmed by the broker and is authoritative.

Tip: an amber timestamp on an old, already-closed trade usually indicates the broker confirmation for the open was never received or never synced back — worth cross-checking against the broker platform directly rather than trusting the local time.

### To (Exit Time)

The timestamp when the trade was closed. For trades that are still open, this column is empty. For `REJECTED` or `CANCELLED` entries (which never had a real close), it falls back to showing the same timestamp as From, so the row doesn't look broken with two dashes.

Same color coding as From: amber means the value is a locally recorded "close requested" timestamp with no confirmed `closed_at` yet; normal color means the close is confirmed.

### HH:MM (Duration)

The trade duration in hours and minutes, calculated from From to To.

`00:15` means the trade lasted 15 minutes. `04:32` means 4 hours 32 minutes. A dash (`—`) means there is no To timestamp yet (trade still open) — duration is **not** computed live for open trades; refresh to update it.

This column is useful for quick pattern recognition: are your winning trades typically longer or shorter than your losing trades? Do certain agents tend to produce short, high-conviction trades vs. longer position holds?

### Id (Broker Order ID)

The broker's official order or position ID as returned at submission confirmation, shown in a monospace font. Use it to look up the trade directly in the broker's platform or API for cross-referencing.

Shows `-` if no broker ID has been received yet (the trade is pending confirmation).

### Units

The position size in units of the base currency, formatted with a thousands separator (e.g. `10,000` not `10000`). This is the raw unit count as submitted to the broker, sized by the BA agent's position sizing logic.

### Stake

**This is a dollar amount, not a percentage.** The column shows `stake_estimate` — the notional exposure of the position, computed as the opened reference price times the unit count — formatted with two decimals and a trailing `$` (e.g. `12,345.67 $`).

Watch out for the formatting quirk: the value is always rendered using German number-grouping (period as thousands separator, comma as decimal separator) regardless of your UI language — so `1.234,56 $` means one thousand two hundred thirty-four dollars fifty-six cents, not 1.234 dollars. If a number here looks small and comma-separated, read it as the decimal, not a European convention you need to re-parse per pair.

Do not read this column as "risk % of equity" — for that, you'd need to relate the SL distance and Units to your account balance yourself; the Stake column alone does not tell you the percentage risked.

### Result

The profit or loss for this trade in the account's base currency (e.g., USD), to two decimals.

- **Green text:** result ≥ 0 (profit or break-even)
- **Red text:** result < 0 (loss)
- `—` for open trades, or for rejected/cancelled trades where no position was ever opened

For open trades, check the broker platform or the GA monitor agent's output for current floating P&L — this column stays blank until the trade closes.

### Close (Close Reason)

The reason the trade was closed, or the current status text if it hasn't really "closed" in the traditional sense. See [Section 5](#5-close-reasons-reference) for the exact values and what drives them. Below the primary value, a second line shows the stored close reasoning text (a short freeform note) or, if none was stored, repeats the status.

### Analysis

Four small action buttons: **Open**, **Trace**, **AI**, and **Chart**. Each opens a different tool scoped to this specific order. See the next section for exactly what each one does and when to reach for it.

---

## 4. Per-Row Actions: Open, Trace, AI, Chart

Every table row ends with four buttons. They overlap in that all four are "tell me more about this order," but they answer genuinely different questions — picking the right one saves time.

### Open (document icon) — AA Analysis popup

Opens a modal showing the raw, full-text AA analysis that was stored with this trade at decision time. No interpretation, no extra tool calls — just the stored record. This is the fastest way to read "what did the analysis actually say" verbatim. See [Section 8](#8-aa-analysis-and-recommendation-popups).

**Use when:** you already have a specific question in mind and know the answer is literally in the analysis text (e.g. "what setup type did it call this?").

### Trace (branch icon, emerald) — Event Trace viewer

Opens the causal event trace for this order: it looks up the event whose `correlation` id matches this order's id, and if that lookup comes up empty, it falls back to scanning recent `order_request`/`order_placed` events for a payload match. Once resolved, it hands off to the same TraceViewer used elsewhere in the system, showing the chain of events that led to (and followed from) this order.

**Use when:** you need to understand the plumbing — which agent fired, what events were published in what order, whether a guard or EC intercepted something — rather than the trading rationale itself. If the trace can't resolve an event (e.g. the order predates event logging, or it's a synthetic/backfilled entry), you'll see an explicit "no event found" message rather than a silent empty screen.

### AI (bot icon, indigo) — "Ask AI" investigate chat

Opens a free-floating (draggable, resizable) chat window backed by a real tool-calling agent, pre-loaded with this order's full record (AA analysis, P&L, close reasoning). Unlike a static popup, it can go fetch more data mid-conversation — event trace, the live agent/EC config, EC run history, market candles/indicators/swing levels — using the same restricted tool set the Chart Analysis order-focus assistant uses (`get_order`, `get_order_trace`, `get_order_book`, `get_agent_config`, `get_ec_config`, `get_ec_runs`, `get_agent_decisions`, `get_candles`, `calculate_indicator`, `get_swing_levels`).

Because it's a floating window rather than a centered modal, it doesn't block the table behind it — you can keep clicking other rows or scrolling while it's open (though it stays scoped to the order it was opened for; open a fresh one per order rather than expecting it to follow your selection).

**Use when:** you have a natural-language question about *this one order* and want a synthesized answer rather than raw data — e.g. "why was this order closed here?" or "if I want to adjust the entry filter, where do I do that?" It's quick Q&A on a single order, not a charting workspace.

**Use Chart instead when:** the question is really about the *market*, not the order record — "show me this against the EMA and swing levels," "what did price do in the hour before entry on M15," "let me draw a trendline through this move." The AI chat can describe indicator values in words; it can't give you an interactive chart to look at yourself.

### Chart (line-chart icon, sky blue) — Open in Chart Analysis

New addition. Switches the Action tab to **Chart Analysis** with this order pre-loaded: candles are anchored around the order's own time window, and the same Entry/Exit/SL/TP price lines and Start/End markers you see in the embedded Orderbook chart are drawn there too — but now inside the full charting workspace, where you can add indicators (EMA, RSI, ATR, and more), enable swing levels, draw on the chart, and talk to the Chart Analysis assistant with the order's data already in its context.

**Worked example:** you're reviewing a closed order's P&L in the table and its Result is negative. You want to see it against EMA trend and swing levels before deciding whether the stop was reasonable — click **Chart** on that row. Chart Analysis opens with the order's window loaded and its price lines already drawn; you then add an EMA(20) and enable Swing Levels from the indicator panel to finish the review, something the embedded Orderbook chart alone can't do.

**Recommendation:** reach for **AI** when you want an answer in words about one specific order. Reach for **Chart** when you want to look at the market yourself with real charting tools, or when the AI's text description of "price was near a swing high" isn't enough and you want to see it. They are not redundant — the AI chat button and the Chart button were built to exist side by side.

---

## 5. Close Reasons Reference

The Close column describes why a trade ended. The value comes straight from the backend's `close_reason` enum when one is recorded; if none is recorded, the column falls back to the order's status. Understanding these values is essential for performance analysis.

### SL_HIT — Stop Loss Hit

The price moved against the trade and hit the stop loss level set at entry. The broker closed the position at (or near) the stop loss price.

- This is a planned loss — the risk management worked as intended.
- Slippage on the actual close price vs. the set SL level may cause the Result to differ slightly from the theoretical risk amount.

**Analysis question:** was the stop placement reasonable given the market structure at entry? Use the trade chart (or the **Chart** button for a deeper look with swing levels) to examine where price was relative to structure when the SL was set.

### TP_HIT — Take Profit Hit

The price moved in the trade's favor and hit the take profit level. The broker closed the position at (or near) the take profit price. This is a planned win; slippage on TP is typically minimal in liquid markets but can occur around major news.

### TRAILING_STOP — Trailing Stop Triggered

The position had a trailing stop configured, and price retraced enough to trigger it before reaching the original take-profit level. This typically produces a smaller win than a full TP hit, but locks in profit earlier than waiting for TP.

### AGENT_CLOSED — Closed by a Trading Agent's Decision

A BA or GA agent decided to close the position directly, outside of the SL/TP mechanism — for example, an updated AA analysis reversed the setup's premise mid-trade. If you see this and want to know *why* the agent decided to close, the **AI** or **Trace** button on that row is the fastest way in.

### BROKER_CLOSED — Broker Forced the Close

The broker closed the position for a reason outside OpenForexAI's control — margin call, account restriction, or a broker-side risk action. Check the broker platform directly; the system is only recording what the broker did, not causing it.

### SYNC_DETECTED — Detected as Closed During a Sync Check

The system found, during a routine position sync, that a position it still considered open no longer exists at the broker. This is the safety net for closes that happen while OpenForexAI wasn't actively watching (a `SL_HIT`/`TP_HIT`/`BROKER_CLOSED` event on the broker side that occurred while a connection issue or a gap in polling meant it wasn't caught in real time).

**When this occurs:** a broker-side close happened between sync cycles; a manual close was made on the broker platform while the agent was active; or the broker's API returned inconsistent data over multiple checks, triggering a safety close.

If you see this reason unexpectedly, check the broker account directly for the real cause, and consider narrowing your sync interval if it happens often.

### REJECTED — Order Rejected Before It Opened

The order never became a position. Common broker rejection reasons include insufficient margin, market closed (e.g. weekend gap), invalid unit size (below broker minimum lot), spread too wide at time of submission, or the instrument being suspended/halted by the broker. A `REJECTED` entry has no confirmed From/To timestamps, no Units-derived fill, and no Result.

**Analysis question:** if you see many `REJECTED` entries for the same pair or time of day, the BA agent may need spread filtering or session timing adjustments.

### Fallback values you'll also see in the Close column

Not every entry has a `close_reason` stored. When it's missing, the column falls back to:

| Displayed value | When it appears |
|---|---|
| `REJECTED` | Status is `REJECTED` and no distinct close reason was stored |
| `CANCELLED` | Status is `CANCELLED` — order was built but never submitted to the broker |
| `closed` (lowercase) | Status is `CLOSED` but no `close_reason` was stored for it — treat as "closed, reason not captured" rather than assuming it's an error |
| `running` | Trade is still open — this is the default text for any status that isn't REJECTED, CANCELLED, or CLOSED |

Don't confuse the lowercase fallback text (`closed`, `running`) with the uppercase enum values above — the lowercase ones mean "no specific reason was recorded," not a distinct reason in themselves.

---

## 6. Trade Detail Chart

When a trade is selected in the table, the chart area below loads a lightweight preview of the price action around that trade. This chart is intentionally minimal — candles, price lines, and markers only. As of the latest update, **there are no indicator controls here at all** (no EMA/RSI/ATR checkboxes, no period inputs, no per-indicator timeframe selects). If you need indicators, swing levels, or drawing tools on this order's chart, use the **Chart** button (see [Section 4](#4-per-row-actions-open-trace-ai-chart)) to open it in full Chart Analysis instead — don't go looking for indicator toggles on this page, they were removed by design to keep the Orderbook page focused on trade review rather than duplicating the charting workspace.

### Header Info Boxes

Above the chart, compact info boxes summarize the selected order at a glance:

| Box | Content |
|---|---|
| Pair · Direction | e.g. `EUR_USD · BUY`, plus the AA decision / confidence / setup type on the line below |
| Entry / Exit | Fill price (or requested price if unfilled) and close price |
| SL / TP | Stop loss and take profit price levels |
| Support / Resistance | The support/resistance price levels that were part of the AA's analysis overlay **at trade time** — a static, stored snapshot, not a live recalculation |
| Indicators | Name + value badges for whatever indicators the AA's analysis stored as context for this trade — also static and read-only, not something you configure here |

The Support/Resistance and Indicators boxes look similar to controls but aren't: there's nothing to click or configure. They show whatever the AA agent recorded at decision time. If they're empty (a dash), it usually means the trade's analysis record didn't carry an overlay snapshot — not that nothing existed at the time.

### Price Lines on the Chart

- **Entry (cyan):** fill price if the order filled, otherwise the originally requested price.
- **Exit (amber):** close price, only drawn once the order has actually closed.
- **SL (red):** the stop loss level.
- **TP (green):** the take profit level.
- **Support (teal) / Resistance (purple):** one line per level stored in the analysis overlay snapshot, same static data as the header info box above.

All of these are simple full-width horizontal price lines (not confined to the entry-to-exit span) — they mark price levels, not a time range.

### Start / End Markers

- **Start marker:** an emphasized arrow (up for BUY, down for SELL) placed at the candle nearest the trade's open time, positioned below the bar for BUY and above for SELL.
- **End marker:** an emphasized circle placed at the candle nearest the trade's close time, positioned above the bar for BUY and below for SELL.

Both markers use `findMarkerTimestamp`, which snaps to the nearest loaded candle to the order's actual timestamp — and, importantly, **won't show a marker at all** if the order's timestamp falls well outside the currently loaded candle range (rather than snapping incorrectly to an edge candle). If you select an order and don't see a Start or End marker, that's usually a signal the currently loaded candle window doesn't reach back (or forward) far enough — switch timeframe or use the **Chart** button, which anchors the candle window around the order specifically.

---

## 7. Chart Controls

The only controls on the embedded chart, shown in a small row above it:

### Show the Analyses Checkbox

When enabled (default: on), overlays every AA analysis cycle recorded for this order's pair around the trade's time window as small square markers, colored orange, labeled `U`, `D`, or `N` with the confidence percentage underneath.

- **`U`** — the analysis's `primary_bias` was a long-leaning bias (`BIAS_LONG` or `BIAS_REVERSAL_LONG`)
- **`D`** — the bias was short-leaning (`BIAS_SHORT` or `BIAS_REVERSAL_SHORT`)
- **`N`** — bias was neutral, or the field couldn't be read from the record

Note that this labeling reflects **directional bias only** — it does not indicate whether the analysis flagged the moment as a good entry (`order_start_signal`). All markers share the same color and shape; only the letter and confidence number differ.

Clicking a marker opens the AA Recommendation popup for that specific analysis cycle (see [Section 8](#8-aa-analysis-and-recommendation-popups)).

**When to enable:** when you want the analytical context around a trade, not just the trade itself. For example, if a trade went into a loss, were there subsequent `D`/`N` cycles showing the bias flipping away from the trade's direction while it was still open?

### Timeframe Buttons

**Available:** M5, M15, M30, H1 (there is no H4 or D1 here — those exist only in Chart Analysis).

Switches the chart to the selected timeframe and reloads up to 2000 candles for it. The price lines and Start/End markers are redrawn for the new timeframe automatically.

**Typical usage:** start on H1 for the macro context, M15 for entry timing, M5 for the exact entry/exit candles. If the Start or End marker disappears when you switch, see the note at the end of [Section 6](#6-trade-detail-chart) about markers outside the loaded range.

### Candle Range Shortcuts

Below/alongside the timeframe buttons, the chart itself (not specific to Orderbook) offers quick zoom shortcuts to the last 50 / 100 / 200 / 400 candles, defaulting to 100. These just change how many of the loaded candles are visible at once — they don't refetch data, and switching timeframe or order resets the view back to the default.

---

## 8. AA Analysis and Recommendation Popups

### AA Analysis Popup (Open button)

**Contents:**
- The full stored analysis text from the AA agent associated with this trade.
- A **Copy** button to copy the full text to clipboard.
- A **Close** button to dismiss the popup.

This is the definitive answer to "what did the system think when it decided to enter?" Reading this popup for a losing trade tells you whether the analysis was reasonable given the information available at the time (and the loss was simply bad luck or unfavorable execution), or whether the analysis itself contained a flawed assessment.

### AA Recommendation Popup (clicking a chart marker)

Opened by clicking any `U`/`D`/`N` marker on the chart (requires Show the Analyses to be enabled).

A 4-column header grid shows:
- **Decision** — the AA's decision field for that cycle
- **Confidence** — the confidence value from the LLM output
- **Order Start** — the `order_start_signal` value (readiness for entry)
- **Entry Quality** — the stored entry-quality rating

Below the header:
- **Decision JSON** — the complete decision output (or raw stored analysis text if available), with a Copy button.
- **Decision Snapshot** — the full market snapshot given to the AA at the time of this analysis, tagged with its schema version if one is stored, with its own Copy button. This section only appears if a snapshot was actually stored with the record; older records or configurations without snapshot storage will simply not have anything to show here.

**Why the Snapshot is valuable here:** when reviewing a historical trade, the snapshot tells you exactly what data the agent had — not what you see now, but what existed at that candle at that time. This is the most reliable way to audit an AI trading decision after the fact.

---

## 9. Print and Knowledgebase Export

Both actions are only enabled once a trade row is selected, and both pull from the **same underlying report content** — only the destination differs.

### Print Button

Clicking Print immediately opens a new browser window and writes a self-contained, printer-friendly HTML report — there is **no options dialog** to pick and choose sections (that dialog exists in Chart Analysis's print feature, not here). The report always includes:

- **Timing** — From/To timestamps and the close status text
- **Execution** — entry price, exit price, SL/TP, units
- **Result** — stake estimate, P&L, AA decision, confidence
- **AA Context** — the stored indicator badges and support/resistance levels from the analysis overlay
- **Chart** — a captured image of the chart exactly as it currently looks (whatever timeframe and Show-the-Analyses state you last left it in)
- **AA Analysis** — the full analysis text on its own page (forced page break before it)

The window auto-triggers the browser's native print dialog once it finishes loading. From there you can print physically, save as PDF, or adjust margins/orientation/scale via the browser's own print settings.

**Tip:** set the timeframe and Show-the-Analyses state the way you want them to appear in the printout *before* clicking Print — the captured chart image reflects whatever's currently rendered, not a fixed default view.

### → KB Button

Builds the same information as a Markdown document instead of an HTML/print report, and saves it into the Knowledgebase via `kbImport`, under an auto-managed "Import" folder, titled `Orderbook_<timestamp>`. The Markdown includes the same chart image (embedded inline), Result/Timing/Execution tables, AA Context, and — if the trade's stored `market_context_snapshot` contains an `analyst_recommendation` block — a richer structured writeup (decision, signal, quality, setup type, aggressiveness, invalidation level, first target, conflict flags, plus prose sections for summary, entry reason, trend/momentum/volatility/S-R/M5-price-action assessments, and entry-quality reasoning) instead of the raw analysis text.

**Use Print when** you want something to hand off outside the system (a PDF for a broker dispute, a physical trading journal page). **Use → KB when** you want the write-up to live inside OpenForexAI's own Knowledgebase for later reference or for other assistants/agents to search against.

### Typical Use Cases

- **Trading journal:** → KB each completed trade for a searchable, structured archive; Print the same trade if you also want a paper/PDF copy.
- **Performance review:** Print a batch of closed trades for weekly or monthly review meetings.
- **Audit trail:** Print the full report for `SYNC_DETECTED` closes, for discussion with your broker.
- **Strategy documentation:** → KB trades that exemplify a specific setup type, so the writeup (with the richer `analyst_recommendation` structure, when available) becomes searchable knowledge.

---

## 10. Practical Workflows

### Workflow 1: Daily Performance Review

1. Set filter to **closed**.
2. Raise **Max Orders** past the default of 7 to cover the day's trades (e.g. 20–50).
3. Click **Refresh** (this also forces a broker sync, so wait for the spinner to finish).
4. Review the Result column — which trades were profitable, which were not?
5. For each closed trade, click the row to load the embedded chart, and enable **Show the Analyses** to see the AA analysis context around it.
6. For a trade that went against you, click **Open** to read the AA Analysis popup — was the analysis sound, or was the market simply unfavorable despite a correct read?
7. Check the Close column — were all closes `SL_HIT` or `TP_HIT` (planned)? Any `SYNC_DETECTED` or `BROKER_CLOSED` entries deserve a closer look via **Trace** or **AI**.

Typical time: 10–30 minutes depending on trade count.

### Workflow 2: Reviewing a Losing Trade Step by Step

**Goal:** understand exactly why a specific losing trade occurred and whether it was a system error or simply a losing trade in a valid strategy.

1. Find the losing trade in the table (filter **closed**, look for red Results).
2. Click the row to load the embedded chart for a quick first look, then click **Chart** on that row to open it in full Chart Analysis for the deeper pass — you'll want indicators and swing levels for this workflow, which the embedded chart no longer provides.
3. In Chart Analysis, set timeframe to H1 first: was the direction correct for the macro structure? Add an EMA to check.
4. Switch to M15: was the entry at a sensible location relative to structure?
5. Check the SL line: was the stop below the nearest swing low (for a long), or too tight, inside normal price noise? Enable Swing Levels to check objectively rather than eyeballing it.
6. Back in the Orderbook row, click **Open** to read the AA analysis — did the agent correctly identify the setup?
7. Enable **Show the Analyses** on the embedded chart (or reopen it) and click nearby `U`/`D`/`N` markers — was the bias consistent, or did it flip while the trade was still open?
8. If unclear from the record alone, click **AI** and ask directly — e.g. "why did the AA's bias flip 20 minutes after this entry?"
9. If the analysis was sound and the stop was structurally placed but price hit it anyway: a valid losing trade, no action required. If the analysis had flawed reasoning or the stop was poorly placed: a strategy/configuration issue to address.

### Workflow 3: Investigating a SYNC_DETECTED or BROKER_CLOSED Close

1. Click the trade row to load the chart. Note the To timestamp — for `SYNC_DETECTED`, this is when the sync noticed the discrepancy, not necessarily the actual close time.
2. Click **Trace** to see the surrounding event chain — did a sync-cycle event immediately precede the close?
3. Click **AI** and ask something like "what does the order record say caused this close?" — the assistant can pull the trace and agent config for you in one pass instead of you piecing it together manually.
4. Cross-check the broker platform directly using the trade's Id — what does the broker itself record as the close reason?
5. Common outcome: the broker closed the trade (margin call, its own risk management, or a scheduled weekend/rollover close) and OpenForexAI only detected it on the next sync — the entry is a correct record of what happened, not a bug.

### Workflow 4: Analyzing Rejected Trades

**Goal:** understand patterns in rejected orders to improve BA agent configuration.

1. Set filter to **rejected**, click **Refresh**.
2. Look at the Pair column — is one pair consistently getting rejections?
3. Look at the From timestamps — are rejections clustered at specific times (e.g. market open, low-liquidity periods)?
4. Confirm Units and Result are both empty, confirming no position was ever opened.
5. Click a rejected trade, then **Chart**, to examine spread/price conditions at the rejection time using full charting tools.
6. Consider adding spread filters or session time restrictions to the BA agent's configuration if rejections cluster at specific times.

---

## 11. Scenarios and Examples

### Scenario A: Winning Trade — Validating the Setup

**Trade:** GBPUSD SELL, 4h 15m duration, Result: +12,345.00 $ notional Stake, Close: TP_HIT.

1. Click **Chart** to open it in Chart Analysis on H1 — confirm price was in a clear downtrend.
2. Switch to M15 — the Start marker shows the short was entered after a pullback to resistance. Structurally sound.
3. The SL price line is above the swing high that defined the resistance; the TP price line sits at the next support level.
4. Back in Orderbook, enable Show the Analyses — `D` markers preceding entry were consistent, with rising confidence values.
5. Click the `D` marker nearest to entry for the full Recommendation popup — high confidence, Entry Quality favorable.
6. Conclusion: clean setup, correct execution, deserved winner. No action needed.

### Scenario B: Losing Trade — Premature Stop Loss

**Trade:** EURUSD BUY, 0h 22m duration, negative Result, Close: SL_HIT.

1. Chart button → H1: price is overall bullish but currently in a retracement.
2. M5: the Start marker lands during a retracement; price continued lower before the SL was hit.
3. The SL line sits close to entry — add an ATR indicator in Chart Analysis to check whether the stop was inside one ATR of normal noise.
4. Back in Orderbook, click **Open** — the AA analysis described the market as bullish with a retracement-buying opportunity. Correct direction.
5. Conclusion: the directional call was right; the stop was likely too tight relative to volatility. Consider a wider ATR-based SL multiplier in the BA agent's config.

### Scenario C: SYNC_DETECTED Trade Audit

**Trade:** USDCAD BUY, 1h 55m duration, negative Result, Close: SYNC_DETECTED.

1. To timestamp shows the close was *detected* at 17:33 UTC on a Friday — not necessarily when it actually happened.
2. Click **Trace** — the surrounding events show a sync cycle firing at 17:33 that found the position already closed at the broker.
3. Broker platform confirms the actual close was at 17:00 UTC, an end-of-week margin adjustment by the broker.
4. The `SYNC_DETECTED` entry is correct — OpenForexAI recorded what the broker did, just noticed it 33 minutes late.
5. Action: consider configuring the BA agent to avoid opening new positions after 16:30 UTC on Fridays to sidestep end-of-week broker closures.

### Scenario D: Identifying a Streak of Rejections at Market Open

**Records:** five consecutive `REJECTED` entries for EURUSD BUY between 08:00–08:05 UTC on multiple days.

1. Filter to **rejected**; the pattern clusters right at the Frankfurt session open.
2. Click **Chart** on one of them to inspect spread behavior at that time on a low timeframe — spreads often widen sharply right at open.
3. No spread filter is currently configured on the BA agent, so it submits orders straight into the widened spread and gets rejected.
4. Action: add a max-spread filter to the BA agent configuration (e.g. reject entries if spread > 2.0 pips). After a config change and restart, rejections at open should stop.

---

## 12. Quick Reference

### Filter Buttons Summary

| Filter | Shows |
|---|---|
| all | Every trade regardless of status (the only way to see CANCELLED entries) |
| open | PENDING, OPEN, and PARTIALLY_FILLED positions |
| closed | Completed trades — any close reason |
| rejected | Orders that were never opened (broker/validation rejection) |

### Per-Row Action Buttons Summary

| Button | Icon | Opens | Best for |
|---|---|---|---|
| Open | document | AA Analysis text popup | Reading the stored analysis verbatim |
| Trace | branch | Event Trace viewer | Understanding the causal event chain |
| AI | bot | Ask-AI investigate chat | A natural-language question about this one order |
| Chart | line chart | Chart Analysis, order-focused | Full charting tools (indicators, swing levels, drawing) on this order |

### Close Reasons Summary

| Close Reason | Meaning | Result Sign |
|---|---|---|
| SL_HIT | Stop loss hit — planned loss | Negative |
| TP_HIT | Take profit hit — planned win | Positive |
| TRAILING_STOP | Trailing stop triggered | Positive (usually smaller than TP) |
| AGENT_CLOSED | An agent decided to close directly | Either |
| BROKER_CLOSED | Broker forced the close | Either |
| SYNC_DETECTED | Broker-side close found during a sync check | Either |
| REJECTED | Never opened — broker/validation rejection | None |
| *(fallback)* CANCELLED | Never submitted — pre-trade cancel | None |
| *(fallback)* closed | Status CLOSED but no reason stored | Either |
| *(fallback)* running | Still open | — |

### Chart Markers and Lines Summary

| Marker/Line | Color | Meaning |
|---|---|---|
| Start marker | Cyan, emphasized arrow | Trade open candle |
| End marker | Amber, emphasized circle | Trade close candle |
| Entry line | Cyan horizontal | Fill (or requested) price |
| Exit line | Amber horizontal | Close price |
| SL line | Red horizontal | Stop loss price level |
| TP line | Green horizontal | Take profit price level |
| Support line | Teal horizontal | S/R level from the stored analysis overlay |
| Resistance line | Purple horizontal | S/R level from the stored analysis overlay |
| U / D / N marker | Orange square | AA bias: long-leaning / short-leaning / neutral, with confidence % |

### Column Quick Reference

| Column | Contains | Amber/yellow = |
|---|---|---|
| Pair | Instrument, direction, status | — |
| From | Entry timestamp | Local-only, broker unconfirmed |
| To | Exit timestamp | Local-only, broker unconfirmed |
| HH:MM | Trade duration | — |
| Id | Broker order ID | — |
| Units | Position size in base currency units | — |
| Stake | Notional dollar exposure (price × units) — **not** a % of equity | — |
| Result | P&L in account currency | — |
| Close | Close reason (or status fallback) | — |
| Analysis | Open / Trace / AI / Chart buttons | — |
