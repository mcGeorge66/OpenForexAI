[Back to Config](ui.config.en.md)

# Helper Config

`Helper Config` is a Python editor for the file `config/snapshot_helpers.py`. This file contains optional helper functions that can be called from snapshot transform scripts and assembly scripts — reusable Python logic that does not need to be duplicated in every transform block.

## Reference Documents
- [Snapshot Helper Functions](snapshot-helper-functions.en.md)
- [Snapshot Transformers](snapshot-transformers.en.md)
- [Snapshot Config Guide](snapshot-config-guide.en.md)

---

## What Is snapshot_helpers.py?

`config/snapshot_helpers.py` is the configurable helper layer for the snapshot pipeline. It is a plain Python file that the runtime imports automatically when present.

Functions defined in this file become available in all snapshot scripts without any import statement. If the file is absent, snapshot execution continues normally — scripts simply have no helpers available from this file and must be self-contained.

This separation means you can change shared snapshot logic without touching the main backend modules. All helper changes are applied by editing and saving this file via the Helper Config editor.

---

## Interface

### Header Bar

| Element | Function |
|---|---|
| **File path** | Shows the full path to the file being edited (`config/snapshot_helpers.py`) |
| **Jump to function…** | Dropdown listing all `def` functions in the file, alphabetically sorted — selecting one jumps the editor to that line |
| **Refresh** | Reloads the current version of the file from disk, discarding any unsaved changes |
| **Save** | Runs a backend Python syntax check and writes the file if the check passes |
| **Position** | Shows the current cursor position as `line:column` |

### Jump to Function

Automatically parses all function definitions (`def name(`) from the current editor content and lists them alphabetically. Each entry shows the function name and its line number.

This is useful when the helpers file grows large — you can navigate instantly to any function without scrolling.

### Line Numbers

Displayed on the left side of the editor and scroll in sync with the text.

### Editor Textarea

Full free-edit Python code area. Supports the complete Python syntax. There is no autocompletion or inline error highlighting — the syntax check happens only when you click Save.

### Status Messages

- **"Saved. Python syntax valid."** — Save succeeded, syntax is correct, file has been written
- **Error message with line number** — Python syntax error detected; the file has not been overwritten. The error message shows the line where the problem was found.

---

## Save Behavior

1. When **Save** is clicked, the code is sent to the backend for a syntax check.
2. If a syntax error is found: an error message is shown with the line number. The existing file on disk is not changed.
3. If no syntax error: the file is written and the new helpers are available for all subsequent snapshot executions.

The syntax check prevents broken code from being applied and blocking all snapshot runs. A bad save that passes silently would break every agent analysis cycle — the check is a safety guardrail.

Note: the syntax check catches Python parse errors (invalid syntax, indentation errors, undefined names in function signatures). It does not guarantee that the logic is correct or that the functions will work as intended. Always test after saving.

---

## How Helper Functions Are Used in Scripts

Functions from `snapshot_helpers.py` are automatically available in all transform scripts within Snapshot Config. They do not need to be imported — they are injected into the execution context before the script runs.

### In a Tool Block Transform Script

```python
# snapshot_helpers.py contains: def normalize_candle_tool_output(output, timeframe=None): ...

# In a tool block transform_script:
result = normalize_candle_tool_output(raw_output, timeframe="H1")
```

### In an Assembly Transform Script

```python
# snapshot_helpers.py contains: def build_base_payload(snapshot): ...

# In the assembly script:
base = build_base_payload(snapshot)
output = base | {"extra_field": some_value}
```

### In a Calculation Block Script

Custom helpers defined in this file are also available in calculation block scripts that process intermediate results.

---

## Built-In Helper Functions

The following helpers are part of the standard `snapshot_helpers.py` shipped with OpenForexAI. They cover the most common snapshot processing patterns:

### Micro Helpers

**`latest_value(values)`**
Returns the last numeric (non-None) value from a series (list).

```python
last_close = latest_value(candle_closes)
```

**`classify_series_direction(values, change_threshold=...)`**
Analyzes the direction of a numeric series and returns `"rising"`, `"falling"`, or `"flat"`.

```python
direction = classify_series_direction(ema_values)
```

**`classify_indicator_direction(values, indicator_name)`**
Returns indicator-specific direction labels. For ATR it returns `"expanding"`, `"contracting"`, or `"stable"`. For other indicators falls back to `classify_series_direction` behavior.

```python
atr_state = classify_indicator_direction(atr_values, "ATR")
# returns "expanding", "contracting", or "stable"
```

### Tool Transform Helpers

**`normalize_candle_tool_output(tool_output, timeframe=None)`**
Converts raw candle rows from tool output into a consistent, structured candle format. Use in tool block transform scripts for candle data tools.

```python
candles = normalize_candle_tool_output(raw_output, timeframe="H1")
```

**`build_indicator_tool_output(tool_output, tool_input=None, all_outputs=None)`**
Compatibility helper for indicator transforms. Processes raw indicator tool output into a structured format. Note: the preferred approach for new scripts is to use the micro helpers directly rather than this function.

### Assembly Helpers

These helpers are designed to keep assembly scripts short and readable by encapsulating common payload building patterns:

**`build_base_payload(snapshot)`**
Builds the base payload dict from the snapshot object. Always the starting point for an assembly script.

