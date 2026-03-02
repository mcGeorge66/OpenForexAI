# OpenForexAI — Developer Reference

Autonomous multi-agent LLM-based forex trading system.
Python 3.11+, fully async, hexagonal architecture.

---

## Architecture Overview

```
config/system.json
       │
  bootstrap.py ──► PluginRegistry (import-time self-registration)
       │            RuntimeRegistry (live instances)
       ├── Database (AbstractRepository)
       ├── LLM adapters (AbstractLLMProvider)
       ├── Broker adapters (AbstractBroker)
       ├── EventBus + RoutingTable
       ├── DataContainer (shared market data)
       ├── ConfigService (answers AGENT_CONFIG_REQUESTED)
       ├── ManagementServer (FastAPI, port 8765)
       └── Agent × N  (all same class, config-driven)
```

The system runs inside a single `asyncio.TaskGroup`: the event bus dispatch loop, config service, management API, and all agents run concurrently.

---

## Directory Structure

```
openforexai/
  agents/
    agent.py                  # Single Agent class (AA / BA / GA — cosmetic only)
    optimization/             # Backtester, pattern detector, prompt evolver
    supervisor/               # Risk engine, correlation checker
    technical_analysis/       # Analysis tools and prompt templates
    trading/                  # Trading prompt templates
  adapters/
    brokers/base.py           # BrokerBase (background M5 streaming, account poll)
    brokers/oanda.py          # OANDA REST adapter
    brokers/mt5.py            # MT5 adapter (Windows only)
    database/sqlite.py        # SQLite repository
    database/postgresql.py    # PostgreSQL repository
    llm/anthropic.py          # Anthropic Claude adapter
    llm/openai.py             # OpenAI adapter
    llm/azure.py              # Azure OpenAI adapter
    llm/base.py               # Shared retry decorator (llm_retry)
  config/
    config_service.py         # Answers AGENT_CONFIG_REQUESTED events
    json_loader.py            # Loads JSON with ${VAR:-default} substitution
    agent_tools.json          # Tool approval / tag config (per-agent overrides)
    event_routing.json        # Routing rules for the EventBus
  data/
    container.py              # DataContainer — rolling M5 store + resampler
    resampler.py              # M5 → M15/M30/H1/H4/D1 on-demand
    indicators.py             # Technical indicator calculations
    indicator_tools.py        # Tool-facing indicator dispatcher
    correlation.py            # Pair correlation analysis
    normalizer.py             # Data normalisation utilities
  management/
    api.py                    # FastAPI REST endpoints
    server.py                 # Uvicorn wrapper (non-blocking asyncio task)
  messaging/
    bus.py                    # EventBus — rule-based async pub/sub
    routing.py                # RoutingTable (loaded from event_routing.json)
    agent_id.py               # Agent ID parsing helpers
  models/                     # Pydantic v2 domain models
    messaging.py              # AgentMessage, EventType enum
    market.py                 # Candle, Tick, MarketSnapshot
    trade.py                  # Position, TradeOrder, TradeResult, OrderBookEntry
    account.py                # AccountStatus
    agent.py                  # AgentDecision
    analysis.py               # Analysis results
    risk.py                   # Risk models
    optimization.py           # BacktestResult, PromptCandidate, TradePattern
    monitoring.py             # MonitoringEvent, MonitoringEventType
  monitoring/
    bus.py                    # MonitoringBus — fire-and-forget observability
  ports/                      # Abstract interfaces (hexagonal ports)
    llm.py                    # AbstractLLMProvider, LLMResponseWithTools, ToolCall, ToolResult
    broker.py                 # AbstractBroker
    database.py               # AbstractRepository
    monitoring.py             # AbstractMonitoringBus
    data_feed.py              # AbstractDataFeed
  registry/
    plugin_registry.py        # Class registry — adapters self-register at import
    runtime_registry.py       # Instance registry — live LLM/broker instances
  tools/                      # LLM-callable tool plugins
    base.py                   # BaseTool ABC + ToolContext dataclass
    registry.py               # ToolRegistry
    dispatcher.py             # ToolDispatcher (approval + context budget gating)
    config_loader.py          # Loads agent_tools.json
    account/                  # get_account_status, get_open_positions
    market/                   # get_candles, calculate_indicator
    orderbook/                # get_order_book
    trading/                  # place_order, close_position
    system/                   # raise_alarm, trigger_sync
  utils/
    logging.py                # structlog setup, get_logger()
    retry.py                  # Exponential backoff decorator
    time_utils.py             # UTC helpers, forex session detection
    metrics.py                # Performance metrics

config/
  system.json                 # Central config — one source of truth
  modules/llm/                # Per-LLM module configs (referenced by name)
  modules/broker/             # Per-broker module configs (referenced by name)

migrations/                   # Raw SQL migration files (001_initial_schema.sql, …)
scripts/                      # CLI utilities (db_migrate, export_prompts, run_backtest)
tests/
  unit/                       # Fast, no I/O
  integration/                # Per-agent integration tests
  e2e/                        # Full-cycle end-to-end test
```

