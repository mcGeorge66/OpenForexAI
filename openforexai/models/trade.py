from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """All order types that the system supports.

    Trailing stop is optional — only brokers that support it (e.g. OANDA)
    will implement it; others will raise NotImplementedError.
    """

    MARKET = "MARKET"               # execute immediately at current price
    LIMIT = "LIMIT"                 # enter at limit_price (better-than-market)
    STOP = "STOP"                   # enter at stop_price (worse-than-market, breakout)
    STOP_LIMIT = "STOP_LIMIT"       # stop triggers a limit order at limit_price
    TRAILING_STOP = "TRAILING_STOP" # SL follows price at trailing_distance pips


class OrderStatus(str, Enum):
    PENDING = "PENDING"             # sent to broker, not yet confirmed
    OPEN = "OPEN"                   # live position at the broker
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CLOSED = "CLOSED"               # position fully closed
    REJECTED = "REJECTED"           # broker rejected the order
    CANCELLED = "CANCELLED"         # cancelled before fill


class CloseReason(str, Enum):
    SL_HIT = "SL_HIT"                   # stop-loss triggered by broker
    TP_HIT = "TP_HIT"                   # take-profit triggered by broker
    TRAILING_STOP = "TRAILING_STOP"     # trailing stop triggered
    AGENT_CLOSED = "AGENT_CLOSED"       # trading agent decided to close
    BROKER_CLOSED = "BROKER_CLOSED"     # broker forced close (margin call, etc.)
    SYNC_DETECTED = "SYNC_DETECTED"     # detected as closed during sync check


class TradeStatus(str, Enum):
    """Kept for backward compatibility with TradeResult."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class TradeSignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair: str
    direction: TradeDirection
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    generated_at: datetime
    agent_id: str
    prompt_version: int | None = None   # version of the prompt that generated this


class TradeOrder(BaseModel):
    """Extended order with full order-type support."""

    signal: TradeSignal
    order_type: OrderType = OrderType.MARKET
    units: int
    risk_pct: float
    approved_by: str                            # supervisor agent ID

    # ── Price fields (only relevant for non-MARKET orders) ──────────────────
    limit_price: Decimal | None = None          # LIMIT, STOP_LIMIT
    stop_price: Decimal | None = None           # STOP, STOP_LIMIT
    trailing_stop_distance: Decimal | None = None  # TRAILING_STOP, in pips


class TradeResult(BaseModel):
    """Broker response after placing / closing an order."""

    id: UUID = Field(default_factory=uuid4)
    order: TradeOrder
    broker_order_id: str
    broker_name: str = ""                       # short_name of the broker adapter
    status: TradeStatus
    fill_price: Decimal | None = None
    pnl: Decimal | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None             # raw string from broker or CloseReason value


class Position(BaseModel):
    """Live position as reported by the broker."""

    broker_position_id: str
    broker_name: str = ""
    pair: str
    direction: TradeDirection
    units: int
    open_price: Decimal
    current_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    unrealized_pnl: Decimal
    opened_at: datetime


class OrderBookEntry(BaseModel):
    """Authoritative local record of every order / position.

    One entry is created when a signal is approved and an order is placed.
    It is updated as the trade progresses (fill confirmation, close, sync).
    The market_context_snapshot field captures everything the agent knew at
    decision time — this is the primary input for the OptimizationAgent.
    """

    id: UUID = Field(default_factory=uuid4)

    # ── Broker context ────────────────────────────────────────────────────────
    broker_name: str                            # which broker holds this trade
    broker_order_id: str | None = None          # set once broker confirms

    # ── Trade definition ──────────────────────────────────────────────────────
    pair: str
    direction: TradeDirection
    order_type: OrderType
    units: int

    # ── Prices ────────────────────────────────────────────────────────────────
    requested_price: Decimal                    # price the agent calculated/asked for
    fill_price: Decimal | None = None           # actual fill confirmed by broker
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    trailing_stop_distance: Decimal | None = None   # pips
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    # ── Status ────────────────────────────────────────────────────────────────
    status: OrderStatus = OrderStatus.PENDING

    # ── Agent context at entry (critical for OptimizationAgent) ──────────────
    agent_id: str
    prompt_version: int | None = None
    entry_reasoning: str                        # agent's narrative for entering
    signal_confidence: float
    market_context_snapshot: dict               # last M5 candle + key indicator values
                                                # at the moment of signal generation

    # ── Timing ────────────────────────────────────────────────────────────────
    requested_at: datetime
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    last_broker_sync: datetime | None = None

    # ── Exit ──────────────────────────────────────────────────────────────────
    close_reason: CloseReason | None = None
    close_price: Decimal | None = None
    close_reasoning: str | None = None          # agent quick-note on what happened
                                                # (Option B) or auto-filled label

    # ── P&L ───────────────────────────────────────────────────────────────────
    pnl_pips: Decimal | None = None
    pnl_account_currency: Decimal | None = None

    # ── Sync ──────────────────────────────────────────────────────────────────
    sync_confirmed: bool = False                # True once broker has confirmed position