**`build_h1_payload(snapshot, profile=None)`**
Builds the H1 timeframe section of the payload.

**`build_m5_payload(snapshot, profile=None)`**
Builds the M5 timeframe section of the payload.

**`build_support_resistance_payload(snapshot, profile=None)`**
Builds the support/resistance levels section.

**`build_flags_payload(snapshot)`**
Builds the flags section (entry gates, blockers, and boolean conditions).

**`build_entry_gates_payload(snapshot, profile=None)`**
Builds the entry gates subsection specifically.

**`build_entry_blockers_payload(snapshot)`**
Builds the entry blockers subsection.

**`include_entry_blockers(profile=None)`**
Returns a boolean indicating whether entry blockers should be included for the given profile.

**`include_tool_outputs(profile=None)`**
Returns a boolean indicating whether raw tool outputs should be included for the given profile.

---

## Writing Custom Helper Functions

You can extend `snapshot_helpers.py` with your own functions. They immediately become available in all snapshot scripts without any additional configuration.

### Design Rules

Good helper functions should:

- Do one clearly defined thing
- Accept explicit arguments (no hidden dependencies on global state)
- Return JSON-serializable data (dict, list, string, number, bool, None)
- Avoid hidden side effects
- Stay small — split large functions into smaller composable ones

### Example: Pip Formatting

```python
def format_pips(price_diff, pip_size=0.0001):
    """Convert a price difference to pips, rounded to 1 decimal."""
    if price_diff is None:
        return None
    return round(price_diff / pip_size, 1)
```

Usage in a transform script:
```python
sl_pips = format_pips(entry_price - stop_loss_price)
```

### Example: Trend Classification from Two EMAs

```python
def classify_trend(ema_fast, ema_slow, threshold=0.001):
    """
    Return 'BULLISH', 'BEARISH', or 'NEUTRAL' based on EMA relationship.
    threshold: relative separation required to classify as trending.
    """
    if ema_fast is None or ema_slow is None:
        return "UNKNOWN"
    ratio = (ema_fast - ema_slow) / ema_slow
    if ratio > threshold:
        return "BULLISH"
    elif ratio < -threshold:
        return "BEARISH"
    return "NEUTRAL"
```

Usage:
```python
trend = classify_trend(ema_20_last, ema_50_last)
```

### Example: Candle Body Analysis

```python
def candle_body_pct(open_price, close_price, high_price, low_price):
    """
    Return the body size as a percentage of total candle range.
    Returns 0.0 if the candle range is zero (doji).
    """
    candle_range = high_price - low_price
    if candle_range == 0:
        return 0.0
    body = abs(close_price - open_price)
    return round(body / candle_range * 100, 1)
```

### Example: Price Position Within Range

```python
def price_position_in_range(price, range_low, range_high):
    """
    Return where price sits within a given range as a percentage (0=bottom, 100=top).
    Returns None if range is zero or inputs are missing.
    """
    if None in (price, range_low, range_high):
        return None
    total = range_high - range_low
    if total == 0:
        return None
    return round((price - range_low) / total * 100, 1)
```

### Example: Session Classifier

```python
def classify_forex_session(hour_utc):
    """
    Return the primary forex trading session for a given UTC hour.
    Returns 'SYDNEY', 'TOKYO', 'LONDON', 'NEWYORK', or 'OVERLAP_LDN_NY'.
    """
    if 22 <= hour_utc or hour_utc < 7:
        return "SYDNEY_TOKYO"
    elif 7 <= hour_utc < 8:
        return "TOKYO_LONDON_OVERLAP"
    elif 8 <= hour_utc < 13:
        return "LONDON"
    elif 13 <= hour_utc < 17:
        return "OVERLAP_LDN_NY"
    elif 17 <= hour_utc < 22:
        return "NEWYORK"
    return "OFF_HOURS"
```

---

## Important Note on Helper Changes

Helpers are part of the snapshot configuration surface. Changing a helper function changes snapshot behavior for every agent that uses scripts calling that function.

- If a script references a helper name that is not defined in the file (or the file is missing), that script fails and the snapshot run fails.
- If a helper function has a bug that raises an exception at runtime, it will fail every transform or assembly script that calls it.
- Always test after saving by running a snapshot in the Test Snapshot panel (accessible from Decision Prompt) or via the Tool Executor.

---

## Typical Workflow

1. Click **Refresh** to make sure you have the latest version of the file
2. Use **Jump to function** to locate an existing function you want to modify, or scroll to the end to add a new one
3. Edit the code or add a new function
4. Click **Save**
5. If a syntax error is shown: read the error message, fix the line indicated, and click Save again
6. After a successful save, test the affected snapshot in the Decision Prompt test panel or Tool Executor to confirm the function behaves correctly
7. If the snapshot produces unexpected output, use the **Jump to function** dropdown to quickly revisit the changed function

---

## See Also

- [Snapshot Helper Functions](snapshot-helper-functions.en.md) — Reference for all built-in helper functions
- [Snapshot Transformers](snapshot-transformers.en.md) — How transform scripts use helpers
- [Snapshot Config](ui.config.snapshot_config.en.md) — Snapshot profile structure and calculation blocks
- [Snapshot Config Guide](snapshot-config-guide.en.md) — End-to-end guide for building snapshot profiles
