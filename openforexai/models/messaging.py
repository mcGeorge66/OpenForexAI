from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # ── Market data / candle pipeline ─────────────────────────────────────────
    M5_CANDLE_AVAILABLE = "m5_candle_available"     # broker adapter → event bus
    CANDLE_GAP_DETECTED = "candle_gap_detected"     # adapter signals a gap in M5 sequence
    CANDLE_REPAIR_REQUESTED = "candle_repair_requested"  # data container → broker
    CANDLE_REPAIR_COMPLETED = "candle_repair_completed"  # data container broadcasts

    # ── Account status ────────────────────────────────────────────────────────
    ACCOUNT_STATUS_UPDATED = "account_status_updated"

    # ── Trading flow ──────────────────────────────────────────────────────────
    MARKET_DATA_UPDATED = "market_data_updated"     # kept for backward compat
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_APPROVED = "signal_approved"
    SIGNAL_REJECTED = "signal_rejected"
    ORDER_PLACED = "order_placed"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_BREACH = "risk_breach"

    # ── Order book sync ───────────────────────────────────────────────────────
    ORDER_BOOK_SYNC_DISCREPANCY = "order_book_sync_discrepancy"
    # payload: {broker_name, entry_id, pair, close_reason, close_price, pnl,
    #           request_agent_reasoning: bool}
    ORDER_BOOK_CLOSE_REASONING = "order_book_close_reasoning"
    # agent response: {entry_id, close_reasoning}

    # ── Technical analysis (request / response) ───────────────────────────────
    ANALYSIS_REQUESTED = "analysis_requested"
    ANALYSIS_RESULT = "analysis_result"

    # ── Optimization ──────────────────────────────────────────────────────────
    OPTIMIZATION_COMPLETE = "optimization_complete"
    PROMPT_UPDATED = "prompt_updated"

    # ── Agent config bootstrap ────────────────────────────────────────────────
    AGENT_CONFIG_REQUESTED = "agent_config_requested"   # agent → ConfigService
    AGENT_CONFIG_RESPONSE  = "agent_config_response"    # ConfigService → agent

    # ── Agent query (external → agent → external) ────────────────────────────
    AGENT_QUERY          = "agent_query"           # management API → specific agent
    AGENT_QUERY_RESPONSE = "agent_query_response"  # agent → management API handler

    # ── System / management ───────────────────────────────────────────────────
    ROUTING_RELOAD_REQUESTED = "routing_reload_requested"


class AgentMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    source_agent_id: str
    target_agent_id: str | None = None      # None = broadcast to all subscribers
    payload: dict
    correlation_id: str | None = None       # ties request/response pairs
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MessageEnvelope(BaseModel):
    message: AgentMessage
    acknowledged: bool = False
    processed_at: datetime | None = None
    error: str | None = None

