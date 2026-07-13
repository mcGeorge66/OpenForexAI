[Back to Config](ui.config.en.md)

# Bridge Tools

`Bridge Tools` manages tool definitions that enable agent-to-agent communication via the Event Bus. A bridge tool appears to the LLM like any other tool — but instead of calling an external API or broker function, it forwards the request to another agent and returns that agent's response as the tool result. The configuration is stored in `config/RunTime/agent_tools.json5`.

---

## Table (Overview)

Lists all configured bridge tools with: number, name, mode, target(s). Clicking a row loads the tool into the editor.

---

## Action Buttons (Editor Header)

| Button | Color | Function |
|---|---|---|
| **New Empty Tool** | Amber | Clears all fields for a new tool |
| **Update** | Green | Saves changes to the currently selected tool |
| **Save As New** | Blue | Creates a new tool with the current state |
| **Delete** | Red | Deletes the currently selected tool |

---

## Tool Editor Fields

### Name

Unique identifier for the tool. Appears to the LLM as the tool name — should be descriptive and lowercase_snake_case, e.g. `ask_analysis_agent`.

Required field. Must be unique across all bridge tools.

### Timeout (seconds)

Number field. Default: `90`. Maximum wait time for the target agent's response. If the agent does not respond within this time, the tool call fails with a timeout error and the LLM receives an error string describing the failure.

### Description

Text field. Describes to the LLM what this tool does. Has direct influence on whether and when the model calls this tool. Should clearly state what kind of questions or tasks are forwarded to the target agent. A well-written description is critical: the LLM uses it to decide whether the tool is appropriate for the current reasoning step.

### Question Description

Textarea. Default: `"Your specific question..."`. Describes to the LLM how the question sent to the target agent should be formulated. Appears as the description of the `question` argument in the tool specification.

---

## Mode Selection

### Single Target

The tool has exactly one target agent.

| Field | Function |
|---|---|
| **target_agent_id** | Agent ID of the target agent, e.g. `OAPR1-ALL___-GA-NEWS` |

The calling agent's LLM provides a free-text question. The bridge tool sends it to the single target and returns the response.

### Multi Target

The tool forwards to multiple agents and lets the LLM choose which target to query. Each target appears as its own named option in the tool specification.

**Per target:**

| Field | Function |
|---|---|
| **tool_name** | Name of this target option as shown to the LLM, e.g. `ask_news_agent` |
| **target_agent_id** | Agent ID of the target agent, e.g. `GLOBL-ALL___-GA-TA001` |
| **description** | Short description for the LLM: when should this option be chosen |
| **− (Remove)** | Removes this target |

**+ Add Target** adds a new empty target entry.

In multi-target mode the LLM receives a set of sub-tools under the bridge tool name and selects the appropriate one based on their descriptions.

---

## Sidebar: Live Preview and Validation

**Live preview:** Shows name, mode, timeout, and target summary.

**Validation:** Shows errors when name is missing, target agent IDs are empty, or duplicates are present.

---

## How Bridge Tools Work

Bridge Tools use the Event Bus's `AGENT_QUERY` / `AGENT_QUERY_RESPONSE` message pair for synchronous inter-agent communication.

### Communication Flow

```
Calling Agent LLM
    |
    |  Invokes bridge tool: ask_ga_market_outlook("What is the DXY outlook?")
    v
Bridge Tool Handler
    |
    |  Emits: AGENT_QUERY { target_agent_id: "GLOBL-ALL___-GA-ANLYS", question: "..." }
    v
Event Bus (direct-targeted delivery)
    |
    v
Target Agent (GLOBL-ALL___-GA-ANLYS)
    |
    |  Processes query via its own LLM or logic
    |  Emits: AGENT_QUERY_RESPONSE { answer: "DXY is in a downtrend..." }
    v
Event Bus (response routed back)
    |
    v
Bridge Tool Handler (in calling agent)
    |
    |  Returns answer string as tool result
    v
Calling Agent LLM (continues reasoning with received context)
```

No routing rules are needed. The query uses direct targeting: only the agent whose `agent_id` matches `target_agent_id` receives the event.

### Key Properties

- **Synchronous from the LLM's perspective**: the tool call blocks until the response arrives or the timeout expires
- **No routing rule required**: direct targeting bypasses the routing rule system entirely
- **Transparent to the LLM**: calling a bridge tool looks identical to calling any other tool
- **Response is plain text**: the target agent's reply is returned as a string, which the LLM incorporates into its reasoning

---

