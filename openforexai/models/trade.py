from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
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


class TradeOrder(BaseModel):
    signal: TradeSignal
    units: int
    risk_pct: float
    approved_by: str  # supervisor agent ID


class TradeResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    order: TradeOrder
    broker_order_id: str
    status: TradeStatus
    fill_price: Decimal | None = None
    pnl: Decimal | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None  # TP | SL | manual | timeout


class Position(BaseModel):
    broker_position_id: str
    pair: str
    direction: TradeDirection
    units: int
    open_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    opened_at: datetime
