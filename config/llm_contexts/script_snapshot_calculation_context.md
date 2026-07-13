Script Context: Snapshot Calculation Block
==========================================

This document describes the execution context of a **Snapshot Calculation
Script** in OpenForexAI.

 

Execution environment
---------------------

Scripts run inside a controlled Python `exec()` execution environment. Only
explicitly allowed built-ins and selected helper modules are available.

Available built-ins:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
abs, all, any, bool, callable, complex, dict, divmod, enumerate, filter, float,
frozenset, getattr, hasattr, int, isinstance, iter, len, list, map, max, min,
next, pow, print, range, repr, reversed, round, set, slice, sorted, str, sum,
tuple, type, zip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following exception classes are also available for explicit error handling:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
TypeError, ValueError, KeyError, Exception
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following standard-library helpers are available:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
math, statistics, Decimal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Example:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
average = statistics.mean([1, 2, 3])
distance = math.sqrt(25)
price = Decimal("1.15294")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full Python syntax works: `def`, `for`, `if`, `while`, `try/except`, list/dict
comprehensions, generator expressions, etc.

Scripts are executed in a shared namespace, so variables created inside the
script are available to comprehensions, generator expressions, helper functions,
and subsequent result extraction.

 

Available variables
-------------------

### `tool_outputs` — dict

Contains the outputs of all **Tool Blocks** (after their transform script)
**and** the results of all previous **Calculation Blocks** (keyed by their block
ID).

 

This is the structure of the globals_dict for the scripts:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
{
    # Tool-Block-results (after transform_script), keyed by output_key
    # + Calc-Block-results of all prior blocks, keyed by block id
    "tool_outputs": {
        "m5_recent":      [...],        # Tool-Block
        "h1_recent":      [...],        # Tool-Block
        "ema_fast":       {...},        # Tool-Block
        "rsi_primary":    {...},        # Tool-Block
        "atr_primary":    {...},        # Tool-Block
        # ...alle weiteren Tool-Blocks...
        "trend":          {...},        # Calc-Block (wenn davor)
        "rsi_state":      {...},        # Calc-Block (wenn davor)
        "micro_sr":       {...},        # Calc-Block (wenn davor)
        # ...alle vorherigen Calc-Blocks...
    },

    "strategy_aggressiveness": "BALANCED",   # Profil-Editor
    "short_timeframe":         "M5",         # Profil-Editor
    "long_timeframe":          "H1",         # Profil-Editor

    "result": {},                            # Script result
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Example keys: - `tool_outputs["m5_recent"]` → list of candle dicts -
`tool_outputs["h1_recent"]` → list of candle dicts - `tool_outputs["ema_fast"]`
→ indicator dict - `tool_outputs["atr_primary"]` → indicator dict -
`tool_outputs["micro_sr_1"]` → result dict of a previous calc block with ID
"micro_sr_1"

### `result` — dict (write this)

The script must write its output into `result`. This dict is stored in
`snapshot.calculations.global.<block_id>`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
result = {
    "my_key": 42,
    "another_key": "bullish",
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Data shapes
-----------

### Candle dict (after normalize_candle_tool_output)

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
{
  "timestamp":    "2024-01-15T10:00:00+00:00",  # ISO string
  "open":         1.08521,
  "high":         1.08612,
  "low":          1.08490,
  "close":        1.08580,
  "spread":       0.00012,
  "tick_volume":  342,
  "timeframe":    "M5",   # or "H1", "H4", etc.
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Access the last candle's close:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
candles = tool_outputs.get("m5_recent") or []
price = float(candles[-1]["close"]) if candles else None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Indicator dict (after build_indicator_tool_output / DEFAULT_INDICATOR_TRANSFORM_SCRIPT)

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
{
  "latest":    1.08523,            # most recent value (float)
  "direction": "rising",           # "rising" | "falling" | "flat"
  "values":    [{"value": ...}, {"value": ...}, ...],  # ordered oldest→newest
  "indicator": "EMA",
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Access latest RSI:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
rsi = tool_outputs.get("rsi_primary") or {}
rsi_val = float(rsi["latest"]) if isinstance(rsi, dict) and rsi.get("latest") is not None else None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Reading previous calculation block results
------------------------------------------

If an earlier calc block with ID `"micro_sr_1"` writes `result =
{"nearest_resistance": 1.086}`, the next block can read it:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
micro_sr = tool_outputs.get("micro_sr_1") or {}
resistance = micro_sr.get("nearest_resistance")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Common patterns
---------------

### ATR-relative distance

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
atr = tool_outputs.get("atr_primary") or {}
atr_val = float(atr["latest"]) if isinstance(atr, dict) and atr.get("latest") is not None else None

distance_atr = (level - price) / atr_val if atr_val and atr_val > 0 else None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Collect highs from candle list

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
candles = tool_outputs.get("h1_recent") or []
highs = [float(c["high"]) for c in candles if isinstance(c, dict) and c.get("high") is not None]
max_high = max(highs) if highs else None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Guard against missing data

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
val = None
raw = tool_outputs.get("my_key")
if isinstance(raw, dict) and raw.get("latest") is not None:
    try:
        val = float(raw["latest"])
    except (TypeError, ValueError):
        pass
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Output location
---------------

The result dict is stored at:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
snapshot.calculations.global.<block_id>
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For example, a block with ID `trend_1` produces:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
snapshot.calculations.global.trend_1 = { "direction": "bullish", ... }
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This path is available to the LLM prompt assembly and to subsequent calc blocks
via `tool_outputs["trend_1"]`.
