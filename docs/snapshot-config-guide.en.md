# Snapshot Config Guide

## What a Snapshot Is

A snapshot is a prepared runtime data package for one agent run.

Instead of letting the LLM fetch candles, call tools, and calculate indicators by itself, the runtime builds the snapshot first and then gives the finished result to the LLM.

This has several goals:

- lower token usage
- faster responses
- fewer tool-related failures
- more consistent decisions
- easier debugging

In simple terms:

- tools collect and transform data
- calculation blocks derive structured interpretations from the tool outputs
- an assembly transform combines everything into the final payload sent to the LLM
- the agent reads that prepared snapshot and returns its result

So a snapshot is the agent's market context for one decision.

## How the Snapshot Flow Works

1. The runtime selects a snapshot profile.
2. The configured tool blocks run with their configured arguments. Each tool block optionally runs a per-tool transform script that reshapes the raw output before it is stored.
3. Calculation blocks run. They operate on the stored tool outputs and produce structured results.
4. The assembly transform script combines everything into the final payload.
5. The `decision_input_prefix` text is placed in front of the final decision input, and the assembled result is sent to the LLM.

This means the snapshot profile controls both:

- what data is collected
- how the data is shaped and interpreted before it reaches the LLM

## Snapshot Config Screen Overview

The Snapshot Config dialog is used to define one named snapshot profile.

Each profile contains these main parts, arranged in data-flow order:

1. basic profile information (name, description)
2. decision input prefix and timeframe selectors
3. Tool Blocks — what data is collected, and how each tool output is transformed
4. Calculation Blocks — how tool outputs are turned into structured results
5. Assembly Transform — how everything is combined into the final LLM payload

Each tool block also has a `Test` action.

This opens a preview dialog that shows:

- the raw tool output
- the transformed output after the tool transform script
- the arguments used
- the runtime context
- any tool or transform errors

This is the fastest way to verify whether one tool block is producing the right intermediate structure before you run the full snapshot preview.

The transformer scripts themselves are documented separately here:

- [Snapshot Transformer Guide](snapshot-transformers.en.md)

---

## Basic Fields

### `Name`

This is the profile name.

It is used to identify the snapshot profile in the system and to assign it to agents.

Effect:

- required for saving
- must be unique
- appears in profile selection lists

Example:

- `aa_default_v1`
- `eurusd_reversal_snapshot`
- `mdac_profile_london_open`

### `Description`

This is a human-readable explanation of what the profile is for.

Effect:

- does not directly change runtime logic
- helps you and others understand the profile purpose

Good use:

- describe the strategy style
- describe the intended pair or session
- describe what is special about the snapshot

---

## `decision_input_prefix`

This is free text placed at the beginning of the final input that is sent to the LLM.

Default:

```text
Runtime-prepared market decision snapshot.
Use the snapshot as the complete market context.
Return strict JSON only.
```

What it does:

- tells the LLM how to treat the snapshot
- acts like a short runtime instruction before the JSON payload
- can reduce confusion and unwanted output formats

What it does not do:

- it does not fetch data
- it does not change calculations
- it does not replace the main decision prompt profile

Impact:

- stronger instructions can improve output discipline
- too much text increases token cost
- unclear text can weaken the final decision quality

Recommended use:

- keep it short
- keep it operational
- avoid repeating long strategy explanations here

---

## Timeframe Selectors

Two selectors appear below `decision_input_prefix`:

- **Short timeframe** — the fast candle source (default: `M15`)
- **Long timeframe** — the slow candle source (default: `H1`)

Supported values: `M5`, `M15`, `M30`, `H1`, `H4`, `D1`

Effect:

- the selected values are saved in the profile as `short_timeframe` and `long_timeframe`
- tool blocks can reference these values using the special placeholders `SHORT_TF` and `LONG_TF` in their `arguments.timeframe` field
- at execution time, the runtime automatically replaces `SHORT_TF` with the profile's `short_timeframe` value and `LONG_TF` with `long_timeframe`

This is the recommended way to connect candle blocks to the profile's timeframe selectors. When you change the timeframe selector, all tool blocks using the placeholder update automatically — no per-block editing required.

