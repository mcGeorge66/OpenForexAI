"""FastAPI management application — OpenForexAI control plane.

Endpoints
---------
GET  /health                  System health (agents alive, queue depths, uptime)
GET  /metrics                 Key counters (messages dispatched, tool calls, …)
GET  /version                 Application version from system.json5
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
GET  /config/view             system.json5 with sensitive fields masked
GET  /config/system           Raw system.json5 (editable)
PUT  /config/system           Save raw system.json5
GET  /config/files/{name}     Raw config file (agent_tools or event_routing)
PUT  /config/files/{name}     Save raw config file
GET  /config/modules/{type}   List configured module names for llm | broker
GET  /config/modules/{type}/{name}  Single module config file (secrets masked)
GET  /config/modules/{type}/{name}/raw  Raw module config (editable)
PUT  /config/modules/{type}/{name}/raw  Save raw module config

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import json5
from fastapi import (
    APIRouter,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from openforexai.config.json_loader import load_json_config
from openforexai.management.package_io import (
    apply_import_package,
    build_export_package,
    dump_json5_text,
    parse_json5_text,
    validate_package,
)

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
_data_container = None       # DataContainer — shared market data cache
_repository = None           # AbstractRepository — database access
_connected_brokers: dict = {}  # broker_name → AbstractBroker live instances
_config_service = None
_runtime_agents: dict[str, Any] = {}
_runtime_agent_tasks: dict[str, asyncio.Task] = {}
_start_time: float = time.monotonic()

_LLM_CHECKER_LLM_TIMEOUT_SECONDS = 45.0
_LLM_CHECKER_TOOL_TIMEOUT_SECONDS = 20.0

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_EXPECTED_KEY: str | None = os.environ.get("MANAGEMENT_API_KEY")


def _normalize_broker_selector(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_connected_broker(
    selector: str | None,
) -> tuple[str | None, Any | None]:
    """Resolve a broker by module name or short_name."""
    normalized = _normalize_broker_selector(selector)
    if normalized is None:
        return None, None

    by_module = _connected_brokers.get(normalized)
    if by_module is not None:
        return normalized, by_module

    matches: list[tuple[str, Any]] = [
        (module_name, broker)
        for module_name, broker in _connected_brokers.items()
        if str(getattr(broker, "short_name", "")).strip() == normalized
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        modules = ", ".join(module for module, _ in matches)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Broker selector {normalized!r} is ambiguous (matches modules: {modules}). "
                "Use broker module name."
            ),
        )
    return normalized, None


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


def _project_root() -> Path:
    """Return project root path from this module location."""
    return Path(__file__).resolve().parent.parent.parent


def _write_json_file(path: Path, content: dict[str, Any] | str) -> None:
    """Atomically write JSON5 content with stable formatting.

    If *content* is a string, it is validated as JSON5 and written as-is.
    If it is a dict/list, it is serialized to JSON5-compatible text.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    if isinstance(content, str):
        # Validate before writing so malformed edits are rejected early.
        json5.loads(content)
        serialized = content.rstrip() + "\n"
    else:
        serialized = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    tmp_path.write_text(serialized, encoding="utf-8")
    tmp_path.replace(path)

def _read_text_file(path: Path) -> str:
    """Read a config file as raw UTF-8 text."""
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found on disk: {path.name}")
    return path.read_text(encoding="utf-8")


def _write_text_file(path: Path, content: str) -> None:
    """Atomically write UTF-8 text content to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _resolve_module_config_path(module_type: str, name: str) -> Path:
    if module_type not in ("llm", "broker"):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown module type: {module_type!r}. Valid types: 'llm', 'broker'",
        )
    path_str = _system_config.get("modules", {}).get(module_type, {}).get(name)
    if not path_str:
        raise HTTPException(
            status_code=404,
            detail=f"Module {name!r} not found under modules.{module_type} in system config",
        )
    cfg_path = _project_root() / path_str
    if not cfg_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Config file not found on disk: {cfg_path.name}",
        )
    return cfg_path


def _extract_llm_defaults(module_cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract common LLM runtime defaults from a module config dict."""
    defaults: dict[str, Any] = {}
    if isinstance(module_cfg.get("defaults"), dict):
        defaults.update(module_cfg["defaults"])
    if isinstance(module_cfg.get("params"), dict):
        defaults.update(module_cfg["params"])
    for key in ("temperature", "max_tokens"):
        if key in module_cfg:
            defaults[key] = module_cfg.get(key)
    return defaults


def _emit_checker_monitoring(
    event_type: str,
    *,
    llm_name: str,
    agent_id: str | None,
    broker_name: str | None,
    pair: str | None,
    payload: dict[str, Any],
) -> None:
    """Emit monitoring events for LLM Checker flow."""
    if _monitoring_bus is None:
        return
    try:
        from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType

        _monitoring_bus.emit(MonitoringEvent(
            timestamp=datetime.now(UTC),
            source_module=f"llm_checker:{llm_name}",
            event_type=MonitoringEventType[event_type],
            broker_name=broker_name,
            pair=pair,
            payload={
                "llm_name": llm_name,
                "agent_id": agent_id,
                **payload,
            },
        ))
    except Exception:
        pass


