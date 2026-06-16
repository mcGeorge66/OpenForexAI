# Snapshot Transformer Guide

## Purpose

This document explains how snapshot transformer scripts work.

It focuses on:

- per-tool `transform_script`
- `assembly_transform_script`
- available input variables
- where transformed data goes
- how one tool can access outputs from earlier tools

Use this guide when you want to write or change transformer scripts in Snapshot Config.

## Transformer Levels

The snapshot pipeline has two script levels:

1. tool transformer
2. assembly transformer

### Tool Transformer

A tool transformer runs directly after one tool call.

It receives the raw output of that tool and can reshape it before the result is stored for later snapshot building.

### Assembly Transformer

The assembly transformer runs after all enabled tools have finished.

It can access all transformed tool results and combine them into the final snapshot payload shape.

## Tool Transformer Inputs

Inside a per-tool `transform_script`, these variables are available.

### `tool_input`

This is the arguments object used for the current tool call.

Example:

```python
{
    "indicator": "RSI",
    "period": 7,
    "timeframe": "H1",
    "history": 3,
}
```

### `tool_output`

This is the raw output returned by the current tool before transformation.

Examples:

- a list of candle rows
- an indicator result object
- an account status object
- a positions list

### `all_outputs`

This contains the already transformed outputs of earlier tool blocks in the same snapshot run.

Important:

- it only contains blocks that already ran before the current block
- it does not contain future blocks
- tool order therefore matters when one block depends on another

### `result`

This is the output variable of the current script.

Whatever you write into `result` becomes the transformed output of the current tool block.

That transformed output is then:

- stored under the block's `output_key`
- available to later tool transformers through `all_outputs`
- available to the assembly transformer through `tool_outputs`

### `in_` and `out`

These are convenience variables.

- `in_` starts as a copy of the raw tool output
- `out` starts as a copy of the raw tool output

You can use them if you prefer:

```python
out["latest"] = 1.23
result = out
```

### Optional helper functions

If `config/snapshot_helpers.py` exists, helper functions from that file are injected into the script context.

Examples:

- `latest_value(...)`
- `classify_series_direction(...)`
- `classify_indicator_direction(...)`
- `normalize_candle_tool_output(...)`

If the file does not exist, these helper names are not available.

That means:

- scripts can still run
- but only if they do not reference missing helper names

## Tool Transformer Output

The rule is simple:

- assign the final transformed value to `result`

### Identity transform

```python
result = tool_output
```

### Compact indicator transform

```python
result = dict(tool_output)
points = tool_output.get("values") or tool_output.get("value") or []
values = [float(item["value"]) for item in points if isinstance(item, dict) and item.get("value") is not None]
indicator_name = str(tool_output.get("indicator") or tool_input.get("indicator") or "").upper()
result["indicator"] = indicator_name or result.get("indicator")
result["latest"] = latest_value(values)
result["direction"] = classify_indicator_direction(values, indicator_name)
result["values"] = points
if "value" in result:
    del result["value"]
```

## What Happens After a Tool Transform

After one tool transformer finishes:

1. its raw tool output is kept internally
2. its transformed output is stored under the block's `output_key`
3. that transformed output becomes available to later blocks through `all_outputs`
4. the assembly transformer can later access it through `tool_outputs`

## Assembly Transformer Inputs

Inside `assembly_transform_script`, these variables are available.

### `tool_outputs`

This is the dictionary of all transformed tool outputs.

Keys are normally the block `output_key` values.

Example:

```python
tool_outputs["m5_recent"]
tool_outputs["ema_fast"]
tool_outputs["account_status"]
```

This means:

- if a tool block has `output_key = "ema_fast"`, then the assembly script can read it with `tool_outputs.get("ema_fast")`
- if a tool block has `output_key = "open_positions"`, then the assembly script can read it with `tool_outputs.get("open_positions")`

Typical safe access pattern:

```python
ema_fast = tool_outputs.get("ema_fast")
if isinstance(ema_fast, dict):
    latest_ema = ema_fast.get("latest")
```

Why this matters:

- the assembly script can pull in exactly the tool outputs it needs
- it does not have to scan the full snapshot blindly
- different agent profiles can combine different tool blocks in a predictable way

### `raw_tool_outputs`

This is the dictionary of all raw tool outputs before transformation.

In most profiles, `tool_outputs` should be preferred.

Access works the same way:

```python
raw_ema = raw_tool_outputs.get("ema_fast")
```

Use `raw_tool_outputs` only when:

- you explicitly need the unmodified tool result
- the per-tool transform removed something you still want to inspect
- you are debugging a transform problem

### `snapshot`

This is the partially built snapshot object created by the runtime before assembly.

It can already contain sections such as:

- `market_data_valid`
- `validation_errors`
- `symbol`
- `timestamp_utc`
- `strategy_aggressiveness`
- `features`
- `flags`
- `derived_metrics`
- `recent_context`
- `tool_outputs`

