from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    # ── Market data / candle pipeline ─────────────────────────────────────────
    M5_CANDLE_UPDATE = "m5_candle_update"           # broker adapter → DB/chart consumers
    M5_CANDLE_TRIGGER = "m5_candle_trigger"          # broker adapter → matching AA agents and ECs
    M5_TRIGGER_COUNTER = "m5_trigger_counter"       # agent emits counter info for monitoring
    CANDLE_GAP_DETECTED = "candle_gap_detected"     # adapter signals a gap in M5 sequence
    CANDLE_REPAIR_REQUESTED = "candle_repair_requested"  # data container → broker
    CANDLE_REPAIR_COMPLETED = "candle_repair_completed"  # data container broadcasts

    # ── Account status ────────────────────────────────────────────────────────
    ACCOUNT_STATUS_UPDATED = "account_status_updated"

    # ── Trading flow ──────────────────────────────────────────────────────────
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

    # ── EventComposer config bootstrap ───────────────────────────────────────
    EC_CONFIG_REQUESTED = "ec_config_requested"   # EC → ConfigService
    EC_CONFIG_RESPONSE  = "ec_config_response"    # ConfigService → EC

    # ── EventComposer output ──────────────────────────────────────────────────
    EC_OUTPUT = "ec_output"                       # EC publishes result JSON
    EC_GUARD_BLOCK = "ec_guard_block"             # EC guard blocked a signal (tool error or no valid result)

    # ── Repository service (DB access via bus) ────────────────────────────────
    REPO_REQUEST  = "repo_request"    # any member → SYSTM-ALL___-GA-REPO
    REPO_RESPONSE = "repo_response"   # SYSTM-ALL___-GA-REPO → requester

    # ── Market data (DataContainer queries) ──────────────────────────────────
    CANDLES_REQUEST  = "candles_request"
    CANDLES_RESPONSE = "candles_response"
    CANDLES_REQUEST_TIMEOUT = "candles_request_timeout"
    # DataContainer's own handling of a CANDLES_REQUEST exceeded its internal
    # timeout — published (not just monitoring-emitted) so it's visible/
    # filterable in the persistent Event Log, never silent.

    INDICATOR_REQUEST  = "indicator_request"
    INDICATOR_RESPONSE = "indicator_response"

    SWING_LEVELS_REQUEST  = "swing_levels_request"
    SWING_LEVELS_RESPONSE = "swing_levels_response"

    # ── Broker execution (tool → broker adapter) ──────────────────────────────
    ORDER_REQUEST  = "order_request"
    ORDER_RESULT   = "order_result"

    POSITION_CLOSE_REQUEST = "position_close_request"
    POSITION_CLOSE_RESULT  = "position_close_result"

    ORDER_MODIFY_REQUEST = "order_modify_request"
    ORDER_MODIFY_RESULT  = "order_modify_result"

    ACCOUNT_STATUS_REQUEST  = "account_status_request"
    ACCOUNT_STATUS_RESPONSE = "account_status_response"

    POSITIONS_REQUEST  = "positions_request"
    POSITIONS_RESPONSE = "positions_response"

    # ── Candle repair (DataContainer → broker adapter → DataContainer) ────────
    CANDLE_DATA_BULK = "candle_data_bulk"

    # ── LLM service (one LLMService per configured LLM module) ───────────────
    LLM_REQUEST  = "llm_request"   # any member → llm:{module_name}
    LLM_RESPONSE = "llm_response"  # llm:{module_name} → requester

    # ── Observability lifecycle ───────────────────────────────────────────────
    AGENT_CYCLE_START  = "agent_cycle_start"
    AGENT_CYCLE_END    = "agent_cycle_end"
    SNAPSHOT_START     = "snapshot_start"
    SNAPSHOT_END       = "snapshot_end"
    DECISION_START     = "decision_start"
    DECISION_END       = "decision_end"
    EC_CYCLE_START     = "ec_cycle_start"
    EC_CYCLE_END       = "ec_cycle_end"
    CHARTSHOT_START    = "chartshot_start"
    CHARTSHOT_END      = "chartshot_end"
    BRIDGE_CALL_START  = "bridge_call_start"
    BRIDGE_CALL_END    = "bridge_call_end"

    # ── System / management ───────────────────────────────────────────────────
    ROUTING_RELOAD_REQUESTED = "routing_reload_requested"


class AgentMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    source_agent_id: str
    instrument: str | None = None           # trading instrument (e.g. "EURUSD"); None for system events
    target_agent_id: str | None = None      # None = broadcast to all subscribers
    payload: dict
    correlation_id: str | None = None       # ties request/response pairs
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    chain: list[UUID] = Field(default_factory=list)  # ancestor event IDs, oldest first