def _resolve_llm_checker_params(
    llm_name: str,
    agent_cfg: dict[str, Any] | None,
    request_temperature: float | None,
    request_max_tokens: int | None,
    llm_instance: Any,
) -> tuple[float | None, int | None]:
    """Resolve checker params via module defaults -> agent override -> request override."""
    module_cfg: dict[str, Any] = {}
    llm_path = _system_config.get("modules", {}).get("llm", {}).get(llm_name)
    if isinstance(llm_path, str) and llm_path.strip():
        cfg_file = (_project_root() / llm_path).resolve()
        if cfg_file.exists():
            try:
                loaded = load_json_config(cfg_file)
                if isinstance(loaded, dict):
                    module_cfg = loaded
            except Exception:
                module_cfg = {}

    resolved = _extract_llm_defaults(module_cfg)

    if isinstance(agent_cfg, dict):
        if isinstance(agent_cfg.get("llm_config"), dict):
            resolved.update(agent_cfg["llm_config"])
    if request_temperature is not None:
        resolved["temperature"] = request_temperature
    if request_max_tokens is not None:
        resolved["max_tokens"] = request_max_tokens

    if "temperature" not in resolved and hasattr(llm_instance, "default_temperature"):
        resolved["temperature"] = getattr(llm_instance, "default_temperature")
    if "max_tokens" not in resolved and hasattr(llm_instance, "default_max_tokens"):
        resolved["max_tokens"] = getattr(llm_instance, "default_max_tokens")

    temp = resolved.get("temperature")
    max_toks = resolved.get("max_tokens")
    final_temp = float(temp) if isinstance(temp, (int, float)) else None
    final_max = int(max_toks) if isinstance(max_toks, int) and max_toks > 0 else None
    return final_temp, final_max


# ── Request / response models ─────────────────────────────────────────────────

class EventInjectRequest(BaseModel):
    event_type: str = Field(..., description="EventType value, e.g. 'signal_generated'")
    source_agent_id: str = Field(
        default="MGMT_-ALL___-GA-MGMT", description="Sender agent ID"
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
    agent_id: str | None = Field(
        default=None,
        description="Agent ID for tool execution context (sender identity and defaults).",
    )
    broker_name: str | None = Field(
        default=None,
        description="Configured broker adapter name for tool context.",
    )
    llm_name: str | None = Field(
        default=None,
        description="Configured LLM module name for tool context.",
    )
    pair: str | None = Field(
        default=None,
        description="Optional pair override for tool context, e.g. EURUSD.",
    )


class ToolExecuteResponse(BaseModel):
    tool_name: str
    result: Any
    is_error: bool = False
class LLMCheckerRequest(BaseModel):
    llm_name: str = Field(..., description="Configured LLM module name.")
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Conversation messages in chat format, e.g. [{role, content}, ...].",
    )
    enabled_tools: list[str] = Field(
        default_factory=list,
        description="Tool names to expose to the LLM in this ephemeral session.",
    )
    system_prompt: str = Field(
        default="You are a helpful assistant. Use tools when necessary.",
        description="System prompt for this checker run.",
    )
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=64, le=8192)
    max_tool_turns: int | None = Field(default=None, ge=0, le=20)
    agent_id: str | None = Field(
        default=None,
        description="Optional runtime agent context (for broker/pair defaults).",
    )
    broker_name: str | None = Field(
        default=None,
        description="Optional broker adapter module name override.",
    )
    pair: str | None = Field(
        default=None,
        description="Optional pair override, e.g. EURUSD.",
    )


class LLMCheckerResponse(BaseModel):
    llm_name: str
    final_text: str
    total_tokens: int
    stop_reason: str
    trace: list[dict[str, Any]] = Field(default_factory=list)


class PackageMappingRequest(BaseModel):
    broker_map: dict[str, str] = Field(default_factory=dict)
    llm_map: dict[str, str] = Field(default_factory=dict)
    agent_id_map: dict[str, str] = Field(default_factory=dict)
    agent_id_prefix: str = ""


class PackageExportRequest(BaseModel):
    agent_ids: list[str] = Field(default_factory=list)
    include_routing: bool = True
    include_agent_tools: bool = True
    include_modules_snapshot: bool = True
    strict_dependencies: bool = False


class PackageValidateRequest(BaseModel):
    content: str
    mapping: PackageMappingRequest = Field(default_factory=PackageMappingRequest)
    replace_existing_agents: bool = False


class PackageImportRequest(BaseModel):
    content: str
    mapping: PackageMappingRequest = Field(default_factory=PackageMappingRequest)
    replace_existing_agents: bool = False
    import_routing: bool = True
    import_agent_tools: bool = True


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
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/version")
async def get_version() -> dict:
    """Return the application version from system.json5."""
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
    enabled_agent_ids = {
        agent_id
        for agent_id, cfg in _system_config.get("agents", {}).items()
        if cfg.get("enable", True)
    }
    result = []
    for aid in _bus.registered_agents():
        if aid not in enabled_agent_ids:
            continue
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


