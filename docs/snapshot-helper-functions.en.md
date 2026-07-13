# Snapshot Helper Functions

## Purpose

`config/snapshot_helpers.py` is the configurable helper layer for snapshot transforms and snapshot assembly.

The runtime imports this file when it is present.

If the file is missing, snapshot execution does not fail just because of that. It simply means that no helper functions from this file are available to snapshot scripts.

This allows you to change snapshot helper logic without editing the main backend modules.

## File Location

- `config/snapshot_helpers.py`

## How It Is Used

The snapshot system uses three layers:

1. `tool_blocks`
2. `transform_script` per tool block
3. `assembly_transform_script`

The helper file supports layers 2 and 3.

Typical examples:

- normalizing candle tool output
- normalizing indicator tool output
- classifying series direction
- building reusable payload blocks for AA snapshots

## Current Helper Functions

### Micro Helpers

- `latest_value(values)`
  - returns the last numeric value from a series

- `classify_series_direction(values, change_threshold=...)`
  - returns `rising`, `flat`, or `falling`

- `classify_indicator_direction(values, indicator_name)`
  - returns indicator-specific direction labels
  - for ATR it returns `expanding`, `contracting`, or `stable`

### Tool Transform Helpers

- `normalize_candle_tool_output(tool_output, timeframe=None)`
  - converts raw candle rows into a consistent candle structure

- `build_indicator_tool_output(tool_output, tool_input=None, all_outputs=None)`
  - compatibility helper for indicator transforms
  - not the preferred default anymore
  - the default indicator transform script now uses the micro helpers directly

### Assembly Helpers

- `build_base_payload(snapshot)`
- `build_h1_payload(snapshot, profile=None)`
- `build_m5_payload(snapshot, profile=None)`
- `build_support_resistance_payload(snapshot, profile=None)`
- `build_flags_payload(snapshot)`
- `build_entry_gates_payload(snapshot, profile=None)`
- `build_entry_blockers_payload(snapshot)`
- `include_entry_blockers(profile=None)`
- `include_tool_outputs(profile=None)`

These helpers are meant to keep assembly scripts short and readable.

## Design Rule

Helper functions should:

- stay small
- do one clear thing
- return JSON-serializable data
- avoid hidden side effects

## Important Note

These helpers are part of the snapshot configuration surface.

That means:

- changing them changes snapshot behavior
- if the file exists, snapshot scripts can use its helper functions
- if the file is missing, scripts must work without these helper functions
- if a script references a helper name that is not available, that script fails

## Related Documentation

- [Snapshot Config Guide](snapshot-config-guide.en.md)
