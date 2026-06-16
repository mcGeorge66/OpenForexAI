# Script Context: Decision Prompt Selector Script

This document describes the execution context of the **Selector Script** in a Decision Prompt Profile.

## Purpose

The selector script runs before the LLM call to decide which prompt entry (by ID) should be used
for this particular snapshot. It can inspect the snapshot data and write `result` to select a prompt.

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

### `snapshot` — dict
The full assembled snapshot dict (after assembly transform). Key fields:

```python
snapshot["symbol"]                        # e.g. "EURUSD"
snapshot["timestamp_utc"]                 # ISO timestamp string
snapshot["latest_price"]                  # float — current bid price
snapshot["strategy_aggressiveness"]       # "CONSERVATIVE" | "BALANCED" | "AGGRESSIVE"
snapshot["trigger_candle"]                # dict — the candle that triggered this snapshot
snapshot["tool_outputs"]                  # dict — all tool block outputs (keyed by output_key)
snapshot["calculations"]                  # dict — all calculation block results
snapshot["calculations"]["global"]        # dict — global calc results keyed by block ID
```

### `tool_outputs` — dict
Shorthand alias for `snapshot.get("tool_outputs") or {}`. Keyed by `output_key`.

### `assembled` — dict
The final assembled result dict (after the assembly transform script ran).
This is what the LLM will receive as its snapshot context.

### `placeholders` — dict (write this to pass values to prompt text)
Write key/value pairs into `placeholders` to make them available as `{key}` substitutions
in the prompt text (when `use_placeholders` is enabled on the prompt entry).

```python
placeholders["pair"] = snapshot.get("symbol", "")
placeholders["aggressiveness"] = snapshot.get("strategy_aggressiveness", "")
placeholders["trend"] = (snapshot.get("calculations") or {}).get("global", {}).get("trend_1", {}).get("direction", "")
```

### `result` — int (write this to select a prompt)
Set `result` to the ID of the prompt entry to use.
If not set (or set to `None`), prompt entry with ID 1 is used as fallback.

```python
result = 1   # use prompt entry with ID 1
result = 2   # use prompt entry with ID 2
```

## Common patterns

### Select by strategy aggressiveness
```python
aggressiveness = str(snapshot.get("strategy_aggressiveness") or "").upper()
if aggressiveness == "AGGRESSIVE":
    result = 2
elif aggressiveness == "CONSERVATIVE":
    result = 3
else:
    result = 1
```

### Select by trend direction (from calc block)
```python
calcs  = snapshot.get("calculations") or {}
global_calcs = calcs.get("global") or {}
trend  = global_calcs.get("trend_1") or {}
direction = str(trend.get("direction") or "").lower()

if direction == "bullish":
    result = 1
elif direction == "bearish":
    result = 2
else:
    result = 3  # neutral / unknown
```

### Pass data to prompt placeholders
```python
calcs = snapshot.get("calculations") or {}
global_calcs = calcs.get("global") or {}
rsi_state = global_calcs.get("rsi_state_1") or {}

placeholders["pair"]       = str(snapshot.get("symbol") or "")
placeholders["rsi_label"]  = str(rsi_state.get("label") or "neutral")
placeholders["price"]      = str(round(float(snapshot.get("latest_price") or 0), 5))
result = 1
```

### Inspect a tool output
```python
rsi_data = tool_outputs.get("rsi_h1") or {}
rsi_val  = float(rsi_data.get("value") or 50)

if rsi_val < 30:
    result = 2   # oversold prompt
elif rsi_val > 70:
    result = 3   # overbought prompt
else:
    result = 1   # neutral prompt
```