### `profile`

This is the current snapshot profile configuration as a dictionary.

Use it when the assembly logic depends on profile settings.

Example:

```python
payload_cfg = profile.get("decision_payload") or {}
if payload_cfg.get("include_tool_outputs"):
    result["tool_outputs"] = tool_outputs
```

### `agent_context`

This provides the runtime context of the current snapshot run.

Typical fields:

- `agent_id`
- `broker_name`
- `pair`
- `strategy_aggressiveness`

### `result`

This is the final output variable of the assembly script.

Whatever is assigned to `result` becomes the assembled snapshot payload.

## Assembly Transformer Output

The assembly transformer should write the final object into `result`.

### How `result` reaches the LLM

What happens with `result` depends on the `include_metadata` option in the Decision Payload config:

**`include_metadata: true` (default — AA-style)**

The metadata header is prepended to the assembled result:

```json
{
  "market_data_valid": true,
  "validation_errors": [],
  "symbol": "EURUSD",
  "timestamp_utc": "...",
  "strategy_aggressiveness": "BALANCED",
  "price": { "latest": 1.176, "spread": 0.0001 },
  ... assembled result merged in ...
}
```

Use this when the LLM needs runtime context such as the current symbol, validity state, and aggressiveness setting.

**`include_metadata: false` (BA/GA-style)**

Only the assembled result is returned, without any header:

```json
{
  "account": { ... },
  "positions": [ ... ]
}
```

Use this when the LLM needs only the tool data and the header adds noise.

### BA-style example

```python
result = {"tool_outputs": tool_outputs}
```

Combined with `include_metadata: false` in Decision Payload, this gives the LLM exactly the raw tool outputs and nothing more.

### AA-style example

```python
result = build_base_payload(snapshot)
h1 = build_h1_payload(snapshot, profile)
if h1:
    result["h1"] = h1
```

Combined with `include_metadata: true` (default), this gives the LLM the metadata header plus the assembled market payload.

### Identity example

```python
result = {"tool_outputs": tool_outputs}
```

This is the simplest meaningful assembly script. It groups all transformed tool outputs under one key without any restructuring.

### Custom combination example

```python
result = {
    "account": tool_outputs.get("account_status") or {},
    "positions": tool_outputs.get("open_positions") or [],
}
```

Why this is useful:

- a BA profile can build a compact execution snapshot from only account and position data
- the LLM gets exactly the prepared execution context it needs
- no extra broker lookup tools are needed during the BA decision

## Example: Accessing One Specific Tool Block

Assume you have this tool block:

```json
{
  "id": "ema_fast",
  "tool_name": "calculate_indicator",
  "output_key": "ema_fast"
}
```

Then the assembly script can access it like this:

```python
ema_fast = tool_outputs.get("ema_fast")
```

If the transformed output looks like this:

```json
{
  "indicator": "EMA",
  "period": 20,
  "timeframe": "H1",
  "history": 3,
  "latest": 1.176497,
  "direction": "rising",
  "values": [
    {"timestamp": "2026-05-11T01:00:00Z", "value": 1.176452},
    {"timestamp": "2026-05-11T02:00:00Z", "value": 1.176473},
    {"timestamp": "2026-05-11T03:00:00Z", "value": 1.176497}
  ]
}
```

then you can use it like this:

```python
ema_fast = tool_outputs.get("ema_fast") or {}
latest_ema = ema_fast.get("latest")
ema_direction = ema_fast.get("direction")
```

Practical benefit:

- you do not need to know where in the wider snapshot this block may later end up
- you access the block directly by its configured `output_key`
- this keeps the assembly logic explicit and easy to maintain

## Example: Combining Several Tool Blocks

Example:

```python
account = tool_outputs.get("account_status") or {}
positions = tool_outputs.get("open_positions") or []
orderbook = tool_outputs.get("orderbook_summary") or {}

result = {
    "account": account,
    "positions": positions,
    "orderbook": orderbook,
}
```

Practical benefit:

- useful for BA snapshots
- only the selected runtime data is forwarded
- the final LLM input stays compact and purpose-built

## Important Design Rule

Use the two levels for different responsibilities:

- tool transformer:
  preprocess one tool result
- assembly transformer:
  combine many transformed tool results into the final shape

## Practical Guidelines

- keep each tool transformer small
- use `result = tool_output` only when no preprocessing is needed
- prefer `tool_outputs` over `raw_tool_outputs` in assembly
- use `profile` for conditional behavior
- use `snapshot` when you want runtime-derived sections such as `features` or `flags`
- keep final assembly explicit and readable

## Related Documentation

- [Snapshot Config Guide](snapshot-config-guide.en.md)
- [Snapshot Helper Functions](snapshot-helper-functions.en.md)