Use this when your strategy pairs a different combination such as M15 + H4 or M30 + D1.

---

## Tool Blocks

The Tool Blocks section defines which tools are used to build the snapshot.

This is the most important technical part of the profile.

Each block tells the runtime:

- which tool to run
- what arguments it uses
- how the output is identified
- how the raw output should be reshaped (via a transform script)

### Why Snapshots Use the Same Tools as Agents

The snapshot system uses the same shared tool interface as the agents.

This is intentional.

It means:

- a tool only needs to be implemented once
- the same tool can be used directly by an agent
- the same tool can also be used by the snapshot builder
- calculations stay consistent across the whole system

### How a Snapshot Uses a Tool

When you add a tool block to a snapshot profile, the runtime does this:

1. Load the tool from the shared tool registry.
2. Apply the static arguments from the profile.
3. Execute the tool in the current broker/pair context.
4. Run the per-tool `transform_script` on the raw output (if one is set).
5. Store the transformed result under `output_key` for use by calculation blocks and the assembly transform.

This lets you change:

- which tool is used
- the tool arguments
- how the raw output is shaped
- the output key name

without changing code.

### Block Fields

#### `id`

Internal name of the block.

Effect:

- used for identification
- should be unique inside the profile

#### `tool_name`

The registered tool that will be executed.

Examples:

- `get_candles`
- `calculate_indicator`
- custom tools such as future analytics modules

#### `output_key`

Name under which the transformed tool output is stored.

Effect:

- this key is used by calculation blocks in their `sources` config
- this key is also used in the assembly transform to access the result via `tool_outputs`
- should be descriptive and unique within the profile

#### `enabled`

If unchecked, that block is skipped.

Effect:

- useful for testing or comparing variants

#### `arguments`

Static tool arguments used when running the block.

Examples:

- `timeframe`
- `count`
- `indicator`
- `period`
- `history`

Special placeholder values for `timeframe`:

- `SHORT_TF` — resolved at runtime to the profile's `short_timeframe`
- `LONG_TF` — resolved at runtime to the profile's `long_timeframe`

Using these placeholders is the recommended way to link a candle block to the profile's timeframe selectors. That way, changing the selector in one place updates all linked blocks automatically.

#### `transform_script`

A Python script that runs immediately after the tool call.

It receives the raw tool output and can reshape it before the result is stored.

If left empty, the raw tool output is passed through unchanged.

The script has access to:

- `raw_output` — the raw result returned by the tool
- `arguments` — the arguments used in this tool call
- `snapshot` — the current snapshot object

It must set `result` to produce the transformed output.

### Example Tool Blocks

Typical candle block using a timeframe placeholder:

```json
{
  "id": "m15_recent",
  "tool_name": "get_candles",
  "output_key": "m15_recent",
  "enabled": true,
  "arguments": {
    "timeframe": "SHORT_TF",
    "count": 20
  }
}
```

Typical indicator block:

```json
{
  "id": "rsi_primary",
  "tool_name": "calculate_indicator",
  "output_key": "rsi_primary",
  "enabled": true,
  "arguments": {
    "indicator": "RSI",
    "period": 7,
    "timeframe": "LONG_TF",
    "history": 3
  }
}
```

Typical custom extra block:

```json
{
  "id": "mdac_signal",
  "tool_name": "mdac",
  "output_key": "mdac_signal",
  "enabled": true,
  "arguments": {
    "timeframe": "SHORT_TF",
    "lookback": 24
  }
}
```

---

## Calculation Blocks

Calculation blocks run after all tool blocks have finished.

They operate on the stored tool outputs and produce structured, semantically meaningful results. This is where market interpretation happens — trend, support/resistance, entry readiness, and similar derived logic.

The results are stored in `snapshot["calculations"]` and are available to the assembly transform.

### How Calculation Results Are Stored

The storage location of a calculation result depends on the block type:

- Blocks whose primary candle source is an `output_key` (e.g. `m15_recent`) are stored under `calcs["m15_recent"]`.
- `entry_gates`, `recent_context`, and `script` blocks are always stored under `calcs["global"]`.

