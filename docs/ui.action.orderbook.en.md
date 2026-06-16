[Back to Action](ui.action.en.md)

# Orderbook

The Orderbook is the **complete trade history and inspection page** for all positions managed by OpenForexAI. It gives you a structured view of every order the system has recorded — open, closed, rejected, and cancelled — with a linked interactive chart that shows the exact market context for any selected trade. Use the Orderbook to review performance, understand why trades succeeded or failed, audit the system's execution quality, and print trade reports.

---

## Table of Contents

1. [Page Layout Overview](#1-page-layout-overview)
2. [Filter Bar](#2-filter-bar)
3. [Trade Table — Columns Explained](#3-trade-table--columns-explained)
4. [Close Reasons Reference](#4-close-reasons-reference)
5. [Trade Detail Chart](#5-trade-detail-chart)
6. [Chart Controls](#6-chart-controls)
7. [Summary Info and Analysis Popups](#7-summary-info-and-analysis-popups)
8. [Print Function](#8-print-function)
9. [Practical Workflows](#9-practical-workflows)
10. [Scenarios and Examples](#10-scenarios-and-examples)
11. [Quick Reference](#11-quick-reference)

---

## 1. Page Layout Overview

The Orderbook page is divided into two vertically stacked sections separated by a resizable divider:

```
┌─────────────────────────────────────────────────────────┐
│  FILTER BAR: [all] [open] [closed] [rejected]           │
│              Max Orders: [__]  [Refresh]  [Print]       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  TRADE TABLE                                            │
│  Pair | From | To | HH:MM | ID | Units | Stake |       │
│  Result | Close | Analysis                              │
│                                                         │
├══════════════════ RESIZE DIVIDER ═══════════════════════╡
│                                                         │
│  TRADE DETAIL CHART                                     │
│  [Show Analyses] [M5] [M15] [M30] [H1]                 │
│  [EMA] [RSI] [ATR]                                      │
│  Chart with entry/exit arrows, SL/TP lines              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

The table occupies the top portion and the chart occupies the bottom. The divider between them is draggable — you can set the split between 28% and 72% of the total page height depending on how much chart space you need.

Clicking any row in the table selects that trade and loads its associated chart below. The table and chart remain in sync: scrolling through trades and clicking different rows updates the chart immediately.

---

## 2. Filter Bar

The filter bar sits at the top of the page and controls which trades are loaded and displayed in the table.

### Status Filter Buttons

Four toggle buttons control the status filter:

**All**
Shows every trade in the database regardless of status. This is the default state. With large trade histories, use Max Orders to limit the result set.

**Open**
Shows only positions that are currently open — trades that have been submitted to the broker and have not yet been closed. The To column will be empty for open trades. Use this filter to review active risk exposure.

**Closed**
Shows only completed trades — positions that have been opened and subsequently closed for any reason (take profit, stop loss, manual close, sync-detected close, or expiry). This is the most commonly used filter for performance review.

**Rejected**
Shows only trades that were attempted but rejected at the point of order submission. The trade was evaluated by the BA agent, an order was constructed, but the broker (or a pre-submission validation) rejected it before it ever opened. Rejected trades have no entry price, no From timestamp confirmed by the broker, and no Result. Use this filter to identify systemic rejection patterns.

### Cancelled Filter

In addition to the four main filter buttons, a **Cancelled** state exists for trades that were cancelled before submission — for example, if a BA agent built an order but then reversed the decision before sending it to the broker, or if the system was suspended between decision and execution. Cancelled trades appear in the "All" view but not in other filters unless specifically selected.

### Max Orders

A numeric input field that limits how many trade entries are loaded from the database. Applied when you leave the field (blur) or press Enter.

- **Minimum:** 1
- **No explicit maximum** (but very high values will slow loading)
- **Default:** Typically 50 or 100

Reduce this number when reviewing recent activity (set to 20 to see only the last 20 trades). Increase it when doing a full performance audit across many trades.

### Refresh Button

Reloads the trade table from the database using the current filter and Max Orders settings. Shows a spinner icon while loading. This is a manual refresh — the table does not auto-update when new trades open or close while you are viewing the page.

Click Refresh after a BA agent is expected to have placed a new trade and it has not appeared in the table yet.

### Print Button

Opens the print dialog for the currently selected trade entry. This button is only active when a trade is selected in the table. See [Section 8](#8-print-function) for full details.

---

## 3. Trade Table — Columns Explained

Each row in the table represents one trade record. Clicking a row selects it and loads its chart context below.

### Pair

The currency pair (instrument) of the trade, the direction of the trade, and the current status, displayed together in this column.

**Format:** `EUR/USD · BUY · CLOSED`

Direction is either **BUY** (long position) or **SELL** (short position).

If the trade has not yet been confirmed by the broker — meaning the order was submitted but the broker's acknowledgment has not been received and synced — a **warning icon** (⚠) appears in this column. This is a temporary state that should resolve within a few seconds of order submission. If it persists for more than a minute, check broker connectivity on the Initial page.

### From (Entry Time)

The timestamp when the trade was opened. This is the broker-confirmed open time when available.

- **Yellow color:** The timestamp is local only — it was recorded by OpenForexAI at the moment the order was submitted, but broker confirmation has not yet been received. Once the broker confirms, the timestamp is updated to the broker's official open time.
- **Normal color:** The timestamp has been confirmed by the broker and is authoritative.

Tip: Yellow timestamps in old (closed) trades may indicate a sync issue where broker confirmation was never received. Check the trade's close reason.

### To (Exit Time)

The timestamp when the trade was closed. Empty for open trades.

Same color coding as From: yellow means local-only timestamp, normal color means broker-confirmed.

For trades closed by the broker (SL/TP hit) rather than by the system submitting a close order, the To timestamp reflects when the system detected the closure during a sync cycle — it may be slightly later than the actual closure time on the broker.

### HH:MM (Duration)

The trade duration in hours and minutes, calculated from the From and To timestamps.

`0:15` means the trade lasted 15 minutes.
`4:32` means the trade lasted 4 hours and 32 minutes.
`—` means the trade is still open (no To time).

This column is useful for quick pattern recognition: are your winning trades typically longer or shorter than your losing trades? Do certain agents tend to produce short, high-conviction trades vs. longer position holds?

### ID (Order ID)

The broker's official order or position ID as returned at submission confirmation. This ID can be used to look up the trade directly in the broker's platform or API for cross-referencing.

Shows `—` if no broker ID has been received yet (the trade is pending confirmation).

### Units

The position size in units of the base currency. This is the raw unit count as submitted to the broker.

Displayed with a thousands separator for readability: `10,000` not `10000`.

For forex pairs, typical retail unit sizes are:
- Micro lot: 1,000 units
- Mini lot: 10,000 units
- Standard lot: 100,000 units

The specific unit count depends on the BA agent's position sizing logic (which applies the configured risk percentage to the current account balance and the trade's stop loss distance).

### Stake (Risk %)

The estimated stake or risk for this trade, displayed to 2 decimal places. This represents the approximate percentage of account equity at risk if the stop loss is hit.

A value of `2.00` means this trade risks approximately 2% of account equity. This should align with the BA agent's configured risk percentage per trade.

If Stake shows a value significantly different from the configured risk percentage, the position sizing calculation may have encountered an unusual spread or pip value during calculation. This is normal in low-liquidity conditions.

### Result

The profit or loss for this trade in the account's base currency (e.g., USD). Displayed to 2 decimal places.

- **Green text:** Positive result (profit)
- **Red text:** Negative result (loss)
- `—` for open trades or rejected/cancelled trades (no result exists yet)

For open trades, the Result column remains blank because the final P&L is not known until the trade closes. To see the current floating P&L of open trades, check the broker platform directly or look at the GA monitor agent's output.

For rejected or cancelled trades, no Result is shown because no position was ever opened.

### Close (Close Reason)

The reason the trade was closed. See [Section 4](#4-close-reasons-reference) for the complete reference of all possible values.

For open trades, this column shows the current status (e.g., `OPEN`) rather than a close reason.

### Analysis

A button labeled **Open** that opens the AA Analysis popup for this trade entry. This popup shows the full text of the AA agent's analysis that was associated with this trade at the time the BA agent decided to enter.

See [Section 7](#7-summary-info-and-analysis-popups) for details on the popup content.

---

## 4. Close Reasons Reference

The Close column describes why a trade ended. Understanding these values is essential for performance analysis.

### SL — Stop Loss Hit

The price moved against the trade and hit the stop loss level set at entry. The broker closed the position at (or near) the stop loss price.

- This is a planned loss — the risk management worked as intended.
- The Result will be negative, approximately equal to the configured Stake percentage of equity.
- Slippage on the actual close price vs. the set SL level may cause the Result to differ slightly from the theoretical risk amount.

**Analysis question:** Was the stop placement reasonable given the market structure at entry? Use the trade chart to examine where price was relative to swing levels when the SL was set.

### TP — Take Profit Hit

The price moved in the trade's favor and hit the take profit level. The broker closed the position at (or near) the take profit price.

- This is a planned win.
- The Result will be positive.
- Slippage on TP is typically minimal in liquid markets but can occur around major news.

### SYNC_DETECTED

The system detected a discrepancy between the broker's reported position state and what OpenForexAI expected during a position sync cycle. The system closed or adjusted the position to resolve the discrepancy.

**When this occurs:**
- The broker closed the position externally (e.g., broker margin call, account restriction, or broker-side error) and OpenForexAI detected the closed state on next sync.
- A manual close was made on the broker platform while the agent was active.
- The broker's API returned inconsistent data over multiple sync checks, triggering a safety close.

A `SYNC_DETECTED` close is always logged in detail in the system logs. If you see this reason unexpectedly, check the broker account directly and review the system logs for the sync cycle that detected the discrepancy.

### MANUAL

The trade was closed manually — either via a manual close command through the system's UI or via a direct API call. This reason may also appear if a GA agent or admin action explicitly closed the position outside of the normal SL/TP mechanism.

### REJECTED

The order was rejected at the moment of placement. The trade was never opened. Common broker rejection reasons include:
- Insufficient margin
- Market closed (e.g., weekend gap)
- Invalid unit size (below broker minimum lot)
- Spread too wide at time of submission (if spread check was configured)
- Instrument suspended or halted by broker

A `REJECTED` trade will have no From or To timestamps confirmed by the broker, no Units or Result. The Pair column shows the intended trade direction.

**Analysis question:** If you see many REJECTED entries for the same pair or time of day, the BA agent may need spread filtering or session timing adjustments.

### CANCELLED

The trade entry was prepared (the decision was made, the order object was constructed) but was cancelled before submission to the broker. This can happen if:
- The system was suspended between decision and execution.
- A pre-submission guard triggered (e.g., an open position already exists for this pair and the agent is configured to avoid doubling up).
- A configuration validation failed at the last step.

### EXPIRED

The order was submitted as a pending limit or stop order (not a market order) and expired before being filled. Less common for market-execution systems but may appear for agents configured to use limit entries.

---

## 5. Trade Detail Chart

When a trade is selected in the table, the chart area below loads a detailed price chart showing the complete context for that trade.

### Entry Arrow (Cyan)

A cyan upward arrow (for BUY trades) or downward arrow (for SELL trades) marks the exact entry candle. The arrow is placed at the candle corresponding to the trade's open timestamp.

The entry arrow lets you immediately see:
- Where in the price structure the entry occurred.
- Whether the entry was at a swing high/low, a breakout, a pullback, or another structure type.
- The market conditions at entry (what the preceding candles looked like).

### Exit Arrow (Amber)

An amber arrow marks the exit candle — the candle at which the trade closed. Combined with the entry arrow, you can see the full trade duration visually on the chart.

For trades closed by SL or TP, the exit arrow is precisely on the candle where price reached the stop level.

For `SYNC_DETECTED` closes, the exit arrow marks the candle of the sync cycle that detected the closure, which may be slightly after the actual broker close time.

### SL Line (Red)

A red horizontal line drawn at the stop loss price level set when the trade was opened. The line spans from the entry candle to the exit candle.

If the price closely approaches but does not reach this line before closing by TP, you can visually assess the risk-reward quality of the trade.

If the line is very close to the entry price relative to the TP line, the risk-reward ratio was tight. If it is far below (for a long), the trade had more breathing room.

### TP Line (Green)

A green horizontal line drawn at the take profit price level. The line spans from entry to exit.

### Support/Resistance Lines from Swing Levels

Additional horizontal lines drawn at the swing level prices that were detected at the time of the trade. These represent the support and resistance context that existed when the BA/AA agent made the decision.

These lines are particularly valuable for understanding the decision logic:
- Was the entry positioned near a key support level (for a long)?
- Was the TP placed at a resistance level?
- Was the SL placed just below the nearest support (structurally sound)?

The swing level lines use distinct styling (color and line weight) to differentiate them from the SL and TP lines.

---

## 6. Chart Controls

Controls above and alongside the trade detail chart allow you to adjust the view.

### Show Analyses Checkbox

When enabled, loads and overlays the AA agent's analysis markers on the chart as D/N markers. This shows every analysis cycle that fired during the trade's duration and the surrounding period.

**D markers** (decision markers): analyses where the AA agent output `BIAS_LONG` or `BIAS_SHORT` with `order_start_signal=YES`. These are points where conditions were favorable.

**N markers** (neutral markers): analyses where the agent output `NEUTRAL` or `order_start_signal=NO`.

Clicking an analysis marker on the chart opens the AA Recommendation popup (see Section 7).

**When to enable:** When you want to understand the full analytical context around a trade. For example, if a trade went into a loss, were there subsequent analysis cycles that showed the trend reversing? Did the AA start generating `NEUTRAL` while the trade was still open?

### Timeframe Buttons

**Available:** M5, M15, M30, H1

Switches the chart to display candles at the selected timeframe. The entry/exit arrows, SL/TP lines, and swing level lines are all redrawn and correctly positioned on the new timeframe.

**Typical usage:**
- Start on H1 to see the macro trend context — was the trade in the right direction for the broader structure?
- Switch to M15 to examine the entry timing — was the entry at a sensible point in the swing?
- Switch to M5 to inspect the exact entry and exit candles in detail — was the execution price as expected?

### EMA Indicator

A checkbox plus period input plus timeframe dropdown for adding an EMA line to the chart. Period accepts integers from 1 to 500. Timeframe is independent of the chart timeframe.

**Typical use:** Add EMA 20 on H1 to see whether price was above or below the trend line at entry. Add EMA 50 on H1 for the medium-term trend reference.

### RSI Indicator

A checkbox plus period input plus timeframe dropdown for adding an RSI oscillator panel below the chart.

**Typical use:** Check RSI at the entry candle — was the indicator in an overbought/oversold zone that might have signaled caution? Was the RSI trending in the direction of the trade?

### ATR Indicator

A checkbox plus period input plus timeframe dropdown for adding an ATR oscillator panel.

**Typical use:** Check volatility at entry. Was ATR elevated (news event)? Was ATR very low (consolidation, potentially false breakout)? Does the SL distance make sense relative to the ATR at the time?

---

## 7. Summary Info and Analysis Popups

### Analysis Column — Open Button

Each trade row in the table has an **Open** button in the Analysis column. Clicking it opens the AA Analysis popup.

**AA Analysis Popup contents:**
- The full stored analysis text or JSON from the AA agent that was associated with this trade.
- The complete output of the analysis cycle that preceded the BA agent's decision to enter.
- A **Copy** button to copy the full text to clipboard.
- A **Close** button to dismiss the popup.

This is the definitive answer to "what did the system think when it decided to enter?" Reading this popup for a losing trade tells you whether the analysis was reasonable given the information available at the time (and the loss was simply bad luck or unfavorable execution), or whether the analysis itself contained a flawed assessment.

### Chart Analysis Markers — Recommendation Popup

Clicking any D or N marker on the chart (when Show Analyses is enabled) opens the AA Recommendation popup.

**AA Recommendation popup contents:**

A 4-column header grid showing:
- **Decision:** The directional output (BIAS_LONG, BIAS_SHORT, NEUTRAL)
- **Confidence:** The confidence percentage from the LLM output
- **Order Start Signal:** YES or NO — whether the agent signaled readiness for a trade entry
- **Entry Quality:** The quality rating of the potential entry (HIGH, MEDIUM, LOW)

Below the header:
- **Decision JSON / Full Text:** The complete decision output from the AA agent, including reasoning. A Copy button is included.
- **Decision Snapshot:** The market snapshot that was provided to the AA agent at the time of this analysis. This is the full JSON snapshot (same as what appears in the Chat page's Snapshot inspector tab). A Copy button is included. This section is only shown if the snapshot was stored with the analysis record — older records or configurations without snapshot storage may show `Not available`.

**Why the Snapshot is valuable here:** When reviewing a historical trade, the snapshot tells you exactly what data the agent had — not what you see now, but what existed at that candle at that time. This is the only way to definitively audit an AI trading decision.

---

## 8. Print Function

The Print button in the filter bar opens a print dialog for the currently selected trade. It generates a structured, printer-friendly HTML report that you can print or save as PDF.

### Print Dialog Options

| Checkbox | Description |
|---|---|
| **Chart** | Include a snapshot of the current chart view in the printout |
| **Candle Data** | Include the OHLCV data for the entry and exit candles |
| **Analysis** | Include the AA analysis text associated with this trade |

You can enable any combination of these three options. Deselecting all three and clicking Print generates a minimal report with only the trade metadata (pair, direction, timestamps, units, result, close reason).

### Clicking Print

After confirming the dialog options, click **Print**. The system generates an HTML page with the selected content and opens the browser's native print dialog. From there you can:
- Print to a physical printer.
- Save as PDF using the browser's "Save as PDF" print destination.
- Adjust page margins, orientation, and scale via the browser's print settings.

### Typical Use Cases for Printing

- **Trading journal:** Print a report for each completed trade to add to a physical or digital trading journal with notes.
- **Performance review:** Print a batch of closed trades (using the closed filter and a suitable Max Orders count) for weekly or monthly review meetings.
- **Audit trail:** Print the full report (chart + analysis + data) for trades where `SYNC_DETECTED` was the close reason, for discussion with your broker.
- **Strategy documentation:** Print selected trades that exemplify a specific setup type (e.g., "London breakout long" trades) to document the strategy's real-world execution.

---

## 9. Practical Workflows

### Workflow 1: Daily Performance Review

At the end of each trading day:

1. Set filter to **Closed**.
2. Set Max Orders to a number that covers the day's trades (e.g., 20–50).
3. Click **Refresh**.
4. Review the Result column — which trades were profitable, which were not?
5. For each closed trade, click the row to load the chart.
6. Enable **Show Analyses** to see the AA analysis context around the trade.
7. For any trade that went against you, read the AA Analysis popup — was the analysis sound? Was the market unfavorable despite a correct analysis?
8. Check the Close column — were all closes by SL or TP (planned)? Any SYNC_DETECTED closes need attention.

Typical time: 10–30 minutes depending on trade count.

### Workflow 2: Reviewing a Losing Trade Step by Step

**Goal:** Understand exactly why a specific losing trade occurred and whether it was a system error or simply a losing trade in a valid strategy.

1. Find the losing trade in the table (filter Closed, look for negative Results in red).
2. Click the row to load the chart.
3. Set timeframe to **H1** to see the macro context.
4. **Was the direction correct for the H1 structure?** Check EMA overlay and overall trend.
5. Set timeframe to **M15** for the entry context.
6. **Was the entry at a sensible location?** Entry arrow should be near structure (support for long, resistance for short).
7. Check the **SL line** — was the stop below the nearest swing low (for a long)? Or was it too tight, inside the normal price noise?
8. Check the **TP line** — was the reward reasonable relative to the risk?
9. Click **Open** in the Analysis column — read the AA analysis. Did the agent correctly identify the setup?
10. Enable **Show Analyses** and click nearby D/N markers — was the AA consistently bullish/bearish, or did it start generating NEUTRAL signals early in the trade?
11. If the analysis was sound and the stop was structurally placed but price hit it anyway: this is a valid losing trade. No system action required.
12. If the analysis had flawed reasoning or the stop was poorly placed: this is a strategy/configuration issue to address.

### Workflow 3: Investigating a SYNC_DETECTED Close

**Scenario:** A trade shows `SYNC_DETECTED` in the Close column. You need to understand what happened.

1. Click the trade row to load the chart.
2. Note the exit time (To column) — this is when the sync detected the discrepancy.
3. Switch to M5 to examine price action at the exit time — did price move sharply at that candle?
4. Check the broker platform directly using the trade's ID — what does the broker show as the close reason?
5. Read the system logs for the sync cycle at that timestamp for full details.
6. Common scenario: the broker stopped the trade (e.g., margin call, or the broker's own risk management) and OpenForexAI detected this on the next sync. The `SYNC_DETECTED` entry is the system correctly recording what the broker did.
7. Less common: a data sync glitch caused a false detection. In this case the broker platform will show the trade as still open or closed for a different reason.

### Workflow 4: Analyzing Rejected Trades

**Goal:** Understand patterns in rejected orders to improve BA agent configuration.

1. Set filter to **Rejected**.
2. Click Refresh.
3. Look at the Pair column — is one pair consistently getting rejections?
4. Look at the From timestamps — are rejections clustered at specific times (e.g., market open, low-liquidity periods)?
5. Check the Result and ID columns — both are empty for rejected trades, confirming no position was ever opened.
6. Click a rejected trade to load the chart — examine what price and spread conditions looked like at the rejection time.
7. Consider adding spread filters or session time restrictions to the BA agent's configuration if rejections cluster at specific times.

---

## 10. Scenarios and Examples

### Scenario A: Winning Trade — Validating the Setup

**Trade:** GBPUSD SELL, 4h 15m duration, Result: +$47.20, Close: TP.

**Review steps:**
1. Load chart on H1 — confirm price was in a clear downtrend (EMA sloping down, bearish candles).
2. Switch to M15 — the entry arrow shows a short was entered after a pullback to resistance. Structurally sound.
3. SL line is above the swing high that defined the resistance. TP line is at the next support level.
4. Show Analyses — D markers preceding entry were consistently BIAS_SHORT with order_start_signal=YES. The system had conviction.
5. Click the D marker nearest to entry — confidence was 87%, Entry Quality HIGH.
6. Conclusion: clean setup, correct execution, deserved winner. No action needed.

### Scenario B: Losing Trade — Premature Stop Loss

**Trade:** EURUSD BUY, 0h 22m duration, Result: -$24.00, Close: SL.

**Review steps:**
1. H1 chart — price is overall bullish but currently in a retracement.
2. M5 chart — entry arrow is during a retracement. Price continued lower before the SL was hit.
3. SL line is only 12 pips below entry. ATR at that time was 18 pips — the stop was inside one ATR of noise.
4. Analysis popup — AA analysis described the market as bullish with a retracement buying opportunity. Correct direction.
5. Conclusion: the directional analysis was correct (price eventually went higher after the SL was hit). The stop was too tight relative to ATR. BA agent's SL calculation should use a wider ATR multiplier.

### Scenario C: SYNC_DETECTED Trade Audit

**Trade:** USDCAD BUY, 1h 55m duration, Result: -$18.50, Close: SYNC_DETECTED.

**Review steps:**
1. To timestamp shows the close was detected at 17:33 UTC on a Friday.
2. Broker platform confirms: the trade was closed at 17:00 UTC due to end-of-week margin adjustment by the broker.
3. OpenForexAI detected the closed position at 17:33 UTC (the next sync cycle after 17:00).
4. The SYNC_DETECTED close is correct — the broker closed the trade, and the system accurately recorded this.
5. Action: consider configuring the BA agent to not open new positions after 16:30 UTC on Fridays to avoid end-of-week broker closures.

### Scenario D: Identifying a Streak of Rejections at Market Open

**Trade records:** Five consecutive REJECTED entries for EURUSD BUY at 08:00–08:05 UTC on multiple days.

**Analysis:**
1. The trades are rejected consistently at the start of the Frankfurt open session.
2. The M1/M5 chart at that time shows wide spreads immediately at open — spread is often 3–5 pips vs. the normal 0.8 pips.
3. The BA agent has no spread filter configured, so it submits orders even during spread widening.
4. Action: add a max spread filter to the BA agent configuration (e.g., reject entries if spread > 2.0 pips). After Suspend → config change → Restart, rejections at open should stop.

---

## 11. Quick Reference

### Filter Buttons Summary

| Filter | Shows |
|---|---|
| All | Every trade regardless of status |
| Open | Currently open positions only |
| Closed | Completed trades (SL, TP, Manual, Sync) |
| Rejected | Orders that were never opened (rejected by broker) |

### Close Reasons Summary

| Close Reason | Meaning | Result Sign |
|---|---|---|
| SL | Stop loss hit — planned loss | Negative |
| TP | Take profit hit — planned win | Positive |
| SYNC_DETECTED | Broker state discrepancy detected | Either |
| MANUAL | Manually closed | Either |
| REJECTED | Never opened — broker rejection | None |
| CANCELLED | Never submitted — pre-trade cancel | None |
| EXPIRED | Pending order expired unfilled | None |

### Chart Markers Summary

| Marker | Color | Meaning |
|---|---|---|
| Entry Arrow | Cyan | Trade open candle |
| Exit Arrow | Amber | Trade close candle |
| SL Line | Red horizontal | Stop loss price level |
| TP Line | Green horizontal | Take profit price level |
| Swing Lines | Varies | S/R levels at trade time |
| D Marker | Green label | AA analysis with order signal |
| N Marker | Gray label | AA analysis without order signal |

### Column Quick Reference

| Column | Contains | Yellow = |
|---|---|---|
| Pair | Instrument, direction, status | — |
| From | Entry timestamp | Local-only, broker unconfirmed |
| To | Exit timestamp | Local-only, broker unconfirmed |
| HH:MM | Trade duration | — |
| ID | Broker order ID | — |
| Units | Position size in base currency units | — |
| Stake | Estimated risk as % of equity | — |
| Result | P&L in account currency | — |
| Close | Close reason | — |
| Analysis | Button to open AA analysis popup | — |
