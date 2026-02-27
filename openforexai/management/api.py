"""FastAPI management application — OpenForexAI control plane.

Endpoints
---------
GET  /health            System health (agents alive, queue depths, uptime)
GET  /metrics           Key counters (messages dispatched, tool calls, …)
GET  /agents            List registered agents + queue depths
GET  /agents/{id}       Single agent info
GET  /routing/rules     Current routing rules (JSON)
POST /routing/reload    Hot-reload routing table from disk
POST /events            Inject an arbitrary event into the EventBus
POST /config/reload     Reload application config (YAML) — triggers agents to re-read settings
GET  /indicators        List registered indicators
GET  /tools             List registered tools (per-agent view optional)

Authentication
--------------
A simple static API key via ``X-API-Key`` header.  Set via
``MANAGEMENT_API_KEY`` environment variable.  Defaults to no auth in dev mode.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# ── Dependency injection stubs (populated by ManagementServer) ────────────────
# These are set at startup via ManagementServer.build_app(); the API module
# itself stays import-time clean (no circular imports).
_bus = None
_routing_table = None
_tool_registry = None
_indicator_registry = None
_monitoring_bus = None
_start_time: float = time.monotonic()

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_EXPECTED_KEY: str | None = os.environ.get("MANAGEMENT_API_KEY")


def _check_api_key(api_key: str | None = Depends(_API_KEY_HEADER)) -> None:
    if _EXPECTED_KEY and api_key != _EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ── Request / response models ─────────────────────────────────────────────────

class EventInjectRequest(BaseModel):
    event_type: str = Field(..., description="EventType value, e.g. 'signal_generated'")
    source_agent_id: str = Field(
        default="MGMT._ALL..._GA_MGMT", description="Sender agent ID"
    )
    target_agent_id: str | None = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None)


class EventInjectResponse(BaseModel):
    message_id: str
    status: str = "queued"


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    registered_agents: int
    routing_rules: int
    timestamp: str


class AgentInfo(BaseModel):
    agent_id: str
    queue_size: int
    queue_maxsize: int


class RoutingRuleInfo(BaseModel):
    id: str
    description: str
    event: str
    from_pattern: str
    to: str
    priority: int


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(dependencies=[Depends(_check_api_key)])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    agents = _bus.registered_agents() if _bus else []
    rules = _routing_table.rules if _routing_table else []
    return HealthResponse(
        status="ok",
        uptime_seconds=round(time.monotonic() - _start_time, 1),
        registered_agents=len(agents),
        routing_rules=len(rules),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/metrics")
async def metrics() -> dict:
    """Basic counters — extend as needed."""
    agents = _bus.registered_agents() if _bus else []
    queues = {}
    if _bus:
        for aid in agents:
            q = _bus._agent_queues.get(aid)
            if q:
                queues[aid] = q.qsize()
    return {
        "registered_agents": len(agents),
        "agent_queue_depths": queues,
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    if _bus is None:
        return []
    result = []
    for aid in _bus.registered_agents():
        q = _bus._agent_queues.get(aid)
        result.append(AgentInfo(
            agent_id=aid,
            queue_size=q.qsize() if q else 0,
            queue_maxsize=q.maxsize if q else 0,
        ))
    return result


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str) -> AgentInfo:
    if _bus is None or agent_id not in _bus._agent_queues:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not registered")
    q = _bus._agent_queues[agent_id]
    return AgentInfo(agent_id=agent_id, queue_size=q.qsize(), queue_maxsize=q.maxsize)


@router.get("/routing/rules", response_model=list[RoutingRuleInfo])
async def list_routing_rules() -> list[RoutingRuleInfo]:
    if _routing_table is None:
        return []
    return [
        RoutingRuleInfo(
            id=r.id,
            description=r.description,
            event=r.event,
            from_pattern=r.from_pattern,
            to=r.to,
            priority=r.priority,
        )
        for r in _routing_table.rules
    ]


@router.post("/routing/reload", status_code=202)
async def reload_routing() -> dict:
    """Hot-reload the routing table from disk without restarting."""
    if _bus is None:
        raise HTTPException(status_code=503, detail="EventBus not initialised")
    await _bus.reload_routing()
    return {
        "status": "reloaded",
        "rule_count": len(_routing_table.rules) if _routing_table else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/events", response_model=EventInjectResponse, status_code=202)
async def inject_event(req: EventInjectRequest) -> EventInjectResponse:
    """Inject an arbitrary event into the EventBus.

    Useful for:
    - Manual signal injection during testing
    - Triggering repairs, reloads, or optimization cycles
    - External system integrations
    """
    if _bus is None:
        raise HTTPException(status_code=503, detail="EventBus not initialised")

    from openforexai.models.messaging import AgentMessage, EventType

    try:
        event_type = EventType(req.event_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown event type: {req.event_type!r}. "
            f"Valid values: {[e.value for e in EventType]}",
        )

    msg = AgentMessage(
        event_type=event_type,
        source_agent_id=req.source_agent_id,
        target_agent_id=req.target_agent_id,
        payload=req.payload,
        correlation_id=req.correlation_id,
    )
    await _bus.publish(msg)
    return EventInjectResponse(message_id=str(msg.id))


@router.get("/indicators")
async def list_indicators() -> dict:
    if _indicator_registry is None:
        return {"indicators": []}
    return {"indicators": _indicator_registry.registered_names()}


@router.get("/monitoring/events")
async def monitoring_events(
    since: str | None = None,
    limit: int = 100,
) -> list:
    """Return recent monitoring events from the ring buffer.

    ``since`` — ISO-8601 UTC timestamp; only events after this are returned.
    ``limit`` — max number of events (default 100, max 1000).

    This endpoint is designed for polling by ``tools/monitor.py``.
    """
    if _monitoring_bus is None:
        return []
    since_dt = None
    if since:
        from datetime import timezone
        try:
            from datetime import datetime as _dt
            since_dt = _dt.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid 'since' timestamp: {since!r}")

    limit = max(1, min(limit, 1000))
    events = _monitoring_bus.recent_events(since=since_dt, limit=limit)
    return [
        {
            "id":           str(e.id),
            "timestamp":    e.timestamp.isoformat(),
            "source":       e.source_module,
            "event_type":   e.event_type.value,
            "broker":       e.broker_name,
            "pair":         e.pair,
            "payload":      e.payload,
        }
        for e in events
    ]


@router.get("/tools")
async def list_tools() -> dict:
    if _tool_registry is None:
        return {"tools": []}
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "requires_approval": t.requires_approval,
            }
            for t in _tool_registry.all_tools()
        ]
    }


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    bus=None,
    routing_table=None,
    tool_registry=None,
    indicator_registry=None,
    monitoring_bus=None,
) -> FastAPI:
    """Build the FastAPI application and wire runtime dependencies."""
    global _bus, _routing_table, _tool_registry, _indicator_registry, _monitoring_bus, _start_time

    _bus = bus
    _routing_table = routing_table
    _tool_registry = tool_registry
    _indicator_registry = indicator_registry
    _monitoring_bus = monitoring_bus
    _start_time = time.monotonic()

    app = FastAPI(
        title="OpenForexAI Management API",
        description="Runtime control plane for the OpenForexAI multi-agent system.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(router)
    return app