@router.get("/agents/{agent_id}/candles")
async def get_agent_candles(
    agent_id: str,
    timeframe: str = "M5",
    count: int = 100,
) -> list[dict[str, Any]]:
    """Return recent candles for a specific AA agent.

    Resolves pair and broker from ``system_config.agents[agent_id]`` and maps the
    configured broker module name to its live adapter short_name before querying
    the DataContainer.
    """
    if _data_container is None:
        raise HTTPException(status_code=503, detail="DataContainer not available")

    agent_cfg = _system_config.get("agents", {}).get(agent_id)
    if not agent_cfg or not agent_cfg.get("enable", True):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not enabled")

    if agent_cfg.get("type") != "AA":
        raise HTTPException(status_code=400, detail=f"Agent {agent_id!r} is not an AA agent")

    pair = agent_cfg.get("pair")
    broker_module_name = agent_cfg.get("broker")
    if not pair or not broker_module_name:
        raise HTTPException(status_code=400, detail="Agent has no broker/pair configured")

    broker_instance = _connected_brokers.get(broker_module_name)
    if broker_instance is None:
        raise HTTPException(
            status_code=404,
            detail=f"Broker adapter {broker_module_name!r} is not connected",
        )

    tf = timeframe.upper().strip()
    if tf not in {"M5", "M15", "M30", "H1", "H4", "D1"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe!r}")

    limit = max(1, min(count, 500))
    candles = await _data_container.get_candles(
        broker_name=broker_instance.short_name,
        pair=str(pair).upper(),
        timeframe=tf,
        limit=limit,
    )
    return [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "tick_volume": c.tick_volume,
            "spread": float(c.spread),
        }
        for c in candles
    ]


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

        POST /agents/OAPR1-EURUSD-AA-ANLYS/ask
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
        source_agent_id="MGMT_-ALL___-GA-MGMT",
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
    except TimeoutError:
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
        "timestamp": datetime.now(UTC).isoformat(),
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
        try:
            from datetime import datetime as _dt
            since_dt = _dt.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)
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
            except TimeoutError:
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

    except asyncio.CancelledError:
        # Normal during application shutdown.
        pass
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

    from openforexai.registry.runtime_registry import RuntimeRegistry
    from openforexai.tools.base import ToolContext

    selected_agent_cfg: dict[str, Any] | None = None
    if req.agent_id:
        cfg = _system_config.get("agents", {}).get(req.agent_id)
        if not cfg or not cfg.get("enable", True):
            raise HTTPException(
                status_code=404,
                detail=f"Agent {req.agent_id!r} not found or disabled",
            )
        if _bus is not None and req.agent_id not in _bus.registered_agents():
            raise HTTPException(
                status_code=404,
                detail=f"Agent {req.agent_id!r} is not registered at runtime",
            )
        selected_agent_cfg = cfg

    broker_selector = req.broker_name or (
        str(selected_agent_cfg.get("broker"))
        if selected_agent_cfg and selected_agent_cfg.get("broker")
        else None
    )
    broker_module_name, broker_instance = _resolve_connected_broker(broker_selector)
    if broker_selector and broker_instance is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Broker {broker_selector!r} is not connected "
                "(use module name or short_name)."
            ),
        )
    context_broker_name = broker_instance.short_name if broker_instance is not None else None

    llm_name = req.llm_name or (
        str(selected_agent_cfg.get("llm"))
        if selected_agent_cfg and selected_agent_cfg.get("llm")
        else None
    )
    llm_instance = None
    if llm_name:
        try:
            llm_instance = RuntimeRegistry.get_llm(llm_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    derived_pair: str | None = None
    manual_pair = req.pair.strip().upper() if isinstance(req.pair, str) and req.pair.strip() else None
    if manual_pair:
        derived_pair = manual_pair
    elif selected_agent_cfg and selected_agent_cfg.get("pair"):
        derived_pair = str(selected_agent_cfg.get("pair")).upper()
    else:
        derived_pair = None

    context = ToolContext(
        agent_id=req.agent_id or "MGMT_-ALL___-GA-MGMT",
        broker_name=context_broker_name,
        pair=derived_pair,
        data_container=_data_container,
        repository=_repository,
        broker=broker_instance,
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
        extra={
            "llm_name": llm_name,
            "llm": llm_instance,
        },
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



@router.post("/test/llm/check", response_model=LLMCheckerResponse)
async def llm_checker(req: LLMCheckerRequest) -> LLMCheckerResponse:
    """Run an ephemeral LLM session with selectable tools and return a trace."""
    if _tool_registry is None:
        raise HTTPException(status_code=503, detail="ToolRegistry not available")

    from openforexai.ports.llm import ToolResult
    from openforexai.registry.runtime_registry import RuntimeRegistry
    from openforexai.tools.base import ToolContext

    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must contain at least one message")

    for idx, m in enumerate(req.messages):
        role = m.get("role")
        if role not in {"user", "assistant", "tool", "system"}:
            raise HTTPException(
                status_code=400,
                detail=f"messages[{idx}] has invalid role {role!r}",
            )

    unknown_tools = sorted({name for name in req.enabled_tools if _tool_registry.get(name) is None})
    valid_enabled_tools = [name for name in req.enabled_tools if _tool_registry.get(name) is not None]

    try:
        llm = RuntimeRegistry.get_llm(req.llm_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    selected_agent_cfg: dict[str, Any] | None = None
    if req.agent_id:
        cfg = _system_config.get("agents", {}).get(req.agent_id)
        if not cfg or not cfg.get("enable", True):
            raise HTTPException(
                status_code=404,
                detail=f"Agent {req.agent_id!r} not found or disabled",
            )
        if _bus is not None and req.agent_id not in _bus.registered_agents():
            raise HTTPException(
                status_code=404,
                detail=f"Agent {req.agent_id!r} is not registered at runtime",
            )
        selected_agent_cfg = cfg

    broker_selector = _normalize_broker_selector(req.broker_name)
    broker_module_name, broker_instance = _resolve_connected_broker(broker_selector)

    # LLM checker is diagnostic-first: do not block the whole session when a
    # selected broker is currently disconnected. Tools that depend on a
    # live broker will fail with their own error, but pure LLM exchange still works.
    broker_disconnected = bool(broker_selector and broker_instance is None)

    manual_pair = req.pair.strip().upper() if isinstance(req.pair, str) and req.pair.strip() else None
    if manual_pair:
        derived_pair = manual_pair
    elif selected_agent_cfg and selected_agent_cfg.get("pair"):
        derived_pair = str(selected_agent_cfg.get("pair")).upper()
    else:
        derived_pair = None


    context = ToolContext(
        agent_id=req.agent_id or "MGMT_-ALL___-GA-MGMT",
        broker_name=broker_instance.short_name if broker_instance is not None else None,
        pair=derived_pair,
        data_container=_data_container,
        repository=_repository,
        broker=broker_instance,
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
        extra={"llm_name": req.llm_name, "llm": llm},
    )

    tool_specs = _tool_registry.specs_for(valid_enabled_tools)
    messages: list[dict[str, Any]] = [dict(m) for m in req.messages]
    trace: list[dict[str, Any]] = []
    if broker_disconnected:
        trace.append({
            "type": "warning",
            "stage": "context",
            "message": f"Broker {broker_selector!r} is not connected; broker-dependent tools may fail",
        })
    if unknown_tools:
        trace.append({
            "type": "warning",
            "stage": "context",
            "message": f"Unknown tools ignored: {unknown_tools}",
        })
    total_tokens = 0
    final_text = ""
    stop_reason = "end_turn"
    resolved_max_tool_turns = req.max_tool_turns if isinstance(req.max_tool_turns, int) else 8

    for turn in range(resolved_max_tool_turns + 1):
        try:
            resolved_temp, resolved_max_tokens = _resolve_llm_checker_params(
                llm_name=req.llm_name,
                agent_cfg=selected_agent_cfg,
                request_temperature=req.temperature,
                request_max_tokens=req.max_tokens,
                llm_instance=llm,
            )
            _emit_checker_monitoring(
                "LLM_REQUEST",
                llm_name=req.llm_name,
                agent_id=req.agent_id,
                broker_name=context.broker_name,
                pair=context.pair,
                payload={
                    "turn": turn,
                    "system_prompt": req.system_prompt,
                    "messages": messages,
                    "message_count": len(messages),
                    "tool_count": len(tool_specs),
                    "tool_names": [t.get("name", "") for t in tool_specs],
                    "tool_specs": tool_specs,
                    "temperature": resolved_temp,
                    "max_tokens": resolved_max_tokens,
                },
            )
            response = await asyncio.wait_for(
                llm.complete_with_tools(
                    system_prompt=req.system_prompt,
                    messages=messages,
                    tools=tool_specs,
                    temperature=resolved_temp,
                    max_tokens=resolved_max_tokens,
                ),
                timeout=_LLM_CHECKER_LLM_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            _emit_checker_monitoring(
                "LLM_ERROR",
                llm_name=req.llm_name,
                agent_id=req.agent_id,
                broker_name=context.broker_name,
                pair=context.pair,
                payload={
                    "turn": turn,
                    "error": (
                        f"LLM checker call exceeded {_LLM_CHECKER_LLM_TIMEOUT_SECONDS:.0f}s timeout"
                    ),
                },
            )
            raise HTTPException(
                status_code=504,
                detail={
                    "stage": "llm_call",
                    "turn": turn,
                    "error": (
                        f"LLM checker call exceeded {_LLM_CHECKER_LLM_TIMEOUT_SECONDS:.0f}s timeout"
                    ),
                },
            ) from exc
        except Exception as exc:
            err_text = f"{type(exc).__name__}: {exc}"
            _emit_checker_monitoring(
                "LLM_ERROR",
                llm_name=req.llm_name,
                agent_id=req.agent_id,
                broker_name=context.broker_name,
                pair=context.pair,
                payload={"turn": turn, "error": err_text},
            )
            lower = err_text.lower()
            status_code = (
                400
                if (
                    "error code: 400" in lower
                    or "invalid_request_error" in lower
                    or "unsupported_value" in lower
                    or "invalid_prompt" in lower
                )
                else 500
            )
            raise HTTPException(
                status_code=status_code,
                detail={
                    "stage": "llm_call",
                    "turn": turn,
                    "error": err_text,
                },
            ) from exc

        total_tokens += response.input_tokens + response.output_tokens
        final_text = response.content or ""
        stop_reason = response.stop_reason or "end_turn"

        trace.append({
            "type": "llm_response",
            "turn": turn,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in response.tool_calls
            ],
        })

        _emit_checker_monitoring(
            "LLM_RESPONSE",
            llm_name=req.llm_name,
            agent_id=req.agent_id,
            broker_name=context.broker_name,
            pair=context.pair,
            payload={
                "turn": turn,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "tool_calls": len(response.tool_calls),
                "tool_names": [tc.name for tc in response.tool_calls],
                "tool_call_details": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
                "content": response.content or "",
            },
        )

        if not response.wants_tools:
            break

        if turn >= resolved_max_tool_turns:
            stop_reason = "max_tool_turns"
            trace.append({
                "type": "warning",
                "turn": turn,
                "message": "Max tool turns reached before completion",
            })
            break

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            tool = _tool_registry.get(tc.name)
            if tool is None:
                err = f"Tool {tc.name!r} is not registered"
                _emit_checker_monitoring(
                    "TOOL_CALL_FAILED",
                    llm_name=req.llm_name,
                    agent_id=req.agent_id,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload={
                        "turn": turn,
                        "tool_name": tc.name,
                        "arguments": tc.arguments,
                        "error": err,
                    },
                )
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps({"error": err}),
                    is_error=True,
                ))
                trace.append({
                    "type": "tool_result",
                    "turn": turn,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "is_error": True,
                    "result": {"error": err},
                })
                continue

            _emit_checker_monitoring(
                "TOOL_CALL_STARTED",
                llm_name=req.llm_name,
                agent_id=req.agent_id,
                broker_name=context.broker_name,
                pair=context.pair,
                payload={
                    "turn": turn,
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                },
            )
            try:
                raw_result = await asyncio.wait_for(
                    tool.execute(tc.arguments, context),
                    timeout=_LLM_CHECKER_TOOL_TIMEOUT_SECONDS,
                )
                serialized = json.dumps(raw_result, default=str)
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=serialized,
                    is_error=False,
                ))
                _emit_checker_monitoring(
                    "TOOL_CALL_COMPLETED",
                    llm_name=req.llm_name,
                    agent_id=req.agent_id,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload={
                        "turn": turn,
                        "tool_name": tc.name,
                        "arguments": tc.arguments,
                        "result": serialized,
                        "result_length": len(serialized),
                    },
                )
                trace.append({
                    "type": "tool_result",
                    "turn": turn,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "is_error": False,
                    "result": raw_result,
                })
            except TimeoutError:
                err_result = {
                    "error": (
                        f"Tool execution exceeded {_LLM_CHECKER_TOOL_TIMEOUT_SECONDS:.0f}s timeout"
                    )
                }
                _emit_checker_monitoring(
                    "TOOL_CALL_FAILED",
                    llm_name=req.llm_name,
                    agent_id=req.agent_id,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload={
                        "turn": turn,
                        "tool_name": tc.name,
                        "arguments": tc.arguments,
                        "error": err_result["error"],
                    },
                )
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps(err_result),
                    is_error=True,
                ))
                trace.append({
                    "type": "tool_result",
                    "turn": turn,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "is_error": True,
                    "result": err_result,
                })
            except Exception as exc:
                err_result = {"error": str(exc)}
                _emit_checker_monitoring(
                    "TOOL_CALL_FAILED",
                    llm_name=req.llm_name,
                    agent_id=req.agent_id,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload={
                        "turn": turn,
                        "tool_name": tc.name,
                        "arguments": tc.arguments,
                        "error": err_result["error"],
                    },
                )
                tool_results.append(ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps(err_result),
                    is_error=True,
                ))
                trace.append({
                    "type": "tool_result",
                    "turn": turn,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "is_error": True,
                    "result": err_result,
                })

        if hasattr(llm, "assistant_message_with_tools"):
            messages.append(llm.assistant_message_with_tools(response.content, response.tool_calls))
            turn_result = llm.tool_result_message(tool_results)
            if isinstance(turn_result, list):
                messages.extend(turn_result)
            else:
                messages.append(turn_result)
        else:
            content: list[dict[str, Any]] = []
            if response.content:
                content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.tool_call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in tool_results
                ],
            })

    return LLMCheckerResponse(
        llm_name=req.llm_name,
        final_text=final_text,
        total_tokens=total_tokens,
        stop_reason=stop_reason,
        trace=trace,
    )
