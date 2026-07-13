[Back to Config](ui.config.en.md)

# Snapshot Config

Snapshot Config defines what market data is collected, how it is transformed, and how it is assembled into a structured context block that is injected into the LLM prompt before every analysis cycle. A snapshot profile saves the AA agent from making its own tool calls at analysis time: all data gathering and pre-processing happens in a dedicated pipeline, and the finished snapshot arrives as a ready-made user message.

## Reference Documents
- [Snapshot Config Guide](snapshot-config-guide.en.md)
- [Snapshot Transformers](snapshot-transformers.en.md)
- [Snapshot Helper Functions](snapshot-helper-functions.en.md)

---

## Table of Contents

1. [The Snapshot Pipeline](#the-snapshot-pipeline)
2. [Header Bar](#header-bar)
3. [Profile Basics](#profile-basics)
4. [Snapshot Tool Blocks](#snapshot-tool-blocks)
5. [The Standard aa_default_v1 Tool Blocks](#the-standard-aa_default_v1-tool-blocks)
6. [Calculation Blocks](#calculation-blocks)
7. [The Standard aa_default_v1 Calculation Blocks](#the-standard-aa_default_v1-calculation-blocks)
8. [Assembly Transform](#assembly-transform)
9. [Action Buttons](#action-buttons)
10. [Live Preview and Validation](#live-preview-and-validation)
11. [Execute Preview](#execute-preview)
12. [Calculation Block Details](#calculation-block-details)
13. [Working with Calculation Results](#working-with-calculation-results)
14. [Troubleshooting Snapshot Issues](#troubleshooting-snapshot-issues)

---

## The Snapshot Pipeline

The snapshot pipeline runs once per analysis cycle, triggered when the AA agent receives an `m5_agent_trigger`. The steps are:

**Step 1 — Tool Block Execution (parallel)**
All enabled tool blocks run simultaneously. Each block calls a single tool (e.g. `get_candles`, `calculate_indicator`, `get_swing_levels`) with its configured arguments. The raw output is stored in `tool_outputs[output_key]`.

**Step 2 — Tool Block Transform**
If a tool block has a `transform_script`, it runs immediately after the tool returns, converting raw output into the desired format (e.g. converting raw candle dicts into a compact list).

**Step 3 — Calculation Block Execution (sequential)**
Calculation blocks run in dependency order. Each block reads from `tool_outputs` and/or previous calculation results, performs pure Python computation (no external calls), and stores its result in `calcs[block_id]`.

**Step 4 — Assembly**
The Assembly Transform script runs last. It reads all `tool_outputs` and `calcs` and constructs the final snapshot dictionary. This dictionary is serialized to JSON and injected as the user message to the LLM.

**Step 5 — Prompt Injection**
The Decision Input Prefix text is prepended to the serialized snapshot JSON. The combined string forms the user turn of the LLM conversation.

---

## Header Bar

| Element | Function |
|---------|----------|
| **Snapshot Profile** | Dropdown: select the profile to view or edit |
| **Execute Context Agent** | Dropdown: select which agent's context to use when running Execute preview |
| **Refresh** | Reload profiles and agent list from the backend |
| **New Empty Profile** | Clear all fields to prepare a new profile from scratch |
| **Execute** | Run the current profile live against the selected agent's context and display results |

---

## Profile Basics

### Name

Unique identifier for the profile. Referenced by the `snapshot_profile` field in Agent Config. Required. Convention: `aa_default_v1`, `ba_default_v1`, `eurusd_aggressive_v2`.

### Strategy Aggressiveness

Controls how aggressiveness-sensitive calculation blocks interpret their results.

| Value | Meaning |
|-------|---------|
| `CONSERVATIVE` | Tighter gate thresholds, lower tolerance for ambiguous signals |
| `BALANCED` | Default — balanced thresholds appropriate for most conditions |
| `AGGRESSIVE` | Wider thresholds, higher tolerance for borderline signals |

Calculation blocks that are aggressiveness-aware adjust their output labels and boolean flags based on this setting. The `entry_gates` block is the primary consumer of this setting.

### Description

Free-text documentation field. Has no effect on runtime behavior. Use it to describe the intended use case, version notes, or differences from other profiles.

### Decision Input Prefix

Text prepended to the snapshot JSON when it is injected into the LLM prompt. Default value:

```
Runtime-prepared market decision snapshot for current cycle. Analyze the following structured data and provide your trading decision:
```

This prefix tells the LLM what it is about to receive. Customize it to guide the LLM's framing of the data. The prefix is stored per profile, so different profiles can instruct the LLM differently.

### Short Timeframe / Long Timeframe

| Field | Default | Options |
|-------|---------|---------|
| Short Timeframe | M15 | M5, M15, M30, H1, H4, D1 |
| Long Timeframe | H1 | M5, M15, M30, H1, H4, D1 |

These values are available to tool blocks and calculation scripts as `SHORT_TF` and `LONG_TF` respectively. Tool block arguments that use these special values resolve them at runtime. This allows the same profile to be adapted for different timeframe strategies by changing just two dropdown values.

---

## Snapshot Tool Blocks

Tool blocks are the data-gathering layer. Each block calls one tool and stores its output. Blocks run in parallel — there is no sequencing between them.

### Adding a Block

1. Select a tool from the "Add Tool" dropdown (lists all tools registered in the system)
2. Click "Add Tool"
3. Fill in Block ID, Output Key, and any arguments
4. Optionally write a Transform Script

### Block Fields

| Field | Type | Description |
|-------|------|-------------|
| **Block ID** | Text | Internal identifier. Referenced by calculation blocks via `tool_outputs[id]`. snake_case. Must be unique within the profile. |
| **Tool** | Dropdown | The tool to call. Changing the tool resets arguments and clears the transform script. |
| **Output Key** | Text | Key under which the tool result is stored in `tool_outputs`. Often the same as Block ID. |
| **Enabled** | Checkbox | When unchecked, the block is skipped entirely. Other blocks that depend on its output will receive `None`. |
| **Arguments** | Dynamic | Generated from the tool's JSON schema. Text, number, and dropdown fields depending on argument type. |
| **Transform Script** | Code editor | Python executed after the tool returns. Input: `raw_output`. Output: must be assigned to `result`. |
| **Test** | Button | Runs the block in isolation using the Execute Context Agent's data. Shows raw output and transformed output side by side. |
| **Remove** | Button | Deletes this block from the profile. |

### Special Argument Values

| Value | Resolves to |
|-------|-------------|
| `SHORT_TF` | The profile's Short Timeframe setting (e.g. `M15`) |
| `LONG_TF` | The profile's Long Timeframe setting (e.g. `H1`) |

### Transform Script

The transform script receives the raw tool output and should produce a cleaned, compact version suitable for calculation blocks and the assembly script. Standard template for candle data:

```python
# Convert candle dicts to compact list format
result = [
    [c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"]]
    for c in raw_output
]
```

---

## The Standard aa_default_v1 Tool Blocks

The default profile `aa_default_v1` ships with the following tool blocks. These cover the full data set required by all standard calculation blocks.

### m5_recent

| Field | Value |
|-------|-------|
| Tool | `get_candles` |
| Output Key | `m5_recent` |
| Timeframe | `M5` |
| Count | `5` |
| Purpose | Last 4 closed M5 candles (plus 1 in-progress) for micro-level context |

Returns the most recent M5 candles. Used for micro_sr and as a noise-reduced proxy for very short-term structure. The 5th candle (index 0) is the currently forming candle and should not be used for closed-candle calculations.

### m15_recent

| Field | Value |
|-------|-------|
| Tool | `get_candles` |
| Output Key | `m15_recent` |
| Timeframe | `SHORT_TF` (M15 default) |
| Count | `20` |
| Purpose | 20 M15 candles for trend, structure, S/R, and RSI calculations |

This is the primary candle source for most calculation blocks. Most short-timeframe analysis uses this block.

### h1_recent

| Field | Value |
|-------|-------|
| Tool | `get_candles` |
| Output Key | `h1_recent` |
| Timeframe | `LONG_TF` (H1 default) |
| Count | `60` |
| Purpose | 60 H1 candles for higher-timeframe context, structural S/R, and H1 trend |

60 candles = approximately 2.5 trading weeks of H1 data. Provides sufficient lookback for structural analysis without excessive memory.

### ema_fast

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `ema_fast` |
| Indicator | `EMA` |
| Timeframe | `SHORT_TF` (M15) |
| Period | `3` |
| History | `3` |
| Purpose | Fast EMA on M15 for short-term trend direction |

Returns the last 3 EMA values. Used by the `trend` calculation block to compute direction and slope.

### ema_slow

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `ema_slow` |
| Indicator | `EMA` |
| Timeframe | `SHORT_TF` (M15) |
| Period | `8` |
| History | `3` |
| Purpose | Slow EMA on M15 for trend confirmation |

### rsi_primary

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `rsi_primary` |
| Indicator | `RSI` |
| Timeframe | `SHORT_TF` (M15) |
| Period | `4` |
| History | `3` |
| Purpose | Short-period RSI for momentum and timing signals |

Period 4 (rather than the standard 14) provides faster-reacting RSI values appropriate for M15 timeframe trading decisions.

### atr_primary

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `atr_primary` |
| Indicator | `ATR` |
| Timeframe | `SHORT_TF` (M15) |
| Period | `4` |
| History | `1` |
| Purpose | Current ATR on M15 for volatility normalization |

Used as the denominator for S/R distance calculations. Distances expressed in ATR units are meaningful regardless of pair volatility.

### h1_ema_fast

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `h1_ema_fast` |
| Indicator | `EMA` |
| Timeframe | `LONG_TF` (H1) |
| Period | `3` |
| History | `3` |
| Purpose | Fast EMA on H1 for higher-timeframe trend direction |

### h1_ema_slow

| Field | Value |
|-------|-------|
| Tool | `calculate_indicator` |
| Output Key | `h1_ema_slow` |
| Indicator | `EMA` |
| Timeframe | `LONG_TF` (H1) |
| Period | `8` |
| History | `3` |
| Purpose | Slow EMA on H1 for higher-timeframe trend confirmation |

### last_decision

| Field | Value |
|-------|-------|
| Tool | `get_last_decision` |
| Output Key | `last_decision` |
| Purpose | Previous analysis result for continuity context |

Provides the LLM with awareness of its previous decision for this pair. Prevents oscillation between contradictory decisions without market structure change.

### session_status

| Field | Value |
|-------|-------|
| Tool | `get_session_status` |
| Output Key | `session_status` |
| Purpose | Current trading session information |

Returns whether the current time falls within the configured session window, which session (London, New York, Asian), and time until session end or next session start.

### swing_levels_m15

| Field | Value |
|-------|-------|
| Tool | `get_swing_levels` |
| Output Key | `swing_levels_m15` |
| Timeframe | `SHORT_TF` (M15) |
| Lookback | `100` |
| Max Levels | `10` |
| Purpose | Short-timeframe swing high/low levels for micro S/R calculation |

Returns up to 10 significant swing levels from the last 100 M15 candles.

### swing_levels_h1

| Field | Value |
|-------|-------|
| Tool | `get_swing_levels` |
| Output Key | `swing_levels_h1` |
| Timeframe | `LONG_TF` (H1) |
| Lookback | `48` |
| Max Levels | `5` |
| Purpose | Higher-timeframe swing levels for structural S/R |

Returns up to 5 significant swing levels from the last 48 H1 candles (approximately 2 trading weeks).

---

## Calculation Blocks

Calculation blocks perform pure-Python data processing. They have no external calls — they consume only what tool blocks have already fetched. They run sequentially in dependency order after all tool blocks complete.

### Adding a Calculation Block

1. Select a type from the "Add Calculation" dropdown
2. Click "Add Calculation"
3. Set the Block ID
4. Link data sources (dropdowns list available tool block output keys)
5. Adjust any type-specific parameters

### Block Fields

| Field | Type | Description |
|-------|------|-------------|
| **Block ID** | Text | Unique identifier. Result stored in `calcs[block_id]`. |
| **Enabled** | Checkbox | When unchecked, block is skipped. Downstream blocks that depend on it will receive `None`. |
| **Data Sources** | Dropdowns | Specify which tool block outputs this block consumes. Each calculation type has its own required/optional sources. |
| **Config Parameters** | Number fields | Type-specific settings (lookback periods, thresholds, etc.). |
| **Script** (Script type only) | Code editor | Free Python for custom calculations. |
| **Test** | Button | Runs block in isolation and shows result dict or error. |
| **Remove** | Button | Deletes this block. |

### Available Calculation Types

| Type | Purpose |
|------|---------|
| `trend` | EMA-based trend direction, slope, and state classification |
| `rsi_state` | RSI level, direction, timing signals, and conflict flags |
| `m5_structure` | Short-term candle structure (momentum, range, rejection) |
| `swing_sr_gate` | S/R proximity check using swing levels and ATR normalization |
| `close_quality` | Quality score for each recent candle close |
| `entry_gates` | Consolidated boolean entry condition flags |
| `recent_context` | Raw candle lists for LLM contextual awareness |
| `script` | Free Python calculation with access to all tool outputs and prior calc results |

---

## The Standard aa_default_v1 Calculation Blocks

### trend (primary candle source: m15_recent)

**Sources**: `candles: m15_recent`, `ema_fast: ema_fast`, `ema_slow: ema_slow`

Computes trend direction and state from EMA crossover and candle position.

**Output fields**:
- `direction`: `long` / `short` / `neutral` — current primary direction
- `ema_fast_value`: current fast EMA price
- `ema_slow_value`: current slow EMA price
- `ema_fast_slope`: fast EMA slope (positive = rising)
- `ema_slow_slope`: slow EMA slope
- `price_vs_fast_ema`: `above` / `below` / `at`
- `price_vs_slow_ema`: `above` / `below` / `at`
- `trend_state`: one of:
  - `confirmed_bullish` — both EMAs rising, price above both
  - `confirmed_bearish` — both EMAs falling, price below both
  - `early_bullish_recovery` — fast above slow, recovering from below
  - `early_bearish_breakdown` — fast below slow, breaking down
  - `neutral` — mixed signals, no clear direction

---

### rsi_state (primary candle source: m15_recent)

**Sources**: `rsi: rsi_primary`

Interprets RSI value in context of level and direction.

**Output fields**:
- `value`: current RSI value (0–100)
- `direction`: `rising` / `falling` / `flat`
- `level`: one of:
  - `extreme_oversold` — below 20
  - `oversold` — 20–35
  - `neutral` — 35–65
  - `overbought` — 65–80
  - `extreme_overbought` — above 80
- `long_timing`: `good` / `neutral` / `poor` — suitability for long entry
- `short_timing`: `good` / `neutral` / `poor` — suitability for short entry
- `conflict_long`: `true` if RSI level conflicts with a long signal (e.g. overbought)
- `conflict_short`: `true` if RSI level conflicts with a short signal (e.g. oversold)

---

### m5_structure (primary candle source: m15_recent)

**Sources**: `candles: m15_recent`, `atr: atr_primary`

Note: Despite the name `m5_structure`, this block uses M15 candles. M15 data reduces the noise inherent in raw M5 candle sequences while still capturing short-term structure.

**Output fields**:
- `structure`: one of:
  - `constructive_recovery` — consecutive higher lows, positive momentum
  - `bearish_pressure` — lower highs forming, selling pressure
  - `soft_rejection` — price attempted higher but closed weak
  - `range_bound` — price oscillating within a tight range
- `range_bound`: boolean
- `range_size_atr`: range size expressed in ATR units
- `largest_candle_body_atr`: largest candle body in recent sequence, in ATR units
- `momentum_direction`: `bullish` / `bearish` / `neutral`

---

### micro_sr (primary candle source: m15_recent)

**Type**: `swing_sr_gate`
**Sources**: `candles: m15_recent`, `swing_levels: swing_levels_m15`, `atr: atr_primary`
**Parameter**: `sr_threshold: 0.5` (ATR units)

Checks proximity of current price to nearest swing-derived support and resistance levels on M15.

**Output fields**:
- `nearest_resistance`: price of nearest resistance above current price
- `nearest_support`: price of nearest support below current price
- `distance_to_resistance_atr`: distance to resistance in ATR units
- `distance_to_support_atr`: distance to support in ATR units
- `current_atr`: current ATR value used for normalization
- `sr_gate_passed_long`: `true` if price is not too close to resistance for a long entry (distance > sr_threshold)
- `sr_gate_passed_short`: `true` if price is not too close to support for a short entry (distance > sr_threshold)

The `sr_threshold` of 0.5 ATR means: if price is within 0.5× the current ATR of a resistance level, the long S/R gate fails. A long entry that close to resistance has poor reward/risk.

---

### structural_sr (primary candle source: h1_recent)

**Type**: `swing_sr_gate`
**Sources**: `candles: h1_recent`, `swing_levels: swing_levels_h1`, `atr: atr_primary`
**Parameter**: `sr_threshold: 0.5`

Same logic as micro_sr but using H1 candles and H1 swing levels. Detects structural (higher-timeframe) S/R proximity.

---

### h1_context (primary candle source: h1_recent)

**Type**: `trend`
**Sources**: `candles: h1_recent`, `ema_fast: h1_ema_fast`, `ema_slow: h1_ema_slow`

H1 trend direction, identical in structure to the M15 `trend` block but operating on H1 data. Provides the directional filter for higher-timeframe alignment.

---

### close_quality (primary candle source: m15_recent)

**Sources**: `candles: m15_recent`, `atr: atr_primary`

Evaluates the quality of each recent candle close based on body/wick ratio and close position.

**Output fields**:
- `summary`: `strong_bullish` / `mild_bullish` / `neutral` / `mild_bearish` / `strong_bearish`
- `candles`: array of per-candle assessments, each containing:
  - `body_pct`: body size as percentage of total candle range
  - `close_position`: `upper_third` / `middle` / `lower_third`
  - `quality`: `strong_bull` / `mild_bull` / `doji` / `mild_bear` / `strong_bear`

---

### entry_gates (no single primary source — grouped as `global`)

**Sources**: `micro_sr`, `rsi: rsi_state`, `trend`, `m5_structure`, `h1_context: h1_context`

Consolidates all individual signals into boolean entry flags for long and short.

**Output fields** (each is a boolean):
- `long_sr_gate_passed`: micro_sr says long entry is not blocked by resistance
- `short_sr_gate_passed`: micro_sr says short entry is not blocked by support
- `long_rsi_blocked`: RSI is in a state that conflicts with a long entry
- `short_rsi_blocked`: RSI conflicts with short entry
- `long_m5_confirmed`: m5_structure is constructive for long
- `short_m5_confirmed`: m5_structure is constructive for short
- `long_trend_aligned`: M15 trend direction is long
- `short_trend_aligned`: M15 trend direction is short
- `long_h1_aligned`: H1 context supports long direction
- `short_h1_aligned`: H1 context supports short direction

These flags are passed directly to the LLM snapshot. The LLM reads them and weights them in its final decision, but is not mechanically blocked by them — the LLM can override any gate with sufficient reasoning.

---

### recent_context (no single primary source — grouped as `global`)

**Sources**: `candles_short: m15_recent`, `candles_long: h1_recent`

Provides raw candle data directly to the snapshot for the LLM to examine.

**Output fields**:
- `last_6_m15`: last 6 M15 candles (OHLCV, compact format)
- `last_4_h1`: last 4 H1 candles (OHLCV, compact format)

---

## Assembly Transform

The Assembly Transform is a Python script that runs after all tool blocks and calculation blocks have completed. Its purpose is to combine everything into the final snapshot dictionary.

The script has access to:
- `tool_outputs`: dict mapping output keys to transformed tool results
- `calcs`: dict mapping block IDs to calculation results, grouped by primary candle source

### Grouping in `calcs`

Calculation blocks are grouped by their primary candle source:
- `calcs["m15_recent"]`: blocks whose primary candle source is `m15_recent` (trend, rsi_state, m5_structure, micro_sr, close_quality)
- `calcs["h1_recent"]`: blocks whose primary candle source is `h1_recent` (structural_sr, h1_context)
- `calcs["global"]`: blocks with no single candle source (entry_gates, recent_context)

### Minimal Assembly Example

```python
snapshot = {
    "trend": calcs["m15_recent"]["trend"],
    "rsi": calcs["m15_recent"]["rsi_state"],
    "structure": calcs["m15_recent"]["m5_structure"],
    "micro_sr": calcs["m15_recent"]["micro_sr"],
    "structural_sr": calcs["h1_recent"]["structural_sr"],
    "h1_direction": calcs["h1_recent"]["h1_context"],
    "entry_gates": calcs["global"]["entry_gates"],
    "recent_candles": calcs["global"]["recent_context"],
    "close_quality": calcs["m15_recent"]["close_quality"],
    "session": tool_outputs["session_status"],
    "last_decision": tool_outputs["last_decision"],
}
result = snapshot
```

Leave the Assembly Transform empty to use the auto-assembled object, which includes all calculation results and tool outputs with their default keys.

---

## Action Buttons

| Button | Color | Function |
|--------|-------|----------|
| **Update** | Green | Save changes to the currently selected profile. Disabled if no profile is selected or validation errors exist. |
| **Save As New** | Blue | Save current state as a new profile. Prompts for confirmation if the ID already exists. |
| **Delete** | Red | Delete the current profile. Requires confirmation. Agents referencing this profile will fail at next cycle until reassigned. |

---

## Live Preview and Validation

The sidebar shows real-time status of the current profile.

**Live Preview** includes:
- Profile name and aggressiveness setting
- Short/long timeframe values
- Count of enabled vs. total tool blocks
- Count of enabled vs. total calculation blocks
- Assembly transform status (empty / custom)

**Validation** lists all issues that would prevent saving:
- Missing Block IDs
- Duplicate Block IDs within the profile
- Tool blocks with no tool selected
- Calculation blocks with missing required data sources
- Empty profile name

---

## Execute Preview

Clicking **Execute** runs the complete pipeline live:

1. All tool blocks execute against real data for the selected agent's pair and broker
2. All calculation blocks run against the fetched data
3. The assembly transform runs
4. Results displayed in a dialog with three sections:

**Snapshot JSON**: The complete dictionary that would be injected into the LLM prompt. Inspect this to verify data shape, value ranges, and that all expected keys are present.

**Decision Input**: The final text that goes into the LLM user message — prefix + serialized JSON.

**Block Log**: Per-block execution time, output summary, and any warnings or errors. Useful for identifying slow tool calls or calculation blocks that return unexpected values.

Use Execute before assigning a new or modified profile to a live agent. It catches data availability issues, transform script errors, and unexpected output shapes before they affect live trading.

---

## Calculation Block Details

### Understanding ATR Normalization

Several calculation blocks express distances and sizes in ATR (Average True Range) units rather than absolute price values. This normalization makes the outputs meaningful across different pairs and volatility regimes:

- EURUSD ATR might be 0.0008; GBPJPY ATR might be 0.45
- A distance of "0.6 ATR" means the same relative proximity regardless of pair
- The `sr_threshold` of 0.5 ATR for S/R gate checks works for any pair without manual tuning

### Trend State Interpretation

The `trend_state` field from the `trend` block provides a human-readable and LLM-readable summary:

| State | Condition |
|-------|-----------|
| `confirmed_bullish` | Fast EMA > slow EMA, both rising, price above both |
| `confirmed_bearish` | Fast EMA < slow EMA, both falling, price below both |
| `early_bullish_recovery` | Fast crossing above slow, or recently crossed, not yet confirmed |
| `early_bearish_breakdown` | Fast crossing below slow, not yet confirmed |
| `neutral` | EMAs flat or choppy, price between EMAs, no clear direction |

### RSI Timing Logic

The `rsi_state` block's `long_timing` and `short_timing` fields are derived from RSI level plus direction:

- `long_timing = good`: RSI is oversold (30–45) AND rising — classic oversold bounce signal
- `long_timing = neutral`: RSI neutral zone, not confirming nor denying
- `long_timing = poor`: RSI overbought, entering a long here has momentum against it

---

## Troubleshooting Snapshot Issues

### Problem: Execute shows empty or None for a tool block

- Check the tool block is enabled
- Verify the tool arguments are valid (correct timeframe, count > 0)
- Check the Execute Context Agent is set to a pair/broker that has data in the database
- Check the transform script for errors (test the block in isolation via its Test button)

### Problem: Calculation block shows error or None

- Verify the data source dropdowns reference output keys that actually exist
- Check that the referenced tool block is enabled
- If the tool block returned None (data unavailable), the calculation block will also return None — fix the upstream tool block first

### Problem: Snapshot JSON is missing expected keys

- Review the Assembly Transform script — ensure it includes all desired keys
- If the Assembly Transform is empty, check that the calculation blocks are correctly named and enabled

### Problem: LLM decisions seem to ignore certain signals

- Check the Decision Input Prefix — it may not be guiding the LLM to pay attention to all fields
- Compare the actual Snapshot JSON from Execute to what you expect the LLM to see
- Consider restructuring the snapshot to highlight the most important signals at the top level

---

*This document covers Snapshot Config as implemented in OpenForexAI v0.7+. For prompt configuration, see [Decision Prompt](ui.config.decision_prompt.en.md). For a conceptual guide, see [Snapshot Config Guide](snapshot-config-guide.en.md).*
