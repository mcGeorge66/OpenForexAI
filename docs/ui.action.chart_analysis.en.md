[Back to Action](ui.action.en.md)

# Chart Analysis

Chart Analysis is the **full-featured technical analysis tool** within OpenForexAI. Unlike the Orderbook (which is anchored to specific historical trades) and the Agent Chat chart (which is secondary to agent interaction), the Chart Analysis page is a standalone, unrestricted charting workspace. You control the pair, broker, timeframe, candle count, all indicators, drawing tools, and swing level detection. It auto-refreshes every 30 seconds, and all your indicators are preserved across refreshes. Use it for free-form technical analysis, session planning, strategy development, and visual confirmation of what the agents are "seeing."

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
19. [Practical Workflows and Examples](#19-practical-workflows-and-examples)
20. [Quick Reference](#20-quick-reference)

---

## 1. Page Layout Overview

```
┌───────────────────────────────────────────────────────────────┐
│  HEADER BAR: Pair | Broker | Timeframe | Candles | Reload    │
│              Zoom | Sessions | Analyst | Print                │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│                    MAIN CHART AREA                            │
│         (candlesticks, indicators, drawings, markers)         │
│                                                               │
├═══════════════════════════════════════════════════════════════╡
│  BOTTOM PANEL (resizable, 120–600px)                         │
│  ┌─────────────────┬────────────────┬────────────────────┐   │
│  │ LEFT            │ MIDDLE         │ RIGHT              │   │
│  │ Indicators      │ Drawing Tools  │ Candle Data        │   │
│  │ (EMA/SMA/RSI    │ (lines, fibs,  │ Analyst View       │   │
│  │  ATR/BB/VWAP    │  shapes,       │                    │   │
│  │  SlopeE/SlopeS) │  Elliott)      │                    │   │
│  │ ─────────────── │                │                    │   │
│  │ Swing Levels    │                │                    │   │
│  └─────────────────┴────────────────┴────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

The bottom panel can be resized vertically by dragging the handle at the bottom of the chart area. Minimum height: 120px. Maximum height: 600px.

---

## 2. Header Bar — Controls

### Pair Dropdown

Selects the currency pair (instrument) to display. The available instruments come from the active broker connections configured in `system.json5`. Pairs are listed using broker notation (e.g., `EUR_USD`, `GBP_USD`, `XAU_USD`).

Changing the pair immediately reloads the chart with the new instrument's data. All current indicators are re-applied to the new pair's data. Drawings remain on the chart but may appear at irrelevant price levels for the new pair (they are positionally fixed to price values, not percentage or relative positions).

### Broker Dropdown

Selects which broker's data feed to use for the chart. This dropdown is only visible when more than one broker is connected in the system configuration.

Different brokers may show slightly different prices due to different liquidity providers, spreads, and data normalization. If your agents are configured to use a specific broker, using the same broker in Chart Analysis ensures you are seeing the exact same data the agents see.

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

### Reload Button

Manually fetches fresh candle data from the broker. Shows a spinner while loading and is disabled during the load to prevent duplicate requests.

Use Reload when you want to see the very latest candle immediately rather than waiting for the next 30-second auto-refresh cycle. Also use it after changing the candle count or if you suspect the chart is showing stale data.

### Active Tool Display

When a drawing tool is active (you have clicked one of the drawing buttons), this area in the header shows:
- The tool name (e.g., "Trendline")
- The progress in multi-point drawings (e.g., "(1/2 pts)" for a trendline where you have placed the first point)
- A `✕` button to cancel the active drawing without placing it

This prevents confusion about which tool is active, especially for multi-point drawings where the cursor behavior changes.

### Elliott "Done" Button

This button appears only when an Elliott Wave drawing is in progress. Clicking it finalizes the wave drawing even if fewer than the configured maximum points have been placed. This is useful when you can clearly identify 3 or 5 wave points and do not need to place all configured points.

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

- **Sydney session** (light blue)
- **Tokyo session** (yellow/orange)
- **London session** (green)
- **New York session** (red/pink)

Overlapping sessions (London/New York overlap, for example) appear as blended colors or with a distinct overlap band.

Session bands help you correlate price behavior with session context — breakouts that occur at the London open are typically more reliable than moves in low-volume Asian sessions for European pairs.

The session times are shown in the chart's display timezone. If your system is configured for UTC, the bands align to UTC session times.

### Analyst Checkbox

When enabled, fetches and overlays the AA agent analysis markers on the chart. Each analysis cycle that ran during the visible chart window gets a small labeled marker at the corresponding candle:

- **D** (green): Decision marker — the AA agent output `BIAS_LONG` or `BIAS_SHORT` with `order_start_signal=YES`. Conditions were favorable for trade entry.
- **N** (gray): Neutral marker — the AA agent output `NEUTRAL` or `order_start_signal=NO`. No trade signal.

Clicking a D or N marker opens the Analysis Detail popup for that cycle (see Section 16).

Analyst markers are loaded from the database and reflect real historical analysis cycles that ran on the selected pair. They are not reconstructed or recalculated — they are the actual decisions stored at the time they were made.

### Print Button

Opens the print dialog. See [Section 18](#18-print-function).

---

## 3. Auto-Refresh Behavior

The Chart Analysis page **automatically reloads candle data every 30 seconds**. This means the chart stays live while you work on it — the latest candle is always at most 30 seconds old.

### What Reloads on Auto-Refresh

- Candle data (all OHLCV bars for the current pair, timeframe, and candle count)
- Backend-computed indicators (BB, VWAP) are recomputed with fresh data
- Client-computed indicator values (EMA, SMA, RSI, ATR, SlopeE, SlopeS) are recalculated with fresh candle data

### What is PRESERVED Across Auto-Refresh

**All configured indicators are preserved.** When the auto-refresh fires, every indicator you have added — including all settings (period, timeframe, color, line style, line width) — remains exactly as you configured it. The data updates but your configuration does not change.

This is a critical design property. Previously, auto-refresh would reset the indicator list, requiring you to re-add and re-configure indicators after each refresh. This bug has been fixed. Your indicator setup survives the refresh cycle.

**All drawings are preserved.** Trendlines, Fibonacci retracements, horizontal lines, rectangles, and all other drawing objects remain on the chart through auto-refreshes.

**Swing level settings are preserved.** Your swing level configuration (timeframe, count, ATR period, gap filter) is retained and swing levels are recalculated with fresh data on each refresh if enabled.

### When Auto-Refresh Does Not Apply

- If you are actively placing a drawing (a tool is active), the refresh may be deferred until the drawing is complete to avoid interfering with placement.
- If the browser tab is in the background (hidden), some browsers throttle JavaScript timers, potentially increasing the actual refresh interval beyond 30 seconds.

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
- **Click an analysis marker:** Opens the Analysis Detail popup for that cycle.
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

**BB is backend-computed:** The calculation is performed on the server using the full candle dataset, which allows the standard deviation to be computed correctly over the full period. This produces more accurate bands than a purely client-side approximation.

---

## 10. Indicator Reference: VWAP

**Type:** Price overlay (single line)

**Full name:** Volume Weighted Average Price

**Calculation:** `VWAP = Σ(Typical Price × Volume) / Σ(Volume)` where Typical Price = (High + Low + Close) / 3. Cumulative from the start of the period (typically the start of the trading day or session).

**VWAP is backend-computed** for the same reason as BB — the server has access to the full session's cumulative volume data.

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

**Analysis button:** When a candle is selected and analyst markers are enabled, an **Analysis** button appears. Clicking it opens the Analysis Detail popup for the nearest analysis cycle to the selected candle's timestamp.

The popup shows:
- 4-column grid: Decision, Confidence, Order Start Signal, Entry Quality
- Full decision text/JSON with Copy button
- Market snapshot at time of analysis with Copy button

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

### Interpreting Analysis Markers (D/N)

**D marker (green):** `order_start_signal=YES` — the AA agent found conditions favorable for trade entry. The bias (BIAS_LONG or BIAS_SHORT) indicates direction.

**N marker (gray):** `order_start_signal=NO` — the AA agent ran but did not signal trade readiness. May be NEUTRAL (no directional bias) or a directional bias without entry signal (e.g., the trend is up but the specific entry setup is not ready yet).

A high density of D markers in one direction on a stretch of chart is a visual indicator of consistent AI directional bias during that period.

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

## 19. Practical Workflows and Examples

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

---

## 20. Quick Reference

### Header Bar Controls

| Control | Function | Notes |
|---|---|---|
| Pair | Select instrument | Updates chart immediately |
| Broker | Select data source | Visible only with multiple brokers |
| Timeframe | M5/M15/M30/H1/H4/D1 | Reloads candles |
| Candles | 20–2000 | More = longer history, slower load |
| Reload | Manual data refresh | — |
| Zoom | Toggle draw/navigate mode | — |
| Sessions | Show session bands | Sydney/Tokyo/London/New York |
| Analyst | Show AA analysis markers | D=signal, N=neutral |
| Print | Print dialog | Chart/data/analysis options |

### Indicator Type Reference

| Indicator | Type | Panel | Backend? | Smooth Period? |
|---|---|---|---|---|
| EMA | Price overlay | On chart | No | No |
| SMA | Price overlay | On chart | No | No |
| RSI | Oscillator | Below chart | No | No |
| ATR | Oscillator | Below chart | No | No |
| BB | Price overlay | On chart | Yes | No |
| VWAP | Price overlay | On chart | Yes | No |
| SlopeE | Oscillator | Below chart | No | Yes (amber) |
| SlopeS | Oscillator | Below chart | No | Yes (amber) |

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
| Markers | Up Arrow, Down Arrow |
| Shapes | Rectangle, Label |
| Advanced | Pitchfork, Elliott Wave |
