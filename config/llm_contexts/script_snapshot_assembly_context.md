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

## Where the data lives

**Tool block outputs** (after their transform scripts) are in **`tool_outputs`** — a flat
dict keyed by the `output_key` of each tool block:

```python
tool_outputs = {
    "m5_recent":      [...],   # get_candles block with output_key "m5_recent"
    "rsi_primary":    {...},   # calculate_indicator block
    "session_status": {...},
    # ...
}
```

**Calculation block results** are in **`snapshot["calculations"]`** — grouped by the
primary candle source of each block (or `"global"` for script blocks and blocks without
a candle source):

```python
snapshot["calculations"] = {
    "m15_recent": {          # group: blocks whose primary candle source is "m15_recent"
        "trend":       {...},
        "m5_structure":{...},
        "micro_sr":    {...},
    },
    "h1_recent": {           # group: blocks whose primary candle source is "h1_recent"
        "h1_context":  {...},
        "structural_sr":{...},
    },
    "global": {              # group: script blocks + blocks without a candle source
        "rsi_state":   {...},
        "entry_gates": {...},
        "recent_context": {...},
    },
}
```

## Minimal requirement

**The only hard requirement for the assembly script is to set `result`.**
The simplest form that passes all tool outputs to the LLM:

```python
result = tool_outputs
```

To also include calculation results, add them explicitly:

```python
result = dict(tool_outputs)
calcs = snapshot.get("calculations") or {}
result["calculations"] = calcs
```

## Available variables

| Variable | Type | Content |
|---|---|---|
| `tool_outputs` | dict | Tool block outputs after transform, keyed by `output_key` |
| `raw_tool_outputs` | dict | Tool block outputs **before** transform scripts |
| `snapshot` | dict | Full snapshot dict incl. metadata + `tool_outputs` + `calculations` |
| `profile` | dict | The complete snapshot profile config |
| `agent_context` | dict | `{ agent_id, broker_name, pair, strategy_aggressiveness }` |
| `in_` | dict | Alias for `snapshot` |
| `out` | dict | Alternative output slot (same as `result`) |
| `result` | dict | **Write here.** The dict the LLM receives as its decision input |
| `cancel` | bool | Set `True` to abort the snapshot cycle |
| `cancel_reason` | str | Reason string when `cancel = True` |

### `snapshot` metadata fields

```python
snapshot["symbol"]                  # e.g. "EURUSD"
snapshot["timestamp"]               # ISO timestamp string
snapshot["latest_price"]            # float — current bid price
snapshot["latest_spread"]           # float
snapshot["strategy_aggressiveness"] # "CONSERVATIVE" | "BALANCED" | "AGGRESSIVE"
snapshot["trigger_candle"]          # dict — the candle that triggered this snapshot
snapshot["tool_outputs"]            # same dict as the top-level tool_outputs variable
snapshot["calculations"]            # dict — grouped calculation results (see above)
```

## Accessing tool outputs and calculations

```python
tool_outputs = tool_outputs or {}          # top-level variable
calcs        = snapshot.get("calculations") or {}
global_calcs = calcs.get("global") or {}
m15_calcs    = calcs.get("m15_recent") or {}
h1_calcs     = calcs.get("h1_recent") or {}

candles_m5   = tool_outputs.get("m5_recent") or []
rsi          = tool_outputs.get("rsi_primary") or {}
trend        = global_calcs.get("trend") or {}
entry_gates  = global_calcs.get("entry_gates") or {}
```

## Common patterns

### Minimal with metadata
```python
result = dict(tool_outputs)
result["symbol"]     = snapshot.get("symbol")
result["price"]      = snapshot.get("latest_price")
result["timestamp"]  = snapshot.get("timestamp")
```

### Cancel outside trading hours
```python
import datetime  # NOT available — use string comparison instead

hour = int((snapshot.get("timestamp") or "T00:")[11:13])
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