## What Are Bridge Tools Used For?

Bridge Tools are primarily used to enable **hierarchical analysis** and **cross-agent context sharing**:

### AA Agent Queries a GA Agent

An AA (analysis) agent analyzing a specific pair can ask a GA (global) agent for broader market context that is not available in the pair's own snapshot data. For example:

- DXY direction and strength
- Broad market risk sentiment (risk-on / risk-off)
- Major correlated instrument bias
- Session-specific liquidity conditions

### AA Agent Queries Another Pair's AA Agent

An AA agent can query a correlated pair's AA agent to assess whether a directional signal is pair-specific noise or reflects broad USD movement. For example:

- EUR/USD AA asks GBP/USD AA: "Are you also seeing USD weakness?" — if yes, the signal is more reliable.
- AUD/USD AA asks NZD/USD AA for confirmation before posting a long signal.

### BA Agent Risk Gate

Before placing a trade, a BA (broker/action) agent can query a dedicated risk management GA agent that tracks open positions, daily drawdown, correlation exposure, and lot limits. If the risk agent rejects the query, the BA agent aborts the trade.

### Session and News Awareness

An agent can query a session-aware or news-aware agent to check for upcoming high-impact events, current session liquidity conditions, or recent news that might affect a pair.

---

## Configuration in system.json5

Bridge Tools are assigned to agents via the `allowed_tools` list and defined either inline in `tool_config` or as a top-level `bridge_tools` list.

### Method 1: Inline in `tool_config`

```json
{
  "agents": [
    {
      "agent_id": "OAPR1-EURUSD-AA-ANLYS",
      "tool_config": {
        "allowed_tools": [
          "get_candles",
          "get_indicator",
          "ask_ga_market_outlook"
        ],
        "bridge_tools": {
          "ask_ga_market_outlook": {
            "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
            "description": "Ask the global analysis agent for broader market context, DXY direction, and risk sentiment.",
            "timeout_seconds": 60
          }
        }
      }
    }
  ]
}
```

### Method 2: Top-level `bridge_tools` Array

Defining bridge tools at the top level allows them to be referenced by multiple agents.

```json
{
  "bridge_tools": [
    {
      "name": "ask_ga_market_outlook",
      "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
      "description": "Get broader market context from the GA agent including DXY, risk sentiment, and session bias.",
      "argument": "question",
      "timeout_seconds": 60
    },
    {
      "name": "ask_gbpusd_aa",
      "target_agent_id": "OAPR1-GBPUSD-AA-ANLYS",
      "description": "Query the GBP/USD AA agent for its current bias and key levels.",
      "argument": "question",
      "timeout_seconds": 45
    }
  ]
}
```

---

## Configuration Fields Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Tool name the LLM uses to call it. Must be unique across all bridge tools. Use lowercase_snake_case. |
| `target_agent_id` | string | Yes | Exact `agent_id` of the agent to query. Must match a running agent in the system. |
| `description` | string | Yes | Natural language description of what the tool does. Used in the LLM's tool definition — write it clearly so the model knows when to use it. |
| `argument` | string | No | Name of the single argument the LLM passes (default: `"question"`). |
| `timeout_seconds` | integer | No | How long to wait for a response before timing out (default: `90`). |

### Notes on `target_agent_id`

The `target_agent_id` must exactly match the `agent_id` of a configured and running agent. Agent IDs follow the format `XXXXX-YYYYYY-ZZ-NNNNN`. Examples:

- `GLOBL-ALL___-GA-ANLYS` — global analysis agent
- `OAPR1-EURUSD-AA-ANLYS` — EUR/USD analysis agent on broker OAPR1
- `OAPR1-GBPUSD-BA-TRADE` — GBP/USD broker/action agent

### Notes on `timeout_seconds`

Choose the timeout based on the target agent's typical response time:

| Target Agent Type | Suggested Timeout |
|---|---|
| Simple lookup or data agent | 15–20 seconds |
| GA agent with snapshot but no tool calls | 30–45 seconds |
| GA agent with multiple tool calls | 60–90 seconds |
| Complex multi-factor AA agent | 90–120 seconds |

If the target agent is slow and the timeout is too short, the calling LLM will receive a timeout error and may make a less-informed decision. If the timeout is too generous, it delays the calling agent's overall analysis cycle.

---

## Tool Definition Seen by the LLM

When a bridge tool is configured and assigned to an agent, the system automatically generates a tool definition entry in that agent's system prompt context. From the LLM's perspective it looks like:

