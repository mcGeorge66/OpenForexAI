# Script Context: Snapshot Tool Block — Transform Script

This document describes the execution context of a **Transform Script** in a Snapshot Tool Block.

## Purpose

The transform script runs immediately after a tool call returns its raw output.
It normalises or reshapes the raw output before it is stored as the block's `output_key` value
and made available to all downstream calculation blocks.

## Execution environment

Scripts run inside a Python `exec()` sandbox. Only safe built-ins are available:

```
abs, all, any, bool, dict, enumerate, filter, float, int, isinstance,
len, list, map, max, min, range, round, set, sorted, str, sum, tuple, zip
```

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

### `result` — any (write this)
Set `result` to the transformed output. This value is stored under `output_key`
and passed as `tool_outputs["<output_key>"]` to calc blocks.

## Helper functions (available in scope)

```python
normalize_candle_tool_output(tool_output, timeframe=None)
# Normalises get_candles output to a list of standard candle dicts.
# Always use this for candle tool blocks.

build_indicator_tool_output(tool_output, tool_input=None)
# Normalises calculate_indicator output to the standard indicator dict.
# Always use this for indicator tool blocks.
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

## Output location

The `result` value is stored at `tool_outputs["<output_key>"]` and is available
to all Calculation Blocks and the Assembly Transform.
