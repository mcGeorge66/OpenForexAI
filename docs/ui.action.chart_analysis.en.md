[Back to Action](ui.action.en.md)

# Chart Analysis

Chart Analysis is the **full-featured technical analysis tool** within OpenForexAI. Unlike the Agent Chat chart (which is secondary to agent interaction), the Chart Analysis page is a standalone charting workspace that can run in two modes:

- **Free mode** (🔓, default): you control the pair, broker, timeframe, candle count, all indicators, drawing tools, and swing level detection with no order attached. It auto-refreshes every 30 seconds, and all your indicators/drawings are preserved across refreshes.
- **Order Focus mode** (🔒): opened from the Orderbook's **Chart** button on a specific trade. The chart loads that order's pair/broker and a candle window anchored around its close time, draws its Entry/Exit/SL/TP levels, and freezes (no more 30-second auto-refresh) so the historical setup doesn't shift under you while you review it. See [Section 19](#19-order-focus-mode).

Both modes share a built-in **AI Chart Assistant** — a chat window you open explicitly (it never opens itself) that can explain what's on screen and even draw its own markers/zones on the chart. See [Section 20](#20-chart-assistant).

Use Chart Analysis for free-form technical analysis, session planning, strategy development, visual confirmation of what the agents are "seeing," and post-mortem review of specific trades.

---

## Table of Contents

