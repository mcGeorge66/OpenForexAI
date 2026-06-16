# Script Context: Snapshot Assembly Transform Script

This document describes the execution context of the **Assembly Transform Script** in a Snapshot Profile.

## Purpose

The assembly transform script runs as the final step of the snapshot pipeline.
It receives the complete snapshot data (tool outputs + calculation results) and must
produce the final `result` dict that is passed to the LLM prompt.

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
The full snapshot dict. Key fields:

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

### `result` — dict (write this)
Set `result` to the final dict sent to the LLM. Leave it empty to use the default builder.

### `cancel` — bool (optional)
Set `cancel = True` to abort the snapshot cycle (e.g. outside trading hours).

### `cancel_reason` — str (optional)
Set alongside `cancel = True` to explain why the cycle was aborted.

## Accessing tool outputs

```python
tool_outputs = snapshot.get("tool_outputs") or {}
candles_m5 = tool_outputs.get("m5_recent") or []
rsi        = tool_outputs.get("rsi_primary") or {}
```

## Accessing calculation results

```python
calcs        = snapshot.get("calculations") or {}
global_calcs = calcs.get("global") or {}

trend       = global_calcs.get("trend_1")        # dict from calc block with id "trend_1"
rsi_state   = global_calcs.get("rsi_state_1")
entry_gates = global_calcs.get("entry_gates_1")
```

## Common patterns

### Minimal result with core fields
```python
result = {
    "symbol":                  snapshot.get("symbol"),
    "timestamp_utc":           snapshot.get("timestamp_utc"),
    "strategy_aggressiveness": snapshot.get("strategy_aggressiveness"),
    "price":                   snapshot.get("latest_price"),
    "trigger_candle":          snapshot.get("trigger_candle"),
}
```

### Include all calculation results
```python
calcs        = snapshot.get("calculations") or {}
global_calcs = calcs.get("global") or {}

result = {
    "symbol":      snapshot.get("symbol"),
    "price":       snapshot.get("latest_price"),
    "trend":       global_calcs.get("trend_1"),
    "rsi_state":   global_calcs.get("rsi_state_1"),
    "entry_gates": global_calcs.get("entry_gates_1"),
}
```

### Cancel outside trading hours
```python
import datetime  # NOT available — use string comparison instead

hour = int((snapshot.get("timestamp_utc") or "T00:")[11:13])
if hour < 7 or hour >= 20:
    cancel = True
    cancel_reason = f"Outside trading hours (hour={hour} UTC)"
```

### Add recent candles for LLM context
```python
tool_outputs = snapshot.get("tool_outputs") or {}
m5_candles   = tool_outputs.get("m5_recent") or []
result["recent_m5"] = m5_candles[-6:] if m5_candles else []
```

## Output location

`result` is serialised to JSON and injected into the LLM prompt as the snapshot context.
Keep the dict focused — large candle lists increase token usage.
