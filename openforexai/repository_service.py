"""RepositoryService — database access via EventBus.

All inter-module database access goes through this service.
It registers as ``SYSTM-ALL___-GA-REPO`` on the EventBus and
processes REPO_REQUEST messages, responding with REPO_RESPONSE.

Request payload::

    {
        "operation": "get_sub_prompt",   # AbstractRepository method name
        "args": {"agent": "OXS_T-EURUSD-AA-ANLYS"},
    }

Response payload::

    {
        "operation": "get_sub_prompt",
        "result": "...",                 # return value of the method (JSON-serialisable)
        "error": null,                   # str if an exception occurred
    }
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.database import AbstractRepository
from openforexai.utils.logging import get_logger

REPO_SERVICE_ID = "SYSTM-ALL___-GA-REPO"

_log = get_logger(__name__)

# Fields excluded for operations used by the broker adapter — never needed there
_SLIM_OPERATIONS = {"get_open_order_book_entries"}
_HEAVY_FIELDS = {"market_context_snapshot", "entry_reasoning", "close_reasoning"}


def _serialize_result(result: Any, operation: str) -> Any:
    """Serialize Pydantic models to dicts. Strip heavy fields for slim operations."""
    slim = operation in _SLIM_OPERATIONS
    if result is None:
        return None
    if isinstance(result, list):
        return [_serialize_result(item, operation) for item in result]
    if hasattr(result, "model_dump"):
        d = result.model_dump(mode="json")
        if slim:
            for field in _HEAVY_FIELDS:
                d.pop(field, None)
        return d
    return result


class RepositoryService:
    """Processes REPO_REQUEST messages and responds with REPO_RESPONSE.

    All database access from tools and modules must go through this service.
    Direct repository access from module code is not permitted.
    """

    def __init__(self, repository: AbstractRepository, bus: EventBus, monitoring_bus=None) -> None:
        self._repository = repository
        self._bus = bus
        self._monitoring = monitoring_bus
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_member(REPO_SERVICE_ID)

    async def run(self) -> None:
        """Process REPO_REQUEST messages until cancelled."""
        _log.info("RepositoryService started", member_id=REPO_SERVICE_ID)
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type != EventType.REPO_REQUEST:
                continue

            await self._handle(msg)

    @staticmethod
    def _deserialize_args(operation: str, args: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON-serialized Pydantic model dicts back to model objects."""
        from openforexai.models.composer import ECRun
        from openforexai.models.agent import AgentDecision
        from openforexai.models.trade import OrderBookEntry
        from openforexai.models.account import AccountStatus
        _model_map = {
            "save_ec_run": ("run", ECRun),
            "save_agent_decision": ("decision", AgentDecision),
            "save_order_book_entry": ("entry", OrderBookEntry),
            "save_account_status": ("status", AccountStatus),
        }
        if operation in _model_map:
            key, cls = _model_map[operation]
            if key in args and isinstance(args[key], dict):
                try:
                    args = {**args, key: cls(**args[key])}
                except Exception:
                    pass
        return args

    async def _handle(self, msg: AgentMessage) -> None:
        operation = msg.payload.get("operation", "")
        args: dict[str, Any] = self._deserialize_args(
            operation, msg.payload.get("args", {})
        )

        start = datetime.now(UTC)
        result = None
        error: str | None = None

        try:
            method = getattr(self._repository, operation, None)
            if method is None:
                raise AttributeError(f"Repository has no method '{operation}'")
            result = await method(**args)
        except Exception as exc:
            error = str(exc)
            _log.error(
                "RepositoryService: operation '%s' failed: %s", operation, exc, exc_info=True
            )

        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000

        if self._monitoring is not None:
            try:
                self._monitoring.emit(MonitoringEvent(
                    timestamp=datetime.now(UTC),
                    source_module=f"repo_service",
                    event_type=MonitoringEventType.SYSTEM_INFO,
                    payload={
                        "operation": operation,
                        "requester": msg.source_agent_id,
                        "latency_ms": latency_ms,
                        "error": error,
                    },
                ))
            except Exception:
                pass

        await self._bus.publish(AgentMessage(
            event_type=EventType.REPO_RESPONSE,
            source_agent_id=REPO_SERVICE_ID,
            target_agent_id=msg.source_agent_id,
            payload={
                "operation": operation,
                "result": _serialize_result(result, operation),
                "error": error,
            },
            correlation_id=str(msg.id),
        ))
