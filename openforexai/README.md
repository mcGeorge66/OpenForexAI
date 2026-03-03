# openforexai — Main Application Package

The root package of the OpenForexAI system. This is the entry point for the entire autonomous multi-agent forex trading platform.

## Package Structure

```
openforexai/
├── main.py              # Entry point — asyncio run loop
├── bootstrap.py         # System bootstrap orchestrator
├── agents/              # Single Agent class (AA / BA / GA)
├── adapters/            # Concrete implementations (LLM, Broker, Database)
├── config/              # Config loading and ConfigService agent
├── data/                # DataContainer, resampler, indicators
├── management/          # FastAPI control plane (HTTP API + server)
├── messaging/           # EventBus, RoutingTable, agent ID helpers
├── models/              # Pydantic v2 domain models
├── monitoring/          # Fire-and-forget observability bus
├── ports/               # Abstract interfaces (hexagonal ports)
├── registry/            # PluginRegistry + RuntimeRegistry
├── tools/               # LLM-callable tool plugins
└── utils/               # Logging, retry, time helpers, metrics
```

## Entry Points

### `main.py`
The application entry point. Calls `bootstrap.py`, then runs the full system inside a single `asyncio.TaskGroup`:
- EventBus dispatch loop
- ConfigService agent
- Broker background tasks (M5 candle streaming, account polling)
- All agents (one task per agent)
- ManagementServer (FastAPI/uvicorn, port 8765)

**How to run:**
```bash
python -m openforexai.main
# or
openforexai
```

### `bootstrap.py`
Wires all components together from `config/system.json`:

1. Loads JSON config (with `${ENV_VAR:-default}` substitution)
2. Triggers adapter self-registration via package `__init__.py` imports
3. Creates `AbstractRepository` (SQLite or PostgreSQL)
4. Runs database migrations
5. Instantiates LLM and broker adapters from `RuntimeRegistry`
6. Builds `EventBus` and `RoutingTable`
7. Creates `DataContainer` and `ConfigService`
8. Creates `ManagementServer` (FastAPI)
9. Creates one `Agent` instance per entry in `config/system.json → agents`

## Architecture Overview

The system follows **hexagonal architecture**: abstract ports in `ports/`, concrete adapters in `adapters/`. Business logic never imports from adapters directly.

```
config/system.json
       │
  bootstrap.py ──► PluginRegistry (import-time self-registration)
       │            RuntimeRegistry (live instances)
       ├── Database (AbstractRepository)
       ├── LLM adapters (AbstractLLMProvider)
       ├── Broker adapters (AbstractBroker)
       ├── EventBus + RoutingTable
       ├── DataContainer
       ├── ConfigService
       ├── ManagementServer (FastAPI, port 8765)
       └── Agent × N  (all same class, config-driven)
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Single `Agent` class for all types | Type (AA/BA/GA) is a label; behaviour comes from config alone |
| Config via EventBus handshake | `Agent.__init__` stays dependency-free |
| All I/O is async | No blocking; runs in one asyncio event loop |
| M5-only broker fetches | Higher TFs resampled on-demand — fewer API calls |
| Hexagonal ports | Swap LLM/broker/DB without touching business logic |

## Configuration

Everything is controlled by `config/system.json`. See the [`config/` README](../config/README.md) for details.

Environment variables override config values. The most important ones:

```bash
OPENFOREXAI_LOG_LEVEL=INFO         # DEBUG / INFO / WARNING / ERROR
OPENFOREXAI_DB_BACKEND=sqlite      # sqlite | postgresql
OPENFOREXAI_DB_PATH=./data/openforexai.db

# LLM credentials (at least one required)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

# Broker credentials
OANDA_API_KEY=...
OANDA_ACCOUNT_ID=...
OANDA_PRACTICE=true
```

## Management API

The system exposes a REST API on `http://127.0.0.1:8765` by default.

| Endpoint | Description |
|---|---|
| `GET /health` | System health and uptime |
| `GET /agents` | List all running agents |
| `POST /agents/{id}/ask` | Query any agent directly |
| `GET /monitoring/events` | Real-time event stream (used by `tools/monitor.py`) |
| `POST /routing/reload` | Hot-reload routing rules |
| `GET /tools` | List registered tool plugins |

See the [`management/` README](management/README.md) for full API documentation.

## See Also

- [`agents/`](agents/README.md) — How agents work
- [`messaging/`](messaging/README.md) — EventBus and routing
- [`data/`](data/README.md) — Market data management
- [`tools/`](tools/README.md) — LLM tool plugins
- [`ports/`](ports/README.md) — Abstract interfaces
- [`../tools/README.md`](../tools/README.md) — CLI monitoring and query tools
