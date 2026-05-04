# Agent Core Behavior

This document describes what the shared `Agent` core does at runtime, especially where it transforms, filters, or suppresses incoming information before the LLM sees it.

Source file:
- [openforexai/agents/agent.py](/D:/GitHub/GHG/OpenForexAI/openforexai/agents/agent.py)

## Purpose

All runtime agents use the same `Agent` class:
- `AA`
- `BA`
- `GA`

The type label in the agent id is informational. Runtime behavior is driven by:
- config
- trigger set
- visible tools
- timer settings
- current incoming message

## Startup Flow

At startup the agent does not receive config by constructor injection.

Instead it performs a handshake on the EventBus:
1. Publish `agent_config_requested`
2. Wait for `agent_config_response`
3. Apply config locally
4. Start timer loop and/or message loop

This means config delivery is itself event-driven.

## Incoming Message Handling

The agent inbox receives:
- direct config responses
- direct `agent_query` requests
- normal EventBus events routed to the agent

The core message loop does the following:
1. Read one inbox message
2. Determine its event type
3. Decide whether to ignore it, consume it internally, or run an LLM cycle

## Messages Consumed Internally

These do not become normal LLM input:

- `agent_config_response`
  - Re-applies config at runtime
  - Used both for initial bootstrap and refresh

- `agent_query`
  - Only accepted when addressed directly to this agent
  - Answer is returned as `agent_query_response`
  - Not forwarded as a normal workflow event

## Messages That Can Be Ignored

The core can drop or ignore messages before the LLM sees them.

### 1. Trigger not enabled

If an incoming event is not present in `event_triggers`, no cycle runs.

### 2. Runtime paused

If runtime control is paused, normal trigger events are skipped.

### 3. `AnyCandle` filter

For `m5_candle_available`, the agent can skip most events and only run every Nth candle.

This is controlled by:
- `AnyCandle = 1` -> every candle
- `AnyCandle = 3` -> every third candle

The skipped candle events still existed on the EventBus. They were just filtered by the agent core.

### 4. Wrong direct target

For `agent_query`, a message addressed to a different agent is ignored.

## How the Core Builds LLM Input

The agent does not pass raw `AgentMessage` objects directly into the LLM.

It converts them into one user message string.

### Timer

Timer cycles become:

```text
[timestamp] Periodic analysis cycle. Review current market conditions and act if appropriate.
```

### Agent Query

UI/API questions become:

```text
[timestamp] External query from <source>:

<question>
```

### Generic Events

Normal events become:

```text
[timestamp] Event received: <trigger>
From: <source>
Details: <payload>
```

This is a text serialization step. The LLM does not receive the raw event object.

### `analysis_result` Special Handling

`analysis_result` is now treated specially.

Instead of passing the whole event payload to the target agent, the core extracts only:
- `payload.response`

The receiving agent sees:

```text
[timestamp] Analyst recommendation from <source>:

<payload.response>
```

This behavior exists to keep `BA` agents focused on execution and risk checks instead of receiving the full wrapped EventBus payload.

If `payload.response` is missing or empty, the core sends a short fallback message saying the recommendation arrived without a usable response payload.

## Tool Visibility

The system prompt may describe many tools, but the LLM only receives the tool specs that are visible in the current turn.

Visibility is controlled by the `ToolDispatcher`, not by the event payload.

This means:
- prompt content
- actual visible tools

can diverge if the prompt is broader than the allowed tool set.

## Additional Core Behavior Around Tools

During an LLM cycle the core:
1. Builds the visible tool list for the turn
2. Calls the LLM
3. Executes requested tools
4. Appends tool results to the running message history
5. Repeats until no more tools are requested or max turns are reached

So the LLM sees not only the initial input message, but also:
- its own prior assistant turns
- tool use records
- tool result messages

## Automatic Publish Behavior

After a successful non-`agent_query` cycle:
- `AA` agents automatically publish `analysis_result`

This is done by core logic, not by agent prompt text.

The published payload contains:
- `agent_id`
- `trigger`
- `trigger_source`
- `trigger_payload`
- `response`
- `timestamp`

## Monitoring vs. Raw Runtime Reality

Monitoring is a representation of runtime behavior, not the runtime objects themselves.

Important distinctions:
- EventBus monitoring shows what was published on the bus
- LLM request monitoring shows what was actually sent into the model
- Those two views are related, but not identical

That distinction matters for debugging:
- raw EventBus event != final LLM input

## Summary of Non-Obvious Core Actions

The agent core currently performs these non-obvious actions:
- requests config over the EventBus at startup
- ignores events not present in `event_triggers`
- skips candles due to `AnyCandle`
- converts incoming events into text user messages
- treats `agent_query` specially
- treats `analysis_result` specially
- limits model-visible tools to dispatcher-approved tools
- auto-publishes `analysis_result` for `AA` agents

These behaviors are in code, not only in configuration.