@router.get("/config/view")
async def config_view() -> dict:
    """Return system.json5 with sensitive fields (api_key, password, …) masked.

    All keys whose name matches a known sensitive pattern are replaced with
    ``"***"`` recursively.  Environment variable values are already substituted
    at load time — this endpoint never exposes raw ``${VAR}`` tokens.
    """
    return _deep_mask(copy.deepcopy(_system_config))


@router.get("/config/system")
async def get_system_config_raw() -> dict:
    """Return raw system.json5 from disk for editing."""
    cfg_path = _project_root() / "config" / "system.json5"
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="system.json5 not found")
    try:
        return json5.loads(cfg_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Config file {cfg_path.name} contains invalid JSON5: {exc}",
        )



@router.get("/config/system/text")
async def get_system_config_text() -> dict[str, str]:
    """Return raw system.json5 text for editing (comments preserved)."""
    cfg_path = _project_root() / "config" / "system.json5"
    return {"text": _read_text_file(cfg_path)}


@router.post("/config/packages/export")
async def export_agent_package(req: PackageExportRequest) -> dict[str, Any]:
    """Export a portable multi-agent package as JSON5 text."""
    project_root = _project_root()
    package = build_export_package(
        _system_config,
        selected_agent_ids=req.agent_ids,
        include_routing=req.include_routing,
        include_agent_tools=req.include_agent_tools,
        include_modules_snapshot=req.include_modules_snapshot,
        event_routing_path=project_root / "config" / "RunTime" / "event_routing.json5",
        agent_tools_path=project_root / "config" / "RunTime" / "agent_tools.json5",
        strict_dependencies=req.strict_dependencies,
    )
    return {
        "package": package,
        "text": dump_json5_text(package),
    }