---

## Key Architectural Decisions

### 1. Single Agent Class
All agent types (Analysis Agent `AA`, Broker Agent `BA`, Global Agent `GA`) use the same `Agent` class. The type label is purely informational. Behaviour is entirely determined by the agent's config (system prompt, event triggers, tools, timer interval).

### 2. Config-Driven Bootstrap (EventBus handshake)
Agents receive their config at startup via the EventBus, not from direct injection:
1. Agent sends `AGENT_CONFIG_REQUESTED`
2. `ConfigService` replies with `AGENT_CONFIG_RESPONSE` (direct, targeted)
3. Agent initialises LLM, broker, tools from the payload

This keeps `Agent.__init__` dependency-free (only bus + data_container + repository).

### 3. Hexagonal Ports & Adapters
- `openforexai/ports/` — abstract interfaces only, no implementation
- `openforexai/adapters/` — concrete implementations
- `PluginRegistry` — adapters self-register at import time (`adapters/brokers/__init__.py`, etc.)
- `RuntimeRegistry` — holds live instances created by bootstrap

### 4. Canonical ToolSpec Format (Anthropic-style)
All tools use the Anthropic `input_schema` format internally. Each LLM adapter converts to its own wire format. The agent and tool dispatcher never know which LLM is backing them.

### 5. Context Budget Tiers
As the LLM token budget fills up, the ToolDispatcher restricts which tools are visible. Configured per-agent in `system.json` under `tool_config.context_tiers` and `tool_config.tier_tools`. Typical ladder: `all → decision → safety`.

### 6. EventBus Routing Rules
`openforexai/config/event_routing.json` controls who receives what events. Routing patterns use agent ID segments with wildcards (`*`) and template substitution (`{sender.broker}`). Hot-reload is supported via `ROUTING_RELOAD_REQUESTED` event. Unmatched events are dropped with a warning.

### 7. Data Primary Timeframe: M5
Only M5 candles are fetched from brokers (every 5 minutes). All higher timeframes (M15, M30, H1, H4, D1) are derived on-demand by the resampler inside `DataContainer`. No separate API calls for higher timeframes.

### 8. Table Naming Convention
`{broker_short_name}_{pair}_{timeframe}` — e.g. `OAPR1_EURUSD_M5`. The broker's `short_name` property (not the module name) is the key used throughout the system.

---

## Agent ID Format

```
[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]
```

- `BROKER`: 5-char broker+account identifier, e.g. `OAPR1` (OANDA Practice 1)
- `PAIR`: 6-char currency pair or `ALL...` for broker-wide agents
- `TYPE`: `AA` (Analysis), `BA` (Broker), `GA` (Global)
- `NAME`: 1–5 char descriptive name

Examples:
- `OAPR1_EURUSD_AA_ANLYS` — Analysis Agent, OANDA Practice, EURUSD
- `OAPR1_ALL..._BA_TRADE` — Broker Agent, OANDA Practice, all pairs
- `SYSTM_ALL..._GA_CFGSV` — Global ConfigService agent

---

## Event Types & Routing Topology

Key events in `openforexai/models/messaging.py` `EventType`:

