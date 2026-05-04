# openforexai/config — Configuration Loading & ConfigService

Handles all configuration loading and the runtime distribution of agent configs via the EventBus.

## Files

| File | Purpose |
|---|---|
| `config_service.py` | `ConfigService` — EventBus agent that answers config requests |
| `json_loader.py` | JSON loader with `${ENV_VAR:-default}` substitution |
| `../../config/RunTime/agent_tools.json5` | Per-agent tool approval modes and tier configuration |
| `../../config/RunTime/event_routing.json5` | EventBus routing rules |

---

## `config_service.py` — ConfigService

The ConfigService is a special GA agent (`SYSTM_ALL..._GA_CFGSV`) that answers `AGENT_CONFIG_REQUESTED` events. This is how all agents receive their configuration at startup.

### Why an EventBus Handshake Instead of Direct Injection?

1. **`Agent.__init__` stays dependency-free** — no circular imports, no constructor parameters besides `(agent_id, bus, data_container, repository)`
2. **Config can be hot-reloaded** — send a new `AGENT_CONFIG_REQUESTED` to re-initialise an agent
3. **Central config management** — one service owns all config distribution
4. **Testability** — agents can be tested with any config by publishing a mock response

### Bootstrap Sequence

```
Agent.start()
    1. agent publishes: AGENT_CONFIG_REQUESTED {agent_id: "OAPR1_EURUSD_AA_ANLYS"}
       └── routing rule "config_request_to_service" → ConfigService inbox

ConfigService._handle_request()
    2. looks up agents["OAPR1_EURUSD_AA_ANLYS"] in system.json5
    3. resolves LLM and broker module configs
    4. publishes: AGENT_CONFIG_RESPONSE (direct → requesting agent)
       payload: {config: {...}, modules: {llm: {...}, broker: {...}}}

Agent._wait_for_config()
    5. receives AGENT_CONFIG_RESPONSE (timeout: 30s)
    6. initialises LLM, broker, ToolDispatcher from payload
    7. enters run loop
```

### Response Payload

```json
{
  "agent_id": "OAPR1_EURUSD_AA_ANLYS",
  "config": {
    "type": "AA",
    "llm": "azure_openai",
    "broker": "oanda",
    "pair": "EURUSD",
    "system_prompt": "...",
    "tool_config": {...}
  },
  "modules": {
    "llm": {"adapter": "azure_openai", "api_key": "...", "endpoint": "..."},
    "broker": {"adapter": "oanda", "api_key": "...", "account_id": "..."}
  }
}
```

---

## `json_loader.py` — JSON Config Loader

Loads JSON files with recursive **environment variable substitution**.

### Substitution Syntax

| Pattern | Behaviour |
|---|---|
| `${VAR_NAME}` | Replaced with env var value; raises error if not set |
| `${VAR_NAME:-default}` | Replaced with env var value, or `"default"` if not set |

### Example

`config/modules/llm/azure_openai.json5`:
```json
{
  "adapter": "azure_openai",
  "api_key": "${AZURE_OPENAI_API_KEY}",
  "endpoint": "${AZURE_OPENAI_ENDPOINT}",
  "deployment": "${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}",
  "api_version": "${AZURE_OPENAI_API_VERSION:-2024-02-01}"
}
```

If `AZURE_OPENAI_DEPLOYMENT` is not set, the value `"gpt-4o"` is used. If `AZURE_OPENAI_API_KEY` is not set and no default is provided, an error is raised at startup.

Substitution is applied recursively to all string values at any nesting level.

---

## `config/RunTime/agent_tools.json5` — Tool Approval Configuration

Configures per-agent tool approval modes and context budget tiers. This file allows fine-grained control over when tools require human/supervisor approval.

### Structure

```json
{
  "defaults": {
    "place_order":    {"approval_mode": "supervisor"},
    "close_position": {"approval_mode": "supervisor"},
    "raise_alarm":    {"approval_mode": "direct"}
  },
  "agents": {
    "OAPR1_ALL..._BA_TRADE": {
      "tool_overrides": {
        "place_order": {"approval_mode": "direct"}
      }
    }
  }
}
```

Agent-level overrides take precedence over defaults.

---

## `config/RunTime/event_routing.json5` — Routing Rules

Defines how events flow between agents on the EventBus. See [`messaging/README.md`](../messaging/README.md) for the full routing documentation.

### Communication Topology Summary

```
AA agent  ──analysis_result──►  BA agent (same broker)
AA agent  ──signal_generated──►  BA agent (same broker)
BA agent  ──signal_approved──►  AA agents (same broker)
BA agent  ──prompt_updated──►  AA agents (same broker)
GA agent  ──prompt_updated──►  ALL agents (broadcast)
Any      ──risk_breach──►  BA agent (same broker)
```

Infrastructure events (`m5_candle_available`, `account_status_updated`, etc.) route to `@handlers` (DataContainer and BrokerBase legacy subscribers), bypassing agent queues.

### Hot-Reload

The routing table can be reloaded without restarting the system:
```bash
curl -X POST http://127.0.0.1:8765/routing/reload
```



