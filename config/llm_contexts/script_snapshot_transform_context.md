# Script Context: Snapshot Tool Block — Transform Script

This document describes the execution context of a **Transform Script** in a Snapshot Tool Block.

## Purpose

The transform script runs immediately after a tool call returns its raw output.
It normalises or reshapes the raw output before it is stored as the block's `output_key` value
and made available to all downstream calculation blocks.

## Execution environment

Scripts run inside a Python `exec()` sandbox. Only safe built-ins are available:

```
abs, all, any, bool, callable, complex, dict, divmod, enumerate, filter, float,
frozenset, getattr, hasattr, int, isinstance, iter, len, list, map, max, min,
next, pow, print, range, repr, reversed, round, set, slice, sorted, str, sum,
tuple, type, zip
```

Plus the exception classes `TypeError`, `ValueError`, `KeyError`, `Exception`,
and the standard-library helpers `math`, `statistics`, `Decimal` (e.g.
`statistics.mean([1, 2, 3])`, `math.sqrt(25)`, `Decimal("1.15294")`).

Full Python syntax works: `def`, `for`, `if`, `while`, `try/except`, etc.

**Important:** list/dict/set comprehensions and generator expressions that reference
local variables in their conditions must be rewritten as explicit `for` loops — they
cannot access exec-local variables in their filter conditions.

## Available variables

### `tool_input` — dict
The arguments that were passed to the tool call (e.g. `{"timeframe": "M5", "count": 20}`).

### `tool_output` — any
The raw return value of the tool. Shape depends on the tool:
- `get_candles` → list of candle dicts
- `calculate_indicator` → dict with `indicator`, `values`, etc.
- `get_swing_levels` → dict with `nearest_resistance`, `nearest_support`, `atr`, etc.

### `all_outputs` — dict
Every tool block's transformed output so far, keyed by `output_key`, in the order
blocks were declared — lets a later block's transform reference an earlier one
(e.g. to compute a spread between two timeframes' closes).

### `in_` / `out` — any
Aliases both pre-populated with the raw tool output (same as `tool_output`).
Writing to `out` instead of `result` works identically — the script just needs
to set *one* of `result`/`out`; if neither is set, the raw `tool_output` passes
through unchanged.

### `result` — any (write this)
Set `result` to the transformed output. This value is stored under `output_key`
and passed as `tool_outputs["<output_key>"]` to calc blocks.

## Helper functions (available in scope)

Defined in `config/snapshot_helpers.py` — editable if you need different normalization logic:

```python
normalize_candle_tool_output(tool_output, timeframe=None) -> list[dict]
# Normalises get_candles output to a list of standard candle dicts
# ({timestamp, open, high, low, close, spread, tick_volume, timeframe}).
# Always use this for candle tool blocks.

build_indicator_tool_output(tool_output, tool_input=None, all_outputs=None) -> dict
# Normalises calculate_indicator output to the standard indicator dict
# ({indicator, period, history, latest, direction, values}).
# Always use this for indicator tool blocks.

latest_value(values: list) -> float | None
# Last non-None numeric value in a series (iterates in reverse), rounded to 6 digits.

classify_series_direction(values: list, change_threshold: float = 1e-6) -> str
# "rising" | "falling" | "flat", by comparing the series' last value to its first.

classify_indicator_direction(values: list, indicator_name: str) -> str
# Wraps classify_series_direction with indicator-aware thresholds/labels:
# RSI uses a wider flat threshold (0.1) to avoid noise; ATR returns
# "expanding"/"contracting"/"stable" instead of "rising"/"falling"/"flat".
```

## Standard patterns

### Candle block (most common)
```python
result = normalize_candle_tool_output(tool_output, timeframe=tool_input.get("timeframe"))
```

### Indicator block
```python
result = build_indicator_tool_output(tool_output, tool_input=tool_input)
```

### Pass-through (no transform needed)
```python
result = tool_output
```

### Slice to last N
```python
result = tool_output[-20:] if isinstance(tool_output, list) else tool_output
```

## Output shape after normalization

### Candle dict (after normalize_candle_tool_output)
```python
{
  "timestamp":    "2024-01-15T10:00:00Z",
  "open":         1.08521,
  "high":         1.08612,
  "low":          1.08490,
  "close":        1.08580,
  "spread":       0.00012,
  "tick_volume":  342,
  "timeframe":    "M5",
}
```

### Indicator dict (after build_indicator_tool_output)
```python
{
  "latest":    1.08523,
  "direction": "rising",      # "rising" | "falling" | "flat"
  "values":    [{"value": ...}, ...],
  "indicator": "EMA",
  "period":    20,
}
```

## Available tools reference

[[config/llm_contexts/tools_reference.md]]

## Output location

The `result` value is stored at `tool_outputs["<output_key>"]` and is available
to all Calculation Blocks and the Assembly Transform.
