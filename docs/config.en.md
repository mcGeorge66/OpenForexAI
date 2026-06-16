[Back to Documentation Index](README.en.md)

# Configuration Guide

The `config/` directory is the operational source of truth for OpenForexAI.

It contains:

- the central runtime config
- runtime-editable bridge/routing files
- LLM module configs
- broker module configs
- sample and meta files for module creation

## Directory Layout

```text
config/
  system.json5
  config.default.json5
  RunTime/
    agent_tools.json5
    event_routing.json5
  modules/
    broker/
      *.sample.json5
      *.meta.json5
    llm/
      *.sample.json5
      *.meta.json5
```

## `system.json5`

`system.json5` is the central live configuration document.

Important current top-level sections include:

- `system`
- `modules`
- `snapshot_profiles`
- `decision_prompt_profiles`
- `agents`

Depending on the deployment, additional top-level sections such as `system`,
`database`, `data`, or import rules may also exist and are handled by the UI
and package manager.

### `system`

This section contains runtime-wide infrastructure settings.

Important current sub-sections include:

- `management_api`
- `ui.dev_server`

Example:

```json
"system": {
  "management_api": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "ui": {
    "dev_server": {
      "host": "127.0.0.1",
      "port": 5173
    }
  }
}
```

Meaning:

- `system.management_api.port` controls the FastAPI management/backend port
- `system.ui.dev_server.port` controls the Vite browser/UI dev port
- the Vite dev proxy also reads `system.management_api.host` and `system.management_api.port`

This allows multiple local instances to run in parallel as long as each
instance uses its own pair of ports.

### `modules`

This section maps logical module names to concrete config file paths.

Current example:

```json
"modules": {
  "llm": {
    "azure_azmin": "config/modules/llm/azure.azmin.json5"
  },
  "broker": {
    "mt5_oxs_t": "config/modules/broker/mt5.oxs_t.json5"
  }
}
```

Agents reference these names instead of embedding connection details directly.

### `snapshot_profiles`

This section contains named snapshot definitions used as runtime-built prompt
context for agents.

A snapshot profile can define:

- description
- `decision_input_prefix`
- `decision_payload`
- `decision_semantics`
- `recent_context`
- `include_sections`
- `tool_blocks`
- optional strategy-specific shaping values

Snapshot profiles are selected from the Agent Config UI and edited in
`Snapshot Config`.

### `decision_prompt_profiles`

Named prompt profiles for snapshot-driven agent runs.

A prompt profile usually contains:

- description
- `mode`
- `prompt`

Typical `mode` values:

- `replace`
- `append`

These profiles are selected per agent and let the runtime keep a normal
system prompt in config while still injecting a cleaner snapshot-aware prompt
for execution.

### `agents`

Each running agent has one entry here.

Important current fields can include:

- `enable`
- `type`
- `llm`
- `broker`
- `pair`
- `timer`
- `event_triggers`
- `AnyCandle`
- `snapshot_profile`
- `decision_prompt_profile`
- `system_prompt`
- `tool_config`

Current AA example concepts:

- `event_triggers` includes `m5_agent_trigger`, `prompt_updated`, `agent_query`
- `snapshot_profile` points to a snapshot profile name
- `decision_prompt_profile` points to a decision prompt profile name

Current BA example concepts:

- `event_triggers` includes `analysis_result` and `agent_query`
- a snapshot profile can be used to inject prepared broker/account/orderbook
  context instead of forcing the BA to fetch that context every run

## Runtime Files in `config/RunTime`

### `agent_tools.json5`

Used for bridge-tool style runtime configuration.

This file is exposed through the `Bridge Tools` UI.

### `event_routing.json5`

Defines event routing rules for the EventBus.

This file is exposed through the `Event Routing` UI and can be reloaded at
runtime through the management API.

## Module Config Files

Broker and LLM connection details live in `config/modules/...`.

These files are edited from:

- `Broker Modules`
- `LLM Modules`

Important points:

- active modules are referenced by name from `system.json5`
- sample files document required fields
- meta files describe module structure and UI hints

## UI and Package Manager Relationship

The current UI does not treat all configuration as one giant text blob.

Instead:

- `Agent Config` edits agent entries
- `Snapshot Config` edits `snapshot_profiles`
- `Decision Prompt` edits `decision_prompt_profiles`
- `Bridge Tools` edits runtime tool config
- `Event Routing` edits routing rules
- `System Config` edits the central system file
- `Helper Config` edits `config/snapshot_helpers.py`
- `Package Manager` exports/imports selected config areas

## Package Export/Import Areas

The current Package Manager supports selective export/import of:

- agents
- snapshot profiles
- decision prompt profiles
- bridge tools
- event routing
- system config

This makes it possible to move a strategy setup without exporting everything.

## Environment Variables

Config files use `${VAR}` or `${VAR:-default}` substitution.

Typical variables include:

- LLM API keys and endpoints
- broker credentials
- database settings
- log level

Secrets should stay outside version-controlled config files.
