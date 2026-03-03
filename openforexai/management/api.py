"""FastAPI management application — OpenForexAI control plane.

Endpoints
---------
GET  /health                  System health (agents alive, queue depths, uptime)
GET  /metrics                 Key counters (messages dispatched, tool calls, …)
GET  /version                 Application version from system.json
GET  /runtime/status          Live runtime state (agents, routing rules)
GET  /agents                  List registered agents + queue depths
GET  /agents/{id}             Single agent info
POST /agents/{id}/ask         Send a question to an agent, await response
GET  /routing/rules           Current routing rules (JSON)
POST /routing/reload          Hot-reload routing table from disk
POST /events                  Inject an arbitrary event into the EventBus
GET  /indicators              List registered indicators
GET  /monitoring/events       Recent events from ring buffer (polling)
WS   /ws/monitoring           WebSocket live monitoring stream
GET  /tools                   List registered tools
POST /tools/execute           Execute a registered tool directly (for testing)
GET  /config/view             system.json with sensitive fields masked
GET  /config/files/{name}     Raw config file (agent_tools or event_routing)

Authentication
--------------
A simple static API key via ``X-API-Key`` header.  Set via
``MANAGEMENT_API_KEY`` environment variable.  Defaults to no auth in dev mode.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# ── Agent-query response registry ────────────────────────────────────────────
# Maps correlation_id → asyncio.Future.  Populated by ask_agent(); resolved by
# _on_agent_query_response() when the agent publishes AGENT_QUERY_RESPONSE.
_pending_queries: dict[str, asyncio.Future] = {}


async def _on_agent_query_response(msg) -> None:
    """Bus handler: resolve the pending Future for the given correlation_id."""
    cid = msg.correlation_id
    if not cid:
        return
    fut = _pending_queries.pop(cid, None)
    if fut is not None and not fut.done():
        fut.set_result(msg.payload)


def setup_query_handler(bus) -> None:
    """Subscribe the AGENT_QUERY_RESPONSE handler to the EventBus.

    Called once by ManagementServer after the app is built.  Safe to call
    with bus=None (no-op) so startup code never has to guard against it.
    """
    if bus is None:
        return
    from openforexai.models.messaging import EventType
    bus.subscribe(EventType.AGENT_QUERY_RESPONSE, _on_agent_query_response)


# ── Dependency injection stubs (populated by ManagementServer) ────────────────
# These are set at startup via ManagementServer.build_app(); the API module
# itself stays import-time clean (no circular imports).
_bus = None
_routing_table = None
_tool_registry = None
_indicator_registry = None
_monitoring_bus = None
_system_config: dict[str, Any] = {}
_config_dir: Path | None = None
_start_time: float = time.monotonic()

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_EXPECTED_KEY: str | None = os.environ.get("MANAGEMENT_API_KEY")


def _check_api_key(api_key: str | None = Depends(_API_KEY_HEADER)) -> None:
    if _EXPECTED_KEY and api_key != _EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ── Config masking ─────────────────────────────────────────────────────────────

_MASK_KEYS = frozenset({
    "api_key", "apikey", "api-key",
    "password", "passwd", "secret",
    "token", "access_token",
    "private_key", "client_secret",
})


def _deep_mask(obj: Any, *, _depth: int = 0) -> Any:
    """Recursively copy *obj*, replacing values whose key suggests a secret."""
    if _depth > 20:
        return obj  # guard against deeply nested structures
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in _MASK_KEYS else _deep_mask(v, _depth=_depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_deep_mask(item, _depth=_depth + 1) for item in obj]
    return obj


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


class AgentQueryRequest(BaseModel):
    question: str = Field(..., description="Free-text question or instruction for the agent")
    timeout: float = Field(
        default=120.0, ge=5.0, le=300.0,
        description="Seconds to wait for the agent's response (5–300)",
    )


class AgentQueryResponse(BaseModel):
    correlation_id: str
    agent_id: str
    response: str


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


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the registered tool to execute")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments to pass to the tool"
    )


class ToolExecuteResponse(BaseModel):
    tool_name: str
    result: Any
    is_error: bool = False


# ── Routers ───────────────────────────────────────────────────────────────────
# WebSocket endpoints cannot use APIKeyHeader (no HTTP Request object in WS scope).
# They live on a separate router without the auth dependency.

router = APIRouter(dependencies=[Depends(_check_api_key)])
ws_router = APIRouter()   # no auth — WebSocket-compatible


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


@router.get("/version")
async def get_version() -> dict:
    """Return the application version from system.json."""
    version = _system_config.get("system", {}).get("version", "unknown")
    return {"version": version}


@router.get("/runtime/status")
async def get_runtime_status() -> dict:
    """Return live runtime state: active agents and routing rule count."""
    agents = _bus.registered_agents() if _bus else []
    rule_count = len(_routing_table.rules) if _routing_table else 0
    return {
        "agents": agents,
        "routing_rules": rule_count,
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


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


@router.post("/agents/{agent_id}/ask", response_model=AgentQueryResponse)
async def ask_agent(agent_id: str, req: AgentQueryRequest) -> AgentQueryResponse:
    """Send a free-text question to a specific agent and wait for its response.

    The question is delivered directly to the target agent's inbox as an
    ``AGENT_QUERY`` event (``target_agent_id`` set → routing table bypassed).
    The endpoint blocks until the agent publishes ``AGENT_QUERY_RESPONSE`` with
    the matching ``correlation_id``, or until *timeout* seconds have elapsed.

    Typical round-trip time is the agent's LLM latency (2–15 s depending on
    how many tool calls the agent makes to answer the question).

    Example::

        POST /agents/OAPR1_EURUSD_AA_ANLYS/ask
        {"question": "What is the current EURUSD trend on H1?", "timeout": 60}
    """
    if _bus is None:
        raise HTTPException(status_code=503, detail="EventBus not initialised")

    if agent_id not in _bus.registered_agents():
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not registered")

    from openforexai.models.messaging import AgentMessage, EventType

    correlation_id = str(uuid4())
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending_queries[correlation_id] = fut

    await _bus.publish(AgentMessage(
        event_type=EventType.AGENT_QUERY,
        source_agent_id="MGMT._ALL..._GA_MGMT",
        target_agent_id=agent_id,
        payload={"question": req.question, "source": "management_api"},
        correlation_id=correlation_id,
    ))

    try:
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=req.timeout)
        return AgentQueryResponse(
            correlation_id=correlation_id,
            agent_id=result.get("agent_id", agent_id),
            response=result.get("response", ""),
        )
    except asyncio.TimeoutError:
        _pending_queries.pop(correlation_id, None)
        raise HTTPException(
            status_code=504,
            detail=f"Agent {agent_id!r} did not respond within {req.timeout:.0f}s",
        )


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


# ── WebSocket payload helpers ─────────────────────────────────────────────────

# LLM_REQUEST payloads include the full system prompt, complete message history,
# and all tool specs — they can easily be 100KB–500KB.  Truncate bulky fields
# before sending over WebSocket; the ring buffer keeps the full data for
# GET /monitoring/events (the console monitor uses that endpoint).

_WS_MAX_STR_LEN  = 2_000   # max chars for any single string field
_WS_MAX_MSG_KEEP = 5       # keep only the last N messages from history


def _ws_safe_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a WebSocket-safe copy of *payload*, truncating large LLM fields."""
    if event_type not in ("llm_request", "llm_response"):
        return payload  # non-LLM events are small — pass through unchanged

    out = dict(payload)  # shallow copy; don't mutate the original

    # Truncate system prompt
    sp = out.get("system_prompt")
    if isinstance(sp, str) and len(sp) > _WS_MAX_STR_LEN:
        out["system_prompt"] = sp[:_WS_MAX_STR_LEN] + f" …[{len(sp) - _WS_MAX_STR_LEN} chars omitted]"

    # Keep only the last N messages to limit size
    msgs = out.get("messages")
    if isinstance(msgs, list) and len(msgs) > _WS_MAX_MSG_KEEP:
        omitted = len(msgs) - _WS_MAX_MSG_KEEP
        out["messages"] = msgs[-_WS_MAX_MSG_KEEP:]
        out["messages_omitted"] = omitted

    # Replace full tool specs with a placeholder (names are already in tool_names)
    if "tool_specs" in out:
        out["tool_specs"] = "[omitted — fetch /monitoring/events for full data]"

    # Truncate long response content
    content = out.get("content")
    if isinstance(content, str) and len(content) > _WS_MAX_STR_LEN:
        out["content"] = content[:_WS_MAX_STR_LEN] + f" …[{len(content) - _WS_MAX_STR_LEN} chars omitted]"

    return out