@router.post("/config/packages/validate")
async def validate_agent_package(req: PackageValidateRequest) -> dict[str, Any]:
    """Validate a package against local modules/tools and mapping rules."""
    package = parse_json5_text(req.content)
    known_tools = set()
    if _tool_registry is not None:
        known_tools = {tool.name for tool in _tool_registry.all_tools()}
    result = validate_package(
        package,
        current_system_config=_system_config,
        known_tools=known_tools,
        mapping=req.mapping.model_dump(),
        replace_existing_agents=req.replace_existing_agents,
    )
    return result


@router.post("/config/packages/import")
async def import_agent_package(req: PackageImportRequest) -> dict[str, Any]:
    """Import a validated package and apply runtime refresh/reload."""
    global _system_config
    package = parse_json5_text(req.content)
    known_tools = set()
    if _tool_registry is not None:
        known_tools = {tool.name for tool in _tool_registry.all_tools()}

    validation = validate_package(
        package,
        current_system_config=_system_config,
        known_tools=known_tools,
        mapping=req.mapping.model_dump(),
        replace_existing_agents=req.replace_existing_agents,
    )
    if not validation.get("ok"):
        return {
            "status": "invalid",
            **validation,
        }

    project_root = _project_root()
    next_system, next_routing, next_agent_tools = apply_import_package(
        package,
        current_system_config=_system_config,
        mapping=req.mapping.model_dump(),
        replace_existing_agents=req.replace_existing_agents,
        import_routing=req.import_routing,
        import_agent_tools=req.import_agent_tools,
        event_routing_path=project_root / "config" / "RunTime" / "event_routing.json5",
        agent_tools_path=project_root / "config" / "RunTime" / "agent_tools.json5",
    )

    _write_json_file(project_root / "config" / "system.json5", next_system)
    if req.import_routing:
        _write_json_file(project_root / "config" / "RunTime" / "event_routing.json5", next_routing)
    if req.import_agent_tools:
        _write_json_file(project_root / "config" / "RunTime" / "agent_tools.json5", next_agent_tools)

    previous_system_config = copy.deepcopy(_system_config)
    _system_config = next_system

    if _config_service is not None and hasattr(_config_service, "update_config"):
        _config_service.update_config(_system_config)

    runtime_apply = await _apply_runtime_agent_changes(previous_system_config)

    if _routing_table is not None and req.import_routing:
        try:
            _routing_table.load_rules_from_file(project_root / "config" / "RunTime" / "event_routing.json5")
        except Exception:
            pass

    return {
        "status": "imported",
        "runtime_apply": runtime_apply,
        "validation": validation,
    }