| Event | Direction |
|---|---|
| `m5_candle_available` | Broker adapter → `@handlers` (DataContainer) |
| `agent_config_requested` | Any agent → ConfigService (`SYSTM_*_GA_CFGSV`) |
| `agent_config_response` | ConfigService → requesting agent (direct) |
| `analysis_result` | AA → BA (same broker) |
| `signal_generated` | AA → BA (same broker); also triggers supervisor approval |
| `signal_approved` / `signal_rejected` | BA → AA (same broker) |
| `risk_breach` | Any → BA (same broker) |
| `prompt_updated` | BA → AAs (same broker); GA → all agents |
| `order_book_sync_discrepancy` | Any → BA (same broker) |

Communication topology:
- `AA ↔ BA` within same broker
- `BA ↔ GA` cross-broker
- `GA → *` broadcast capable

---

## Tool System

Tools live in `openforexai/tools/` and must subclass `BaseTool`:

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "..."
    input_schema = {"type": "object", "properties": {...}}

    async def execute(self, arguments: dict, context: ToolContext) -> Any:
        ...
```

Register in `openforexai/tools/__init__.py` `DEFAULT_REGISTRY`.

**Approval modes** (set per-tool per-agent in config):
- `"direct"` — always execute (default)
- `"supervisor"` — publish `signal_generated`, wait for `signal_approved/rejected` (15 s timeout)
- `"human"` — blocks for Management API approval (not yet implemented)

---

## LLM Adapter Pattern

Each adapter implements `AbstractLLMProvider` and registers itself:

```python
# In openforexai/adapters/llm/__init__.py
PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
```

`from_config(cfg: dict)` is the only sanctioned factory. The `cfg` dict comes from `config/modules/llm/<name>.json`.

LLM adapters must implement:
- `complete(system_prompt, user_message, ...)` — simple completion
- `complete_structured(system_prompt, user_message, response_schema)` — Pydantic-typed
- `complete_with_tools(system_prompt, messages, tools, ...)` — tool-use loop turn
- `assistant_message_with_tools(content, tool_calls)` — build assistant turn dict
- `tool_result_message(tool_results)` — build tool-result turn dict

---

## Configuration

### Environment Variables
`${VAR_NAME}` or `${VAR_NAME:-default}` substitution is applied to all JSON config files by `json_loader.py`. Secrets always live in `.env` (never committed).

Key env vars:
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT`
- `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, `OANDA_PRACTICE`
- `OPENFOREXAI_DB_BACKEND` (`sqlite` | `postgresql`)
- `OPENFOREXAI_DB_PATH` (SQLite path)
- `OPENFOREXAI_LOG_LEVEL`

### Adding a New LLM Provider
1. Create `openforexai/adapters/llm/<name>.py` implementing `AbstractLLMProvider`
2. Register in `openforexai/adapters/llm/__init__.py`
3. Create `config/modules/llm/<name>.json` with `"adapter": "<name>"`
4. Reference in `config/system.json` under `modules.llm`

### Adding a New Broker
Same pattern as LLM, in `adapters/brokers/` and `config/modules/broker/`.

### Adding a New Agent
Add an entry to `config/system.json` under `agents` with the ID naming convention. No code changes needed.

---

## Code Conventions

- `from __future__ import annotations` — top of every module
- `structlog` for logging — always `get_logger(__name__)`, never `logging.getLogger`
- All I/O is `async/await` — no blocking calls
- Pydantic v2 models for all domain data
- `ruff` linting, line length 100, targets Python 3.11
- `mypy` strict mode
- Test asyncio mode: `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)
- Tool results are always JSON-serialisable; errors return `{"error": "..."}` with `is_error=True`
- Exceptions in tool `execute()` are caught by `ToolDispatcher` automatically

---

## Running the System

```bash
# Install (in .venv)
pip install -e ".[all]"

# Run
openforexai            # via console script
python -m openforexai.main

# Scripts
python scripts/db_migrate.py
python scripts/run_backtest.py
python scripts/export_prompts.py

# Tests
pytest                         # all tests
pytest tests/unit/             # fast unit tests only
```

Management API runs at `http://127.0.0.1:8765` by default.

---

## Testing Approach

- `tests/unit/` — pure unit tests, no external dependencies, mocked brokers/LLMs
- `tests/integration/` — per-agent integration tests with mocked adapters
- `tests/e2e/test_full_cycle.py` — full bootstrap + cycle test
- Root-level `test_broker.py` / `test_llm.py` — live connectivity tests (require real credentials)

Fixtures and mocks live in `tests/conftest.py`.