def _build_ws_message(event: Any) -> str:
    """Serialise a MonitoringEvent to a JSON string safe for WebSocket sending."""
    et: str = event.event_type.value
    data: dict[str, Any] = {
        "id":         str(event.id),
        "timestamp":  event.timestamp.isoformat(),
        "source":     event.source_module,
        "event_type": et,
        "broker":     event.broker_name,
        "pair":       event.pair,
        "payload":    _ws_safe_payload(et, event.payload),
    }
    return json.dumps(data, default=str)


@ws_router.websocket("/ws/monitoring")
async def ws_monitoring(websocket: WebSocket) -> None:
    """WebSocket endpoint for live monitoring event streaming.

    Connects to the MonitoringBus subscriber queue and pushes every
    MonitoringEvent as a JSON object to the client.  The connection is kept
    alive with 30-second heartbeat pings.

    On first connect, the last 100 ring-buffer events are replayed so the
    client immediately sees recent history (useful if events occurred before
    the browser tab opened).

    Optional query param:
        ?filter=<comma-separated event_type values>
        e.g. ?filter=llm_request,llm_response,llm_error

    Each message is a JSON object::

        {
            "id": "...",
            "timestamp": "2026-03-03T08:12:34.123+00:00",
            "source": "...",
            "event_type": "llm_response",
            "broker": null,
            "pair": null,
            "payload": { ... }
        }
    """
    await websocket.accept()

    # Optional event-type filter via query param
    filter_param: str | None = websocket.query_params.get("filter")
    allowed_types: set[str] | None = None
    if filter_param:
        allowed_types = {t.strip() for t in filter_param.split(",") if t.strip()}

    if _monitoring_bus is None:
        try:
            await websocket.send_text(json.dumps({"error": "MonitoringBus not available"}))
            await websocket.close()
        except Exception:
            pass
        return

    # Subscribe to live events FIRST, then replay history.
    # This order ensures no events are missed between the two phases.
    q = _monitoring_bus.subscribe()
    seen_ids: set[str] = set()

    try:
        # ── Phase 1: replay recent ring-buffer history ────────────────────────
        recent = _monitoring_bus.recent_events(limit=100)
        for hist_event in recent:
            if allowed_types and hist_event.event_type.value not in allowed_types:
                continue
            eid = str(hist_event.id)
            seen_ids.add(eid)
            try:
                await websocket.send_text(_build_ws_message(hist_event))
            except Exception:
                # Client disconnected during catchup — bail out immediately
                return

        # ── Phase 2: live stream ──────────────────────────────────────────────
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a heartbeat ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
                continue

            # Apply optional filter
            if allowed_types and event.event_type.value not in allowed_types:
                continue

            # Skip events already sent as part of the history replay
            eid = str(event.id)
            if eid in seen_ids:
                seen_ids.discard(eid)  # free memory — won't repeat
                continue

            try:
                await websocket.send_text(_build_ws_message(event))
            except Exception:
                # Connection lost (WebSocketDisconnect, RuntimeError, etc.)
                break

    except Exception:
        pass  # absorb any unexpected exception — never let monitoring crash
    finally:
        _monitoring_bus.unsubscribe(q)