```
Tool: ask_ga_market_outlook
Description: Ask the global analysis agent for broader market context,
             DXY direction, and risk sentiment.
Arguments:
  - question (string): Your specific question for the global analysis agent.
```

The LLM can invoke this at any point during its tool-use loop, the same way it would call `get_candles` or `get_indicator`.

---

## Practical Examples

### Example 1: EUR/USD AA Queries GA for DXY Context

**Scenario**: EUR/USD H1 AA agent identifies a potential long setup but is uncertain because of recent USD strength in other pairs.

**Bridge tool definition** assigned to `OAPR1-EURUSD-AA-ANLYS`:

```json
{
  "name": "ask_dxy_context",
  "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
  "description": "Ask the global agent about current DXY (US Dollar Index) strength, direction, and whether it is likely to suppress EUR/USD upside.",
  "timeout_seconds": 75
}
```

**LLM behavior**: When the EUR/USD AA agent sees a bullish setup, it calls:

```
ask_dxy_context("Is DXY currently showing strength or weakness? Is it likely to continue strengthening over the next 2–4 hours?")
```

The GA agent analyzes its own DXY snapshot and responds. If the GA says DXY is bearish, the EUR/USD AA agent has higher confidence in the long. If the GA says DXY is in a strong uptrend, the AA agent may reduce confidence or flip to no-trade.

---

### Example 2: GBP/USD Confirms USD Weakness via EUR/USD

**Scenario**: GBP/USD H1 AA agent is bullish but wants to confirm the signal reflects broad USD weakness rather than GBP-specific strength.

**Bridge tool definition** assigned to `OAPR1-GBPUSD-AA-ANLYS`:

```json
{
  "name": "ask_eurusd_bias",
  "target_agent_id": "OAPR1-EURUSD-AA-ANLYS",
  "description": "Query the EUR/USD H1 analysis agent for its current directional bias. Use this to confirm whether USD weakness is broad across majors or pair-specific.",
  "timeout_seconds": 60
}
```

**LLM behavior**:

```
ask_eurusd_bias("What is your current directional bias on EUR/USD? Are you also seeing broad USD weakness?")
```

If EUR/USD AA confirms USD is weak, GBP/USD AA increases confidence. If EUR/USD is flat or bearish (EUR-specific weakness), GBP/USD treats the signal more cautiously.

---

### Example 3: BA Agent Risk Gate Before Trade

**Scenario**: GBP/USD BA agent is about to place a long order. Before executing, it queries a risk management GA agent that tracks daily drawdown, correlation exposure, and active positions.

**Bridge tool definition** assigned to `OAPR1-GBPUSD-BA-TRADE`:

```json
{
  "name": "check_risk_clearance",
  "target_agent_id": "GLOBL-ALL___-GA-RISKM",
  "description": "Check with the risk management agent whether there is budget available to open a new trade. Provide the pair, direction, and intended lot size in your question.",
  "timeout_seconds": 30
}
```

**LLM behavior**:

```
check_risk_clearance("GBP/USD long, 0.1 lots. Is the daily risk budget still available and are there any correlation conflicts with current open positions?")
```

If the risk agent says the daily loss limit is approaching or that there is already significant long USD exposure, the BA agent does not place the order.

---

### Example 4: Multi-Target Bridge Tool for News and Session Context

**Scenario**: An AA agent needs to check either a news agent or a session agent depending on what context is needed.

```json
{
  "name": "ask_context_agent",
  "mode": "multi",
  "timeout_seconds": 45,
  "description": "Ask a context agent for session or news information.",
  "targets": [
    {
      "tool_name": "ask_news_agent",
      "target_agent_id": "GLOBL-ALL___-GA-NEWS1",
      "description": "Ask about upcoming high-impact economic events, recent news, or current fundamental sentiment."
    },
    {
      "tool_name": "ask_session_agent",
      "target_agent_id": "GLOBL-ALL___-GA-SESSN",
      "description": "Ask about the current trading session, liquidity conditions, or typical volatility for this time of day."
    }
  ]
}
```

The LLM picks `ask_news_agent` or `ask_session_agent` based on which context it currently needs.

---

### Example 5: Multiple Bridge Tools on One Agent

An AA agent can have multiple bridge tools configured simultaneously. The LLM decides which ones to call and in what order:

```json
{
  "agent_id": "OAPR1-EURUSD-AA-ANLYS",
  "tool_config": {
    "allowed_tools": [
      "get_candles",
      "get_indicator",
      "ask_ga_outlook",
      "ask_gbpusd_correlation",
      "ask_session_agent"
    ],
    "bridge_tools": {
      "ask_ga_outlook": {
        "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
        "description": "Ask the global analysis agent for macro context: DXY direction, risk sentiment, and broad USD bias.",
        "timeout_seconds": 75
      },
      "ask_gbpusd_correlation": {
        "target_agent_id": "OAPR1-GBPUSD-AA-ANLYS",
        "description": "Query the GBP/USD H1 agent for its current bias to confirm or deny broad USD direction as opposed to pair-specific EUR moves.",
        "timeout_seconds": 60
      },
      "ask_session_agent": {
        "target_agent_id": "GLOBL-ALL___-GA-SESSN",
        "description": "Ask about the current trading session, liquidity conditions, and any upcoming news events in the next 2 hours.",
        "timeout_seconds": 20
      }
    }
  }
}
```

---

## Assigning Bridge Tools to Agents

A bridge tool definition alone does not activate the tool for any agent. It must also appear in the agent's `allowed_tools` list. If the tool name is not in `allowed_tools`, the LLM does not see it.

Steps to activate a bridge tool for an agent:

1. Define the bridge tool (in the Bridge Tools editor or directly in `system.json5`)
2. Open Agent Config for the target agent
3. Add the bridge tool's `name` to the agent's `allowed_tools` list
4. Save the agent config
5. Restart or reload the agent

---

## Error Handling

| Situation | What the LLM Receives |
|---|---|
| Target agent responds successfully | The full response text from the target agent |
| Timeout exceeded | `"[Bridge tool timeout: no response from AGENT_ID within N seconds]"` |
| Target agent not running | `"[Bridge tool error: target agent AGENT_ID is not available]"` |
| Target agent returns an error | `"[Bridge tool error: AGENT_ID reported: <error message>]"` |

The calling agent's system prompt should describe how to handle these cases. A typical instruction is: "If a bridge tool returns a timeout or error, proceed with a conservative assessment based on available snapshot data alone."

---

## Performance Considerations

- Each bridge tool call adds the target agent's full processing time as latency to the calling agent's analysis cycle.
- Avoid chaining: do not create scenarios where Agent A calls Agent B which calls Agent C — this creates cascading latency and risks circular deadlock.
- Use bridge tools only when the external context is meaningfully likely to change the decision. If the snapshot already contains sufficient data, a bridge call adds latency without value.
- For time-sensitive high-frequency setups (M5 agents), bridge tools may be too slow. They are better suited to H1/H4/D1 agents where analysis cycles are longer.

---

## Relationship to Routing Rules

Bridge Tools use **direct targeting** and do not pass through the routing rule system. The `target_agent_id` is specified explicitly in the tool configuration. This is intentional:

- Bridge Tool queries are point-to-point
- They return a value synchronously (from the LLM's perspective)
- They bypass event routing, filtering, and transformation pipelines
- The target agent receives the query regardless of any routing rules that might otherwise block events

---

## Security and Scope

- A bridge tool can only reach the agent explicitly named in its `target_agent_id`. There is no dynamic discovery.
- The LLM provides only the question text at runtime — it cannot redirect the tool to a different agent or change the target.
- The target agent's response may contain analysis data. Do not expose sensitive account or risk information through bridge responses unless it is appropriate for the calling agent to receive it.

---

## Typical Workflow

1. Click **New Empty Tool**
2. Enter a **Name** (snake_case, descriptive — this is what the LLM sees)
3. Write a **Description** — be specific about what questions to ask and when the tool should be used
4. Choose **mode**: Single or Multi Target
5. Enter the **target_agent_id** (must be an existing, running agent)
6. Write a clear **Question Description** to guide the LLM on how to phrase the question
7. Adjust **Timeout** based on expected response time of the target agent
8. Click **Save As New**
9. Open Agent Config for the agent that should use this tool
10. Add the bridge tool's name to the agent's **Allowed Tools** list

---

## See Also

- [Agent Config](ui.config.agent_config.en.md) — Full agent configuration including allowed tools
- [Event Routing](ui.config.event_routing.en.md) — Rule-based event routing (separate from bridge tool direct targeting)
- [System Config](ui.config.system_config.en.md) — Editing system.json5 directly
- [Snapshot Config](ui.config.snapshot_config.en.md) — How agent snapshots are assembled before the LLM is called
- [Snapshot Helper Functions](snapshot-helper-functions.en.md) — Python helpers available in transform scripts
