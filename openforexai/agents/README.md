# openforexai/agents — Agent System

The core agent implementation. All agent types (Analysis Agent `AA`, Broker Agent `BA`, Global Agent `GA`) use a single parameterised `Agent` class. Behaviour is entirely determined by configuration — not by subclassing.

## Files

| File | Purpose |
|---|---|
| `agent.py` | Single `Agent` class — the only agent implementation |
| `optimization/` | Backtester, pattern detector, prompt evolver |
| `supervisor/` | Risk engine, correlation checker |
| `technical_analysis/` | Analysis helper tools and AA prompt templates |
| `trading/` | Trading prompt templates for BA agents |

---

## `agent.py` — The Agent Class

### Design Philosophy

All three agent roles share one class:

| Role | ID suffix | Behaviour |
|---|---|---|
| **AA** — Analysis Agent | `_AA_` | Reads market data, computes indicators, publishes analysis |
| **BA** — Broker Agent | `_BA_` | Executes trades, manages positions, monitors risk |
| **GA** — Global Agent | `_GA_` | System-wide coordination, config, optimization |

The role label is purely informational. The actual behaviour is controlled by three things in `config/system.json`:
1. **`system_prompt`** — what the LLM is instructed to do
2. **`event_triggers`** — which EventBus events wake the agent
3. **`tool_config.allowed_tools`** — which tools the agent can call

### Bootstrap Sequence

The agent uses a two-phase boot to keep `__init__` dependency-free:

```
Agent.__init__(agent_id, bus, data_container, repository)
    └─ registers inbox queue with EventBus

Agent.start()
    1. Publishes AGENT_CONFIG_REQUESTED to EventBus
    2. Waits up to 30s for AGENT_CONFIG_RESPONSE from ConfigService
    3. Initialises LLM, broker, ToolDispatcher from config
    4. Enters run loop
```

This avoids circular imports and lets the ConfigService manage all config loading.

### Run Loop

The agent's run loop processes two sources of activation:

```
┌─────────────────────────────────────────────┐
│              Agent Run Loop                 │
│                                             │
│  inbox (asyncio.Queue)                      │
│    ├── AGENT_CONFIG_RESPONSE → bootstrap    │
│    ├── AGENT_QUERY → _run_cycle() directly  │
│    └── any event in event_triggers          │
│           → _run_cycle()                    │
│                                             │
│  timer (if enabled)                         │
│    └── every interval_seconds → _run_cycle()│
└─────────────────────────────────────────────┘
```

**`_run_cycle(trigger, payload, ...)`** is the core method:
1. Builds a user message from the triggering event payload
2. Calls `_run_with_tools(system_prompt, user_message)` — the LLM tool-use loop
3. For `AGENT_QUERY` triggers, publishes `AGENT_QUERY_RESPONSE` with the final text

### LLM Tool-Use Loop

```
_run_with_tools(system_prompt, user_message)
    turn 0:  LLM(system, [user_msg])
    turn 1+: if stop_reason == "tool_use":
               execute tool calls via ToolDispatcher
               append assistant + tool_result turns to messages
               call LLM again
    exit:    stop_reason == "end_turn" OR max_tool_turns reached
```

Token usage is tracked across turns. When the context budget fills up, `ToolDispatcher` automatically restricts which tools are visible (see context tiers in `tools/dispatcher.py`).

### Agent Query Feature

Any agent can be queried externally via the Management API:

```
POST /agents/{agent_id}/ask  →  EventBus(AGENT_QUERY)
                                    │
                              Agent._run_message_loop()
                              detects AGENT_QUERY (bypasses event_triggers)
                                    │
                              _run_cycle(trigger="agent_query")
                                    │
                              publishes AGENT_QUERY_RESPONSE
                                    │
                              Management API resolves Future → HTTP response
```

No config changes are needed — all agents handle `AGENT_QUERY` automatically.

### Config Keys (`system.json → agents.<agent_id>`)

| Key | Type | Description |
|---|---|---|
| `type` | `"AA"` \| `"BA"` \| `"GA"` | Label only — no code effect |
| `llm` | `str` | LLM module name (RuntimeRegistry key) |
| `broker` | `str \| null` | Broker module name — omit for GA agents |
| `pair` | `str \| null` | Currency pair — AA agents only |
| `timer.enabled` | `bool` | Enable periodic activation |
| `timer.interval_seconds` | `int` | Timer interval |
| `event_triggers` | `list[str]` | EventType values that wake the agent |
| `system_prompt` | `str` | Full LLM system prompt |
| `tool_config.allowed_tools` | `list[str]` | Tool names this agent may call |
| `tool_config.context_tiers` | `dict` | Token% → tier name mapping |
| `tool_config.tier_tools` | `dict` | Tier name → allowed tool list |
| `tool_config.max_tool_turns` | `int` | Max LLM turns per cycle |
| `tool_config.max_tokens` | `int` | Max tokens per LLM call |

---

## Subdirectories

### `optimization/`

Prompt and strategy optimization components:

- **`backtester.py`** — Replays historical M5 data to evaluate prompt candidates
- **`pattern_detector.py`** — Detects and classifies recurring trade patterns in history
- **`prompt_evolver.py`** — Evolves system prompts using a genetic algorithm based on backtest results

### `supervisor/`

Risk management components used by Broker Agents:

- **`risk_engine.py`** — Stateless risk checker; validates trade signals against configured limits (drawdown, exposure, pair correlation)
- **`correlation_checker.py`** — Computes pair correlation matrices to enforce portfolio diversification constraints

### `technical_analysis/`

Support for Analysis Agents:

- **`analysis_tools.py`** — Helper functions for market analysis (trend detection, S/R identification)
- **`prompt_templates.py`** — Pre-built prompt fragments for AA system prompts

### `trading/`

Support for Broker Agents:

- **`prompt_templates.py`** — Pre-built prompt fragments for BA and GA system prompts

---

## Adding a New Agent

No code changes are needed. Add an entry in `config/system.json`:

```json
"MY_BR_EURUSD_AA_MYAG": {
  "type": "AA",
  "llm": "azure_openai",
  "broker": "oanda",
  "pair": "EURUSD",
  "timer": {"enabled": true, "interval_seconds": 300},
  "event_triggers": ["m5_candle_available"],
  "system_prompt": "You are ...",
  "tool_config": {
    "allowed_tools": ["get_candles", "calculate_indicator"],
    "max_tool_turns": 8,
    "max_tokens": 4096
  }
}
```

The agent is created automatically by `bootstrap.py` on next start.