1. [Page Layout Overview](#1-page-layout-overview)
2. [Header Bar — Controls](#2-header-bar--controls)
3. [Auto-Refresh Behavior](#3-auto-refresh-behavior)
4. [Chart Area](#4-chart-area)
5. [Bottom Panel — Left Column: Indicators](#5-bottom-panel--left-column-indicators)
6. [Indicator Reference: EMA and SMA](#6-indicator-reference-ema-and-sma)
7. [Indicator Reference: RSI](#7-indicator-reference-rsi)
8. [Indicator Reference: ATR](#8-indicator-reference-atr)
9. [Indicator Reference: BB (Bollinger Bands)](#9-indicator-reference-bb-bollinger-bands)
10. [Indicator Reference: VWAP](#10-indicator-reference-vwap)
11. [Indicator Reference: SlopeE (EMA Slope)](#11-indicator-reference-slopee-ema-slope)
12. [Indicator Reference: SlopeS (SMA Slope)](#12-indicator-reference-slopes-sma-slope)
13. [Indicator Row Controls](#13-indicator-row-controls)
14. [Swing Levels](#14-swing-levels)
15. [Bottom Panel — Middle Column: Drawing Tools](#15-bottom-panel--middle-column-drawing-tools)
16. [Bottom Panel — Right Column: Candle Data and Analyst View](#16-bottom-panel--right-column-candle-data-and-analyst-view)
17. [Sessions and Analyst Overlays](#17-sessions-and-analyst-overlays)
18. [Print Function](#18-print-function)
19. [Order Focus Mode](#19-order-focus-mode)
20. [Chart Assistant](#20-chart-assistant)
21. [Practical Workflows and Examples](#21-practical-workflows-and-examples)
22. [Quick Reference](#22-quick-reference)

---

## 1. Page Layout Overview

```
┌───────────────────────────────────────────────────────────────┐
│ HEADER: Pair|Broker|🔒/🔓 Mode|Timeframe|Candles|Anchor|Reload│
│         [range diagnostic] [active tool]     Fit|Zoom|Sessions│
│                                          Analyst|Print|→KB|Assistant│
├───────────────────────────────────────────────────────────────┤
│                                                               │
│                    MAIN CHART AREA                            │
│         (candlesticks, indicators, drawings, markers)         │
│                                       ┌─────────────────────┐ │
│                                       │  Chart Assistant     │ │
│                                       │  (floating, drag/    │ │
│                                       │   resize, opened via │ │
│                                       │   the Assistant      │ │
│                                       │   toggle button)     │ │
│                                       └─────────────────────┘ │
├═══════════════════════════════════════════════════════════════╡
│  BOTTOM PANEL (resizable, 120–600px)                         │
│  ┌─────────────────┬────────────────┬────────────────────┐   │
│  │ LEFT            │ MIDDLE         │ RIGHT              │   │
│  │ Indicators      │ Drawing Tools  │ Candle Data        │   │
│  │ (EMA/SMA/RSI    │ (lines, fibs,  │ Analyst View       │   │
│  │  ATR/BB/VWAP    │  shapes,       │                    │   │
│  │  SlopeE/SlopeS) │  Elliott,      │                    │   │
│  │ ─────────────── │  Measure)      │                    │   │
│  │ Swing Levels    │                │                    │   │
│  └─────────────────┴────────────────┴────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

The bottom panel can be resized vertically by dragging the handle at the bottom of the chart area. Minimum height: 120px. Maximum height: 600px.

The Chart Assistant window (top-right corner by default) is drawn **outside** this layout — it floats above the chart, can be dragged by its header and resized from its bottom-right corner, and only appears once you click the **Assistant** toggle button. It never opens itself, including when Order Focus mode loads a trade.

---

## 2. Header Bar — Controls

### Pair Dropdown

Selects the currency pair (instrument) to display. The available instruments come from the active broker connections configured in `system.json5`. Pairs are listed using broker notation (e.g., `EUR_USD`, `GBP_USD`, `XAU_USD`).

Changing the pair immediately reloads the chart with the new instrument's data. All current indicators are re-applied to the new pair's data. Drawings remain on the chart but may appear at irrelevant price levels for the new pair (they are positionally fixed to price values, not percentage or relative positions).

### Broker Dropdown

Selects which broker's data feed to use for the chart. This dropdown is only visible when more than one broker is connected in the system configuration.

Different brokers may show slightly different prices due to different liquidity providers, spreads, and data normalization. If your agents are configured to use a specific broker, using the same broker in Chart Analysis ensures you are seeing the exact same data the agents see.

### Mode Indicator (🔒 Order / 🔓 Frei)

A small badge sits right after the Broker dropdown and always shows which mode the page is in:

- **🔓 Frei** (gray) — free mode. You control everything manually; nothing is pinned to a trade.
- **🔒 Order** (indigo, clickable) — Order Focus mode. The pair, broker, and anchor were set automatically from a specific order (opened via the Orderbook's **Chart** button). Hovering it shows the pair/direction in a tooltip.

Clicking the **🔒 Order** badge while focused immediately leaves Order Focus mode and returns to free mode (candle count resets to 200, the anchor is cleared, and auto-refresh resumes). This is the fastest way to "unpin" the chart after reviewing a trade without losing your place — pair/broker/timeframe stay as they were, only the order-specific parts are dropped. See [Section 19](#19-order-focus-mode) for the full behavior.

### Timeframe Buttons

Button group for selecting the chart resolution:

| Button | Resolution | Bar Duration | Typical Use |
|---|---|---|---|
| M5 | 5-minute | 5 minutes per candle | Entry precision, scalping |
| M15 | 15-minute | 15 minutes per candle | Short-term structure |
| M30 | 30-minute | 30 minutes per candle | Intraday structure |
| H1 | 1-hour | 1 hour per candle | Trend analysis, primary timeframe |
| H4 | 4-hour | 4 hours per candle | Swing trading context |
| D1 | Daily | 1 day per candle | Long-term bias |

Switching timeframes immediately reloads candles. All indicators are re-computed for the new timeframe. Drawings remain in place but may need review for relevance.

Additional timeframes may be available depending on your broker adapter configuration.

### Candle Count

A number field that sets how many candles to load. Range: 20 to 2000.

- **Low values (50–100):** Faster loading, focused view of recent price action. Good for entry analysis.
- **Medium values (200–500):** Balanced context, shows several weeks of H1 data or months of H4.
- **High values (1000–2000):** Extended history, useful for identifying long-term support/resistance zones and swing levels with wide lookback windows.

Loading more candles increases chart load time. On H1 with 2000 candles, you are viewing approximately 83 days of history (2000 candles × 1 hour ÷ 24 hours = 83 days).

### Anchor Field

A `datetime-local` input, always visible right after Candle Count, labeled **Anchor**. Left empty (the default), the chart loads the most recent candles — live/latest data, refreshed on the 30-second cycle. Set it to a specific date/time and the chart instead loads exactly `Candle Count` candles **ending at that point in time**, and stays there (no more "latest" fetches sneaking newer candles into view). A small `×` button next to the field appears once it has a value, to clear it back to live data in one click.

This is the same mechanism Order Focus mode uses automatically — Order Focus just pre-fills this exact field with the order's own close time (see [Section 19](#19-order-focus-mode)) instead of leaving it for you to set by hand. Indicators, the DXY overlay, and Swing Levels all now read this same anchor too, so everything on screen is computed against the same historical point instead of silently mixing an anchored candle window with live-computed indicator values (a bug that has since been fixed — previously, indicators/DXY/swing levels always computed against "now" even when the chart itself was anchored to the past, which could show today's EMA value next to last month's candles).

**Example — reviewing why a trade lost:** set Anchor to the order's own close timestamp (e.g. `2026-08-14T09:35`) and Candle Count to something that comfortably spans the trade (e.g. 200), then Reload — you now see exactly the price action leading into and out of the close, with indicators/swing levels computed as of that moment, not today. Better yet: don't set it by hand at all — open the trade from the Orderbook's **Chart** button, which sets this same field for you (close time + 1 hour) and also draws the trade's own Entry/Exit/SL/TP lines on top, see [Section 19](#19-order-focus-mode).

**Warning:** the anchor (like all order/candle timestamps in this system) is a naive broker-local wall-clock value — it is never converted through the browser's own timezone. Typing a time here means "load candles ending at this clock time in the broker's own timezone," not "in my local timezone," which matters if your machine's timezone differs from the broker's.

### Reload Button

Manually fetches fresh candle data from the broker. Shows a spinner while loading and is disabled during the load to prevent duplicate requests.

Use Reload when you want to see the very latest candle immediately rather than waiting for the next 30-second auto-refresh cycle. Also use it after changing the candle count or the anchor, or if you suspect the chart is showing stale data.

### Loaded-Range Diagnostic Badge

Directly after the Reload button (and any error message), a small badge shows exactly what was loaded, e.g. `200× 2026-08-14 06:00 → 2026-08-14 22:35`. Hovering it shows the full first/last timestamp and candle count. This exists because a screenshot of the chart alone can't tell you *why* something looks off — it answers "is my requested window wrong, or is something else (a marker, an indicator) the problem" at a glance.

In Order Focus mode, the badge additionally turns amber and appends a warning if the focused order's own start and/or end time falls **outside** the loaded candle window (`⚠ Order-Start außerhalb!`, `⚠ Order-Ende außerhalb!`, or both) — a direct sign that the loaded window needs to be widened (increase Candle Count) or the anchor adjusted, because the trade's markers/price lines have nothing to attach to on screen.

### Active Tool Display

When a drawing tool is active (you have clicked one of the drawing buttons), this area in the header shows:
- The tool name (e.g., "Trendline")
- The progress in multi-point drawings (e.g., "(1/2 pts)" for a trendline where you have placed the first point)
- A `✕` button to cancel the active drawing without placing it

This prevents confusion about which tool is active, especially for multi-point drawings where the cursor behavior changes.

### Elliott "Done" Button

This button appears only when an Elliott Wave drawing is in progress. Clicking it finalizes the wave drawing even if fewer than the configured maximum points have been placed. This is useful when you can clearly identify 3 or 5 wave points and do not need to place all configured points.

### Fit Button

Located immediately to the left of the Zoom/Pan toggle. Fits **all currently loaded candles** into the visible chart width in one click — the entire loaded window, edge to edge, regardless of how many candles that is.

This is deliberately different from what happens when the chart resets to its default zoom (e.g. after a Reload): that reset shows `min(configured range, loaded candles)`, which can still **crop** a larger loaded window down to a smaller configured range (so if you loaded 1000 candles but the configured range is 200, a plain reset only shows the most recent 200). Fit ignores the configured range entirely and stretches every loaded candle across the pane — use it right after loading a large historical window (e.g. via the Anchor field) when you want to see the whole thing at once instead of just the tail end of it.

### Zoom Toggle (Pan/Zoom)

Switches the mouse behavior between two modes:

**Zoom mode (default):**
- Mouse wheel: zooms in and out on the chart horizontally
- Click and drag on chart: pans the chart
- Clicking to place drawings works normally

**Pan mode (✋ icon active):**
- All mouse interactions are dedicated to panning
- Drawing placement is disabled in this mode
- Switch back to Zoom mode to resume drawing

Use Pan mode when you want to scroll through long chart history without accidentally placing drawing points.

### Sessions Checkbox

When enabled, overlays colored session bands on the chart to mark the opening and closing times of the major trading sessions:

- **Sydney session** (blue)
- **Tokyo session** (amber/orange)
- **London session** (green)
- **New York session** (orange)

Overlapping sessions (London/New York overlap, for example) appear as blended colors or with a distinct overlap band.

Session bands help you correlate price behavior with session context — breakouts that occur at the London open are typically more reliable than moves in low-volume Asian sessions for European pairs.

The session times are shown in the chart's display timezone. If your system is configured for UTC, the bands align to UTC session times.

### Analyst Checkbox

When enabled, fetches and overlays the AA agent analysis markers on the chart. Each analysis cycle that ran during the visible chart window gets one marker, bucketed to its own candle (if two analyses land in the same candle, the later one wins):

- **U** (green, ▲ arrow, below the bar): the analysis's `primary_bias` was `BIAS_LONG` (or `BIAS_REVERSAL_LONG`) — bullish bias.
- **D** (red, ▼ arrow, below the bar): `primary_bias` was `BIAS_SHORT` (or `BIAS_REVERSAL_SHORT`) — bearish bias.
- **N** (gray, circle, below the bar): anything else (including `BIAS_NEUTRAL`) — no directional bias.

If the analysis also has a stored confidence value, it's appended on a second line, e.g. `U` + `85%`. Note this marker only reflects the *bias direction* — it does **not** filter on whether the agent actually signalled a trade entry (`order_start_signal`); that field is only shown once you open the AA Recommendation popup (see Section 16), not encoded in the marker's letter or color.

Clicking a marker opens the AA Recommendation popup for that cycle (see Section 16).

Analyst markers are loaded from the database and reflect real historical analysis cycles that ran on the selected pair. They are not reconstructed or recalculated — they are the actual decisions stored at the time they were made.

### Print Button

Opens the print dialog. See [Section 18](#18-print-function).

### → KB Button

Saves a Markdown snapshot of the current chart to the Knowledgebase's `ChartAnalysis` import bucket: a screenshot of the chart, the selected candle's OHLCV (if any), the current indicator values, the swing level list (if enabled), and the selected analysis text (if any). Useful for building a written record of a setup you want to reference later without re-configuring the whole chart from scratch. Shows a brief "✓ In Knowledgebase gespeichert" confirmation in place of the button for two seconds.

### Assistant Button

Toggles the floating **Chart Assistant** chat window open/closed. It is off by default and stays off even when Order Focus mode loads a trade — you always open it explicitly. See [Section 20](#20-chart-assistant) for what it can do.

---

## 3. Auto-Refresh Behavior

In **free mode** with no Anchor set, the Chart Analysis page **automatically reloads candle data every 30 seconds**. This means the chart stays live while you work on it — the latest candle is always at most 30 seconds old.

**Auto-refresh does not run in Order Focus mode.** A closed historical trade doesn't need "the latest candles," and re-fetching on a timer would reset your pan/zoom out from under you every 30 seconds for no benefit — so the chart stays frozen on the order's own candle window until you leave Order Focus mode (click the 🔒 badge). See [Section 19](#19-order-focus-mode). Setting an Anchor manually in free mode does **not** by itself stop the 30-second timer — it re-fetches the same anchored (past) window every cycle, which is a no-op in practice but is worth knowing if you're wondering why the loading spinner still blinks periodically on an anchored chart.

### What Reloads on Auto-Refresh

- Candle data (all OHLCV bars for the current pair, timeframe, and candle count)
- All indicator values (EMA, SMA, RSI, ATR, BB, VWAP, SlopeE, SlopeS) — every indicator instance is recomputed via the same backend calculation call, so there is no separate "client-side" calculation path; see [Section 6](#6-indicator-reference-ema-and-sma) onward for what's computed, not where.
- The DXY overlay data shown in the Candle Data panel

### What is PRESERVED Across Auto-Refresh

**All configured indicators are preserved.** When the auto-refresh fires, every indicator you have added — including all settings (period, timeframe, color, line style, line width) — remains exactly as you configured it. The data updates but your configuration does not change.

This is a critical design property. Previously, auto-refresh would reset the indicator list, requiring you to re-add and re-configure indicators after each refresh. This bug has been fixed. Your indicator setup survives the refresh cycle.

**All drawings are preserved.** Trendlines, Fibonacci retracements, horizontal lines, rectangles, and all other drawing objects remain on the chart through auto-refreshes.

**Swing level settings are preserved.** Your swing level configuration (timeframe, count, ATR period, gap filter) is retained and swing levels are recalculated with fresh data on each refresh if enabled.

### When Auto-Refresh Does Not Apply

- **Order Focus mode:** never — the chart is frozen until you leave focus mode (see above).
- If the browser tab is in the background (hidden), some browsers throttle JavaScript timers, potentially increasing the actual refresh interval beyond 30 seconds.
- Placing a drawing is not itself deferred or blocked by auto-refresh — a refresh landing mid-placement does not cancel or interrupt an in-progress drawing, since drawings, once placed, are stored independently of the candle data.

---

## 4. Chart Area

The main chart area is the central interactive canvas. It displays:

**Candlestick Bars:** Standard OHLCV candlesticks. Green/hollow bars for bullish candles (close above open), red/filled bars for bearish candles. The exact color scheme depends on the configured theme.

**Volume Bars:** If volume data is available from the broker, volume bars are displayed at the bottom of the chart area as thin vertical bars, with height proportional to tick volume. Tick volume (number of price ticks) is used for forex pairs since true transactional volume is not available in OTC markets.

**Indicator Overlays:** EMA, SMA, BB, VWAP lines are drawn directly on the price chart. Oscillator-type indicators (RSI, ATR, SlopeE, SlopeS) appear in separate panels below the price chart, stacked vertically.

**Drawing Objects:** All placed drawings (lines, Fibonacci tools, shapes, labels) appear in their configured positions.

**Analysis Markers:** D/N markers from AA agent cycles appear as small text labels attached to specific candles when the Analyst checkbox is enabled.

**Session Bands:** Colored vertical bands spanning the full chart height, marking session open/close times when the Sessions checkbox is enabled.

**Swing Level Lines:** Horizontal lines at detected swing high/low prices, colored and styled according to the swing level configuration.

### Chart Interaction

- **Click a candle:** Selects that candle. Populates the Candle Data panel in the bottom-right column with that candle's OHLCV data and computed indicator values.
- **Click a drawing control point:** Selects the drawing for editing.
- **Click an analysis marker:** Opens the AA Recommendation popup for that cycle.
- **Mouse wheel:** Zoom in/out (Zoom mode).
- **Click and drag on empty space:** Pan the chart left/right.
- **Click a drawing button:** Activates the tool. First click on the chart places the first point; subsequent clicks place additional points until the drawing is complete.

---

## 5. Bottom Panel — Left Column: Indicators

The left column of the bottom panel contains two collapsible sections: **Indicators** and **Swing Levels**.

### Indicators Section

Click the section title to expand or collapse it.

**Adding indicators:** Eight buttons add new indicator instances — one per click:
- `EMA` — Exponential Moving Average
- `SMA` — Simple Moving Average
- `RSI` — Relative Strength Index
- `ATR` — Average True Range
- `BB` — Bollinger Bands
- `VWAP` — Volume Weighted Average Price
- `SlopeE` — EMA Slope oscillator
- `SlopeS` — SMA Slope oscillator

Each click adds one new indicator instance with default settings. Multiple instances of the same type are fully supported — for example, three EMA lines at periods 20, 50, and 200 are a common setup.

The per-indicator row controls are described in [Section 13](#13-indicator-row-controls).

---

## 6. Indicator Reference: EMA and SMA

### EMA — Exponential Moving Average

**Type:** Price overlay (drawn on the candlestick chart)

**Calculation:** A moving average that gives exponentially more weight to recent prices. Reacts faster to price changes than SMA.

**Formula:** `EMA(n) = Price × k + EMA_prev × (1 - k)` where `k = 2 / (n + 1)`

**Common periods:**
- EMA 20: Short-term trend, entry trigger reference
- EMA 50: Medium-term trend, structural reference
- EMA 200: Long-term trend, major trend definition

**Reading the EMA:**
- Price above EMA → bullish bias (buyers in control)
- Price below EMA → bearish bias (sellers in control)
- EMA slope upward → trend is accelerating upward
- EMA slope downward → trend is accelerating downward
- Price crossing the EMA → potential trend change (confirm with other factors)

**Multi-EMA setups:** Adding three EMA lines (e.g., 20/50/200) lets you quickly see alignment: if all three are stacked in order (price > EMA20 > EMA50 > EMA200), the trend is strongly bullish on all timeframes.

### SMA — Simple Moving Average

**Type:** Price overlay

**Calculation:** A simple arithmetic average of the last N closing prices. Equal weight to all periods.

**Differences from EMA:**
- SMA is slower to react to price changes than EMA.
- SMA is smoother and less prone to false signals in choppy markets.
- EMA is preferred for trend-following; SMA is preferred for identifying key price levels that markets respect over longer periods.

**Common SMA use case:** SMA 200 on D1 is widely watched as the long-term bull/bear dividing line. Many institutional strategies reference whether price is above or below the 200-day SMA.

---

## 7. Indicator Reference: RSI

**Type:** Oscillator (separate panel below price chart)

**Calculation:** RSI measures the speed and change of price movements. Range: 0 to 100.

**Formula:** `RSI = 100 - (100 / (1 + RS))` where `RS = Average Gain / Average Loss` over N periods.

**Standard period:** 14 (configurable 1–500)

**Key levels:**
- **Above 70:** Overbought zone — price has risen sharply and may be due for a pullback or consolidation. In strong trends, RSI can stay above 70 for extended periods.
- **Below 30:** Oversold zone — price has fallen sharply and may be due for a bounce.
- **50 level:** The centerline. RSI above 50 indicates net bullish momentum; below 50 indicates net bearish momentum.

**RSI divergence (advanced):**
- **Bullish divergence:** Price makes a lower low but RSI makes a higher low. Signals weakening bearish momentum, potential reversal up.
- **Bearish divergence:** Price makes a higher high but RSI makes a lower high. Signals weakening bullish momentum, potential reversal down.

**Timeframe independence:** RSI can be configured on a different timeframe than the chart. Adding RSI 14 H1 while viewing M15 candles shows the H1 RSI value at each M15 candle, painted as a horizontal segment extending from each H1 boundary.

---

## 8. Indicator Reference: ATR

**Type:** Oscillator (separate panel)

**Full name:** Average True Range

**Calculation:** Measures volatility. True Range is the greatest of: (High - Low), |High - Previous Close|, |Low - Previous Close|. ATR is the moving average of True Range over N periods.

**Standard period:** 14

**Units:** Price units (pips for forex). An ATR of 0.0015 for EURUSD means the average volatility over the ATR period is 15 pips per candle.

**Practical uses:**
- **Stop loss sizing:** Place stops at 1.5× or 2× ATR below entry (for longs) to allow for normal price volatility without being stopped out prematurely.
- **Volatility context:** High ATR = volatile market (news events, active sessions). Low ATR = quiet market (consolidation, weekend approach). Know which environment you are trading in.
- **Breakout confirmation:** A breakout candle with ATR significantly above the recent average confirms genuine momentum; a breakout with low ATR may be a false move.
- **Trade target sizing:** If ATR is 25 pips on H1, a take profit of 50 pips is 2× ATR — achievable in normal conditions. A TP of 150 pips is 6× ATR — may require holding through multiple sessions.

---

## 9. Indicator Reference: BB (Bollinger Bands)

**Type:** Price overlay (three lines on the chart)

**Full name:** Bollinger Bands

**Calculation:** Three lines computed by the backend:
- **Middle band:** SMA of N periods (typically 20)
- **Upper band:** Middle band + (K × standard deviation over N periods)
- **Lower band:** Middle band − (K × standard deviation over N periods)

Standard settings: Period 20, K = 2 (2 standard deviations).

**How to read Bollinger Bands:**
- **Band width:** Wide bands = high volatility. Narrow bands (squeeze) = low volatility, often precedes a breakout.
- **Price touching upper band:** Price is at the statistical upper edge of its recent range. In a trending market, this is normal and the upper band acts as a dynamic resistance. In a ranging market, a touch of the upper band is a potential shorting zone.
- **Price touching lower band:** Price is at the statistical lower edge. In a ranging market, a potential buy zone.
- **Walking the bands:** In strong trends, price "walks" along the upper (for uptrends) or lower (for downtrends) band for multiple candles. This indicates sustained directional momentum.
- **Mean reversion:** In ranging markets, prices tend to return to the middle band after touching the outer bands.

**BB is backend-computed:** like every indicator in this panel, the calculation is performed on the server (via the same `calculate_indicator` call used for EMA/SMA/RSI/ATR/SlopeE/SlopeS too) using the full candle dataset, which allows the standard deviation to be computed correctly over the full period.

---

## 10. Indicator Reference: VWAP

**Type:** Price overlay (single line)

**Full name:** Volume Weighted Average Price

**Calculation:** `VWAP = Σ(Typical Price × Volume) / Σ(Volume)` where Typical Price = (High + Low + Close) / 3. Cumulative from the start of the period (typically the start of the trading day or session).

**VWAP is backend-computed** — same as every other indicator in this panel — and benefits from it the same way BB does: the server has access to the full session's cumulative volume data.

**How to read VWAP:**
- **Price above VWAP:** Buyers have been dominant since the session start. Bullish intraday bias.
- **Price below VWAP:** Sellers have been dominant. Bearish intraday bias.
- **VWAP as support/resistance:** In liquid markets, VWAP acts as an intraday support/resistance level. Price often gravitates back to VWAP after deviating, especially during low-liquidity periods.
- **Institutional reference:** Institutional traders often benchmark execution against VWAP. Price near VWAP is where large orders are absorbed; significant deviations attract mean-reversion activity.

**Forex note:** True transactional volume is not available in OTC forex markets. VWAP uses tick volume (number of price updates) as a proxy for volume. This is less precise than equity VWAP but still provides useful directional context.

---

## 11. Indicator Reference: SlopeE (EMA Slope)

SlopeE is a **custom-built oscillator** that measures how steeply the configured EMA is rising or falling at each candle. It is one of the most unique and practically useful indicators in the system.

**Type:** Oscillator (separate panel below price chart)

**What it measures:** The rate of change of the EMA per candle, expressed in price units (pips for forex pairs). Specifically: `SlopeE(n, candle) = EMA(n, candle) - EMA(n, candle - 1)`

- **Positive SlopeE:** The EMA is rising — price trend is upward.
- **Negative SlopeE:** The EMA is falling — price trend is downward.
- **SlopeE near zero:** The EMA is flat — no directional trend, consolidation or transition.
- **Zero line crossing:** The EMA just changed direction. This is a trend reversal signal.

### The Smooth Period (Amber Input)

SlopeE has an additional configuration field displayed in amber: **Smooth Period** (default: 3, range: 1–20).

The Smooth Period applies an EMA smoothing pass to the raw slope values. Without smoothing (period = 1), the raw slope line is noisy and reacts to every small wiggle in the EMA. With smoothing, the slope line becomes smoother and more readable.

**The key insight about Smooth Period:** With a higher smooth period (e.g., 10), the smoothed slope **turns upward or downward before the EMA itself visually levels off**. This makes SlopeE a **leading indicator** — it signals a trend change while the EMA still appears to be moving in the old direction.

**Example:**
```
Scenario: EMA 20 on H1, Smooth Period = 10

Raw SlopeE values over 6 candles:
Candle -6: -1.2 pips (EMA falling strongly)
Candle -5: -1.0 pips (EMA still falling)
Candle -4: -0.8 pips (EMA falling but decelerating)
Candle -3: -0.5 pips (deceleration continues)
Candle -2: -0.2 pips (EMA barely moving)
Candle -1: +0.1 pips (EMA just started rising — SlopeE crossing zero)

At candle -1, SlopeE crossed zero. The EMA 20 line on the chart still looks like
it is falling slightly because the visual smoothing of the EMA has not yet caught
up to the real change in momentum. But SlopeE detected it ~2 candles earlier.
```

This leading property makes SlopeE useful for:
- Detecting trend exhaustion before the EMA makes a visible turn.
- Timing entries in the direction of a new trend before the EMA-based signal fires.
- Filtering out trades in the direction of a weakening trend (when SlopeE is flattening, the trend is losing momentum even if EMA still points the same way).

### Practical SlopeE Setups

**Setup 1: Trend Strength Filter**
- Add SlopeE(20) on H1 with Smooth Period 5.
- Condition for BIAS_LONG: SlopeE must be positive (EMA rising) and above a minimum threshold (e.g., > 0.3 pips/candle to filter out flat markets).
- Condition against BIAS_LONG: SlopeE negative (do not fight a falling EMA).

**Setup 2: Early Reversal Detection**
- Add SlopeE(20) on H1 with Smooth Period 10.
- Watch for the SlopeE line crossing zero from below (negative to positive) — this fires ~2 candles before the EMA visually turns up.
- Combine with RSI crossing above 50 for confirmation.

**Setup 3: Multi-Timeframe Slope Analysis**
- Add SlopeE(20) on H4 and SlopeE(20) on H1 simultaneously.
- If H4 SlopeE is positive and H1 SlopeE is also positive → strong alignment, higher-confidence long entries.
- If H4 SlopeE is positive but H1 SlopeE is negative → trend is intact on H4 but H1 is in a pullback. Wait for H1 SlopeE to turn positive before entering.

---

## 12. Indicator Reference: SlopeS (SMA Slope)

**Type:** Oscillator (separate panel)

SlopeS is identical in concept to SlopeE but operates on the Simple Moving Average instead of the Exponential Moving Average.

`SlopeS(n, candle) = SMA(n, candle) - SMA(n, candle - 1)`

The same Smooth Period amber input is available.

**Key differences between SlopeE and SlopeS:**
- **SlopeE is more sensitive** (reacts faster) because EMA gives more weight to recent prices.
- **SlopeS is smoother** naturally (less noisy) because SMA responds slower to price changes.
- SlopeE is typically preferred for shorter periods (EMA 20–50) where reactivity is desired.
- SlopeS may be preferred for longer periods (SMA 50–200) where stability is more important than speed.

For most analysis workflows, SlopeE is the primary choice. SlopeS is useful when you want a slope indicator that closely matches a long-period SMA you are already tracking.

---

## 13. Indicator Row Controls

Every indicator instance in the Indicators section has a row of controls for configuration.

### Color Picker

A color swatch button. Clicking it opens a color selection interface. The chosen color is applied to the indicator line on the chart. Each indicator instance can have a different color, making it easy to visually distinguish multiple instances of the same type (e.g., EMA 20 in blue vs. EMA 50 in orange vs. EMA 200 in red).

### Eye Toggle (Show/Hide)

Clicking the eye icon toggles the indicator's visibility on the chart. When hidden (eye with a strikethrough), the indicator line disappears from the chart and its oscillator panel collapses, but all configuration is preserved. Click again to make it visible.

Use show/hide to temporarily suppress an indicator without deleting it. For example, hide the RSI when you want to focus purely on price action, then show it again for oscillator-based confirmation.

### Name Label

A static display label showing the indicator type (EMA, SMA, RSI, ATR, BB, VWAP, SlopeE, SlopeS). This is not editable.

### Period Input

A number field (range 1–500) for the calculation period. Changes take effect when you leave the field or press Enter, triggering a recalculation and chart update.

The field has a fixed width (`w-14` CSS class) for compact display in the row.

### Timeframe Dropdown

Selects the candle timeframe used for this indicator's calculation. This is independent of the chart's display timeframe.

**Cross-timeframe indicators:** Setting an indicator's timeframe to H1 while the chart displays M15 candles allows you to see the H1 trend reference overlaid on M15 price action. The indicator value is "painted" as a flat horizontal segment on the M15 chart for the entire H1 period, then updates when the H1 candle closes.

This is a powerful multi-timeframe analysis technique: you can see exactly where the H1 EMA is while analyzing M15 entries, without switching charts.

### Line Style Dropdown

Options include: Solid, Dashed, LargeDashed, Dotted, SparseDotted.

Use different line styles to further differentiate multiple indicator instances visually. For example: EMA 20 as Solid, EMA 50 as Dashed, EMA 200 as LargeDashed.

### Line Width Input

A number input for line thickness (typically 1–4). Thicker lines are more visible but can obscure nearby candles. Default is 1 for most indicators.

### Smooth Period (SlopeE / SlopeS only)

An additional amber-colored number input that appears only for SlopeE and SlopeS indicators. Controls the EMA smoothing applied to the raw slope values. Range: 1–20. Default: 3.

The amber color distinguishes this field from the standard period input to prevent confusion (the period controls the underlying EMA/SMA; the smooth period controls the smoothing of the slope itself).

### Delete Button (Trash Icon)

Permanently removes this indicator instance from the list and the chart. This cannot be undone — if you accidentally delete an indicator, you must re-add it and reconfigure it from scratch.

---

## 14. Swing Levels

The Swing Levels section (below Indicators in the left column) detects and displays horizontal support and resistance levels derived from historical price swings.

### Enable Checkbox

The master toggle for swing level display. When unchecked, no swing level lines appear on the chart and the controls are inactive.

### Timeframe

Dropdown for selecting which candle timeframe to use for swing detection. This is independent of the chart's display timeframe.

- **M15:** Detects micro-level swings (intraday support/resistance). Shows many levels, useful for scalp entries and tight stop placement.
- **H1:** Detects structural swing levels. These are the key levels that last hours to days. Most relevant for intraday trading.
- **H4:** Detects major swing levels. These are macro boundaries that can hold for days to weeks. Use for identifying the big picture trading range.

Combining two swing level configurations (e.g., one M15 set and one H1 set with different line styles) gives a layered view of micro and structural levels simultaneously.

### Count

Maximum number of swing levels to display, from 1 to 20. Default: 5.

Increasing count shows more historical swing levels. Too many levels create visual clutter. For most analysis, 5–8 levels provide adequate context without overwhelming the chart.

### ATR Period

The ATR period used for the gap filter calculation (see Min Gap ATR below). Range: 1–200. Default: 14.

This ATR is calculated on the swing level timeframe, not the chart display timeframe.

### Min Gap ATR (Minimum Distance as ATR Fraction)

Minimum distance between two swing levels, expressed as a multiple of ATR. Range: 0–5, step 0.1.

- **Value 0:** No gap filtering — every detected swing is shown, even closely clustered ones.
- **Value 0.5:** Levels within 0.5 ATR of each other are clustered into one level. Reduces redundancy.
- **Value 1.0:** Levels must be at least 1 full ATR apart to be shown separately.

Higher values produce fewer, more significant levels by eliminating closely clustered swings. Lower values show finer-grained structure but can produce visual noise.

**Recommended starting value:** 0.5–0.8 for H1 swing levels in major currency pairs.

### Sort Mode

Two options for which levels to prioritize when Count limits the displayed set:

**Next (default):** Prioritizes swing levels nearest to the current price. The N most relevant levels are those closest to where price currently is — the nearest support below and nearest resistance above, plus the next few levels beyond.

**Prominent:** Prioritizes the most visually significant swings — levels with the largest price reversals, regardless of distance from current price. Use Prominent when you want to see where the major long-term structural levels are, even if they are far from current price.

### Visible / All Toggle

**Visible:** Shows only swing levels that fall within the current chart view (the visible price range). Levels that would be off-screen are not drawn. This keeps the display clean when you have zoomed in.

**All:** Shows all detected swing levels regardless of whether they are within the current view. Off-screen levels appear as clipped lines at the chart edges. Use All when you want to know where levels are even when price is far away.

### HL / OC Toggle

Controls which price data is used for swing point detection:

**HL (High/Low):** Swing highs are detected at candle High prices; swing lows at candle Low prices. This captures the full extent of price movement including wicks. More sensitive — detects more swings.

**OC (Open/Close):** Swing highs are detected at the higher of Open/Close; swing lows at the lower. This ignores wicks and only considers the "body" of candles. Less sensitive — detects fewer, more significant structural swings.

For most analysis: HL is standard for general S/R detection. OC is useful for finding levels where closing prices (not wicks) consistently stalled.

### Reload Button

Manually recalculates and redraws swing levels using the current settings. Use this after changing any swing level parameters or after the chart has been refreshed with new candle data. Swing levels do not update automatically during auto-refresh — you must click Reload manually.

### Swing Level List

Below the controls, the section displays a list of all calculated levels. Each entry shows:
- A color dot: **red** for swing high (resistance), **green** for swing low (support), **yellow** for a confluence zone (where a swing high and swing low align closely, forming a strong zone).
- The level's price value.
- An optional label indicating the level type (SH = Swing High, SL = Swing Low, SH/SL = confluence).

---

## 15. Bottom Panel — Middle Column: Drawing Tools

The middle column of the bottom panel contains the full suite of drawing tools.

### Style Controls (Apply to All Tools)

Before selecting a tool, configure the style controls — they determine how the next drawing will look:

| Control | Options | Notes |
|---|---|---|
| Color | Full color picker | Applied to the line/border of the drawing |
| Line Style | Solid, Dashed, LargeDashed, Dotted, SparseDotted | Applies to all line-type drawings |
| Line Width | 1–4 | Thicker for visibility on busy charts |
| Fill Color | Color picker | For shapes with fill areas (channel, rectangle) |
| Fill Opacity | 0–1, step 0.05 | 0 = transparent, 1 = fully opaque fill |

Style settings apply to newly created drawings. They do not retroactively change existing drawings (use the drawing's detail editor for that).

### Line Tools

**H Line (Horizontal Line):** A perfectly horizontal line at a user-clicked price level. One click places it. Extend it infinitely to the left and right, or optionally constrain it. Best for marking key S/R price levels.

**V Line (Vertical Line):** A vertical line at a user-clicked time position. Marks a specific candle timestamp. Useful for marking event times (news releases, session opens).

**Ray:** A line that starts at a click point and extends infinitely in one direction. Useful for marking a level or trend that you expect to project forward from a specific point.

**Ext. Line (Extended Line):** A line defined by two points that extends infinitely in both directions beyond those points. Useful for extended trend lines and channel boundaries.

**Trend Line:** A line drawn between exactly two points. Does not extend beyond the endpoints (unlike Ext. Line). Directly connects two price points to highlight a specific slope or trend over a defined period.

**Channel:** A parallel channel drawn with a reference trend line (two points) plus a channel width adjustment. Results in two parallel lines enclosing a price channel. Useful for identifying parallel trend channels.

### Fibonacci Tools

**Fib Ret. (Fibonacci Retracement):** Two-point drawing. Draw from a swing low to a swing high (for uptrend) or swing high to swing low (for downtrend). The system draws horizontal lines at the standard Fibonacci ratios: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%.

Common use: identify where price may retrace to during a pullback in a trend. The 38.2%, 50%, and 61.8% levels are the most watched retracement zones.

**Fib Ext. (Fibonacci Extension):** Three-point drawing (swing start, swing end, retracement end). Draws extension levels beyond the swing range: 127.2%, 161.8%, 200%, 261.8%. Used to set take profit targets beyond the swing high/low.

**Fib Fan:** Two-point drawing from a swing extreme. Draws diagonal lines at Fibonacci angles from the base point. Used to identify dynamic trend lines at Fibonacci gradients.

**Fib TZ (Fibonacci Time Zones):** Marks vertical lines at Fibonacci intervals (1, 2, 3, 5, 8, 13, 21...) forward from a reference point. Used to project potential reversal or reaction times based on Fibonacci periodicity.

### Markers

**Up Arrow:** Single-click to place an upward arrow marker at any candle. Typically used to mark actual or planned long entries, or bullish signal points.

**Down Arrow:** Single-click to place a downward arrow marker. Typically used to mark short entries or bearish signals.

**↔ Measure:** Two-click drawing between any two points. Draws a semi-transparent box between them with tick marks at both ends, labeled with the **candle count** and **pip distance** spanning the box (e.g. `12c +34.5p`). This is the fastest way to answer "how many pips/candles between these two points" without doing the arithmetic yourself — e.g. measuring a swing's exact size before sizing a Fibonacci retracement, or checking how many candles a consolidation lasted.

### Shapes and Labels

**Rectangle:** Two-click drawing (diagonal corners). Creates a filled or outlined rectangle. Useful for marking consolidation zones, trading ranges, or key price area boxes.

**Label (Text):** Two-click (position + anchor) text label. You can type any text. Line breaks are entered with the `|` character in the text field. Font size configurable from 8 to 72. Useful for annotating key events, dates, or analysis notes directly on the chart.

### Advanced Tools

**Pitchfork (Andrews' Pitchfork):** Three-point drawing. Creates a median line with two parallel channels, used for identifying the central axis and channel boundaries of a price swing. The Andrews Pitchfork is based on the principle that price tends to return to the median line.

**Elliott (Elliott Wave):** Multi-point drawing for labeling Elliott Wave patterns. Configurable wave count (3–9 points). Mode selection:
- `1-2-3-4-5` for impulse waves
- `A-B-C` for corrective waves

Points are placed sequentially on the chart. Click the **Done** button (visible in header bar during Elliott drawing) to finalize with fewer points than configured.

### Drawing List

All placed drawings are listed in the middle column below the tool buttons. Each drawing entry shows:
- An eye icon (toggle visibility)
- A color dot (current color)
- Drawing type name
- An expand arrow to open the detail editor
- A trash icon to delete the drawing

**Detail editor (expanded):** Shows all style controls for that specific drawing (color, line style, width, fill, opacity) plus point coordinates — the price and timestamp for each control point. You can edit coordinates numerically for precision placement (e.g., snap a horizontal line to an exact price level like 1.08520 by typing it directly).

For text labels, the detail editor includes the text content field and font size.

---

## 16. Bottom Panel — Right Column: Candle Data and Analyst View

### Candle Data Panel

Appears and populates when you click any candle on the chart.

**Displays:**
- **Time:** The open timestamp of the selected candle in the configured display timezone.
- **O / H / L / C:** Open, High, Low, Close prices for the candle.
- **V (Volume):** Tick volume for the candle.
- **Spread:** The bid-ask spread recorded at or near this candle's time (if available from the broker data).
- **Tick Volume:** Alias for V in some display configurations.

**Indicator Values at Clicked Candle:**
Below the OHLCV data, each configured indicator shows its computed value at the clicked candle's timestamp. Values are displayed in the indicator's configured color for easy identification.

Example display:
```
EMA 20 (H1):  1.08542    [blue]
RSI 14 (H1):  58.4       [orange]
ATR 14 (H1):  0.00182    [gray]
SlopeE 20 (H1):  +0.4 pips  [green]
```

**DXY Data (if available):**
If DXY (US Dollar Index) data is configured and available:
- **DXY Close:** The DXY closing price at the nearest available timestamp.
- **DXY Direction:** UP or DOWN based on DXY's movement.
- **Correlation:** The computed correlation coefficient between DXY and the current pair over the lookback period. Values near -1.0 indicate strong inverse correlation; near +1.0 indicates strong positive correlation.

DXY correlation is particularly useful for USD pairs — if DXY is strongly trending upward and shows -0.87 correlation with EURUSD, a bearish EURUSD bias aligns with the macro USD strength context.

### Analyst View Checkbox

**Enable/disable analysis markers:** The Analyst View checkbox in the right column mirrors the Analyst checkbox in the header bar. Checking either one enables the same marker overlay.

**Analysis button:** When a candle is selected and analyst markers are enabled, an **Analysis** button appears. Clicking it opens the AA Recommendation popup for the nearest analysis cycle to the selected candle's timestamp.

The popup shows:
- 4-column grid: Decision, Confidence, Order Start, Entry Quality
- Full decision text/JSON with Copy button
- Market snapshot at time of analysis with Copy button

Note: "Decision" here is a direct passthrough of whatever the AA's own prompt/schema wrote to that field — it is not a fixed enum in the codebase. Depending on which prompt profile is active for the agent, you may see values like `BIAS_LONG`/`BIAS_SHORT`/`NEUTRAL`, `OPEN_BUY`/`OPEN_SELL`/`SKIP_*`, or a nested state object — read it as free text, not against a single fixed list.

---

## 17. Sessions and Analyst Overlays

### Trading Sessions Reference

Session times are approximate and may shift by ±1 hour during daylight saving transitions in the respective regions.

| Session | UTC Open | UTC Close | Characteristics |
|---|---|---|---|
| Sydney | 22:00 | 07:00 (+1) | Low volume, AUD/NZD pairs most active |
| Tokyo | 00:00 | 09:00 | Moderate volume, JPY pairs active |
| London | 08:00 | 17:00 | Highest volume, EUR/GBP most active |
| New York | 13:00 | 22:00 | High volume, USD pairs active |
| London/NY Overlap | 13:00 | 17:00 | Peak volume, highest volatility |

The London/New York overlap (13:00–17:00 UTC) is typically the most liquid and volatile period. Many trading strategies specifically target this window for entries.

### Interpreting Analysis Markers (U/D/N)

**U marker (green ▲):** the analysis's `primary_bias` was bullish (`BIAS_LONG`/`BIAS_REVERSAL_LONG`).

**D marker (red ▼):** the analysis's `primary_bias` was bearish (`BIAS_SHORT`/`BIAS_REVERSAL_SHORT`).

**N marker (gray ○):** `BIAS_NEUTRAL` or an unrecognized bias value — no directional bias.

None of the three markers say anything about whether the agent actually signalled a trade entry — open the AA Recommendation popup and check the **Order Start** field for that (backed by the `order_start_signal` value); a trending market can show a run of U markers with `order_start_signal=NO` throughout because the entry setup itself never qualified.

A high density of U or D markers in one direction on a stretch of chart is a visual indicator of consistent AI directional bias during that period.

**Marker absence** means no analysis cycle ran at that time. This is expected during overnight gaps, weekends, or suspended periods.

---

## 18. Print Function

The Print button in the header bar opens a print dialog. The print function generates a formatted HTML report of the current chart view.

### Print Dialog Options

| Option | Description |
|---|---|
| **Chart** | Captures the current chart view as an image and includes it in the printout |
| **Candle Data** | Includes the OHLCV data from the currently selected candle |
| **Analysis** | Includes the nearest analysis data from the AA agent (if analyst markers are enabled) |

After selecting options, click **Print** to open the browser's native print dialog. You can print to a physical printer or save as PDF.

**Tip:** For best chart prints, zoom the chart to show the specific period you want to document before clicking Print.

---

## 19. Order Focus Mode

Order Focus mode pins Chart Analysis to one specific historical trade. It's reached from the **Orderbook**: click the **Chart** button (LineChart icon) on any order row — this switches the Action tab to Chart Analysis and loads that order. It's a separate, dedicated entry point from the Orderbook's own **AI** button (which opens a lighter-weight "Ask AI" investigate popup without leaving the Orderbook) — use **Chart** when you want the full charting toolkit (indicators, drawing tools, swing levels) against the trade, and **AI** when you just want a quick answer without switching views.

### What Happens Automatically on Entry

1. The order's pair and broker are loaded, replacing whatever was previously selected.
2. The **Anchor** field ([Section 2](#2-header-bar--controls)) is set to the order's close time + 1 hour (or, if the order never closed, whatever "end" time is available) — a fixed offset, not a dynamically sized window.
3. **Candle Count** is left exactly as it was (default 200 on first use) — that many candles are loaded ending at the anchor above.
4. Once the candles land, the chart automatically re-fits its viewport once so the trade's markers are actually on screen (it does not repeat this on every subsequent reload, so you're free to pan/zoom afterward without being fought).
5. Entry, Exit, Stop Loss, and Take Profit price lines are drawn, along with emphasized **Start**/**End** trade markers at the order's open/close candles.
6. The header's mode badge switches to **🔒 Order**.

The **Chart Assistant does not auto-open** in this process — you still open it explicitly with the Assistant toggle if you want to ask it about the trade (see [Section 20](#20-chart-assistant)).

### What's Different While Focused

- **Auto-refresh stops** — see [Section 3](#3-auto-refresh-behavior). The window is frozen until you leave focus mode, which is the point: a closed trade's context shouldn't shift while you're studying it.
- The **Anchor** field stays populated and editable — you can nudge it manually (e.g. to look further before the entry) without leaving Order Focus; only the mode badge and the Assistant's extra order context are tied to the focused order itself, not to the exact anchor value.
- The **Loaded-Range Diagnostic Badge** ([Section 2](#2-header-bar--controls)) turns amber and warns if the order's own start and/or end timestamp falls outside the loaded window — increase Candle Count or adjust the Anchor until the warning clears if you need the full trade visible.
- If you open the Assistant while focused, it receives the order's full context automatically — direction, signal confidence, requested/fill/close prices and times, stop-loss/take-profit, close reason and result, the short entry reasoning, the **full original analysis text**, the structured decision context, the analysis overlays, and the raw market context snapshot — plus a set of read-only investigation tools it otherwise doesn't have (`get_order_trace`, `get_agent_decisions`, `get_agent_config`, `get_ec_config`, `get_ec_runs`, `get_order`/`get_order_book`, `get_candles`/`calculate_indicator`/`get_swing_levels`). See [Section 20](#20-chart-assistant).

### Leaving Order Focus Mode

Click the **🔒 Order** badge in the header. This clears the focused order, resets Candle Count to 200 and the Anchor to empty (live data), and resumes the 30-second auto-refresh — pair, broker, and timeframe are left as they are rather than reset, since you may want to keep looking at the same instrument in free mode.

### Example: Reviewing Why a Trade Lost

**Goal:** understand exactly what the AA agent saw before a losing EURUSD trade closed, and whether the close made sense.

1. Open **Orderbook**, find the losing trade, click its **Chart** button.
2. Chart Analysis opens in Order Focus mode: EURUSD loads, anchored to the trade's close time, with Entry/SL/TP/Exit lines and Start/End markers already drawn.
3. Click the **Assistant** toggle to open the Chart Assistant — it already has the order's full analysis text, decision context, and market snapshot, so you can ask directly: *"Why did this trade get stopped out — was the SL placement reasonable given the volatility at entry?"*
4. If the answer references a specific candle or level, ask the assistant to mark it (e.g. *"draw a zone around the consolidation right before entry"*) rather than trying to eyeball coordinates from a text description.
5. When done, click the **🔒 Order** badge to return to free mode without losing your EURUSD/H1 selection.

You could reach the same anchored view manually (set Anchor to the order's close time yourself in free mode), but the Orderbook's **Chart** button does it in one click and additionally draws the trade's own price lines/markers — prefer it over the manual route whenever you have a specific order in hand.

## 20. Chart Assistant

The Chart Assistant is an AI chat window built into Chart Analysis. It can explain whatever is currently loaded on the chart, and — in Order Focus mode — the specific order too. Unlike the assistants elsewhere in the system, it isn't purely read-only: it can draw directly on the chart itself using the same tool-calling mechanism the Simulation/Prompt Workbench "sandbox" tools use.

It **never opens on its own** — click the **Assistant** toggle button (top-right of the header bar) to open it, and again to close it. Opening it does not change anything about the chart itself.

### The Window

The Assistant renders as a **floating window**, not a docked panel — this is deliberate: a docked side panel would share width with the chart via flexbox, but the chart's own canvas doesn't reliably shrink to match in every case, so a panel could end up visually overlapping the chart. A floating window never participates in that layout at all.

- **Drag** it by its header (the title bar reading "Chart Assistant").
- **Resize** it from the small handle in the bottom-right corner (minimum 320×280px).
- It defaults to the top-right area of the screen, sized to fit the viewport.
- If a trade is focused, the header shows a compact summary (`EURUSD BUY · Fill 1.0842 · Close 1.0798`) so you don't lose track of which order you're discussing while the window is dragged around.
- Close it with the **✕** in its header, or the Assistant toggle button again — either way, your chat history is discarded (there's also an explicit **Delete** button inside the panel to clear history without closing the window).

### What It Can Do

- **Explain price action, trends, support/resistance, and what indicators are showing** for the currently loaded pair/timeframe/candles.
- **Draw on the chart itself** rather than describing coordinates in prose — it prefers to when explaining *why* something happened, because a marker is unambiguous and a text description of "where" on a chart is not:
  - `candle_marker` — a single arrow+label on one candle.
  - `zone_marker` — a labelled zone spanning a candle range (e.g. a support/resistance zone, a consolidation range).
  - `trade_marker` — mark a hypothetical or historical entry/exit pair to illustrate a setup.
  - `get_annotation` — look up something marked earlier in the same conversation.

  These are drawn with the **same rendering used by the Simulation tab** — a marker the assistant places here looks and behaves identically to one placed there.
- **Remember a note about a trading agent's behavior** across conversations with `assessment_memory` (get/set), keyed by that agent's id — useful so it doesn't have to re-derive a recurring pattern every time you ask about that agent.
- **In Order Focus mode only**, additional read-only investigation tools become available (see [Section 19](#19-order-focus-mode) for the full list) — the same read-only reach the former per-order "Investigate" popup had, so moving to the unified Assistant didn't lose any of that capability. Ask things like *"what closed this trade — was it the AA itself, a trailing stop, or a risk guard?"* and it can trace both the open and close decision chains, look up the agent's or EventComposer's actual live configuration, and pull other orders for comparison.

### Reading a Response

Each answer bubble can show a **Tools:** line underneath it listing exactly which tool calls happened for that answer (e.g. `trade_marker(open) OK`, `assessment_memory FAILED`) — this is derived from the actual tool-call events the backend returned, not guessed from the answer text, so you can always tell whether a claimed action ("I've marked the zone") actually happened.

Long answers default to a capped, scrollable box (about 15 lines) with **Show more/Show less** and a **Copy** button — the full text is always present, the cap only affects how much is visible without scrolling.

### Things to Know / Troubleshooting

- If the persona/instructions file (`config/llm_contexts/chart_analysis_assistant.md`) fails to load, an amber banner appears at the top of the panel warning that answers may be lower quality — the chat still works, just without its full instructions.
- A `404` error when sending a message means the backend process hasn't picked up the assistant's chat route yet — this needs a **backend restart** (Python has no hot-reload for newly added routes), not just a page refresh.
- The input box and Send button are disabled until a pair is loaded — there's nothing to discuss yet on an empty chart.
- Nothing you type here changes what's saved for the order (if focused) — it's a conversation about the chart/order, not an edit to its stored record.

---

## 21. Practical Workflows and Examples

### Workflow 1: Identifying Trend Reversals Using SlopeE

**Goal:** Detect when the H1 EURUSD trend is turning before the EMA visually confirms it.

**Setup:**
1. Pair: EUR_USD, Timeframe: H1, Candles: 200.
2. Add EMA, period 20, H1, solid blue line.
3. Add SlopeE, period 20, H1, Smooth Period 10, green/red coloring.
4. Click Reload.

**Reading the setup:**
- Watch SlopeE in the oscillator panel below.
- When SlopeE crosses zero from below (negative → positive), the EMA 20 is beginning to turn upward.
- Compare this to the EMA line on the chart — at the moment of SlopeE zero crossing, the EMA line likely still appears flat or slightly declining visually.
- This is the leading signal. Watch for price confirmation (close above EMA, or RSI crossing 50) over the next 1–2 candles.
- If SlopeE turns positive AND RSI crosses above 50: high-confidence reversal setup for a long entry.

**Example reading:**
```
Candle sequence on H1:
H -3: EMA visually declining, SlopeE = -0.9 (strong bearish slope)
H -2: EMA still declining visually, SlopeE = -0.4 (slope weakening)
H -1: EMA visually flat/slightly declining, SlopeE = +0.1 (zero crossing)
H  0: EMA just starting to curve upward visually, SlopeE = +0.3 (confirmed rising)

The SlopeE gave the signal at H-1 when the EMA was still visually flat.
Entry on H0's close or H1's open captures the beginning of the EMA rise.
```

### Workflow 2: Finding S/R Levels Using Swing Levels + Fibonacci

**Goal:** Identify the key price levels for a GBPUSD trade plan for the London session.

**Setup:**
1. Pair: GBP_USD, Timeframe: H1, Candles: 500.
2. Enable Swing Levels, Timeframe H4, Count 6, ATR Period 14, Min Gap ATR 0.8, Sort: Prominent.
3. Click the Swing Levels Reload button.
4. Note the top 3 resistance levels (red dots) and top 3 support levels (green dots) from the list.
5. Switch to M30 candles for entry-level detail.
6. Add Fib Retracement from the most recent H4 swing low to H4 swing high.
7. Observe where the Fibonacci retracement levels align with the swing level horizontal lines — confluence zones.

**Reading the result:**
- If the H4 swing level at 1.2740 aligns with the 50% Fibonacci retracement at 1.2738: this is a strong confluence zone. A pullback to this area in a bullish trend is a high-probability entry zone.
- Session bands (enable Sessions) show whether this zone will be tested during the London session or during the quieter Asian period.

### Workflow 3: Timing Entries Using Session Bands

**Goal:** Plan entry timing around session activity for EURUSD.

**Setup:**
1. Enable Sessions checkbox.
2. Set timeframe to H1 with 100 candles.
3. Observe colored session bands.

**Pattern to look for:**
- London open band: look at how EURUSD behaves in the first 1–2 H1 candles of the London session. Is there a consistent directional move? Many institutional trend-following strategies use the London open breakout as an entry trigger.
- London/NY overlap band: highest volatility period. If price is consolidating heading into this band, a breakout during the overlap is statistically more likely to continue.
- Late NY / Asian session: lower volatility. Tight range moves. Avoid breakout strategies during these periods.

**Cross-reference with Swing Levels:** If a swing resistance level sits just above the current price at the London open, a London open rally that breaks through that resistance has structural significance — it is not just a random move but a confirmed breakout of a structural level.

### Workflow 4: Using Fib Retracement to Find Entry Targets

**Goal:** On a confirmed H1 uptrend, find the optimal pullback entry zone.

**Steps:**
1. Identify a clear uptrend on H1 (EMA 20 sloping up, price above EMA, SlopeE positive).
2. Identify the most recent significant swing low (the start of the rally).
3. Identify the most recent swing high (the high of the rally).
4. Select Fib Ret. from the drawing tools.
5. Click the swing low, then click the swing high to draw the Fibonacci retracement.
6. The system draws lines at 23.6%, 38.2%, 50%, 61.8%, 78.6%.

**Entry zone identification:**
- Shallow pullbacks (23.6%–38.2%): Price barely pulled back. Entry here is aggressive — the move is still strong but you are buying at a relatively high level.
- Classic pullback (38.2%–61.8%): The "sweet spot" for trend continuation entries. The 50% level is particularly watched.
- Deep pullback (61.8%–78.6%): Price has retraced significantly. This level tests the validity of the uptrend. If supported here, the reward potential is highest but trend conviction must be confirmed by other indicators.

**Combining with swing levels:** If a Fibonacci level aligns with a swing level (e.g., the 61.8% retracement is at the same price as a previous swing high that is now acting as support), this confluence strengthens the entry zone's significance.

### Workflow 5: Multi-Indicator EURUSD Analysis Session

**Complete setup for a structured analysis session:**

1. Pair: EUR_USD, Broker: oanda-demo, Timeframe: H1, Candles: 300.
2. Indicators:
   - EMA 20, H1, blue, solid
   - EMA 50, H1, orange, dashed
   - EMA 200, H1, red, solid, width 2
   - RSI 14, H1, purple
   - SlopeE 20, H1, Smooth 8, green
3. Swing Levels: H1, Count 8, ATR 14, Min Gap 0.7, Sort: Prominent.
4. Enable Sessions, enable Analyst.
5. Click Reload.

**Reading the full picture:**
- **Macro trend (EMA 200):** Is price above or below EMA 200? This is your long-term bull/bear divide.
- **Medium trend (EMA 50):** Is EMA 20 above EMA 50? If yes, medium-term trend is bullish.
- **Short-term trend (EMA 20):** Is price above EMA 20? Is EMA 20 slope positive (check SlopeE)?
- **Momentum (RSI):** Is RSI above 50? Is it trending in the direction of the trade bias?
- **Structure (Swing Levels):** Where are the nearest resistance levels above and support levels below current price?
- **AI Confirmation (Analyst markers):** What have the D/N markers been showing over the last 50 candles? Consistent D markers in one direction confirm AI alignment with the manual analysis.

**Decision framework:**
- All EMAs aligned (price > EMA20 > EMA50 > EMA200) AND RSI > 50 AND SlopeE > 0: strong LONG environment. Look for pullback entries at EMA 20 or Fibonacci retracement levels.
- EMAs misaligned or crossing: transition period. Avoid directional trades until alignment clarifies.
- SlopeE crossing zero: monitor for trend change. Do not add new trades in the old direction until SlopeE confirms new direction.

### Workflow 6: Post-Mortem on a Losing Trade (Order Focus + Anchor + Assistant)

**Goal:** Understand exactly what an agent saw before a losing trade and whether the exit made sense — without manually reconstructing the historical chart state.

**Steps:**
1. Open **Orderbook**, locate the trade, click its **Chart** button — this is faster and more complete than setting the Anchor field by hand, because it also draws the trade's own Entry/Exit/SL/TP lines and Start/End markers for you.
2. Note the **Loaded-Range Diagnostic Badge** — if it's amber with a warning, widen Candle Count or nudge the Anchor until the order's own start/end both fall inside the loaded window.
3. Open the **Assistant** and ask it to explain the setup — it already has the order's full analysis text, decision context, and market snapshot, so you don't need to paste anything.
4. Ask it to trace the close (*"what actually closed this — the AA, a trailing stop, or a risk guard?"*) — in Order Focus mode it has the extra investigation tools to answer with the real causal chain instead of guessing from the stored `close_reason` alone.
5. Ask it to mark anything it references on the chart (a zone, a candle) rather than describing coordinates — the marker is unambiguous, the assistant's own placement never is.
6. Click the **🔒 Order** badge when done to return to free mode on the same pair.

See [Section 19](#19-order-focus-mode) and [Section 20](#20-chart-assistant) for the full mechanics behind each step.

---

## 22. Quick Reference

### Header Bar Controls

| Control | Function | Notes |
|---|---|---|
| Pair | Select instrument | Updates chart immediately |
| Broker | Select data source | Visible only with multiple brokers |
| Mode badge | 🔓 Frei / 🔒 Order | Click 🔒 to leave Order Focus mode |
| Timeframe | M5/M15/M30/H1/H4/D1 | Reloads candles |
| Candles | 20–2000 | More = longer history, slower load |
| Anchor | Load candles ending at a past point instead of live | Same field Order Focus pre-fills automatically |
| Reload | Manual data refresh | — |
| Range diagnostic | Shows loaded count/first/last timestamp | Turns amber + warns in Order Focus if the order falls outside the window |
| Fit | Fit ALL loaded candles into view | Different from the default zoom reset, which can crop to a smaller configured range |
| Zoom | Toggle draw/navigate mode | — |
| Sessions | Show session bands | Sydney/Tokyo/London/New York |
| Analyst | Show AA analysis markers | U=bullish bias, D=bearish bias, N=neutral |
| Print | Print dialog | Chart/data/analysis options |
| → KB | Save chart + data snapshot to Knowledgebase | — |
| Assistant | Toggle the floating Chart Assistant window | Never opens itself |

### Indicator Type Reference

All indicators are computed server-side via the same `calculate_indicator` call — the "Backend?" column below reflects that there is no separate client-side calculation path for any of them.

| Indicator | Type | Panel | Backend? | Smooth Period? |
|---|---|---|---|---|
| EMA | Price overlay | On chart | Yes | No |
| SMA | Price overlay | On chart | Yes | No |
| RSI | Oscillator | Below chart | Yes | No |
| ATR | Oscillator | Below chart | Yes | No |
| BB | Price overlay | On chart | Yes | No |
| VWAP | Price overlay | On chart | Yes | No |
| SlopeE | Oscillator | Below chart | Yes | Yes (amber) |
| SlopeS | Oscillator | Below chart | Yes | Yes (amber) |

### Swing Level Sort Modes

| Sort | Prioritizes |
|---|---|
| Next | Levels nearest to current price |
| Prominent | Most visually significant historical swings |

### Fibonacci Level Reference

| Retracement Level | Significance |
|---|---|
| 23.6% | Shallow — strong trend |
| 38.2% | Moderate — healthy pullback |
| 50.0% | Mid — key watch level |
| 61.8% | Deep — critical support/resistance |
| 78.6% | Very deep — trend validity test |

### Session Times (UTC)

| Session | Open | Close |
|---|---|---|
| Sydney | 22:00 | 07:00 |
| Tokyo | 00:00 | 09:00 |
| London | 08:00 | 17:00 |
| New York | 13:00 | 22:00 |
| LDN/NY Overlap | 13:00 | 17:00 |

### Drawing Tools Reference

| Category | Tools |
|---|---|
| Lines | H Line, V Line, Ray, Ext. Line, Trend Line, Channel |
| Fibonacci | Fib Ret., Fib Ext., Fib Fan, Fib TZ |
| Markers | Up Arrow, Down Arrow, Rectangle, Label, ↔ Measure |
| Advanced | Pitchfork, Elliott Wave |

### Order Focus / Assistant Quick Reference

| Item | Where | Notes |
|---|---|---|
| Enter Order Focus | Orderbook → **Chart** button on an order row | Sets pair/broker/anchor automatically |
| Leave Order Focus | Click the **🔒 Order** badge | Resets Candles to 200, clears Anchor, resumes auto-refresh |
| Open the Assistant | **Assistant** toggle (header, right side) | Never opens itself, in either mode |
| Assistant base tools | `zone_marker`, `trade_marker`, `candle_marker`, `get_annotation`, `assessment_memory` | Available in both modes |
| Assistant order-focus tools | `get_order_trace`, `get_agent_decisions`, `get_agent_config`, `get_ec_config`, `get_ec_runs`, `get_order`/`get_order_book`, `get_candles`/`calculate_indicator`/`get_swing_levels` | Only when a specific order is focused |
| Assistant persona/instructions | `config/llm_contexts/chart_analysis_assistant.md` | Edit this to change what the assistant is told it can do |