So if you have two `trend` blocks — one reading from `m15_recent` and one from `h1_recent` — their results land in `calcs["m15_recent"]` and `calcs["h1_recent"]` respectively.

Within each group, results are keyed by block `id`.

### Block Fields

#### `id`

Internal name of the block. Also used as the key under which the result is stored within its group.

#### `type`

The calculation type. See the types listed below.

#### `enabled`

If unchecked, the block is skipped.

#### `sources`

Optional. Maps named inputs to tool `output_key` values.

Example:

```json
{
  "candles": "m15_recent",
  "ema_fast": "ema_fast_primary",
  "ema_slow": "ema_slow_primary"
}
```

The keys on the left are type-specific input names. The values on the right are the `output_key` values from the tool blocks.

#### `config`

Optional. Type-specific parameters. See each type below.

### Calculation Block Types

#### `trend`

Builds a structured trend interpretation from EMA fast and slow sources.

Typical sources:

- `candles` — the candle series (used for price position)
- `ema_fast` — the fast EMA tool output
- `ema_slow` — the slow EMA tool output

Typical output fields:

- EMA alignment
- EMA slope bias
- price position bias
- combined trend state

Result is stored in `calcs["<candles_output_key>"]["<block_id>"]`.

#### `micro_sr`

Builds micro support/resistance levels from a candles source.

These levels are used for entry timing — they are close to price and sensitive to recent market structure.

Result is stored in `calcs["<candles_output_key>"]["<block_id>"]`.

#### `structural_sr`

Builds structural support/resistance levels from a candles source.

These levels are used for broader trade structure — they are farther from price and represent stronger historical zones.

Typical config:

- `min_gap_atr` — minimum ATR-based distance from current price for a level to count as structural

Result is stored in `calcs["<candles_output_key>"]["<block_id>"]`.

#### `close_quality`

Evaluates recent candle quality from a candles source.

Typical output fields:

- bullish closes
- bearish closes
- net direction
- total body size relative to ATR
- largest body relative to ATR
- quality label

Typical config:

- `recent_count` — how many recent candles to evaluate
- `weak_threshold_atr` — ATR multiplier below which movement is considered weak
- `strong_threshold_atr` — ATR multiplier above which movement is considered strong

Result is stored in `calcs["<candles_output_key>"]["<block_id>"]`.

#### `entry_gates`

Builds directional entry readiness flags for long and short.

Typical output fields:

- `sr_gate_passed`
- `rsi_blocked`
- `m5_confirmed`

Typical config:

- `long_confirmed_structures` — list of candle structure labels that count as valid long confirmation
- `short_confirmed_structures` — list of candle structure labels that count as valid short confirmation

Result is always stored in `calcs["global"]["<block_id>"]`.

#### `recent_context`

Stores a recent candle window for reference in the assembly transform.

Useful when you want to include a compact candle slice in the final payload without forwarding the entire tool output.

Typical config:

- `count` — how many recent candles to store

Result is always stored in `calcs["global"]["<block_id>"]`.

#### `script`

Free-form Python script with access to all tool outputs. Produces a custom result dict.

The script has access to:

- `tool_outputs` — dict of all transformed tool block outputs, keyed by `output_key`
- `snapshot` — the current snapshot object

The script must set `result` to a dict.

Example:

```python
# tool_outputs contains all transformed tool block outputs (keyed by output_key)
candles = tool_outputs.get("m15_recent") or []
rsi = tool_outputs.get("rsi_primary") or {}
result = {
    "custom_flag": True,
    "rsi_latest": rsi.get("latest"),
}
```

Result is always stored in `calcs["global"]["<block_id>"]`.

### Accessing Calculation Results in the Assembly Transform

The assembly transform receives the full `snapshot` dict. Calculations are accessed like this:

```python
calcs = snapshot.get("calculations", {})

# blocks whose candle source output_key is "m15_recent"
m15 = calcs.get("m15_recent", {})

# entry_gates, recent_context, and script blocks
global_calcs = calcs.get("global", {})

result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
    "trend": m15.get("trend"),
    "entry_gates": global_calcs.get("entry_gates"),
}
```

---

## Assembly Transform