async def _trigger_agent_config_refresh() -> dict[str, int]:
    """Ask ConfigService to resend config for all running enabled agents."""
    if _bus is None:
        return {"requested": 0, "eligible": 0, "registered": 0}

    from openforexai.config.config_service import CONFIG_SERVICE_ID
    from openforexai.models.messaging import AgentMessage, EventType

    registered = set(_bus.registered_agents())
    eligible_agents = [
        agent_id
        for agent_id, cfg in _system_config.get("agents", {}).items()
        if cfg.get("enable", True) and agent_id in registered
    ]

    requested = 0
    for agent_id in eligible_agents:
        await _bus.publish(AgentMessage(
            event_type=EventType.AGENT_CONFIG_REQUESTED,
            source_agent_id="MGMT_-ALL___-GA-MGMT",
            target_agent_id=CONFIG_SERVICE_ID,
            payload={"agent_id": agent_id},
        ))
        requested += 1

    return {
        "requested": requested,
        "eligible": len(eligible_agents),
        "registered": len(registered),
    }


async def _run_runtime_agent(agent) -> None:
    try:
        await agent.start()
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def _apply_runtime_agent_changes(previous_system_config: dict[str, Any]) -> dict[str, Any]:
    """Start newly enabled agents and stop dynamically started disabled ones."""
    if _bus is None or _data_container is None or _repository is None:
        return {"started": 0, "stopped": 0, "refresh": await _trigger_agent_config_refresh()}

    global _runtime_agents, _runtime_agent_tasks

    prev_agents = previous_system_config.get("agents", {}) if isinstance(previous_system_config, dict) else {}
    next_agents = _system_config.get("agents", {}) if isinstance(_system_config, dict) else {}

    prev_enabled = {
        agent_id
        for agent_id, cfg in prev_agents.items()
        if isinstance(cfg, dict) and cfg.get("enable", True)
    }
    next_enabled = {
        agent_id
        for agent_id, cfg in next_agents.items()
        if isinstance(cfg, dict) and cfg.get("enable", True)
    }

    registered = set(_bus.registered_agents())
    to_start = sorted(agent_id for agent_id in next_enabled if agent_id not in registered)

    started = 0
    for agent_id in to_start:
        from openforexai.agents.agent import Agent

        agent = Agent(
            agent_id=agent_id,
            bus=_bus,
            data_container=_data_container,
            repository=_repository,
            monitoring_bus=_monitoring_bus,
        )
        task = asyncio.create_task(_run_runtime_agent(agent), name=f"runtime:{agent_id}")
        _runtime_agents[agent_id] = agent
        _runtime_agent_tasks[agent_id] = task
        started += 1

    to_stop = sorted(
        agent_id
        for agent_id in prev_enabled
        if agent_id not in next_enabled and agent_id in _runtime_agents
    )

    stopped = 0
    for agent_id in to_stop:
        agent = _runtime_agents.pop(agent_id, None)
        if agent is not None:
            await agent.stop()
        task = _runtime_agent_tasks.pop(agent_id, None)
        if task is not None:
            task.cancel()
        if _bus is not None:
            _bus.unregister_agent(agent_id)
        stopped += 1

    refresh = await _trigger_agent_config_refresh()
    return {"started": started, "stopped": stopped, "refresh": refresh}


