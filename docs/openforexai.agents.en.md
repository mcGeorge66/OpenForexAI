[Back to Documentation Index](README.en.md)

# openforexai/agents — Agent Runtime

OpenForexAI uses one runtime agent class for all agent types:

- `openforexai/agents/agent.py`

`AA`, `BA`, and `GA` are configuration-driven variants of the same class.
There are no role-specific subclasses in the live runtime path.

## What Controls an Agent

An agent is primarily defined by configuration received from `ConfigService`.

Important config fields include:

- `type`
- `llm`
- `broker`
- `pair`
- `event_triggers`
- `AnyCandle`
- `system_prompt`
- `tool_config`
- `snapshot_profile`
- `decision_prompt_profile`

## Bootstrap Flow

At startup the agent does not receive direct constructor dependencies for its
full behavior. Instead it asks for its config through the event bus.

1. The agent publishes `agent_config_requested`.
2. `ConfigService` responds with `agent_config_response`.
3. The agent resolves its LLM, broker, and allowed tools from that payload.
4. The message loop and optional timer loop start.

This keeps the runtime architecture uniform across all agent types.

## Snapshot-Aware Runtime Paths

The live runtime now supports snapshot-backed execution for multiple agent
types. The exact behavior still depends on the agent role, trigger, and tool
policy.

The Analysis Agent (`AA`) currently has the strongest specialization.

### 1. Decision-only snapshot path

This is the important current production path for market analysis runs.

It is used when the trigger should be handled by the decision-only snapshot
engine, for example `m5_agent_trigger`.

Flow:

1. The runtime builds a market snapshot with `build_analysis_snapshot(...)`.
2. The snapshot profile controls which tools are used and how data is shaped.
3. The decision prompt profile controls the final decision-only system prompt.
4. The LLM receives one prepared user payload instead of a multi-turn tool loop.
5. The agent persists and publishes the final `analysis_result`.

This path is designed to avoid repeated tool calls by the LLM and to reduce
prompt size, latency, and failure risk.

### 2. Snapshot-backed tool loop and standard tool loop

For agent queries, broker execution agents, global agents, or any
snapshot-enabled agent that must still keep explicit action tools, the runtime
can continue to use the classic tool-enabled loop.

In that mode the runtime may still inject a prepared snapshot into the prompt,
but tool use remains available for explicit actions or exceptional follow-up
queries.

The tool-enabled path:

- sends conversation history plus visible tool schemas to the LLM
- executes approved tool calls through `ToolDispatcher`
- appends assistant/tool turns until a final response is produced

## Snapshot and Decision Profiles

The current agent workflow supports two profile types resolved from top-level
config sections in `config/system.json5`.

### `snapshot_profile`

Selects a named snapshot profile from `snapshot_profiles`.

The resolved profile controls:

- which shared tools are executed
- fixed tool arguments
- decision payload shaping
- decision semantics
- token-saving inclusion options

### `decision_prompt_profile`

Selects a named prompt profile from `decision_prompt_profiles`.

The resolved profile controls how the agent system prompt is replaced or
extended for snapshot-driven runs.

This allows the old long agent prompt to exist in config while the runtime can
still inject a much cleaner snapshot-aware execution prompt for AA, BA, or GA
runs.

## Agent Triggers

Common current triggers include:

- `m5_agent_trigger`
- `prompt_updated`
- `agent_query`
- `analysis_result` for broker agents

`AnyCandle` is used to divide M5 triggers so an analysis agent can, for
example, run every third M5 event instead of every candle.

## Analysis Agent Output

If an AA finishes successfully, it:

- persists the analysis result in the repository
- stores the market snapshot with the analysis record
- publishes `analysis_result` on the event bus

If the snapshot is invalid, the AA does not proceed to the LLM call. Instead
the runtime emits monitoring information and skips the cycle.

## Broker Agent Behavior

The current Broker Agent (`BA`) is execution-focused.

It receives an `analysis_result` and then:

- validates the payload
- checks account and position state
- may call broker and account tools
- may place or close trades depending on its system prompt and tool results

The BA can also use snapshot profiles. In that case the snapshot acts as
prepared execution context while the BA remains tool-capable for explicit
broker actions such as opening or closing trades.

## Agent Query vs Execute Inspection

The UI now distinguishes between two ways of interacting with agents.

### Agent query

`Send` in Agent Chat uses the normal query path and returns the agent response.

### Execute inspection

`Execute` in Agent Chat runs an isolated inspect cycle and returns:

- visible chat output in the left chat history
- run details for snapshot, LLM, tools, and runtime in the inspector below the chart

This makes configuration testing easier without relying only on live runtime
events.
