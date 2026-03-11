[Back to README](./README.md)

# Developer Guide

This document contains developer-oriented reference sections.

## Running tests

```bash
pytest                    # all tests
pytest tests/unit         # unit tests only
pytest tests/integration  # integration tests
pytest tests/e2e          # end-to-end cycle test
pytest --cov=openforexai  # with coverage
```

---

## Project layout

```
OpenForexAI/
├── config/
│   ├── system.json5                   # central config — agents, modules, prompts
│   ├── modules/
│   │   ├── llm/
│   │   │   └── anthropic_claude.json5 # LLM module config (credentials + settings)
│   │   └── broker/
│   │       ├── oanda.json5            # OANDA module config
│   │       └── mt5.json5              # MT5 module config
│   └── event_routing.json5            # EventBus routing rules (hot-reloadable)
├── tools/
│   └── monitor.py                    # console monitor — polls /monitoring/events
├── test_llm.py                       # LLM module test script
├── test_broker.py                    # Broker module test script
├── openforexai/
│   ├── agents/
│   │   └── agent.py                  # THE single Agent class (AA, BA, GA)
│   ├── adapters/
│   │   ├── brokers/
│   │   │   ├── base.py               # BrokerBase: _m5_loop, _account_poll, _sync_loop
│   │   │   ├── oanda.py              # OANDABroker
│   │   │   └── mt5.py                # MT5Broker
│   │   ├── database/                 # SQLiteRepository, PostgreSQLRepository
│   │   └── llm/
│   │       ├── anthropic.py          # Native tool_use API
│   │       ├── openai.py             # Native function_calling API
│   │       └── base.py               # llm_retry helper
│   ├── config/
│   │   ├── json_loader.py            # JSON loader with ${ENV_VAR} substitution
│   │   └── config_service.py         # ConfigService agent (SYSTM_ALL..._GA_CFGSV)
│   ├── registry/
│   │   ├── plugin_registry.py        # Adapter class registry (LLM, broker, DB)
│   │   └── runtime_registry.py       # Live instance registry (name → instance)
│   ├── messaging/
│   │   ├── bus.py                    # EventBus: routing + direct target_agent_id
│   │   ├── routing.py                # RoutingTable, RoutingRule, JSON loader
│   │   └── agent_id.py               # AgentId parsing, formatting, wildcard matching
│   ├── monitoring/
│   │   └── bus.py                    # MonitoringBus: ring buffer + subscriber queues
│   ├── ports/                        # Abstract interfaces (broker, database, llm, monitoring)
│   ├── models/                       # Pydantic domain models
│   │   ├── market.py                 # Candle, MarketSnapshot
│   │   ├── trade.py                  # OrderType, OrderStatus, OrderBookEntry
│   │   ├── account.py                # AccountStatus
│   │   ├── messaging.py              # AgentMessage, EventType (incl. AGENT_CONFIG_*)
│   │   └── monitoring.py             # MonitoringEvent, MonitoringEventType
│   ├── data/
│   │   ├── container.py              # DataContainer: multi-broker, event-driven
│   │   ├── resampler.py              # M5 → higher timeframes
│   │   ├── indicators.py             # Pure indicator functions
│   │   ├── indicator_plugins.py      # IndicatorPlugin subclasses + DEFAULT_REGISTRY
│   │   └── indicator_tools.py        # IndicatorToolset (broker-aware)
│   ├── tools/
│   │   ├── __init__.py               # DEFAULT_REGISTRY + all built-in tools registered
│   │   ├── base.py                   # BaseTool ABC, ToolContext
│   │   ├── registry.py               # ToolRegistry (plug-and-play)
│   │   ├── dispatcher.py             # ToolDispatcher: context tiers, monitoring
│   │   ├── market/                   # get_candles, calculate_indicator
│   │   ├── account/                  # get_account_status, get_open_positions
│   │   ├── orderbook/                # get_order_book
│   │   ├── trading/                  # place_order, close_position
│   │   └── system/                   # raise_alarm, trigger_sync
│   ├── management/
│   │   ├── api.py                    # FastAPI endpoints (incl. /monitoring/events)
│   │   └── server.py                 # ManagementServer (uvicorn background task)
│   ├── utils/                        # logging, metrics, retry, time utils
│   ├── bootstrap.py                  # wires all components from system.json5
│   └── main.py                       # entry point
├── scripts/
│   ├── db_migrate.py
│   ├── run_backtest.py
│   └── export_prompts.py
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## Tech stack

| Component | Library / Tool |
|---|---|
| Python | 3.11+ |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) |
| Anthropic API | `anthropic` SDK (native tool_use) |
| OpenAI API | `openai` SDK (native function_calling) |
| Async HTTP | `httpx` |
| Management API | `fastapi` + `uvicorn` |
| SQLite async | `aiosqlite` |
| PostgreSQL async | `asyncpg` |
| Structured logging | `structlog` |
| Numerics | `numpy` |
| Build system | [Hatchling](https://hatch.pypa.io/) |
| Tests | `pytest` + `pytest-asyncio` + `pytest-mock` |
| Linting | `ruff` |
| Type checking | `mypy` (strict) |

---

> **Disclaimer:** This software is provided for educational and research purposes.
> Forex trading involves substantial risk of loss. Always test with a practice
> account before connecting real funds. The authors are not responsible for any
> financial losses incurred through the use of this software.

## Additional Documentation

- Consolidated package docs: [`docs/README.md`](./docs/README.md)
- Project-specific contributor instructions: [`AGENTS.md`](./AGENTS.md)