@router.put("/config/system")
async def save_system_config_raw(content: dict[str, Any] | str) -> dict:
    """Persist raw system.json5, refresh memory, and trigger runtime apply."""
    cfg_path = _project_root() / "config" / "system.json5"
    _write_json_file(cfg_path, content)
    global _system_config
    previous_system_config = copy.deepcopy(_system_config)
    _system_config = (json5.loads(content) if isinstance(content, str) else content)

    if _config_service is not None and hasattr(_config_service, "update_config"):
        _config_service.update_config(_system_config)

    runtime_apply = await _apply_runtime_agent_changes(previous_system_config)
    return {
        "status": "saved",
        "file": "config/system.json5",
        "runtime_apply": runtime_apply,
    }

def _resolve_information_doc_path() -> Path:
    """Resolve information document under config/."""
    cfg_root = _project_root() / "config"
    path = cfg_root / "config.md"
    if path.exists():
        return path
    raise HTTPException(status_code=404, detail="Config file not found on disk: config.md")


@router.get("/config/information/readme")
async def get_information_readme_text() -> dict[str, str]:
    """Return config/config.md as raw text for the Information view."""
    doc_path = _resolve_information_doc_path()
    return {"text": _read_text_file(doc_path)}


@router.put("/config/information/readme")
async def save_information_readme_text(content: str = Body(..., embed=False)) -> dict[str, str]:
    """Save config/config.md raw text from the Information editor."""
    doc_path = _resolve_information_doc_path()
    _write_text_file(doc_path, content)
    return {"status": "saved", "file": f"config/{doc_path.name}"}


# Known config file names that can be served
_CONFIG_FILES: dict[str, str | None] = {
    "agent_tools":    None,  # resolved under project root config/RunTime/
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

    # Runtime config files live under project root config/RunTime/
    cfg_path = _project_root() / "config" / "RunTime" / f"{name}.json5"

    if not cfg_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Config file not found on disk: {cfg_path.name}",
        )

    try:
        return json5.loads(cfg_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Config file {cfg_path.name} contains invalid JSON5: {exc}",
        )



