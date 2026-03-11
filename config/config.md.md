[Back to Documentation Index](../docs/README.md)

# config — System Configuration

Central configuration files for OpenForexAI. The directory **[config]** is the **single source of truth** for all system settings.

## Structure

```
config/
├── system.json5              # Central config — agents, modules, database, system
├── RunTime/
│   ├── agent_tools.json5     # Tool permissions, tiers, bridge tools
│   └── event_routing.json5   # EventBus routing rules (hot-reloadable)
└── modules/
    ├── llm/                  # Config files for the different language models
    │   ├── azure_openai.json5
    │   ├── openai.json5
    │   └── anthropic_claude.json5
    └── broker/               # Config files for different broker
        ├── oanda.json5
        └── mt5.json5
```

---

## `system.json5` — Central Configuration

All parameters live here. Module-specific connection details (API keys, endpoints) are referenced by name and stored in `config/modules/`.

### Top-Level Sections

#### `system`
```json
"system": {
  "log_level": "${OPENFOREXAI_LOG_LEVEL:-INFO}",
  "management_api": {
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

#### `data`
```json
"data": {
  "rolling_weeks": 4,
  "timeframes": ["M5"],
  "indicator_cache_ttl_seconds": 30
}
```
- `rolling_weeks`: How many weeks of M5 history to back-fill on startup (~8,064 bars per 4 weeks)
- `timeframes`: Only `["M5"]` — all higher TFs are derived by the resampler

#### `database`
```json
"database": {
  "backend": "${OPENFOREXAI_DB_BACKEND:-sqlite}",
  "sqlite_path": "${OPENFOREXAI_DB_PATH:-./data/openforexai.db}",
  "pool_size": 5
}
```

#### `modules`
Declares available LLM and broker module config file paths:
```json
"modules": {
  "llm": {
    "azure_openai": "config/modules/llm/azure_openai.json5",
    "openai":       "config/modules/llm/openai.json5"
  },
  "broker": {
    "oanda": "config/modules/broker/oanda.json5"
  }
}
```
Agents reference modules by name (e.g., `"llm": "azure_openai"`). The config loader resolves the name to the file path, then loads the module config.

#### `agents`
One entry per running agent:
```json
"agents": {
  "OAPR1_EURUSD_AA_ANLYS": {
    "type": "AA",
    "llm": "azure_openai",
    "broker": "oanda",
    "pair": "EURUSD",
    "timer": {"enabled": true, "interval_seconds": 300},
    "event_triggers": ["m5_candle_available", "prompt_updated", "agent_query"],
    "AnyCandle": 3,
    "system_prompt": "...",
    "tool_config": {
      "allowed_tools": ["get_candles", "calculate_indicator", "get_order_book", "raise_alarm", "trigger_sync"],
      "context_tiers": {"0": "all", "85": "safety"},
      "tier_tools": {
        "all":    ["get_candles", "calculate_indicator", "get_order_book", "raise_alarm", "trigger_sync"],
        "safety": ["raise_alarm"]
      },
      "max_tool_turns": 10,
      "max_tokens": 4096
    }
  }
}
```

---

## `modules/llm/` — LLM Module Configs

Each file contains connection details for one LLM provider. Values use `${ENV_VAR:-default}` substitution.

### `azure_openai.json5`
```json
{
  "adapter": "azure_openai",
  "api_key": "${AZURE_OPENAI_API_KEY}",
  "endpoint": "${AZURE_OPENAI_ENDPOINT}",
  "deployment": "${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}",
  "api_version": "${AZURE_OPENAI_API_VERSION:-2024-02-01}"
}
```

### `openai.json5`
```json
{
  "adapter": "openai",
  "api_key": "${OPENAI_API_KEY}",
  "model": "${OPENAI_MODEL:-gpt-4o}"
}
```

### `anthropic_claude.json5`
```json
{
  "adapter": "anthropic",
  "api_key": "${ANTHROPIC_API_KEY}",
  "model": "${ANTHROPIC_MODEL:-claude-opus-4-5}"
}
```

---

## `modules/broker/` — Broker Module Configs

### `oanda.json5`
```json
{
  "adapter": "oanda",
  "api_key": "${OANDA_API_KEY}",
  "account_id": "${OANDA_ACCOUNT_ID}",
  "practice": "${OANDA_PRACTICE:-true}",
  "short_name": "${OANDA_SHORT_NAME:-OAPR1}",
  "background_tasks": {
    "account_poll_interval_seconds": 60,
    "sync_interval_seconds": 60,
    "request_agent_reasoning": false
  }
}
```
`short_name` is the 5-character identifier used in agent IDs and database table names (e.g., `OAPR1_EURUSD_M5`).
`background_tasks` controls broker polling/sync frequency per broker module.

### `mt5.json5`
```json
{
  "adapter": "mt5",
  "login": "${MT5_LOGIN}",
  "password": "${MT5_PASSWORD}",
  "server": "${MT5_SERVER}",
  "short_name": "${MT5_SHORT_NAME:-MT5B1}",
  "background_tasks": {
    "account_poll_interval_seconds": 60,
    "sync_interval_seconds": 60,
    "request_agent_reasoning": false
  }
}
```

---

## Environment Variables

Never put secrets directly in JSON files. Use environment variables or a `.env` file (not committed to git):

```bash
# .env
AZURE_OPENAI_API_KEY=sk-...
AZURE_OPENAI_ENDPOINT=https://myresource.openai.azure.com/
OANDA_API_KEY=...
OANDA_ACCOUNT_ID=...
OANDA_PRACTICE=true
OPENFOREXAI_LOG_LEVEL=INFO
OPENFOREXAI_DB_BACKEND=sqlite
```

---

## Adding a New Agent

Add an entry to `system.json5 → agents` with a valid agent ID. No code changes needed. The system creates the agent automatically on next startup.

**Agent ID format:** `[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]`
- Example: `OAPR1_GBPUSD_AA_ANLYS` — Analysis Agent for GBP/USD on OANDA Practice