The Assembly Transform script runs after all tool blocks and calculation blocks have finished.

It receives the full `snapshot` dict and must set `result` to the final payload that will be sent to the LLM.

The assembled result is returned directly to the LLM — there is no additional metadata wrapper added around it.

### `transform_script` (per tool block)

A Python script that runs after each individual tool call.

It receives the raw tool output and can reshape it before the result is stored.

If left empty, the raw tool output is passed through unchanged.

### `assembly_transform_script`

A Python script that runs after all enabled tool blocks and calculation blocks have finished.

It receives the full `snapshot` dict and combines everything into the final payload.

The script must set `result` to a dict. That dict is what the LLM receives.

Minimal example:

```python
result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
}
```

Structured market payload example:

```python
calcs = snapshot.get("calculations", {})
m15 = calcs.get("m15_recent", {})
h1 = calcs.get("h1_recent", {})
global_calcs = calcs.get("global", {})

result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
    "trend": m15.get("trend"),
    "micro_sr": m15.get("micro_sr"),
    "structural_sr": h1.get("structural_sr"),
    "close_quality": m15.get("close_quality"),
    "entry_gates": global_calcs.get("entry_gates"),
    "recent_context": global_calcs.get("recent_context"),
}
```

BA-style example (only tool outputs, no derived logic):

```python
result = {"tool_outputs": tool_outputs}
```

### Cancelling the Agent Cycle from the Assembly Script

The assembly script has access to a `cancel` variable (default `False`) and an optional `cancel_reason` string (default `""`).

If the script sets `cancel = True`, the runtime skips the LLM call entirely for this trigger cycle. No analysis is run, no result is stored. The agent simply waits for the next trigger.

This is useful when the snapshot can determine that the current conditions make an LLM call pointless — for example when no trading session is active, or when a pre-condition check fails.

Variables available:

| Variable | Type | Default | Description |
|---|---|---|---|
| `cancel` | bool | `False` | Set to `True` to abort the cycle |
| `cancel_reason` | str | `""` | Optional log message explaining why |

Example — skip cycle when no Forex session is active:

```python
calcs = snapshot.get("calculations", {})
global_calcs = calcs.get("global", {})

session = tool_outputs.get("session_status") or {}
if not session.get("active_sessions"):
    cancel = True
    cancel_reason = "no active session"
    result = {}
```

Important:

- `cancel` is only evaluated from the `assembly_transform_script`, not from per-tool `transform_script`
- the agent logs the cancellation at INFO level with the `cancel_reason`
- setting `cancel = True` does not produce an error or a warning — it is normal operational filtering

---

## Script Editor

All script fields in the Snapshot Config use a Monaco-based code editor with Python syntax highlighting and a dark theme.

This includes:

- the `transform_script` on each tool block
- the `assembly_transform_script`
- the `script` type calculation block

The editor provides three controls:

### Snippets button

Opens a dropdown with context-specific code snippets.

Select a snippet to insert it at the current cursor position.

All snippets are stored in `config/ui_snippets.json5` and can be edited directly without touching source code.

### Copy button

Copies the full script content to the clipboard.

### Expand button

Opens the script in a full-screen overlay modal for comfortable editing.

The modal uses the same Monaco editor with the same syntax highlighting.

When you are done editing, press the Apply button to write the changes back to the field.

---

## Practical Rule of Thumb

Use the profile like this:

- **Tool Blocks** define what is measured and how each raw output is reshaped.
- **Calculation Blocks** define what the tool outputs mean — trend, S/R levels, entry readiness, and other derived structure.
- **Assembly Transform** defines the exact payload shape the LLM receives.

For a BA or GA agent:

- configure only the tool blocks you need
- write an `assembly_transform_script` that returns exactly the data structure the LLM needs
- keep calculation blocks minimal or empty if no derived logic is needed

For an AA agent:

- configure candle and indicator tool blocks with appropriate `SHORT_TF` / `LONG_TF` placeholders
- add calculation blocks for trend, S/R, close quality, and entry gates
- write an assembly transform that composes the final structured payload from `snapshot["calculations"]`

That is the core model of the Snapshot Config system.