@router.get("/config/files/{name}/text")
async def config_file_text(name: str) -> dict[str, str]:
    """Return raw JSON5 config text by name (comments preserved)."""
    if name not in _CONFIG_FILES:
        raise HTTPException(
            status_code=404,
            detail=f"Config file {name!r} not available. "
                   f"Valid names: {list(_CONFIG_FILES.keys())}",
        )
    cfg_path = _project_root() / "config" / "RunTime" / f"{name}.json5"
    return {"text": _read_text_file(cfg_path)}

@router.put("/config/files/{name}")
async def save_config_file(name: str, content: dict[str, Any] | str) -> dict:
    """Save editable config files (agent_tools | event_routing)."""
    if name not in _CONFIG_FILES:
        raise HTTPException(
            status_code=404,
            detail=f"Config file {name!r} not available. "
                   f"Valid names: {list(_CONFIG_FILES.keys())}",
        )
    cfg_path = _project_root() / "config" / "RunTime" / f"{name}.json5"
    if not cfg_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Config file not found on disk: {cfg_path.name}",
        )
    _write_json_file(cfg_path, content)
    return {"status": "saved", "file": f"config/RunTime/{name}.json5"}


@router.get("/config/modules/{module_type}")
async def list_module_configs(module_type: str) -> dict:
    """Return the names of configured modules for *module_type* (llm | broker).

    Reads the module names from the in-memory system config so no disk I/O
    is needed here.  The names can then be used with the detail endpoint below.
    """
    if module_type not in ("llm", "broker"):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown module type: {module_type!r}. Valid types: 'llm', 'broker'",
        )
    names = list(_system_config.get("modules", {}).get(module_type, {}).keys())
    return {"names": names}


@router.get("/config/modules/{module_type}/{name}")
async def get_module_config(module_type: str, name: str) -> dict:
    """Return a single module config file with secrets masked.

    The path is resolved from ``system.json5`` under ``modules.<type>.<name>``,
    relative to the project root.  Sensitive fields are replaced with ``"***"``
    via *_deep_mask*.
    """
    cfg_path = _resolve_module_config_path(module_type, name)
    try:
        raw = json5.loads(cfg_path.read_text(encoding="utf-8"))
        return _deep_mask(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Config file {cfg_path.name} contains invalid JSON5: {exc}",
        )


@router.get("/config/modules/{module_type}/{name}/raw")
async def get_module_config_raw(module_type: str, name: str) -> dict:
    """Return a raw single module config file for editing."""
    cfg_path = _resolve_module_config_path(module_type, name)
    try:
        return json5.loads(cfg_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Config file {cfg_path.name} contains invalid JSON5: {exc}",
        )



@router.get("/config/modules/{module_type}/{name}/raw_text")
async def get_module_config_raw_text(module_type: str, name: str) -> dict[str, str]:
    """Return raw module config text for editing (comments preserved)."""
    cfg_path = _resolve_module_config_path(module_type, name)
    return {"text": _read_text_file(cfg_path)}

@router.put("/config/modules/{module_type}/{name}/raw")
async def save_module_config_raw(module_type: str, name: str, content: dict[str, Any] | str) -> dict:
    """Save a raw single module config file."""
    cfg_path = _resolve_module_config_path(module_type, name)
    _write_json_file(cfg_path, content)
    return {"status": "saved", "file": str(cfg_path)}


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(
    bus=None,
    routing_table=None,
    tool_registry=None,
    indicator_registry=None,
    monitoring_bus=None,
    system_config: dict[str, Any] | None = None,
    data_container=None,
    repository=None,
    connected_brokers: dict | None = None,
    config_service=None,
) -> FastAPI:
    """Build the FastAPI application and wire runtime dependencies."""
    global _bus, _routing_table, _tool_registry, _indicator_registry
    global _monitoring_bus, _system_config, _start_time
    global _data_container, _repository, _connected_brokers, _config_service
    global _runtime_agents, _runtime_agent_tasks

    _bus = bus
    _routing_table = routing_table
    _tool_registry = tool_registry
    _indicator_registry = indicator_registry
    _monitoring_bus = monitoring_bus
    _system_config = system_config or {}
    _data_container = data_container
    _repository = repository
    _connected_brokers = connected_brokers or {}
    _config_service = config_service
    _runtime_agents = {}
    _runtime_agent_tasks = {}
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
    # NOTE: app.mount("/", StaticFiles(...)) is intentionally avoided here because
    # Starlette's Mount matches WebSocket scopes too, causing StaticFiles to crash
    # with AssertionError("scope['type'] == 'http'") on WS /ws/monitoring.
    # A plain GET catch-all route only ever matches HTTP — WebSocket routes are safe.
    _ui_dist = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
    if _ui_dist.exists():
        from fastapi.responses import FileResponse as _FileResponse

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _serve_spa(full_path: str) -> _FileResponse:  # type: ignore[return]
            target = _ui_dist / full_path
            if target.is_file():
                return _FileResponse(str(target))
            return _FileResponse(str(_ui_dist / "index.html"))

    return app


