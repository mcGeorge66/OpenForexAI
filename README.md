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
the current moment is worth acting on. When the picture is unclear, it can call a
chart analyst who digs deeper into patterns and indicator signals. A risk manager
sits between every decision and the actual order. And in the background, a fourth
agent quietly studies what has worked and what has not — then rewrites the team's
strategy prompts to do better next time.

The result is a system that not only trades autonomously, but continuously improves
its own decision-making without human intervention.

---

**Autonomous multi-agent LLM-based forex trading system** *(technical summary)*

OpenForexAI is an asynchronous, fully autonomous forex trading framework in which a
fleet of specialised AI agents collaborate through a rule-based internal event bus.
Every trading decision — from market observation to order placement — is reasoned
by a large language model using its **native tool-use API**. The system is designed
for extensibility: brokers, LLM providers, indicators, tools, and databases are all
swappable via clean port/adapter interfaces.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Agent types and naming](#agent-types-and-naming)
3. [TradingAgent — the tool-use loop](#tradingagent--the-tool-use-loop)
4. [Other agents](#other-agents)
5. [Event bus and routing](#event-bus-and-routing)
6. [Tool system](#tool-system)
7. [Indicator plugin system](#indicator-plugin-system)
8. [Broker adapters](#broker-adapters)
9. [Data pipeline](#data-pipeline)
10. [LLM adapters](#llm-adapters)
11. [Monitoring bus](#monitoring-bus)
12. [Management API](#management-api)
13. [Database](#database)
14. [Self-optimisation loop](#self-optimisation-loop)
15. [Configuration](#configuration)
16. [Installation](#installation)
17. [Quick start](#quick-start)
18. [Running tests](#running-tests)
19. [Project layout](#project-layout)
20. [Tech stack](#tech-stack)

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Rule-based EventBus                               │
│  JSON routing rules · per-agent queues · wildcard matching           │
│  hot-reload · MonitoringBus warnings for unmatched events            │
└───┬──────────────┬───────────────┬─────────────────┬────────────────┘
    │              │               │                 │
    ▼              ▼               ▼                 ▼
TradingAgent  SupervisorAgent  TechnicalAnalysis  OptimizationAgent
OANDA_EURUSD  OANDA_ALL..._    GLOBL_ALL..._      GLOBL_ALL..._
_AA_TRD1      BA_SUP1          GA_TA__1           GA_OPT1
(per pair)    (per broker)     (singleton)        (singleton)
    │
    ▼  native tool_use API (Anthropic / OpenAI)
ToolDispatcher
    ├── get_candles          ← DataContainer
    ├── calculate_indicator  ← IndicatorToolset
    ├── get_account_status   ← BrokerAdapter
    ├── get_open_positions   ← BrokerAdapter
    ├── get_order_book       ← Repository
    ├── place_order          ← BrokerAdapter
    ├── close_position       ← BrokerAdapter
    ├── raise_alarm          → MonitoringBus
    └── trigger_sync         ← BrokerAdapter

BrokerAdapter (one instance per pair)
    ├── _m5_loop       → publishes M5_CANDLE_AVAILABLE every 5 min
    ├── _account_poll  → updates AccountStatus in repository
    └── _sync_loop     → detects SL/TP hits, publishes SYNC_DISCREPANCY

DataContainer  ←  M5_CANDLE_AVAILABLE
    └── derives H1, H4, D1 from M5 via Resampler (on-demand)

ManagementAPI (localhost:8765 / FastAPI)
    ├── POST /events        ← inject events from outside
    ├── POST /routing/reload← hot-reload routing table
    └── GET  /health|metrics|agents|tools|indicators
```

All agents run concurrently as asyncio tasks in a single process. They communicate
exclusively through typed `AgentMessage` events — there are no direct method calls
between agents at runtime.

---

## Agent types and naming

### Agent ID format

Every agent has a fixed-length structured identifier:

```
[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]
```

| Segment | Length | Padding | Examples |
|---|---|---|---|
| BROKER | 5 chars | `.` right-pad | `OANDA`, `MT5..`, `GLOBL` |
| PAIR | 6 chars | `.` right-pad | `EURUSD`, `USDJPY`, `ALL...` |
| TYPE | 2 chars | none | `AA`, `BA`, `GA` |
| NAME | 1–5 chars | none | `TRD1`, `SUP1`, `OPT1` |

If NAME is exactly 5 characters, an optional 5th extension segment is allowed
(e.g. `OANDA_EURUSD_AA_TRD1_V2`).

**Examples:**

| Agent ID | Description |
|---|---|
| `OANDA_EURUSD_AA_TRD1` | TradingAgent for EURUSD on OANDA |
| `MT5.._USDJPY_AA_TRD1` | TradingAgent for USDJPY on MT5 |
| `OANDA_ALL..._BA_SUP1` | SupervisorAgent for the OANDA broker |
| `GLOBL_ALL..._GA_TA__1` | TechnicalAnalysisAgent (global singleton) |
| `GLOBL_ALL..._GA_OPT1` | OptimizationAgent (global singleton) |

### Agent types

| Type | Code | Created by | Description |
|---|---|---|---|
| **Adapter Agent** | `AA` | Auto (one per broker adapter) | Per-pair decision maker |
| **Broker Agent** | `BA` | Config (one per broker) | Supervision, risk gate |
| **Global Agent** | `GA` | Config (singletons) | TA, optimisation, etc. |

> **Note:** The broker adapter itself is not an agent — it is an infrastructure
> component that publishes events under the ID `BROKER_PAIR_AA_ADPT`
> (e.g. `OANDA_EURUSD_AA_ADPT`). One broker adapter instance handles exactly
> **one currency pair**.

---

## TradingAgent — the tool-use loop

The `TradingAgent` (`AA` type) is the core decision-maker. One instance runs per
configured broker/pair combination.

### Cycle

Every `cycle_interval_seconds` (default: 60 s) the agent runs a single
**multi-turn tool-use loop**:

```
  Agent sends initial message:
  "Analyse EURUSD right now. Use available tools as needed."
         │
         ▼
  LLM responds with tool calls:
  ┌─────────────────────────────────────────────┐
  │  turn 1:  get_candles(H1, 50)               │
  │           calculate_indicator(RSI, 14, H1)  │
  │  turn 2:  get_account_status()              │
  │           get_open_positions()              │
  │  turn 3:  place_order(BUY, MARKET, ...)     │
  │           [or: raise_alarm / close_position]│
  │  turn N:  LLM returns final text → done     │
  └─────────────────────────────────────────────┘
         │
         ▼
  AgentDecision persisted to database
```

The LLM decides **which data to fetch** and **what action to take** — there is no
pre-determined context-building step.  The `ToolDispatcher` executes every tool
call with the following guarantees:

- **Context budget tiers**: as token usage grows, only a subset of tools remains
  visible to the LLM (configured in `config/agent_tools.json`).  Default tiers:
  0–70 % → all tools; 70–90 % → decision tools only; 90–100 % → safety only.
- **All tool calls are logged** to the `MonitoringBus`.
- **Max turns** are configurable per agent (default: 10).

### Inbound messages

The agent also processes messages delivered to its EventBus inbox:

| Event | Action |
|---|---|
| `PROMPT_UPDATED` | Hot-swap system prompt from OptimizationAgent |
| `SIGNAL_APPROVED` | Log approval from supervisor |
| `SIGNAL_REJECTED` | Log rejection from supervisor |
| `ORDER_BOOK_SYNC_DISCREPANCY` | Log discrepancy; optionally generate close reasoning |

---

## Other agents

### TechnicalAnalysisAgent *(global singleton, reactive)*

Does not tick on a timer. Listens for `ANALYSIS_REQUESTED` events and performs
a deep LLM-driven analysis using the same tool-use loop.  Results are published as
`ANALYSIS_RESULT` with the same `correlation_id`, so the requesting `TradingAgent`
receives exactly its response.

Capabilities: chart pattern recognition, support/resistance identification, trend
assessment across multiple timeframes, indicator divergence detection.

### SupervisorAgent *(per-broker, reactive)*

Acts as the risk gate. Reacts to `SIGNAL_GENERATED` events:

1. Fetches current positions and account status via tools.
2. Runs risk assessment (exposure, daily loss, correlation).
3. Publishes `SIGNAL_APPROVED` or `SIGNAL_REJECTED`.
4. Persists the decision.

Also runs a slow background loop to refresh the inter-pair correlation matrix
and monitor margin levels.

### OptimizationAgent *(global singleton, background)*

Implements the self-improving prompt evolution loop — see
[Self-optimisation loop](#self-optimisation-loop).

---

## Event bus and routing

The `EventBus` (`openforexai/messaging/bus.py`) is a rule-based asyncio pub/sub
dispatcher with **dual delivery**:

### Agent queue delivery (new)

Each agent registers a personal `asyncio.Queue` (inbox) with the bus.  The routing
table (`config/event_routing.json`) determines which agent queues receive each
published message.

### Legacy handler delivery (backward compat)

Infrastructure components (`DataContainer`, `BrokerBase`) subscribe directly to
event types via `bus.subscribe(EventType.X, handler)`.  These fire unconditionally
regardless of routing rules.

### Routing rules

Rules are JSON, evaluated in ascending priority order (lower number = first).
Multiple matching rules are all applied — the union of their targets receives the
message.

```json
{
  "rules": [
    {
      "id": "m5_candle_to_handlers",
      "event": "m5_candle_available",
      "from": "*",
      "to": "@handlers",
      "priority": 10
    },
    {
      "id": "signal_to_supervisor",
      "event": "signal_generated",
      "from": "*_*_AA_TRD*",
      "to": "{sender.broker}_ALL..._BA_SUP1",
      "priority": 20
    }
  ]
}
```

**`to` target types:**

| Value | Effect |
|---|---|
| Literal ID | Deliver to that single registered agent |
| `{sender.broker}_..._BA_SUP1` | Template substitution from sender's ID segments |
| `*_EURUSD_AA_*` | Fan-out to all matching registered agents |
| `*` | Broadcast to all agents |
| `@handlers` | Legacy handler-subscriber delivery only |

**Supported `{sender.*}` placeholders:** `.broker`, `.pair`, `.type`, `.name`,
`.extension`, `.id`

**Unmatched events:** if no rule matches AND no handler is registered, the message
is silently dropped and a warning is emitted to the `MonitoringBus`.

**Hot-reload:** `POST /routing/reload` via the Management API atomically reloads
`config/event_routing.json` without restarting the system.

---

## Tool system

OpenForexAI uses the **native tool-use API** of each LLM provider (Anthropic
`tool_use`, OpenAI `function_calling`) — no JSON schema prompt hacks.

### Built-in tools

| Tool | Category | Description |
|---|---|---|
| `get_candles` | Market | OHLCV candle data at any timeframe (M5–D1), 1–500 bars |
| `calculate_indicator` | Market | RSI, ATR, SMA, EMA, BB, VWAP with `history` support |
| `get_account_status` | Account | Balance, equity, margin, leverage, trade_allowed |
| `get_open_positions` | Account | All open positions with unrealised P&L |
| `get_order_book` | Order book | Internal order book entries with reasoning and P&L |
| `place_order` | Trading | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP |
| `close_position` | Trading | Close any open position by broker ID |
| `raise_alarm` | System | Severity-levelled alarm → MonitoringBus + Python logging |
| `trigger_sync` | System | Manual order book sync with the broker |

### ToolRegistry — plug and play

Tools are registered once and become available system-wide:

```python
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import BaseTool, ToolContext

class MyCustomTool(BaseTool):
    name = "my_tool"
    description = "Does something useful."
    input_schema = {
        "type": "object",
        "properties": {
            "param": {"type": "string"}
        },
        "required": ["param"]
    }

    async def execute(self, arguments, context: ToolContext):
        return {"result": f"processed: {arguments['param']}"}

DEFAULT_REGISTRY.register(MyCustomTool())
```

After registration the tool appears in the LLM's tool manifest automatically for
any agent that has it in its `allowed_tools` list.

### Per-agent tool configuration (`config/agent_tools.json`)

Each agent type gets its own tool configuration, matched by agent ID pattern:

```json
{
  "agents": [
    {
      "pattern": "*_*_AA_TRD*",
      "allowed_tools": ["get_candles", "calculate_indicator", "place_order", "..."],
      "context_tiers": {"0": "all", "70": "decision", "90": "safety"},
      "tier_tools": {
        "all":      ["get_candles", "calculate_indicator", "place_order", "..."],
        "decision": ["place_order", "close_position", "raise_alarm"],
        "safety":   ["raise_alarm", "close_position"]
      },
      "max_tool_turns": 10,
      "max_tokens": 4096
    }
  ]
}
```

---

## Indicator plugin system

### Design

The `DataContainer` holds **only raw candle data**. No indicators are pre-computed
or cached. All indicators are computed **on-demand** by the `calculate_indicator`
tool when the LLM requests them.

The `history` parameter returns a series of consecutive values (oldest first),
enabling trend, divergence, and momentum analysis:

```python
# Single latest value
rsi = toolset.calculate("RSI", 14, "H1", "EURUSD")
# → 62.4

# Last 5 RSI values — is momentum accelerating or fading?
rsi_series = toolset.calculate("RSI", 14, "H1", "EURUSD", history=5)
# → [48.2, 51.7, 55.3, 59.1, 62.4]  (oldest → newest)
```

### Built-in indicators

| Plugin | Name | Description |
|---|---|---|
| `SMAPlugin` | `SMA` / `MA` | Simple Moving Average |
| `EMAPlugin` | `EMA` | Exponential Moving Average |
| `RSIPlugin` | `RSI` | Relative Strength Index (0–100) |
| `ATRPlugin` | `ATR` | Average True Range |
| `BollingerBandsPlugin` | `BB` / `BOLLINGER` | Upper / Middle / Lower bands |
| `VWAPPlugin` | `VWAP` | Volume Weighted Average Price (uses tick_volume) |

### Adding an indicator

```python
class MACDPlugin(IndicatorPlugin):
    name = "MACD"
    description = "MACD histogram."
    min_candles = 35

    def calculate(self, candles, period, history):
        ...

DEFAULT_REGISTRY.register(MACDPlugin())
```

After registration it appears in the `calculate_indicator` tool's enum automatically.

---

## Broker adapters

### One adapter = one pair

Each broker adapter instance handles **exactly one currency pair**. To trade
multiple pairs on the same broker, configure multiple adapter instances:

```yaml
adapters:
  - broker: oanda
    pair: EURUSD
    account_id: "101-001-..."
  - broker: oanda
    pair: USDJPY
    account_id: "101-001-..."   # same account, separate adapter
```

The adapter publishes events under the structured ID `BROKER_PAIR_AA_ADPT`
(e.g. `OANDA_EURUSD_AA_ADPT`).

### Background tasks (per adapter)

Each adapter runs three background asyncio tasks:

| Task | Interval | Description |
|---|---|---|
| `_m5_loop` | every 5-min boundary +10 s | Fetches latest M5 candle, detects gaps, publishes `M5_CANDLE_AVAILABLE` |
| `_account_poll_loop` | configurable (default 60 s) | Fetches `AccountStatus` (balance, equity, margin, leverage) |
| `_sync_loop` | configurable (default 60 s) | Compares broker positions against local order book, publishes `ORDER_BOOK_SYNC_DISCREPANCY` on mismatch |

### Supported brokers

| Adapter | Class | Notes |
|---|---|---|
| **OANDA** | `OANDABroker` | REST v20 API; practice and live; all 5 order types |
| **MetaTrader 5** | `MT5Broker` | Windows only; `MetaTrader5` Python package required; TRAILING_STOP not supported |

### Supported order types

`MARKET`, `LIMIT`, `STOP`, `STOP_LIMIT`, `TRAILING_STOP`

### Account status fields

`balance`, `equity`, `margin`, `margin_free`, `margin_level`, `leverage`,
`currency`, `trade_allowed`, `recorded_at`

---

## Data pipeline

```
BrokerAdapter._m5_loop
        │  publishes M5_CANDLE_AVAILABLE
        ▼
EventBus → DataContainer._on_m5_candle()
        │  dedup · append · trim · persist · monitoring
        │
        │  gap detected?
        ├──► CANDLE_GAP_DETECTED → DataContainer._repair()
        │    back-fills 200 M5 bars · saves bulk · recalculates higher TFs
        │
        ▼
DataContainer.get_candles(broker, pair, timeframe)
        │  M5: direct · H1/H4/D1: derived via Resampler on-demand
        │  tick_volume: summed per TF · spread: from closing bar
        ▼
IndicatorToolset.calculate(indicator, period, tf, pair, history)
```

The `DataContainer` is keyed by `(broker_name, pair)`, enabling true multi-broker
operation where each pair tracks its own independent candle history.

---

## LLM adapters

| Adapter | Provider | Default model | Tool-use |
|---|---|---|---|
| `AnthropicLLMProvider` | Anthropic | `claude-opus-4-6` | Native `tool_use` API |
| `OpenAILLMProvider` | OpenAI | `gpt-4o` | Native `function_calling` API |
| `LMStudioLLMProvider` | Local (LM Studio) | any GGUF | OpenAI-compatible endpoint |

All adapters implement `AbstractLLMProvider` with three methods:

- `complete(system, user, ...)` — plain text completion
- `complete_structured(system, user, schema)` — JSON-schema structured output
- `complete_with_tools(system, messages, tools, ...)` — **native multi-turn
  tool-use loop**; returns `LLMResponseWithTools` with `.wants_tools` property

The canonical internal tool format is Anthropic's (`name`, `description`,
`input_schema`).  The OpenAI adapter converts `input_schema → parameters`
automatically.

Temperature defaults to `0.1` for deterministic trading decisions.

---

## Monitoring bus

The `MonitoringBus` is a **fire-and-forget observability sink**.  Every component
emits `MonitoringEvent` objects without waiting for acknowledgement:

- Bounded `asyncio.Queue` (default 10 000 events) — full queues drop silently
- Never blocks the calling coroutine
- External monitors subscribe via `monitoring_bus.subscribe()`

Covered event types include: broker connection, M5 candle pipeline, account status,
order book, sync checks, agent decisions, tool calls (started / completed / failed),
LLM calls, EventBus routing warnings, and agent alarms.

---

## Management API

A FastAPI HTTP server running on `localhost:8765` provides a runtime control plane.
It starts as a background asyncio Task alongside all agents.

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | System status, uptime, agent count, rule count |
| `/metrics` | GET | Agent queue depths, uptime counters |
| `/agents` | GET | List all registered agents with queue depths |
| `/agents/{id}` | GET | Single agent info |
| `/routing/rules` | GET | Active routing rules |
| `/routing/reload` | POST | Hot-reload `config/event_routing.json` |
| `/events` | POST | Inject an arbitrary event into the EventBus |
| `/indicators` | GET | List registered indicator plugins |
| `/tools` | GET | List registered tools |
| `/docs` | GET | Interactive Swagger UI |

**Event injection example:**

```bash
curl -X POST http://localhost:8765/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "routing_reload_requested",
       "source_agent_id": "MGMT._ALL..._GA_MGMT",
       "payload": {}}'
```

Optional API key authentication via `X-API-Key` header
(set `MANAGEMENT_API_KEY` environment variable).

---

## Database

Two backends are supported:

| Backend | Adapter | Use case |
|---|---|---|
| **SQLite** | `SQLiteRepository` | Development, single-machine |
| **PostgreSQL** | `PostgreSQLRepository` (asyncpg) | Production |

Core tables:

| Table | Description |
|---|---|
| `candles_{broker}_{pair}_{tf}` | Candle history per broker/pair/timeframe (e.g. `OANDA_DEMO_EURUSD_M5`) |
| `order_book` | Full trade lifecycle with entry reasoning, confidence, market context snapshot, P&L, close reason |
| `account_status` | Historical account status snapshots |
| `agent_decisions` | Full audit trail of every LLM cycle (including HOLDs) with tokens and latency |
| `prompt_candidates` | Versioned system prompts per pair with backtest scores |
| `patterns` | Detected trade patterns |
| `backtest_results` | Optimisation run results |

The `order_book` table is comprehensive — each entry stores:
`agent_id`, `prompt_version`, `entry_reasoning`, `signal_confidence`,
`market_context_snapshot`, `fill_price`, `stop_loss`, `take_profit`,
`close_reason`, `pnl_pips`, `pnl_account_currency`, `sync_confirmed`.

---

## Self-optimisation loop

```
Closed trades (≥ 20 per pair)
        │
        ▼
PatternDetector  →  detected patterns (time-of-day, indicator combos, …)
        │
        ▼
PromptEvolver   →  LLM generates new candidate system prompt
        │
        ▼
Backtester      →  simulate against historical trades
        │
        ▼
delta PnL > 0?
  yes → mark active · broadcast PROMPT_UPDATED
        ↓
        TradingAgent.load_prompt()  ← hot-swap in _handle_message()
  no  → discard candidate · keep current prompt
```

All candidates and results are persisted for full reproducibility and manual review.

---

## Configuration

Configuration is layered: `config/default.yaml` → `config/<env>.yaml` →
environment variables (`OPENFOREXAI_` prefix, `__` nesting).

Copy `.env.example` to `.env` and fill in credentials:

```bash
cp .env.example .env
```

Key sections:

```yaml
# One entry per broker/pair combination (one adapter = one pair)
adapters:
  - broker: oanda
    pair: EURUSD
    practice: true
    account_id: "101-001-..."
  - broker: oanda
    pair: USDJPY
    practice: true
    account_id: "101-001-..."

llm:
  provider: anthropic          # anthropic | openai | lmstudio
  model: claude-opus-4-6
  temperature: 0.1
  max_tokens: 4096

database:
  backend: sqlite              # sqlite | postgresql

management_api:
  host: 127.0.0.1
  port: 8765
  # api_key: ""  # leave empty to disable auth in development

agents:
  trading:
    cycle_interval_seconds: 60
    max_tool_turns: 10
  optimization:
    interval_hours: 6
    min_trades_before_run: 20
```

Routing rules are in `config/event_routing.json` and can be hot-reloaded.
Per-agent tool configuration is in `config/agent_tools.json`.

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

# Management API (required for HTTP control plane)
pip install -e ".[api]"

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

- Spawn one `TradingAgent` (`AA`) per configured broker/pair.
- Spawn broker adapter background tasks (`_m5_loop`, `_account_poll`, `_sync_loop`)
  per adapter.
- Start the `SupervisorAgent` (`BA`) per configured broker.
- Start the `TechnicalAnalysisAgent` and `OptimizationAgent` (`GA`) as global
  singletons.
- Start the `ManagementAPI` on `localhost:8765`.
- Begin event routing and trading cycles immediately.

Logs are structured JSON via `structlog`. The Management API's Swagger UI is
available at `http://localhost:8765/docs`.

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
│   ├── default.yaml              # base configuration
│   ├── development.yaml
│   ├── production.yaml
│   ├── event_routing.json        # EventBus routing rules (hot-reloadable)
│   └── agent_tools.json          # per-agent tool configuration
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_optimization_tables.sql
├── openforexai/
│   ├── agents/
│   │   ├── base.py               # BaseAgent: cycle loop + message loop + run_with_tools()
│   │   ├── trading/              # TradingAgent (AA) + prompt templates
│   │   ├── technical_analysis/   # TechnicalAnalysisAgent (GA)
│   │   ├── supervisor/           # SupervisorAgent (BA) + RiskEngine
│   │   └── optimization/         # OptimizationAgent (GA) + PatternDetector + Backtester
│   ├── adapters/
│   │   ├── brokers/
│   │   │   ├── base.py           # BrokerBase: _m5_loop, _account_poll, _sync_loop
│   │   │   ├── oanda.py          # OANDABroker (all 5 order types)
│   │   │   └── mt5.py            # MT5Broker
│   │   ├── database/             # SQLiteRepository, PostgreSQLRepository
│   │   └── llm/
│   │       ├── anthropic.py      # Native tool_use API
│   │       ├── openai.py         # Native function_calling API
│   │       └── base.py           # llm_retry helper
│   ├── ports/                    # Abstract interfaces (broker, database, llm, monitoring)
│   ├── models/                   # Pydantic domain models
│   │   ├── market.py             # Candle (tick_volume, spread), MarketSnapshot
│   │   ├── trade.py              # OrderType, OrderStatus, CloseReason, OrderBookEntry
│   │   ├── account.py            # AccountStatus
│   │   ├── messaging.py          # AgentMessage, EventType
│   │   └── monitoring.py         # MonitoringEvent, MonitoringEventType
│   ├── data/
│   │   ├── container.py          # DataContainer: multi-broker, event-driven
│   │   ├── resampler.py          # M5 → higher timeframes
│   │   ├── indicators.py         # Pure indicator functions
│   │   ├── indicator_plugins.py  # IndicatorPlugin subclasses + DEFAULT_REGISTRY
│   │   └── indicator_tools.py    # IndicatorToolset (broker-aware)
│   ├── messaging/
│   │   ├── bus.py                # EventBus: rule-based routing + legacy handlers
│   │   ├── routing.py            # RoutingTable, RoutingRule, JSON loader
│   │   └── agent_id.py           # AgentId parsing, formatting, wildcard matching
│   ├── tools/
│   │   ├── __init__.py           # DEFAULT_REGISTRY + all built-in tools registered
│   │   ├── base.py               # BaseTool ABC, ToolContext
│   │   ├── registry.py           # ToolRegistry (plug-and-play)
│   │   ├── dispatcher.py         # ToolDispatcher: context tiers, approval flow, monitoring
│   │   ├── config_loader.py      # AgentToolConfig: loads agent_tools.json
│   │   ├── market/               # get_candles, calculate_indicator
│   │   ├── account/              # get_account_status, get_open_positions
│   │   ├── orderbook/            # get_order_book
│   │   ├── trading/              # place_order, close_position
│   │   └── system/               # raise_alarm, trigger_sync
│   ├── management/
│   │   ├── api.py                # FastAPI endpoints
│   │   └── server.py             # ManagementServer (uvicorn background task)
│   ├── monitoring/
│   │   └── bus.py                # MonitoringBus (fire-and-forget, bounded queues)
│   ├── config/                   # Settings, YAML loader
│   ├── registry/                 # Plugin registry for adapters
│   ├── utils/                    # Logging, metrics, retry, time utils
│   ├── bootstrap.py              # Wires all agents, adapters, and routing together
│   └── main.py                   # Entry point
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
