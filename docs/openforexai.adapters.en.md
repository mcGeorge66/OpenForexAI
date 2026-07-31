[Back to Documentation Index](README.md)

# openforexai/adapters — Pluggable Adapters

Concrete implementations of the abstract ports defined in `openforexai/ports/`. This package provides all external integrations: LLM providers, broker APIs, and database backends.

## Structure

```
adapters/
├── llm/
│   ├── __init__.py      # Self-registration of all LLM adapters
│   ├── base.py          # Shared retry decorator (llm_retry)
│   ├── anthropic.py     # Anthropic Claude (native tool_use API)
│   ├── openai.py        # OpenAI-compatible: OpenAI, Azure AI Foundry (v1, via base_url), any OpenAI-compatible API
│   ├── lmstudio.py      # LM Studio (local) — subclasses openai.py
│   └── ollama.py        # Ollama (local) — subclasses openai.py
├── brokers/
│   ├── __init__.py      # Self-registration of all broker adapters
│   ├── base.py          # BrokerBase — shared M5 streaming + account polling
│   ├── oanda.py         # OANDA v20 REST API
│   └── mt5.py           # MetaTrader 5 (Windows only)
└── database/
    ├── __init__.py      # Self-registration of database adapters
    ├── sqlite.py        # Async SQLite (aiosqlite)
    └── postgresql.py    # PostgreSQL (asyncpg)
```

---

## Self-Registration Pattern

All adapters register themselves at **import time** via `PluginRegistry`. This happens automatically when `bootstrap.py` imports the adapter packages:

```python
# adapters/llm/__init__.py
from openforexai.registry.plugin_registry import PluginRegistry
from openforexai.adapters.llm.anthropic import AnthropicLLMProvider
from openforexai.adapters.llm.openai import OpenAILLMProvider
from openforexai.adapters.llm.lmstudio import LMStudioLLMProvider
from openforexai.adapters.llm.ollama import OllamaLLMProvider

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai", OpenAILLMProvider)
PluginRegistry.register_llm_provider("lmstudio", LMStudioLLMProvider)
PluginRegistry.register_llm_provider("ollama", OllamaLLMProvider)
```

The `bootstrap.py` then creates live instances via `adapter_class.from_config(cfg)`.

---

## LLM Adapters (`adapters/llm/`)

All LLM adapters implement `AbstractLLMProvider` from `ports/llm.py`.

### Canonical Tool Format

All adapters accept tools in the internal **Anthropic-style** `input_schema` format and convert to the provider's own wire format internally. The agent and tools never see provider-specific formats.

```python
# Canonical ToolSpec (internal format)
{
    "name": "get_candles",
    "description": "Retrieve OHLCV candle data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "timeframe": {"type": "string"},
            "count": {"type": "integer"}
        },
        "required": ["timeframe"]
    }
}
```

### `base.py` — Retry Decorator

`llm_retry` is a shared exponential backoff decorator applied to all `complete*` methods. It retries on transient errors (rate limits, timeouts) without the caller needing to handle retries.

### `anthropic.py`

- Uses the Anthropic Python SDK
- Supports native `tool_use` API with `input_schema` format (no conversion needed)
- Config keys: `api_key`, `model` (e.g. `claude-opus-4-5`)

### `openai.py`

- Uses the plain OpenAI Python SDK client (`AsyncOpenAI`), pointed at any
  OpenAI-compatible `base_url` — real OpenAI, Azure AI Foundry's `/openai/v1`
  endpoint, LM Studio, Ollama, or anything else implementing the same API.
  There is no separate Azure adapter: Azure's v1 API dropped the `api-version`
  requirement and the need for a dedicated `AzureOpenAI` client.
- Converts `input_schema` → OpenAI `function` / `tool` format
- Config keys: `api_key`, `model`, optional `base_url` (omit for real OpenAI;
  set to `https://<resource>.services.ai.azure.com/openai/v1` for Azure, or a
  local server URL for LM Studio/Ollama), `reasoning_effort`, `verbosity`,
  `timeout_seconds`, `transcript_enabled` + `transcript_path`
- `lmstudio.py`/`ollama.py` are thin subclasses that just set a local default
  `base_url`

### Adding a New LLM Provider

1. Create `adapters/llm/<name>.py` implementing `AbstractLLMProvider`
2. Register in `adapters/llm/__init__.py`
3. Create `config/modules/llm/<name>.json5` with `"adapter": "<name>"`
4. Reference in `config/system.json5` under `modules.llm`

---

## Broker Adapters (`adapters/brokers/`)

All broker adapters implement `AbstractBroker` from `ports/broker.py`.

### `base.py` — BrokerBase

Shared base class providing:
- **`_m5_loop()`** — Background asyncio task: polls recent M5 candles, publishes `M5_CANDLE_UPDATE` events for DB/chart state and delayed `M5_AGENT_TRIGGER` events for AA wakeups. Transient errors (502/503/504) are logged as `WARNING` without traceback.
- **`_account_poll_loop()`** — Background asyncio task: polls account status periodically, publishes `ACCOUNT_STATUS_UPDATED` events.
- Candle normalisation helpers (OHLCV → `Candle` model)

### `oanda.py` — OANDA Adapter

Full implementation of the OANDA v20 REST API:
- Candle fetching (M5 primary, back-fill on startup)
- Order placement: market, limit, stop orders with SL/TP
- Position management: open/close/modify
- Account status: balance, equity, margin, NAV
- Order book: pending orders and their positions
- Practice and live account support

Config keys (in `config/modules/broker/oanda.json5`):
```json
{
  "adapter": "oanda",
  "api_key": "${OANDA_API_KEY}",
  "account_id": "${OANDA_ACCOUNT_ID}",
  "practice": "${OANDA_PRACTICE:-true}",
  "short_name": "OAPR1"
}
```

### `mt5.py` — MetaTrader 5 Adapter

Windows-only adapter using the `MetaTrader5` Python package. Provides equivalent functionality to the OANDA adapter for MT5-connected brokers.

### Adding a New Broker

1. Create `adapters/brokers/<name>.py` subclassing `BrokerBase`
2. Register in `adapters/brokers/__init__.py`
3. Create `config/modules/broker/<name>.json5`
4. Reference in `config/system.json5` under `modules.broker`

---

## Database Adapters (`adapters/database/`)

All database adapters implement `AbstractRepository` from `ports/database.py`.

### Migration Tracking

Migrations are tracked in a `schema_migrations` table. The adapter runs only unapplied SQL files from `migrations/` on startup. Existing databases are bootstrapped automatically via `_bootstrap_migration_history()` which detects already-applied migrations by inspecting the schema.

### `sqlite.py` — SQLite Backend

- Uses `aiosqlite` for non-blocking async I/O
- **Candle storage**: `INSERT OR REPLACE` for upsert semantics — duplicate candles are silently replaced
- **Connection**: single connection with `WAL` journal mode for concurrent reads
- Default path: `./data/openforexai.db`

### `postgresql.py` — PostgreSQL Backend

- Uses `asyncpg` for high-performance async I/O
- Suitable for production deployments or multi-process access

### Selecting a Backend

Set via environment variable:
```bash
OPENFOREXAI_DB_BACKEND=sqlite      # default
OPENFOREXAI_DB_BACKEND=postgresql
```

