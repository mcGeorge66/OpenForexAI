from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # Market data
    MARKET_DATA_UPDATED = "market_data_updated"

    # Trading flow
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_APPROVED = "signal_approved"
    SIGNAL_REJECTED = "signal_rejected"
    ORDER_PLACED = "order_placed"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_BREACH = "risk_breach"

    # Technical analysis (request/response)
    ANALYSIS_REQUESTED = "analysis_requested"
    ANALYSIS_RESULT = "analysis_result"

    # Optimization
    OPTIMIZATION_COMPLETE = "optimization_complete"
    PROMPT_UPDATED = "prompt_updated"


class AgentMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    source_agent_id: str
    target_agent_id: str | None = None  # None = broadcast
    payload: dict
    correlation_id: str | None = None  # ties request/response pairs
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MessageEnvelope(BaseModel):
    message: AgentMessage
    acknowledged: bool = False
    processed_at: datetime | None = None
    error: str | None = None