@router.get("/tools")
async def list_tools() -> dict:
    if _tool_registry is None:
        return {"tools": []}
    return {
        "tools": [
            {
                "name":             t.name,
                "description":      t.description,
                "input_schema":     t.input_schema,
                "requires_approval": t.requires_approval,
            }
            for t in _tool_registry.all_tools()
        ]
    }


@router.post("/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest) -> ToolExecuteResponse:
    """Execute a registered tool directly (for testing/debugging).

    Creates a minimal ToolContext with the monitoring bus and event bus wired
    in.  Tools that require a broker adapter or data container will return an
    appropriate error from their own validation rather than crashing the API.

    Example::

        POST /tools/execute
        {"tool_name": "raise_alarm", "arguments": {"message": "test alarm"}}
    """
    if _tool_registry is None:
        raise HTTPException(status_code=503, detail="ToolRegistry not available")

    tool = _tool_registry.get(req.tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool {req.tool_name!r} not registered")

    from openforexai.tools.base import ToolContext

    context = ToolContext(
        agent_id="MGMT._ALL..._GA_MGMT",
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
    )

    try:
        result = await tool.execute(req.arguments, context)
        return ToolExecuteResponse(tool_name=req.tool_name, result=result, is_error=False)
    except Exception as exc:
        return ToolExecuteResponse(
            tool_name=req.tool_name,
            result={"error": str(exc)},
            is_error=True,
        )


@router.get("/config/view")
async def config_view() -> dict:
    """Return system.json with sensitive fields (api_key, password, …) masked.

    All keys whose name matches a known sensitive pattern are replaced with
    ``"***"`` recursively.  Environment variable values are already substituted
    at load time — this endpoint never exposes raw ``${VAR}`` tokens.
    """
    return _deep_mask(copy.deepcopy(_system_config))


# Known config file names that can be served
_CONFIG_FILES: dict[str, str | None] = {
    "agent_tools":    None,  # resolved at runtime relative to this file
    "event_routing":  None,
}


@router.get("/config/files/{name}")
async def config_file(name: str) -> dict:
    """Return a raw config file by name (agent_tools | event_routing).

    Returns the parsed JSON content.  The file is read from disk on every
    request so edits are reflected without restart.
    """
    if name not in _CONFIG_FILES:
        raise HTTPException(
            status_code=404,
            detail=f"Config file {name!r} not available. "
                   f"Valid names: {list(_CONFIG_FILES.keys())}",
        )

    # Config files live next to this package at openforexai/config/
    here = Path(__file__).resolve().parent.parent  # openforexai/
    cfg_path = here / "config" / f"{name}.json"

    if not cfg_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Config file not found on disk: {cfg_path.name}",
        )

    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Config file {cfg_path.name} contains invalid JSON: {exc}",
        )


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    bus=None,
    routing_table=None,
    tool_registry=None,
    indicator_registry=None,
    monitoring_bus=None,
    system_config: dict[str, Any] | None = None,
) -> FastAPI:
    """Build the FastAPI application and wire runtime dependencies."""
    global _bus, _routing_table, _tool_registry, _indicator_registry
    global _monitoring_bus, _system_config, _start_time

    _bus = bus
    _routing_table = routing_table
    _tool_registry = tool_registry
    _indicator_registry = indicator_registry
    _monitoring_bus = monitoring_bus
    _system_config = system_config or {}
    _start_time = time.monotonic()

    app = FastAPI(
        title="OpenForexAI Management API",
        description="Runtime control plane for the OpenForexAI multi-agent system.",
        version=_system_config.get("system", {}).get("version", "1.0.0"),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow Vite dev server (port 5173) and same-origin requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(ws_router)   # WebSocket routes (no auth dependency)

    # Serve the compiled React UI from ui/dist/ if it exists.
    # Must be mounted AFTER the API router so API routes take precedence.
    _ui_dist = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
    if _ui_dist.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")

    return app
