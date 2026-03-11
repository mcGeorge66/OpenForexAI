# openforexai/models — Domain Models

Pydantic v2 data models for all system data. These are the canonical data structures used throughout the application — from market data to trade orders, agent decisions, and observability events.

All models use Pydantic v2 with strict validation. No raw dicts are passed between components; everything is a typed model.

## Files

| File | Key Models |
|---|---|
| `messaging.py` | `AgentMessage`, `EventType`, `MessageEnvelope` |
| `market.py` | `Candle`, `Tick`, `MarketSnapshot` |
| `trade.py` | `TradeOrder`, `Position`, `TradeResult`, `OrderBookEntry` |
| `account.py` | `AccountStatus` |
| `agent.py` | `AgentDecision`, `AgentRole` |
| `analysis.py` | `AnalysisResult`, `TechnicalAnalysis` |
| `risk.py` | `RiskParameters`, `RiskAssessment`, `CorrelationMatrix` |
| `optimization.py` | `PromptCandidate`, `BacktestResult`, `TradePattern` |
| `monitoring.py` | `MonitoringEvent`, `MonitoringEventType` |

---

## `messaging.py`

The core communication primitives.

### `EventType` (Enum)

All event types in the system. Key events:

**Market data pipeline:**
- `m5_candle_available` — broker adapter → DataContainer, agents
- `candle_gap_detected` — DataContainer signals a gap
- `candle_repair_requested` / `candle_repair_completed`

**Trading flow:**
- `signal_generated` — AA publishes a trade signal → supervisor check
- `signal_approved` / `signal_rejected` — supervisor → BA
- `order_placed` / `position_opened` / `position_closed`
- `risk_breach` — risk engine fires

**Analysis:**
- `analysis_requested` / `analysis_result` — BA requests, AA responds

**Agent lifecycle:**
- `agent_config_requested` — agent → ConfigService on startup
- `agent_config_response` — ConfigService → agent (direct)
- `agent_query` — Management API → specific agent
- `agent_query_response` — agent → Management API handler

**System:**
- `account_status_updated`, `order_book_sync_discrepancy`
- `routing_reload_requested`
- `prompt_updated`, `optimization_complete`

### `AgentMessage`

Every message on the EventBus is an `AgentMessage`:

```python
class AgentMessage(BaseModel):
    id: UUID                   # auto-generated
    event_type: EventType
    source_agent_id: str       # sender
    target_agent_id: str | None  # None = broadcast; set = direct delivery
    payload: dict              # event-specific data
    correlation_id: str | None # ties request/response pairs
    created_at: datetime       # UTC
```

---

## `market.py`

### `Candle`

OHLCV bar from any timeframe:

```python
class Candle(BaseModel):
    timestamp: datetime    # open time (UTC)
    timeframe: str         # "M5", "M15", "H1", "H4", "D1"
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float | None   # broker spread in pips (OANDA provides this)
    broker_name: str | None
    pair: str | None
```

### `Tick`

High-frequency bid/ask data (for spreads and real-time pricing).

### `MarketSnapshot`

Aggregated view of all timeframes for a pair at one point in time:
- `candles: dict[str, list[Candle]]` — keyed by timeframe
- `latest_tick: Tick | None`
- `session: str` — current forex trading session (Asian/European/US/overlap)

---

## `trade.py`

### Enums

| Enum | Values |
|---|---|
| `TradeDirection` | `LONG`, `SHORT` |
| `OrderType` | `MARKET`, `LIMIT`, `STOP` |
| `TradeStatus` | `PENDING`, `OPEN`, `CLOSED`, `CANCELLED` |
| `OrderStatus` | `PENDING`, `FILLED`, `PARTIALLY_FILLED`, `CANCELLED` |
| `CloseReason` | `TAKE_PROFIT`, `STOP_LOSS`, `MANUAL`, `TIMEOUT`, `RISK_BREACH` |

### Key Models

```python
class TradeOrder(BaseModel):
    pair: str
    direction: TradeDirection
    order_type: OrderType
    size: float              # in units (e.g., 1000 for a micro lot)
    price: float | None      # None for market orders
    stop_loss: float | None
    take_profit: float | None
    reasoning: str | None    # LLM's rationale for this trade

class Position(BaseModel):
    entry_id: str
    pair: str
    direction: TradeDirection
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    open_time: datetime
    broker_name: str

class OrderBookEntry(BaseModel):
    entry_id: str
    pair: str
    direction: TradeDirection
    size: float
    entry_price: float
    status: TradeStatus
    stop_loss: float | None
    take_profit: float | None
    open_time: datetime
    close_time: datetime | None
    realized_pnl: float | None
    close_reason: CloseReason | None
```

---

## `account.py`

### `AccountStatus`

```python
class AccountStatus(BaseModel):
    broker_name: str
    balance: float           # account balance (no open P&L)
    equity: float            # balance + unrealized P&L
    margin_used: float       # margin locked by open positions
    margin_available: float  # free margin
    nav: float               # net asset value
    open_positions: int      # count of open positions
    timestamp: datetime
```

---

## `agent.py`

### `AgentDecision`

Persisted to the database after each agent cycle:

```python
class AgentDecision(BaseModel):
    agent_id: str
    trigger: str             # event_type that triggered this cycle
    decision_type: str       # "analysis" | "trade" | "query_response"
    payload: dict            # the agent's output
    reasoning: str | None    # extracted reasoning text
    input_tokens: int
    output_tokens: int
    tool_calls: int
    created_at: datetime
```

---

## `risk.py`

```python
class RiskParameters(BaseModel):
    max_drawdown_pct: float     # e.g. 5.0 = 5% max drawdown
    max_position_size: float    # max size per trade
    max_open_positions: int
    max_correlated_exposure: float   # max exposure to correlated pairs
    risk_per_trade_pct: float   # % of balance risked per trade

class RiskAssessment(BaseModel):
    approved: bool
    reason: str
    risk_score: float        # 0.0–1.0
```

---

## `optimization.py`

```python
class PromptCandidate(BaseModel):
    candidate_id: str
    parent_id: str | None
    system_prompt: str
    generation: int
    fitness_score: float | None
    backtest_result_id: str | None

class BacktestResult(BaseModel):
    result_id: str
    candidate_id: str
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    start_date: datetime
    end_date: datetime

class TradePattern(BaseModel):
    pattern_id: str
    pattern_type: str        # e.g. "breakout", "reversal", "trend_continuation"
    pair: str
    timeframe: str
    conditions: dict
    occurrence_count: int
    win_rate: float
```

---

## `monitoring.py`

### `MonitoringEvent`

```python
class MonitoringEvent(BaseModel):
    id: UUID                       # auto-generated
    timestamp: datetime            # UTC
    source_module: str             # "agent", "broker", "eventbus", etc.
    event_type: MonitoringEventType
    broker_name: str | None
    pair: str | None
    payload: dict                  # event-specific data
```

The `payload` structure varies by event type. For `LLM_RESPONSE` it includes `content`, `tokens`, `stop_reason`; for `M5_CANDLE_FETCHED` it includes `open`, `high`, `low`, `close`, `volume`.

