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

```text
OpenForexAI/
├── README.md                         # Root overview + links to topic docs
├── architecture.md                   # Architecture and runtime design
├── setup.md                          # Setup, configuration, quick start
├── developer.md                      # Developer reference (this file)
├── CONTRIBUTING.md                   # Contribution rules and process
├── CLA.md                            # Contributor license agreement
├── LICENSE                           # MIT license
├── AGENTS.md                         # Project-specific coding/agent guidance
├── pyproject.toml                    # Build metadata and dependencies
├── config/
│   ├── system.json5                  # Central runtime config
│   ├── config.md                     # Config information document shown in UI
│   ├── modules/
│   │   ├── llm/                      # Per-LLM module configs
│   │   └── broker/                   # Per-broker module configs
│   └── RunTime/
│       ├── agent_tools.json5         # Tool approvals / bridge tool config
│       └── event_routing.json5       # Event routing rules
├── docs/
│   ├── README.md                     # Documentation index
│   └── *.md                          # Package/topic docs
├── migrations/                       # SQL migrations
├── openforexai/
│   ├── main.py                       # App entrypoint
│   ├── bootstrap.py                  # System wiring/bootstrap
│   ├── agents/                       # Unified agent implementation + optimizers
│   ├── adapters/                     # Broker / LLM / DB adapters
│   ├── config/                       # Config service + JSON loader
│   ├── data/                         # Data container, resampling, indicators
│   ├── management/                   # FastAPI management API/server
│   ├── messaging/                    # EventBus and routing
│   ├── models/                       # Domain models (pydantic)
│   ├── monitoring/                   # Monitoring bus/events
│   ├── ports/                        # Hexagonal interfaces
│   ├── registry/                     # Plugin/runtime registries
│   ├── tools/                        # Runtime tool plugins for agents
│   ├── ui/                           # Backend UI support layer
│   └── utils/                        # Logging, retries, metrics, time helpers
├── scripts/                          # Utility scripts (db, backtest, export)
├── tests/
│   ├── unit/                         # Unit tests
│   ├── integration/                  # Integration tests
│   └── e2e/                          # End-to-end tests
├── tools/
│   ├── ask.py                        # CLI: query agents
│   ├── monitor.py                    # CLI: live monitoring
│   ├── logging.py                    # CLI: rotating event logger
│   ├── test_llm.py                   # CLI: LLM diagnostics
│   └── test_broker.py                # CLI: broker diagnostics
└── ui/                               # Web frontend
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
