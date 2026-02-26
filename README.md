# OpenForexAI

**Autonomous multi-agent LLM-based forex trading system**

Currency markets never sleep, and neither does OpenForexAI. The project was born
from a simple question: what happens if you replace every rule in an algorithmic
trading system with the judgment of an AI? Instead of hardcoding "buy when RSI
drops below 30", OpenForexAI lets a large language model read the market, reason
about risk, and decide — just like a human trader would, but around the clock and
without fatigue.

Under the hood, a team of specialised AI agents divides the work much like a
professional trading desk. One agent watches each currency pair and decides whether
the current moment is worth acting on. When the picture is unclear, it calls in a
chart analyst who digs deeper into patterns and indicator signals. A risk manager
sits between every decision and the actual order, making sure no single trade or
series of losses can seriously hurt the portfolio. And in the background, a fourth
agent quietly studies what has worked and what has not — then rewrites the team's
strategy prompts to do better next time.

The result is a system that not only trades autonomously, but continuously improves
its own decision-making without human intervention.

---

**Autonomous multi-agent LLM-based forex trading system** *(technical summary)*

OpenForexAI is an asynchronous, fully autonomous forex trading framework in which a
fleet of specialised AI agents collaborate through an internal event bus. Every
trading decision — from market observation to order placement — is reasoned by a
large language model (LLM). The system is designed for extensibility: brokers, LLM
providers, and databases are all swappable via clean port/adapter interfaces.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Agents](#agents)
3. [Event bus & messaging](#event-bus--messaging)
4. [Broker adapters](#broker-adapters)
5. [LLM adapters](#llm-adapters)
6. [Database](#database)
7. [Risk management](#risk-management)
8. [Self-optimisation loop](#self-optimisation-loop)
9. [Configuration](#configuration)
10. [Installation](#installation)
11. [Quick start](#quick-start)
12. [Running tests](#running-tests)
13. [Project layout](#project-layout)
14. [Tech stack](#tech-stack)

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Event Bus                               │
│  (asyncio-based publish/subscribe message broker)               │
└───┬─────────────┬────────────────┬──────────────────────────────┘
    │             │                │
    ▼             ▼                ▼
TradingAgent  SupervisorAgent  TechnicalAnalysisAgent  OptimizationAgent
(per pair)    (risk gate)      (on-demand TA)          (slow background)
    │             │
    ▼             ▼
 LLM call     RiskEngine ──► Broker (place / close order)
    │
 DataContainer (live candles + indicators)
```

All agents run concurrently as asyncio tasks in a single process. They communicate
exclusively through typed `AgentMessage` events — there is no direct method call
between agents at runtime.

---

## Agents

### TradingAgent *(one instance per currency pair)*

The TradingAgent is the core decision-maker. Every `cycle_interval_seconds`
(default: 60 s) it:

1. Fetches the current `MarketSnapshot` (tick price, raw candles) from the
   `DataContainer`.
2. Sends a **first-pass LLM call** with a compact context — current price, the last
   5 H1 candles, account balance, open position count, and recent trade history —
   and receives a structured `_TradingDecision` (action, entry, SL, TP, confidence,
   reasoning, `needs_deep_analysis` flag). Raw indicators are intentionally withheld
   here; interpreting them is the TechnicalAnalysisAgent's responsibility.
3. If `needs_deep_analysis` is `true`, publishes an `ANALYSIS_REQUESTED` event and
   awaits the `TechnicalAnalysisAgent`'s reply (up to `analysis_timeout_seconds`).
4. If deep analysis arrived, sends a **second LLM call** enriched with the TA
   result.
5. Publishes a `SIGNAL_GENERATED` event when `action ∈ {BUY, SELL}` and
   `confidence ≥ 0.65`. Otherwise it logs a HOLD.
6. Persists every `AgentDecision` (including HOLDs) to the database for later
   analysis.

The agent's system prompt is version-controlled and can be hot-swapped at runtime by
the `OptimizationAgent` via a `PROMPT_UPDATED` event.

### TechnicalAnalysisAgent *(singleton, reactive)*

Does not tick on a timer. It listens exclusively for `ANALYSIS_REQUESTED` events and
performs a deep LLM-driven analysis:

- Chart pattern recognition (head & shoulders, double tops/bottoms, triangles, …)
- Support / resistance level identification
- Trend assessment across multiple timeframes
- Per-timeframe signal aggregation

Results are published as `ANALYSIS_RESULT` events carrying the same
`correlation_id`, so the correct `TradingAgent` receives exactly its response even
when multiple analyses run concurrently. A semaphore limits parallelism to
`max_concurrent_requests` (default: 3).

### SupervisorAgent *(singleton, reactive + periodic)*

Acts as the **risk gate** between generated signals and actual orders. It is
reactive to `SIGNAL_GENERATED` events and also runs a slow background loop every
5 minutes to refresh the inter-pair correlation matrix and monitor open positions.

When a signal arrives the supervisor:

1. Fetches current open positions and account balance from the broker.
2. Runs the `RiskEngine` assessment (see [Risk management](#risk-management)).
3. If approved: constructs a `TradeOrder`, calls `broker.place_order()`, saves the
   trade result, and publishes `SIGNAL_APPROVED`.
4. If rejected: publishes `SIGNAL_REJECTED` with the rejection reason.
5. Persists the approval/rejection decision.

### OptimizationAgent *(singleton, slow background)*

Runs every `optimization_interval_hours` (default: 6 h) and implements a
**self-improving prompt evolution loop**:

1. Loads the last 200 closed trades per pair from the database.
2. Runs the `PatternDetector` to identify statistically significant trade patterns
   (e.g. recurring SL hits under certain indicator conditions, profitable hours,
   winning chart patterns).
3. Uses an LLM call (`PromptEvolver`) to generate a new candidate system prompt
   that incorporates the observed patterns.
4. Backtests the candidate against the historical trades with the `Backtester`.
5. If the candidate's simulated PnL exceeds the current baseline, it is marked
   active and broadcast as a `PROMPT_UPDATED` event — causing all affected
   `TradingAgent` instances to hot-swap their system prompt immediately.

This loop means the system continuously improves its own decision-making without
human intervention.

---

## Event bus & messaging

`EventBus` (`openforexai/messaging/bus.py`) is a lightweight asyncio publish /
subscribe dispatcher. Events are typed `AgentMessage` Pydantic models with fields:

| Field | Type | Description |
|---|---|---|
| `event_type` | `EventType` | e.g. `SIGNAL_GENERATED`, `ANALYSIS_REQUESTED`, `PROMPT_UPDATED` |
| `source_agent_id` | `str` | Originating agent |
| `target_agent_id` | `str \| None` | Optional unicast target |
| `payload` | `dict` | Event-specific data |
| `correlation_id` | `str \| None` | Used to match async request/reply pairs |

Agents register handlers named `on_<event_type_snake_case>`. The bus discovers and
wires them automatically at startup.

---

## Broker adapters

Two broker adapters ship out of the box:

| Adapter | Class | Notes |
|---|---|---|
| **OANDA** | `OandaAdapter` | REST v20 API; practice and live accounts; default |
| **MetaTrader 5** | `MT5Adapter` | Windows only; requires `MetaTrader5` Python package |

All adapters implement `AbstractBroker` (`openforexai/ports/broker.py`) which
exposes: `place_order`, `close_position`, `get_open_positions`,
`get_account_balance`, `get_candles`.

Adding a new broker requires only implementing `AbstractBroker` and registering it
in the plugin registry.

---

## LLM adapters

| Adapter | Provider | Default model |
|---|---|---|
| `AnthropicAdapter` | Anthropic | `claude-opus-4-6` |
| `OpenAIAdapter` | OpenAI | `gpt-4o` |
| `LMStudioAdapter` | Local (LM Studio) | any GGUF model |

All adapters implement `AbstractLLMProvider` (`openforexai/ports/llm.py`) with a
`complete_structured(system_prompt, user_message, response_schema)` method that
returns validated structured output (Pydantic model) rather than raw text.

Temperature is set to `0.1` by default to keep trading decisions deterministic.

---

## Database

Two database backends are supported:

| Backend | Adapter | Use case |
|---|---|---|
| **SQLite** | `SQLiteRepository` | Development, single-machine deployments |
| **PostgreSQL** | `PostgreSQLRepository` (asyncpg) | Production, multi-instance |

The schema is managed via plain SQL migrations in `migrations/`. The core tables are:

- `trades` — every filled/closed order with entry, SL, TP, fill price, PnL, close
  reason.
- `agent_decisions` — full audit trail of every LLM decision (including HOLDs and
  rejections) with latency and token usage.
- `prompt_candidates` — versioned system prompts per pair with backtest scores
  (migration 002).
- `patterns` — detected trade patterns used by the optimiser.
- `backtest_results` — results of each optimisation run.

---

## Risk management

The `RiskEngine` (`openforexai/agents/supervisor/risk_engine.py`) enforces hard
limits before any order reaches the broker:

| Parameter | Default | Description |
|---|---|---|
| `max_risk_per_trade_pct` | 1.0 % | Maximum account risk per single trade |
| `max_total_exposure_pct` | 5.0 % | Sum of open position risk |
| `max_drawdown_pct` | 10.0 % | Halt trading if drawdown exceeds threshold |
| `max_daily_loss_pct` | 3.0 % | Daily loss circuit breaker |
| `max_correlation_threshold` | 0.7 | Block correlated signals (based on H1 returns) |
| `max_open_positions` | 6 | Hard cap on concurrent positions |

The `CorrelationChecker` computes a live pair-correlation matrix from H1 candles and
blocks new signals when a too-similar position is already open.

Position sizing (`adjusted_units`) is calculated by the supervisor based on the
approved risk percentage and current balance, ensuring consistent 1 % risk per trade
regardless of pair volatility.

---

## Self-optimisation loop

```
Closed trades (≥ 20)
       │
       ▼
 PatternDetector  ──►  detected patterns (time-of-day, indicator combos, …)
       │
       ▼
 PromptEvolver  ──►  LLM generates a new system prompt incorporating patterns
       │
       ▼
 Backtester  ──►  simulate the new prompt against historical trades
       │
       ▼
 delta PnL > 0 ?
   yes ──►  mark prompt active, broadcast PROMPT_UPDATED
   no  ──►  discard candidate, keep current prompt
```

The entire loop runs in the background and never blocks trading. All candidate
prompts and backtest results are persisted, enabling full reproducibility and manual
review via `scripts/export_prompts.py`.

---

## Configuration

Configuration is layered: `config/default.yaml` → `config/<env>.yaml` →
environment variables. Environment variables use the prefix `OPENFOREXAI_` and
double-underscore nesting (e.g. `OPENFOREXAI_LLM__MODEL=claude-opus-4-6`).

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Key configuration sections:

```yaml
pairs: [EURUSD, USDJPY, GBPUSD]   # one TradingAgent + one TA agent per pair

llm:
  provider: anthropic              # anthropic | openai | lmstudio
  model: claude-opus-4-6
  temperature: 0.1

broker:
  name: oanda                      # oanda | mt5
  practice: true                   # use paper trading account

database:
  backend: sqlite                  # sqlite | postgresql

risk:
  max_risk_per_trade_pct: 1.0
  max_total_exposure_pct: 5.0
  max_drawdown_pct: 10.0
  max_daily_loss_pct: 3.0

agents:
  optimization:
    optimization_interval_hours: 6
    min_trades_before_run: 20
```

---

## Installation

**Requirements:** Python 3.11+

```bash
# Clone the repository
git clone https://github.com/GeorgGebert/OpenForexAI.git
cd OpenForexAI

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install runtime dependencies
pip install -e .

# MetaTrader 5 support (Windows only, optional)
pip install -e ".[mt5]"

# Development dependencies (tests, linter, type checker)
pip install -e ".[dev]"
```

---

## Quick start

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Run database migrations
python scripts/db_migrate.py

# 3. Start the system
openforexai
# or: python -m openforexai.main
```

The system will:
- Spawn one `TradingAgent` and one `TechnicalAnalysisAgent` per configured pair.
- Start the `SupervisorAgent` and `OptimizationAgent`.
- Begin the main event loop and start trading cycles immediately.

Logs are structured JSON via `structlog` at the configured `log_level`.

---

## Running tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit

# Integration tests
pytest tests/integration

# End-to-end cycle test
pytest tests/e2e

# With coverage
pytest --cov=openforexai
```

---

## Project layout

```
OpenForexAI/
├── config/
│   ├── default.yaml          # base configuration
│   ├── development.yaml
│   └── production.yaml
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_optimization_tables.sql
├── openforexai/
│   ├── agents/
│   │   ├── base.py                        # BaseAgent (start/stop/publish)
│   │   ├── trading/                       # TradingAgent + prompts + context builder
│   │   ├── technical_analysis/            # TechnicalAnalysisAgent + prompts
│   │   ├── supervisor/                    # SupervisorAgent + RiskEngine + CorrelationChecker
│   │   └── optimization/                 # OptimizationAgent + PatternDetector + Backtester + PromptEvolver
│   ├── adapters/
│   │   ├── brokers/                       # OandaAdapter, MT5Adapter
│   │   ├── database/                      # SQLiteRepository, PostgreSQLRepository
│   │   └── llm/                           # AnthropicAdapter, OpenAIAdapter, LMStudioAdapter
│   ├── ports/                             # Abstract interfaces (broker, database, llm, data_feed)
│   ├── models/                            # Pydantic domain models (trade, market, risk, …)
│   ├── data/                              # DataContainer, indicators, normalizer, correlation
│   ├── messaging/                         # EventBus, AgentMessage, EventType
│   ├── config/                            # Settings, YAML loader
│   ├── registry/                          # Plugin registry for adapters
│   ├── utils/                             # Logging, metrics, retry, time utils
│   ├── bootstrap.py                       # Wires all agents and adapters together
│   └── main.py                            # Entry point
├── scripts/
│   ├── db_migrate.py
│   ├── run_backtest.py
│   └── export_prompts.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .env.example
└── pyproject.toml
```

---

## Tech stack

| Component | Library / Tool |
|---|---|
| Python | 3.11+ |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) |
| LLM structured output | [pydantic-ai](https://github.com/pydantic/pydantic-ai) |
| Anthropic API | `anthropic` SDK |
| OpenAI API | `openai` SDK |
| Async HTTP | `httpx` |
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
