from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MonitoringEventType(str, Enum):
    # ── Broker connection ─────────────────────────────────────────────────────
    BROKER_CONNECTED = "broker_connected"
    BROKER_DISCONNECTED = "broker_disconnected"
    BROKER_RECONNECTING = "broker_reconnecting"
    BROKER_ERROR = "broker_error"

    # ── M5 candle pipeline ────────────────────────────────────────────────────
    M5_CANDLE_FETCHED = "m5_candle_fetched"       # adapter fetched from broker
    M5_CANDLE_QUEUED = "m5_candle_queued"         # adapter published to event bus
    CANDLE_GAP_DETECTED = "candle_gap_detected"   # gap in M5 sequence detected
    CANDLE_REPAIR_STARTED = "candle_repair_started"
    CANDLE_REPAIR_COMPLETED = "candle_repair_completed"
    CANDLE_REPAIR_FAILED = "candle_repair_failed"
    TIMEFRAME_CALCULATED = "timeframe_calculated" # higher TF derived from M5

    # ── Account status ────────────────────────────────────────────────────────
    ACCOUNT_STATUS_UPDATED = "account_status_updated"
    ACCOUNT_POLL_ERROR = "account_poll_error"

    # ── Order book ────────────────────────────────────────────────────────────
    ORDER_BOOK_ENTRY_CREATED = "order_book_entry_created"
    ORDER_BOOK_ENTRY_UPDATED = "order_book_entry_updated"
    ORDER_BOOK_ENTRY_CLOSED = "order_book_entry_closed"

    # ── Broker sync ───────────────────────────────────────────────────────────
    SYNC_CHECK_STARTED = "sync_check_started"
    SYNC_CHECK_COMPLETED = "sync_check_completed"
    SYNC_DISCREPANCY_FOUND = "sync_discrepancy_found"
    SYNC_ORDER_BOOK_UPDATED = "sync_order_book_updated"
    SYNC_AGENT_NOTIFIED = "sync_agent_notified"

    # ── Agent decisions ───────────────────────────────────────────────────────
    AGENT_SIGNAL_GENERATED = "agent_signal_generated"
    AGENT_DECISION_MADE = "agent_decision_made"
    AGENT_TOOL_CALLED = "agent_tool_called"
    AGENT_TOOL_RESULT = "agent_tool_result"
    AGENT_ALARM = "agent_alarm"

    # ── Tool dispatcher ───────────────────────────────────────────────────────
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    AGENT_QUEUE_FULL = "agent_queue_full"
    ROUTING_RELOADED = "routing_reloaded"
    ROUTING_RELOAD_FAILED = "routing_reload_failed"

    # ── LLM calls ─────────────────────────────────────────────────────────────
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"

    # ── Data container ────────────────────────────────────────────────────────
    DATA_CONTAINER_ACCESS = "data_container_access"  # get_candles / get_snapshot

    # ── Inter-agent bus ───────────────────────────────────────────────────────
    EVENT_BUS_MESSAGE = "event_bus_message"

    # ── System ────────────────────────────────────────────────────────────────
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_INFO = "system_info"


class MonitoringEvent(BaseModel):
    """Universal event envelope for the monitoring bus.

    Every component in the system emits MonitoringEvents.  If no monitor is
    connected the events are silently discarded (fire-and-forget).  The
    payload dict is intentionally open-ended so each source can include all
    relevant details without a rigid schema per event type.
    """

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime                    # always UTC
    source_module: str                     # e.g. "broker.OANDA_DEMO", "data_container"
    event_type: MonitoringEventType
    broker_name: str | None = None         # set when event relates to a specific broker
    pair: str | None = None                # set when event relates to a specific pair
    payload: dict = Field(default_factory=dict)
