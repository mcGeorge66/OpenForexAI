# OpenForexAI

**Autonomous multi-agent LLM-based forex trading system**

Currency markets never sleep, and neither does OpenForexAI. Instead of hardcoding
"buy when RSI drops below 30", the system lets a large language model read the market,
reason about risk, and decide — just like a human trader would, but around the clock.

A fleet of AI agents divides the work: **Analysis Agents** watch each currency pair,
a **Broker Agent** controls risk and executes trades, and a **Global Optimization Agent**
continuously rewrites the strategy prompts to improve future decisions.

All agent behaviour is defined entirely by configuration — one JSON file, one module
config per LLM/broker. No code changes needed to add a pair, switch providers, or
change a strategy.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Agent system](#agent-system)
3. [Config-driven bootstrap](#config-driven-bootstrap)
4. [Module system (LLM and Broker)](#module-system)
5. [Tool-use loop](#tool-use-loop)
6. [Event bus and routing](#event-bus-and-routing)
7. [Tool system](#tool-system)
8. [Indicator plugin system](#indicator-plugin-system)
9. [Broker adapters](#broker-adapters)
10. [Data pipeline](#data-pipeline)
11. [LLM adapters](#llm-adapters)
12. [Monitoring](#monitoring)
13. [Management API](#management-api)
14. [Database](#database)
15. [Self-optimisation loop](#self-optimisation-loop)
16. [Configuration](#configuration)
17. [Installation](#installation)
18. [Quick start](#quick-start)
19. [Module tests](#module-tests)
20. [Running tests](#running-tests)
21. [Project layout](#project-layout)
22. [Tech stack](#tech-stack)

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         config/system.json5                           │
│  All agents, modules, prompts, tools, timers — one source of truth   │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   ConfigService          │
                    │   SYSTM_ALL..._GA_CFGSV  │
                    │   answers AGENT_CONFIG_  │
                    │   REQUESTED on startup   │
                    └────────────┬────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────┐
│                       Rule-based EventBus                            │
│  JSON routing rules · per-agent queues · direct target_agent_id      │
│  wildcard fan-out · hot-reload · MonitoringBus integration           │
└───┬──────────────────────┬────────────────────┬───────────────────────┘
    │                      │                    │
    ▼                      ▼                    ▼
OANDA_EURUSD_AA_ANLYS  OANDA_ALL..._BA_TRADE  GLOBL_ALL..._GA_OPTIM
OANDA_GBPUSD_AA_ANLYS  (Broker Agent,         (Global Optimization
OANDA_USDJPY_AA_ANLYS  per broker)            Agent)
(Analysis Agents,
 per pair)
    │
    ▼  native tool_use API (Anthropic / OpenAI)
ToolDispatcher  ←  tool_config per agent (from system.json5)
    ├── get_candles          ← DataContainer
    ├── calculate_indicator  ← IndicatorToolset
    ├── get_order_book       ← Repository
    ├── place_order          ← BrokerAdapter
    ├── close_position       ← BrokerAdapter
    ├── get_account_status   ← BrokerAdapter
    ├── get_open_positions   ← BrokerAdapter
    ├── raise_alarm          → MonitoringBus
    └── trigger_sync         ← BrokerAdapter

BrokerAdapter  (one per broker, shared across pairs)
    ├── _m5_loop       → publishes M5_CANDLE_AVAILABLE every 5 min
    ├── _account_poll  → updates AccountStatus
    └── _sync_loop     → detects SL/TP hits, publishes SYNC_DISCREPANCY

DataContainer  ←  M5_CANDLE_AVAILABLE
    └── derives M15, M30, H1, H4, D1 from M5 via Resampler (on-demand)

ManagementAPI (localhost:8765 / FastAPI)
    ├── GET  /monitoring/events   ← polled by tools/monitor.py
    ├── POST /events              ← inject events from outside
    ├── POST /routing/reload      ← hot-reload routing table
    └── GET  /health|metrics|agents|tools|indicators
```

All agents run concurrently as asyncio tasks in a single process. They communicate
exclusively through typed `AgentMessage` events — no direct method calls between agents.

---

## Agent system

### The single Agent class

There is **one Python class** for all agent types: `openforexai/agents/agent.py`.

The difference between an Analysis Agent (AA), Broker Agent (BA), and Global Agent (GA)
is entirely in their configuration — not in code. The config determines:

- Which LLM module to use
- Which broker module to use (AA/BA only)
- Which currency pair to watch (AA only)
- Which tools are available
- Whether to run on a timer, on events, or both
- The system prompt

### Agent ID format

```
[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]
```

| Segment | Length | Padding | Examples |
|---|---|---|---|
| BROKER | 5 chars | `.` right-pad | `OANDA`, `MT5..`, `GLOBL`, `SYSTM` |
| PAIR | 6 chars | `.` right-pad | `EURUSD`, `USDJPY`, `ALL...` |
| TYPE | 2 chars | none | `AA`, `BA`, `GA` |
| NAME | 1–5 chars | none | `ANLYS`, `TRADE`, `OPTIM` |

**Default agents (defined in `config/system.json5`):**

| Agent ID | Type | Role |
|---|---|---|
| `OANDA_EURUSD_AA_ANLYS` | AA | Analysis agent for EURUSD on OANDA |
| `OANDA_GBPUSD_AA_ANLYS` | AA | Analysis agent for GBPUSD on OANDA |
| `OANDA_USDJPY_AA_ANLYS` | AA | Analysis agent for USDJPY on OANDA |
| `OANDA_ALL..._BA_TRADE` | BA | Broker agent for OANDA (all pairs) |
| `GLOBL_ALL..._GA_OPTIM` | GA | Global optimization agent |
| `SYSTM_ALL..._GA_CFGSV` | GA | ConfigService (system-internal) |

### Communication topology

```
AA  ←→  BA   (same broker, bidirectional)
BA  ←→  GA   (any broker ↔ any global agent)
GA  →   ALL  (broadcast to all agents)
```

---

## Config-driven bootstrap

Every agent follows the same startup sequence regardless of type:

```
1. Agent created with:  (agent_id, bus, data_container, repository)
       │
       ▼
2. Agent publishes:  AGENT_CONFIG_REQUESTED
                     payload: {agent_id}
       │
       ▼
3. ConfigService replies:  AGENT_CONFIG_RESPONSE  (direct, bypasses routing)
                           payload: {config, modules}
       │
       ▼
4. Agent initialises:
   - LLM instance  ← RuntimeRegistry.get_llm(config["llm"])
   - Broker instance  ← RuntimeRegistry.get_broker(config["broker"])
   - ToolDispatcher  ← config["tool_config"]
   - system_prompt, event_triggers, timer
       │
       ▼
5. Agent runs:
   ├── timer loop (if timer.enabled)
   └── message loop (delivers EventBus messages)
```

This means: **adding a new agent requires zero code changes** — only an entry in
`config/system.json5`.

---

## Module system

LLM providers and brokers are **external modules** with their own config files.
The main system only knows their name — all connection details are encapsulated.

### LLM modules (`config/modules/llm/`)

```json
// config/modules/llm/anthropic_claude.json5
{
  "adapter":         "anthropic",
  "api_key":         "${ANTHROPIC_API_KEY}",
  "model":           "${ANTHROPIC_MODEL:-claude-opus-4-6}",
  "temperature":     0.1,
  "max_tokens":      1024,
  "retry_attempts":  3
}
```

### Broker modules (`config/modules/broker/`)

```json
// config/modules/broker/oanda.json5
{
  "adapter":    "oanda",
  "api_key":    "${OANDA_API_KEY}",
  "account_id": "${OANDA_ACCOUNT_ID}",
  "practice":   true
}
```

All string values support `${VAR_NAME}` and `${VAR_NAME:-default}` env-var substitution.

### RuntimeRegistry

At bootstrap, module instances are created once and stored in `RuntimeRegistry`:

```python
RuntimeRegistry.register_llm("anthropic_claude", AnthropicLLMProvider(...))
RuntimeRegistry.register_broker("oanda", OANDABroker(...))
```

Agents look up their instance by name after receiving their config.

---

## Tool-use loop

Every agent cycle (timer or event-triggered) runs the same loop:

```
Agent sends initial message:
"[2026-02-27 09:14:00 UTC] Periodic analysis cycle. Review current
 market conditions and act if appropriate."
       │
       ▼
  LLM responds with tool calls:
  ┌─────────────────────────────────────────────┐
  │  turn 1:  get_candles(H1, 50)               │
  │           calculate_indicator(RSI, 14, H1)  │
  │  turn 2:  get_account_status()              │
  │           get_open_positions()              │
  │  turn 3:  place_order(BUY, MARKET, ...)     │
  │           [or: raise_alarm / no action]     │
  │  turn N:  LLM returns final text → done     │
  └─────────────────────────────────────────────┘
```

The LLM decides **which data to fetch** and **what action to take** — there is no
pre-determined context-building step.

**Context budget tiers** (configured per agent in `system.json5`):
- `0–84%` budget: all allowed tools visible
- `85–100%` budget: safety tools only (e.g. `raise_alarm`)

---

## Event bus and routing

The `EventBus` is a rule-based asyncio pub/sub dispatcher with **three delivery modes**:

### 1. Direct targeting (highest priority)

If `message.target_agent_id` is set, the message is delivered directly to that agent's
queue — **no routing rules evaluated**. Used by ConfigService for config responses.

### 2. Agent queue delivery

The routing table (`config/RunTime/event_routing.json5`) determines which agent queues receive
each published message.

### 3. Legacy handler delivery

Infrastructure components (`DataContainer`, `BrokerBase`) subscribe via
`bus.subscribe(EventType.X, handler)` — fire unconditionally, bypass routing rules.

### Routing rules

```json
{
  "rules": [
    {
      "id": "config_request_to_service",
      "event": "agent_config_requested",
      "from": "*",
      "to": "SYSTM_ALL..._GA_CFGSV",
      "priority": 1
    },
    {
      "id": "aa_signal_to_ba",
      "event": "signal_generated",
      "from": "*_*_AA_*",
      "to": "{sender.broker}_ALL..._BA_*",
      "priority": 20
    }
  ]
}
```

**`to` target types:**

| Value | Effect |
|---|---|
| Literal ID | Deliver to that single agent |
| `{sender.broker}_ALL..._BA_*` | Template + wildcard fan-out |
| `*_*_AA_*` | Fan-out to all matching registered agents |
| `*` | Broadcast to all agents |
| `@handlers` | Legacy handler-subscriber delivery only |

**Hot-reload:** `POST /routing/reload` atomically reloads `event_routing.json5`.

---

## Tool system

OpenForexAI uses the **native tool-use API** of each LLM provider (Anthropic `tool_use`,
OpenAI `function_calling`) — no JSON schema prompt hacks.

### Built-in tools

| Tool | Category | Description |
|---|---|---|
| `get_candles` | Market | OHLCV candle data at any timeframe (M5–D1), 1–500 bars |
| `calculate_indicator` | Market | RSI, ATR, SMA, EMA, BB, VWAP with `history` support |
| `get_account_status` | Account | Balance, equity, margin, leverage, trade_allowed |
| `get_open_positions` | Account | All open positions with unrealised P&L |
| `get_order_book` | Order book | Internal order book with reasoning and P&L |
| `place_order` | Trading | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP |
| `close_position` | Trading | Close any open position by broker ID |
| `raise_alarm` | System | Severity-levelled alarm → MonitoringBus + logging |
| `trigger_sync` | System | Manual order book sync with the broker |

### Per-agent tool configuration (in `system.json5`)

```json
"OANDA_EURUSD_AA_ANLYS": {
  "tool_config": {
    "allowed_tools": ["get_candles", "calculate_indicator", "get_order_book", "raise_alarm"],
    "context_tiers": {"0": "all", "85": "safety"},
    "tier_tools": {
      "all":    ["get_candles", "calculate_indicator", "get_order_book", "raise_alarm"],
      "safety": ["raise_alarm"]
    },
    "max_tool_turns": 10,
    "max_tokens": 4096
  }
}
```

### Adding a custom tool

```python
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import BaseTool, ToolContext

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful."
    input_schema = {"type": "object", "properties": {"param": {"type": "string"}}, "required": ["param"]}

    async def execute(self, arguments, context: ToolContext):
        return {"result": f"processed: {arguments['param']}"}

DEFAULT_REGISTRY.register(MyTool())
```

Add `"my_tool"` to `allowed_tools` for any agent in `system.json5`.

---

## Indicator plugin system

The `DataContainer` holds **only raw candle data**. All indicators are computed
**on-demand** when the LLM requests them via `calculate_indicator`.

The `history` parameter returns a series of consecutive values (oldest first):

```python
# Single latest RSI value
rsi = toolset.calculate("RSI", 14, "H1", "EURUSD")
# → 62.4

# Last 5 values — is momentum accelerating?
rsi_series = toolset.calculate("RSI", 14, "H1", "EURUSD", history=5)
# → [48.2, 51.7, 55.3, 59.1, 62.4]
```

### Built-in indicators

`SMA`, `EMA`, `RSI`, `ATR`, `BB` (Bollinger Bands), `VWAP`

---

## Broker adapters

Each broker adapter handles **all configured pairs** for that broker.
Background tasks run per pair:

| Task | Interval | Description |
|---|---|---|
| `_m5_loop` | every 5-min boundary +10 s | Fetches M5 candle, detects gaps, publishes `M5_CANDLE_AVAILABLE` |
| `_account_poll_loop` | 60 s | Fetches balance, equity, margin, leverage |
| `_sync_loop` | 60 s | Compares broker vs. internal order book, detects SL/TP hits |

| Adapter | Notes |
|---|---|
| **OANDA** | REST v20 API, practice and live, all 5 order types |
| **MetaTrader 5** | Windows only, `MetaTrader5` package required |

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
        ├──► CANDLE_GAP_DETECTED → repair (back-fills M5 bars)
        │
        ▼
DataContainer.get_candles(broker, pair, timeframe)
        │  M5: direct · M15/M30/H1/H4/D1: derived via Resampler on-demand
        ▼
IndicatorToolset.calculate(indicator, period, tf, pair, history)
```

---

## LLM adapters

| Adapter | Provider | Default model | Tool-use |
|---|---|---|---|
| `AnthropicLLMProvider` | Anthropic | `claude-opus-4-6` | Native `tool_use` |
| `OpenAILLMProvider` | OpenAI | `gpt-4o` | Native `function_calling` |
| `LMStudioLLMProvider` | Local (LM Studio) | any GGUF | OpenAI-compatible |

All adapters implement `AbstractLLMProvider` with three methods:

- `complete(system, user, ...)` — plain text completion
- `complete_structured(system, user, schema)` — JSON-schema structured output
- `complete_with_tools(system, messages, tools, ...)` — native multi-turn tool-use loop

---

## Monitoring

### MonitoringBus

Fire-and-forget observability sink — every component emits `MonitoringEvent` objects
without blocking.

**New:** a ring buffer stores the last **1000 events** in memory, accessible via
`monitoring_bus.recent_events(since=..., limit=...)`. This powers HTTP polling.

### Console monitor — `tools/monitor.py`

```bash
# All events, live
python tools/monitor.py

# Filter by event type
python tools/monitor.py --filter llm_response,tool_call_started,tool_call_completed

# Filter by pair
python tools/monitor.py --pair EURUSD

# Custom host/port and faster polling
python tools/monitor.py --host 127.0.0.1 --port 8765 --interval 1.0
```

Sample output:
```
OpenForexAI Monitor — http://127.0.0.1:8765
────────────────────────────────────────────────────────────────────────────────
2026-02-27 09:14:01  broker_connected           [OANDA]       broker.oanda
2026-02-27 09:14:05  llm_request                [OANDA/EURUSD] agent:OANDA_EURUSD_AA_ANLYS  turn=0
2026-02-27 09:14:07  tool_call_started          [OANDA/EURUSD] tool_dispatcher  name='get_candles'
2026-02-27 09:14:07  tool_call_completed        [OANDA/EURUSD] tool_dispatcher  name='get_candles'
2026-02-27 09:14:09  llm_response               [OANDA/EURUSD] agent:OANDA_EURUSD_AA_ANLYS  input_tokens=1204 output_tokens=87
2026-02-27 09:14:11  agent_signal_generated     [OANDA/EURUSD] agent:OANDA_EURUSD_AA_ANLYS
```

Color coding: green = OK, yellow = warning, red = error, blue = tool calls, cyan = LLM.

---

## Management API

FastAPI HTTP server on `localhost:8765` (configurable in `system.json5`).

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Status, uptime, agent count, rule count |
| `/metrics` | GET | Agent queue depths, uptime counters |
| `/agents` | GET | All registered agents with queue depths |
| `/agents/{id}` | GET | Single agent info |
| `/routing/rules` | GET | Active routing rules |
| `/routing/reload` | POST | Hot-reload `event_routing.json5` |
| `/events` | POST | Inject an arbitrary event into the EventBus |
| `/monitoring/events` | GET | Recent monitoring events (ring buffer, for `monitor.py`) |
| `/indicators` | GET | Registered indicator plugins |
| `/tools` | GET | Registered tools |
| `/docs` | GET | Interactive Swagger UI |

**Query params for `/monitoring/events`:**
- `since` — ISO-8601 UTC timestamp; only events after this are returned
- `limit` — max events returned (default 100, max 1000)

Optional API key auth via `X-API-Key` header (`MANAGEMENT_API_KEY` env var).

---

## Database

| Backend | Use case |
|---|---|
| **SQLite** | Development, single-machine |
| **PostgreSQL** (asyncpg) | Production |

| Table | Description |
|---|---|
| `candles_{broker}_{pair}_{tf}` | Candle history per broker/pair/timeframe |
| `order_book` | Full trade lifecycle with reasoning, P&L, close reason |
| `account_status` | Historical account status snapshots |
| `agent_decisions` | Audit trail of every LLM cycle with tokens and latency |
| `prompt_candidates` | Versioned system prompts with backtest scores |
| `patterns` | Detected trade patterns |
| `backtest_results` | Optimisation run results |

---

## Self-optimisation loop

```
Closed trades (≥ 20 per pair)
        │
        ▼
GLOBL_ALL..._GA_OPTIM  (triggered by timer every 6 h)
  uses: get_order_book → analyse → generate new prompt candidate
        │
        ▼
delta PnL > 0?
  yes → broadcast PROMPT_UPDATED → all AA agents hot-swap prompt
  no  → discard candidate, keep current prompt
```

All candidates and results are persisted for full reproducibility.

---

## Configuration

### `config/system.json5` — central config

One file contains everything: all agents, their tools, prompts, timers, and module
references. The system reads only this file at startup.

```json
{
  "system": {
    "log_level": "INFO",
    "management_api": {"host": "127.0.0.1", "port": 8765}
  },
  "database": {
    "backend": "sqlite",
    "sqlite_path": "${OPENFOREXAI_DB_PATH:-./data/openforexai.db}"
  },
  "modules": {
    "llm":    {"anthropic_claude": "config/modules/llm/anthropic_claude.json5"},
    "broker": {"oanda": "config/modules/broker/oanda.json5"}
  },
  "agents": {
    "OANDA_EURUSD_AA_ANLYS": {
      "type": "AA",
      "llm": "anthropic_claude",
      "broker": "oanda",
      "pair": "EURUSD",
      "timer": {"enabled": true, "interval_seconds": 300},
      "event_triggers": ["m5_candle_available", "prompt_updated"],
      "system_prompt": "You are a professional Forex analysis agent for EURUSD...",
      "tool_config": { ... }
    }
  }
}
```

All string values support `${VAR_NAME}` and `${VAR_NAME:-default}` env-var substitution.

### Module configs

```
config/
├── system.json5                      ← main config
├── modules/
│   ├── llm/
│   │   └── anthropic_claude.json5    ← LLM credentials + settings
│   └── broker/
│       ├── oanda.json5               ← OANDA credentials
│       └── mt5.json5                 ← MT5 credentials
└── event_routing.json5               ← routing rules (hot-reloadable)
```

### Environment variables

Set credentials in a `.env` file or export directly:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OANDA_API_KEY=...
OANDA_ACCOUNT_ID=101-001-...
OPENFOREXAI_LOG_LEVEL=INFO         # optional
OPENFOREXAI_DB_PATH=./data/db.sqlite  # optional
MANAGEMENT_API_KEY=secret          # optional, enables API auth
```

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/GeorgGebert/OpenForexAI.git
cd OpenForexAI

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[api]"     # core + FastAPI management server

# Optional extras:
pip install -e ".[mt5]"     # MetaTrader 5 (Windows only)
pip install -e ".[dev]"     # pytest, ruff, mypy
pip install -e ".[all]"     # everything
```

---

## Quick start

```bash
# 1. Set credentials
export ANTHROPIC_API_KEY=sk-ant-...
export OANDA_API_KEY=...
export OANDA_ACCOUNT_ID=101-001-...

# 2. Run database migrations
python scripts/db_migrate.py

# 3. Start the system
openforexai
# or: python -m openforexai.main
```

The system will:
- Load `config/system.json5`
- Start all configured agents (they each request their own config via the EventBus)
- Start broker background tasks (M5 streaming, account poll, sync)
- Start the Management API on `localhost:8765`
- Start the ConfigService

In a second terminal, open the live monitor:

```bash
python tools/monitor.py
```

---

## Module tests

Test an LLM or broker module independently — no full system startup needed:

```bash
# Test LLM connectivity and tool-use
python test_llm.py anthropic_claude

# Test broker connectivity, account status, and candle fetching
python test_broker.py oanda
```

Both scripts exit with code `0` on success, `1` on failure.

---

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


