"""FastAPI management application — OpenForexAI control plane.

Endpoints
---------
GET  /health                  System health (agents alive, queue depths, uptime)
GET  /metrics                 Key counters (messages dispatched, tool calls, â€¦)
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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import json5
from fastapi import (
    APIRouter,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.agents.analysis_snapshot import (
    _SAFE_SCRIPT_BUILTINS,
    _substitute_placeholders,
    build_analysis_snapshot,
    build_decision_only_system_prompt,
    build_decision_only_user_message,
    build_snapshot_system_prompt,
    build_snapshot_user_message,
    preview_snapshot_tool_block,
    preview_calculation_block,
)
from openforexai.config.json_loader import load_json_config
from openforexai.management.package_io import (
    apply_import_package,
    build_export_package,
    dump_json5_text,
    parse_json5_text,
    validate_package,
)
from openforexai.runtime import control as runtime_control
from openforexai.tools.argument_templates import (
    build_agent_placeholder_values,
    resolve_argument_templates,
)
from openforexai.utils.logging import configure_logging, get_logger

_logger = get_logger(__name__)

# â"€â"€ Agent-query response registry â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# Uses the EventBus pending-future mechanism — no subscribe() needed.
# The bus resolves futures keyed by correlation_id when AGENT_QUERY_RESPONSE arrives.


def setup_query_handler(bus) -> None:
    """No-op — response routing now uses bus.register_response_future()."""
    pass


# â"€â"€ Dependency injection stubs (populated by ManagementServer) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
_connected_brokers: dict = {}  # broker_name â†’ AbstractBroker live instances
_config_service = None
_runtime_agents: dict[str, Any] = {}
_runtime_agent_tasks: dict[str, asyncio.Task] = {}
_runtime_composers: dict[str, Any] = {}
_runtime_composer_tasks: dict[str, asyncio.Task] = {}
_active_agents: dict[str, Any] = {}
_active_composers: dict[str, Any] = {}
_llm_services: dict[str, Any] = {}   # module_name → LLMService
_start_time: float = time.monotonic()

_update_task: asyncio.Task | None = None
_update_output: list[str] = []
_UPDATE_OUTPUT_LIMIT = 600
_update_status: dict[str, Any] = {
    "state": "idle",  # idle | running | completed | failed
    "started_at": None,
    "ended_at": None,
    "exit_code": None,
    "message": "",
    "requested_version": None,
}

_LLM_CHECKER_LLM_TIMEOUT_SECONDS = 45.0
_LLM_CHECKER_TOOL_TIMEOUT_SECONDS = 20.0

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_EXPECTED_KEY: str | None = os.environ.get("MANAGEMENT_API_KEY")


_GITHUB_RELEASES_URL = "https://api.github.com/repos/mcGeorge66/OpenForexAI/releases"


def _configured_log_level() -> str:
    system_cfg = _system_config.get("system", {}) if isinstance(_system_config, dict) else {}
    raw = system_cfg.get("log_level", "INFO") if isinstance(system_cfg, dict) else "INFO"
    level = str(raw).strip().upper()
    return "DEBUG" if level == "DEBUG" else "INFO"


def _apply_monitoring_detail_level() -> None:
    configure_logging(_configured_log_level())
    if _monitoring_bus is None or not hasattr(_monitoring_bus, "set_detail_level"):
        return
    _monitoring_bus.set_detail_level(_configured_log_level())


_CLOSED_STATUSES = frozenset(("closed", "closed_holiday", "closed_weekend"))

def _compute_agent_session_active(cfg: dict[str, Any], now_utc: datetime) -> bool:
    """Return True if the agent's session_filter passes for the given UTC time.

    Uses get_session_status (the canonical tool) so session logic is shared
    across the whole system.
    """
    if not cfg.get("enable", True):
        return False
    session_filter = cfg.get("session_filter") or []
    if not session_filter:
        return True

    from openforexai.tools.market.session_status import get_session_status

    status_result = get_session_status(now_utc)
    sessions = status_result.get("sessions", {})

    for entry in session_filter:
        session_name = str(entry.get("session", "")).lower()
        sess = sessions.get(session_name)
        if sess is None:
            continue
        pre_min  = int(entry.get("pre",  0))
        post_min = int(entry.get("post", 0))

        in_base_session = sess.get("status") not in _CLOSED_STATUSES
        minutes_since_open  = sess.get("minutes_since_open")
        minutes_until_close = sess.get("minutes_until_close")

        if in_base_session:
            # pre > 0: agent only activates pre minutes after official open
            if pre_min > 0 and (minutes_since_open is None or minutes_since_open < pre_min):
                continue
            # post < 0: agent deactivates |post| minutes before official close
            if post_min < 0 and (minutes_until_close is None or minutes_until_close <= -post_min):
                continue
            return True

    return False


def _agent_task_summary(agent_cfg: dict[str, Any]) -> str:
    comment = agent_cfg.get("comment")
    if isinstance(comment, str) and comment.strip():
        return comment.strip()
    prompt = agent_cfg.get("system_prompt")
    if isinstance(prompt, str):
        for line in prompt.splitlines():
            text = line.strip()
            if text:
                return text[:160]
    return "(no task description)"


def _fetch_remote_release_info() -> dict[str, Any]:
    req = urllib.request.Request(
        _GITHUB_RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "OpenForexAI-Management"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.status != 200:
                return {
                    "version": None,
                    "prerelease": None,
                    "published_at": None,
                    "url": None,
                    "error": f"HTTP {response.status}",
                }
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, PermissionError, OSError) as exc:
        return {
            "version": None,
            "prerelease": None,
            "published_at": None,
            "url": None,
            "error": str(exc),
        }

    try:
        releases = json.loads(body)
    except json.JSONDecodeError:
        return {
            "version": None,
            "prerelease": None,
            "published_at": None,
            "url": None,
            "error": "Invalid JSON from GitHub API",
        }

    if not isinstance(releases, list) or not releases:
        return {
            "version": None,
            "prerelease": None,
            "published_at": None,
            "url": None,
            "error": "No releases found",
        }

    first = next((r for r in releases if isinstance(r, dict) and not r.get("draft")), None)
    if not isinstance(first, dict):
        return {
            "version": None,
            "prerelease": None,
            "published_at": None,
            "url": None,
            "error": "No non-draft releases found",
        }

    tag = str(first.get("tag_name") or "").strip()
    normalized = tag[1:] if tag.lower().startswith("v") else tag
    return {
        "version": normalized or None,
        "prerelease": bool(first.get("prerelease", False)),
        "published_at": first.get("published_at"),
        "url": first.get("html_url"),
        "error": None,
    }


def _wrapper_restart_signal_path() -> Path | None:
    raw = os.environ.get("OPENFOREXAI_RESTART_SIGNAL_PATH", "").strip()
    if not raw:
        return None
    return Path(raw)


def _restart_supported() -> bool:
    """Return True only when wrapper-managed restart is available.

    For externally supervised deployments (e.g. systemd/services), restart
    should be controlled by the supervisor, not by the UI/API restart action.
    """
    wrapped = os.environ.get("OPENFOREXAI_WRAPPED", "").strip().lower() in {"1", "true", "yes", "on"}
    return wrapped and _wrapper_restart_signal_path() is not None


def _append_update_output(line: str) -> None:
    _update_output.append(line.rstrip("\n"))
    if len(_update_output) > _UPDATE_OUTPUT_LIMIT:
        del _update_output[: len(_update_output) - _UPDATE_OUTPUT_LIMIT]


def _update_status_payload() -> dict[str, Any]:
    payload = dict(_update_status)
    payload["output"] = list(_update_output)
    payload["runtime_paused"] = runtime_control.is_paused()
    payload["restart_supported"] = _restart_supported()
    payload["restart_available"] = bool(
        payload.get("state") == "completed" and payload.get("exit_code") == 0
    )
    return payload


def _serialize_monitoring_event(event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "timestamp": event.timestamp.isoformat(),
        "source": event.source_module,
        "event_type": str(event.event_type),
        "broker": event.broker_name,
        "pair": event.pair,
        "payload": event.payload,
    }


def _event_belongs_to_agent(event, agent_id: str) -> bool:
    if getattr(event, "source_module", "") == f"agent:{agent_id}":
        return True
    payload = getattr(event, "payload", None)
    if not isinstance(payload, dict):
        return False
    return payload.get("agent_id") == agent_id or payload.get("agent") == agent_id


def _resolve_active_agent(agent_id: str):
    agent = _active_agents.get(agent_id)
    if agent is not None:
        return agent
    return _runtime_agents.get(agent_id)


def _resolve_agent_runtime_context(agent_id: str) -> tuple[dict[str, Any], str, str]:
    agent_cfg = _system_config.get("agents", {}).get(agent_id)
    if not isinstance(agent_cfg, dict) or not agent_cfg.get("enable", True):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not enabled")
    pair = str(agent_cfg.get("pair") or "").strip().upper()
    broker_module_name = str(agent_cfg.get("broker") or "").strip()
    if not pair or not broker_module_name:
        raise HTTPException(
            status_code=400,
            detail=f"Agent {agent_id!r} has no broker/pair runtime context",
        )
    broker_instance = _connected_brokers.get(broker_module_name)
    if broker_instance is None:
        raise HTTPException(
            status_code=404,
            detail=f"Broker adapter {broker_module_name!r} is not connected",
        )
    broker_name = str(getattr(broker_instance, "short_name", "")).strip() or broker_module_name
    return agent_cfg, broker_name, pair


def _resolve_agent_snapshot_context(
    agent_id: str,
    *,
    pair_override: str | None = None,
    require_pair: bool = True,
) -> tuple[dict[str, Any], str, str]:
    agent_cfg = _system_config.get("agents", {}).get(agent_id)
    if not isinstance(agent_cfg, dict) or not agent_cfg.get("enable", True):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not enabled")

    broker_module_name = str(agent_cfg.get("broker") or "").strip()
    if not broker_module_name:
        raise HTTPException(
            status_code=400,
            detail=f"Agent {agent_id!r} has no broker runtime context",
        )
    broker_instance = _connected_brokers.get(broker_module_name)
    if broker_instance is None:
        raise HTTPException(
            status_code=404,
            detail=f"Broker adapter {broker_module_name!r} is not connected",
        )
    broker_name = str(getattr(broker_instance, "short_name", "")).strip() or broker_module_name

    configured_pair = str(agent_cfg.get("pair") or "").strip().upper()
    if configured_pair and configured_pair != "ALL___":
        return agent_cfg, broker_name, configured_pair

    requested_pair = str(pair_override or "").strip().upper()
    if requested_pair and requested_pair != "ALL___":
        return agent_cfg, broker_name, requested_pair

    agent = _resolve_active_agent(agent_id)
    context = getattr(getattr(agent, "_tool_dispatcher", None), "_context", None)
    context_pair = str(getattr(context, "pair", "") or "").strip().upper() if context is not None else ""
    if context_pair and context_pair != "ALL___":
        return agent_cfg, broker_name, context_pair

    if require_pair:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Agent {agent_id!r} has no fixed pair context for snapshot preview. "
                "Use a pair-bound context agent or provide a pair override."
            ),
        )
    return agent_cfg, broker_name, ""


async def _build_standard_agent_trigger_payload(
    agent_id: str,
    *,
    pair_override: str | None = None,
    require_pair: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    if _data_container is None:
        raise HTTPException(status_code=503, detail="DataContainer not available")
    _, broker_name, pair = _resolve_agent_snapshot_context(
        agent_id, pair_override=pair_override, require_pair=require_pair
    )
    if pair:
        candles = await _data_container.get_candles(broker_name, pair, "M5", limit=1)
        latest = candles[-1] if candles else None
    else:
        latest = None
    payload = {
        "broker_name": broker_name,
        "pair": pair,
        "candle": (
            {
                "timestamp": latest.timestamp.isoformat(),
                "open": round(float(latest.open), 5),
                "high": round(float(latest.high), 5),
                "low": round(float(latest.low), 5),
                "close": round(float(latest.close), 5),
                "tick_volume": latest.tick_volume,
                "spread": round(float(latest.spread), 2),
                "timeframe": "M5",
            }
            if latest is not None
            else {}
        ),
        "is_null_candle": latest is None,
    }
    return broker_name, pair, payload


def _drain_monitoring_queue(queue: asyncio.Queue) -> list[Any]:
    events: list[Any] = []
    while True:
        try:
            events.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return events


async def _execute_agent_inspection(
    *,
    agent_id: str,
    input_text: str,
    snapshot_profile_override: dict[str, Any] | None = None,
    decision_prompt_profile_override: dict[str, Any] | None = None,
) -> AgentExecuteResponse:
    agent = _resolve_active_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} is not active")
    if getattr(agent, "_llm_service_id", None) is None or getattr(agent, "_tool_dispatcher", None) is None:
        raise HTTPException(status_code=503, detail=f"Agent {agent_id!r} is not ready")
    if _monitoring_bus is None:
        raise HTTPException(status_code=503, detail="Monitoring bus not available")

    queue = _monitoring_bus.subscribe(maxsize=4096)
    run_id = str(uuid4())
    source = "inspect_console"
    started = perf_counter()

    context = agent._tool_dispatcher._context
    previous_pair = context.pair if context is not None else None
    previous_snapshot_name = getattr(agent, "_snapshot_profile_name", None)
    previous_snapshot_cfg = dict(getattr(agent, "_snapshot_profile_config", {}) or {})
    previous_decision_name = getattr(agent, "_decision_prompt_profile_name", None)
    previous_decision_cfg = dict(getattr(agent, "_decision_prompt_profile_config", {}) or {})
    previous_cycle_extra: dict[str, Any] = {}

    effective_snapshot_profile = dict(previous_snapshot_cfg)
    if isinstance(snapshot_profile_override, dict):
        effective_snapshot_profile.update(snapshot_profile_override)
    effective_decision_profile = dict(previous_decision_cfg)
    if isinstance(decision_prompt_profile_override, dict):
        effective_decision_profile.update(decision_prompt_profile_override)

    if effective_snapshot_profile and not effective_snapshot_profile.get("name"):
        effective_snapshot_profile["name"] = previous_snapshot_name
    if effective_decision_profile and not effective_decision_profile.get("name"):
        effective_decision_profile["name"] = previous_decision_name

    built_user_message = ""
    final_response = ""
    effective_system_prompt: str | None = None
    total_tokens = 0
    validation_errors: list[str] = []
    snapshot: dict[str, Any] | None = None
    trigger = "agent_query"
    lock_acquired = False

    run_lock = getattr(agent, "_run_lock", None)
    if run_lock is not None:
        try:
            await asyncio.wait_for(run_lock.acquire(), timeout=30.0)
            lock_acquired = True
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail=f"Agent {agent_id!r} is busy processing another cycle — try again in a moment",
            )

    try:
        # Substitute {pair} / {broker} placeholders in the agent system prompt once,
        # using the configured values so the prompt can reference e.g. "You trade {pair}".
        _prompt_ph: dict[str, Any] = {
            "pair":    str(agent._config.get("pair")    or "").strip().upper(),
            "comment": str(agent._config.get("comment") or "").strip(),
        }
        _base_prompt = _substitute_placeholders(agent._system_prompt, _prompt_ph)

        agent._snapshot_profile_name = str(effective_snapshot_profile.get("name") or previous_snapshot_name or "").strip() or None
        agent._snapshot_profile_config = effective_snapshot_profile
        agent._decision_prompt_profile_name = str(effective_decision_profile.get("name") or previous_decision_name or "").strip() or None
        agent._decision_prompt_profile_config = effective_decision_profile

        if agent._is_analysis_agent():
            trigger = "m5_candle_trigger"
            broker_name, pair, trigger_payload = await _build_standard_agent_trigger_payload(agent_id)
            if context is not None:
                context.pair = pair
            snapshot, validation_errors = await build_analysis_snapshot(
                broker_name=broker_name,
                pair=pair,
                trigger_payload=trigger_payload,
                profile=effective_snapshot_profile,
                strategy_aggressiveness=str(agent._config.get("strategy_aggressiveness", "BALANCED")),
                agent_id=agent.agent_id,
                repository=_repository,
                broker=None,
                monitoring_bus=_monitoring_bus,
                event_bus=_bus,
            )
            if validation_errors:
                agent._emit_analysis_snapshot_invalid(
                    trigger=trigger,
                    source=source,
                    snapshot=snapshot,
                    errors=validation_errors,
                )
            else:
                agent._emit_analysis_snapshot_built(
                    trigger=trigger,
                    source=source,
                    snapshot=snapshot,
                )
            built_user_message = build_decision_only_user_message(snapshot, effective_snapshot_profile)
            agent._emit_agent_input_built(
                trigger=trigger,
                source=source,
                raw_payload=trigger_payload,
                derived_user_message=built_user_message,
            )
            effective_system_prompt = build_decision_only_system_prompt(
                _base_prompt,
                effective_decision_profile,
            )
            if not validation_errors:
                final_response, total_tokens, _ = await agent._run_decision_only_cycle(
                    user_message=built_user_message,
                    trigger=trigger,
                    source=source,
                )
        elif agent._is_broker_agent():
            trigger = "analysis_result"
            analysis_text = str(input_text or "").strip()
            if not analysis_text:
                raise HTTPException(
                    status_code=400,
                    detail="Broker-agent execute requires analysis JSON in the chat input.",
                )
            analysis_object = agent._parse_json_object(analysis_text)
            if not isinstance(analysis_object, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Broker-agent execute requires valid analysis JSON in the chat input.",
                )
            built_user_message = analysis_text
            effective_system_prompt = _base_prompt
            if context is not None:
                cycle_pair = agent._resolve_cycle_pair(trigger, {"response": analysis_text})
                context.pair = cycle_pair or context.pair
                for key in (
                    "cycle_trigger",
                    "analysis_response_text",
                    "analysis_response_object",
                    "analysis_event_payload",
                    "analysis_source_agent_id",
                ):
                    previous_cycle_extra[key] = context.extra.get(key)
                context.extra["cycle_trigger"] = trigger
                context.extra["analysis_response_text"] = analysis_text
                context.extra["analysis_response_object"] = analysis_object
                context.extra["analysis_event_payload"] = {"response": analysis_text}
                context.extra["analysis_source_agent_id"] = source
            if effective_snapshot_profile and context is not None and context.pair:
                broker_name, pair, trigger_payload = await _build_standard_agent_trigger_payload(
                    agent_id,
                    pair_override=context.pair,
                )
                snapshot, validation_errors = await build_analysis_snapshot(
                    broker_name=broker_name,
                    pair=pair,
                    trigger_payload=trigger_payload,
                    profile=effective_snapshot_profile,
                    strategy_aggressiveness=str(agent._config.get("strategy_aggressiveness", "BALANCED")),
                    agent_id=agent.agent_id,
                    repository=_repository,
                    broker=None,
                    monitoring_bus=_monitoring_bus,
                    event_bus=_bus,
                )
                if validation_errors:
                    agent._emit_analysis_snapshot_invalid(
                        trigger=trigger,
                        source=source,
                        snapshot=snapshot,
                        errors=validation_errors,
                    )
                else:
                    agent._emit_analysis_snapshot_built(
                        trigger=trigger,
                        source=source,
                        snapshot=snapshot,
                    )
                snapshot_context = build_snapshot_user_message(
                    snapshot,
                    effective_snapshot_profile,
                )
                built_user_message = f"{analysis_text}\n\n{snapshot_context}" if analysis_text.strip() else snapshot_context
                effective_system_prompt = build_snapshot_system_prompt(
                    _base_prompt,
                    effective_decision_profile,
                    allow_tools=True,
                )
            agent._emit_agent_input_built(
                trigger=trigger,
                source=source,
                raw_payload={"response": analysis_text},
                derived_user_message=built_user_message,
            )
            final_response, total_tokens, _ = await agent._run_with_tools(
                built_user_message,
                trigger=trigger,
                source=source,
                system_prompt_override=effective_system_prompt,
            )
        else:
            analysis_text = str(input_text or "").strip()
            if not analysis_text:
                raise HTTPException(
                    status_code=400,
                    detail="Execute requires manual input for this agent type.",
                )
            built_user_message = analysis_text
            effective_system_prompt = _base_prompt
            if effective_snapshot_profile and context is not None:
                try:
                    broker_name, pair, trigger_payload = await _build_standard_agent_trigger_payload(
                        agent_id,
                        pair_override=context.pair,
                    )
                except HTTPException:
                    trigger_payload = {}
                else:
                    snapshot, validation_errors = await build_analysis_snapshot(
                        broker_name=broker_name,
                        pair=pair,
                        trigger_payload=trigger_payload,
                        profile=effective_snapshot_profile,
                        strategy_aggressiveness=str(agent._config.get("strategy_aggressiveness", "BALANCED")),
                        agent_id=agent.agent_id,
                        repository=_repository,
                        broker=None,
                        monitoring_bus=_monitoring_bus,
                        event_bus=_bus,
                    )
                    if validation_errors:
                        agent._emit_analysis_snapshot_invalid(
                            trigger=trigger,
                            source=source,
                            snapshot=snapshot,
                            errors=validation_errors,
                        )
                    else:
                        agent._emit_analysis_snapshot_built(
                            trigger=trigger,
                            source=source,
                            snapshot=snapshot,
                        )
                    snapshot_context = build_snapshot_user_message(
                        snapshot,
                        effective_snapshot_profile,
                    )
                    built_user_message = f"{analysis_text}\n\n{snapshot_context}" if analysis_text.strip() else snapshot_context
                    effective_system_prompt = build_snapshot_system_prompt(
                        _base_prompt,
                        effective_decision_profile,
                        allow_tools=True,
                    )
            agent._emit_agent_input_built(
                trigger=trigger,
                source=source,
                raw_payload={"question": analysis_text},
                derived_user_message=built_user_message,
            )
            final_response, total_tokens, _ = await agent._run_with_tools(
                built_user_message,
                trigger=trigger,
                source=source,
                system_prompt_override=effective_system_prompt,
            )
    except RuntimeError as exc:
        _logger.error(
            "Execute endpoint: LLM call failed",
            agent_id=agent_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail=f"LLM call failed for agent {agent_id!r}: {exc}",
        )
    except Exception as exc:
        import traceback as _tb
        _logger.error(
            "Execute endpoint: unexpected error",
            agent_id=agent_id,
            error=str(exc),
            traceback=_tb.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Execute failed for agent {agent_id!r}: {type(exc).__name__}: {exc}",
        )
    finally:
        if lock_acquired and run_lock is not None:
            run_lock.release()
        if context is not None:
            context.pair = previous_pair
            for key, previous_value in previous_cycle_extra.items():
                if previous_value is None:
                    context.extra.pop(key, None)
                else:
                    context.extra[key] = previous_value
        agent._snapshot_profile_name = previous_snapshot_name
        agent._snapshot_profile_config = previous_snapshot_cfg
        agent._decision_prompt_profile_name = previous_decision_name
        agent._decision_prompt_profile_config = previous_decision_cfg
        await asyncio.sleep(0)
        raw_events = _drain_monitoring_queue(queue)
        _monitoring_bus.unsubscribe(queue)

    events = [
        _serialize_monitoring_event(event)
        for event in raw_events
        if _event_belongs_to_agent(event, agent_id)
    ]
    return AgentExecuteResponse(
        run_id=run_id,
        agent_id=agent_id,
        trigger=trigger,
        source=source,
        built_user_message=built_user_message,
        final_response=final_response,
        effective_system_prompt=effective_system_prompt,
        total_tokens=total_tokens,
        elapsed_ms=round((perf_counter() - started) * 1000.0, 1),
        snapshot=snapshot,
        validation_errors=validation_errors,
        events=events,
    )


def _run_update_process_sync(cmd: list[str], cwd: str) -> int:
    """Run updater process in sync mode (fallback for Windows selector loop)."""
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        _append_update_output(line.rstrip("\n"))
    return proc.wait()


async def _run_update_job(requested_version: str | None) -> None:
    global _update_task, _update_status

    root = _project_root()
    updater = root / "tools" / "github-updater.py"
    if not updater.exists():
        _append_update_output(f"[update-error] updater not found: {updater}")
        _update_status = {
            "state": "failed",
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "exit_code": -1,
            "message": f"Updater not found: {updater}",
            "requested_version": requested_version,
        }
        _update_task = None
        return

    cmd = [sys.executable, str(updater), "--yes"]
    if requested_version:
        cmd.extend(["--version", requested_version])

    _update_output.clear()
    _update_status = {
        "state": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": None,
        "exit_code": None,
        "message": "Update started",
        "requested_version": requested_version,
    }

    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            assert proc.stdout is not None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                _append_update_output(line)

            exit_code = await proc.wait()
        except NotImplementedError:
            _append_update_output(
                "[update-info] Async subprocess unavailable on this runtime; using sync fallback."
            )
            exit_code = await asyncio.to_thread(_run_update_process_sync, cmd, str(root))

        _update_status = {
            "state": "completed" if exit_code == 0 else "failed",
            "started_at": _update_status.get("started_at"),
            "ended_at": datetime.now(UTC).isoformat(),
            "exit_code": exit_code,
            "message": "Update finished" if exit_code == 0 else "Update failed",
            "requested_version": requested_version,
        }
    except Exception as exc:
        detail = str(exc).strip() or repr(exc)
        _append_update_output(f"[update-error] {type(exc).__name__}: {detail}")
        _update_status = {
            "state": "failed",
            "started_at": _update_status.get("started_at"),
            "ended_at": datetime.now(UTC).isoformat(),
            "exit_code": -1,
            "message": f"{type(exc).__name__}: {detail}",
            "requested_version": requested_version,
        }
    finally:
        _update_task = None


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


def _connected_broker_short_names() -> list[str]:
    names: list[str] = []
    for broker in _connected_brokers.values():
        short_name = str(getattr(broker, "short_name", "")).strip()
        if short_name and short_name not in names:
            names.append(short_name)
    return names


def _serialize_order_book_entry(entry: Any, *, include_analysis: bool = False) -> dict[str, Any]:
    snapshot = entry.market_context_snapshot if isinstance(entry.market_context_snapshot, dict) else {}
    decision_context = snapshot.get("decision_context") if isinstance(snapshot.get("decision_context"), dict) else {}
    analysis_raw = snapshot.get("analyst_recommendation_raw")
    analysis_object = snapshot.get("analyst_recommendation") if isinstance(snapshot.get("analyst_recommendation"), dict) else None
    analysis_overlays = snapshot.get("analysis_overlays") if isinstance(snapshot.get("analysis_overlays"), dict) else {}
    opened_reference = entry.fill_price or entry.requested_price
    stake_estimate = None
    if opened_reference is not None:
        try:
            stake_estimate = float(opened_reference) * float(entry.units)
        except (TypeError, ValueError):
            stake_estimate = None

    payload = {
        "id": str(entry.id),
        "broker_name": entry.broker_name,
        "broker_order_id": entry.broker_order_id,
        "sync_key": entry.sync_key,
        "agent_id": entry.agent_id,
        "pair": entry.pair,
        "direction": entry.direction.value,
        "order_type": entry.order_type.value,
        "units": entry.units,
        "requested_price": float(entry.requested_price),
        "fill_price": float(entry.fill_price) if entry.fill_price is not None else None,
        "stop_loss": float(entry.stop_loss) if entry.stop_loss is not None else None,
        "take_profit": float(entry.take_profit) if entry.take_profit is not None else None,
        "status": entry.status.value,
        "requested_at": entry.requested_at.isoformat(),
        "opened_at": entry.opened_at.isoformat() if entry.opened_at else None,
        "close_requested_at": entry.close_requested_at.isoformat() if entry.close_requested_at else None,
        "closed_at": entry.closed_at.isoformat() if entry.closed_at else None,
        "signal_confidence": entry.signal_confidence,
        "entry_reasoning": entry.entry_reasoning,
        "close_reason": entry.close_reason.value if hasattr(entry.close_reason, "value") else entry.close_reason,
        "close_price": float(entry.close_price) if entry.close_price is not None else None,
        "close_reasoning": entry.close_reasoning,
        "pnl_pips": float(entry.pnl_pips) if entry.pnl_pips is not None else None,
        "pnl_account_currency": float(entry.pnl_account_currency) if entry.pnl_account_currency is not None else None,
        "sync_confirmed": entry.sync_confirmed,
        "confirmed_by_broker": bool(getattr(entry, "confirmed_by_broker", False)),
        "stake_estimate": stake_estimate,
        "decision_context": decision_context,
        "analysis_overlays": analysis_overlays,
        "analysis_available": isinstance(analysis_raw, str) and bool(analysis_raw.strip()),
    }
    if include_analysis:
        payload["analysis_text"] = analysis_raw if isinstance(analysis_raw, str) else None
        payload["analysis"] = analysis_object
        payload["market_context_snapshot"] = snapshot
    return payload


async def _reconcile_order_book_entries_with_broker(entries: list[Any]) -> None:
    if _repository is None or not entries:
        return

    by_broker: dict[str, list[Any]] = {}
    for entry in entries:
        if bool(getattr(entry, "confirmed_by_broker", False)):
            continue
        broker_name = str(getattr(entry, "broker_name", "") or "").strip()
        if not broker_name:
            continue
        by_broker.setdefault(broker_name, []).append(entry)

    for broker_name, broker_entries in by_broker.items():
        _, broker = _resolve_connected_broker(broker_name)
        if broker is None:
            continue

        now = datetime.now(UTC)
        open_positions = None
        open_by_id: dict[str, Any] = {}
        open_by_sync_key: dict[str, Any] = {}

        async def _ensure_open_positions() -> None:
            nonlocal open_positions, open_by_id, open_by_sync_key
            if open_positions is not None:
                return
            open_positions = await broker.get_open_positions()
            open_by_id = {str(pos.broker_position_id): pos for pos in open_positions}
            open_by_sync_key = {
                str(pos.sync_key): pos
                for pos in open_positions
                if getattr(pos, "sync_key", None)
            }

        for entry in broker_entries:
            entry_id = str(entry.id)
            status_value = str(getattr(entry.status, "value", entry.status))
            broker_order_id = str(getattr(entry, "broker_order_id", "") or "").strip()
            sync_key = str(getattr(entry, "sync_key", "") or "").strip()

            try:
                if status_value in {"PENDING", "OPEN", "PARTIALLY_FILLED"}:
                    await _ensure_open_positions()
                    broker_position = (
                        open_by_id.get(broker_order_id)
                        or (open_by_sync_key.get(sync_key) if sync_key else None)
                    )
                    if broker_position is not None:
                        updates = {
                            "broker_order_id": broker_position.broker_position_id,
                            "sync_key": broker_position.sync_key or entry.sync_key,
                            "pair": broker_position.pair,
                            "direction": broker_position.direction,
                            "units": broker_position.units,
                            "fill_price": broker_position.open_price,
                            "stop_loss": broker_position.stop_loss,
                            "take_profit": broker_position.take_profit,
                            "status": OrderStatus.OPEN,
                            "opened_at": broker_position.opened_at,
                            "last_broker_sync": now,
                            "sync_confirmed": True,
                            "confirmed_by_broker": True,
                        }
                        await _repository.update_order_book_entry(entry_id, updates)
                        for key, value in updates.items():
                            setattr(entry, key, value)
                        continue

                if broker_order_id and status_value in {"OPEN", "CLOSED", "PARTIALLY_FILLED"}:
                    broker_result = await broker.get_closed_trade_result(
                        broker_order_id,
                        pair=getattr(entry, "pair", None),
                        sync_key=getattr(entry, "sync_key", None),
                    )
                    if isinstance(broker_result, dict):
                        updates: dict[str, Any] = {
                            "last_broker_sync": now,
                            "sync_confirmed": True,
                            "confirmed_by_broker": True,
                        }
                        if status_value != "CLOSED":
                            updates["status"] = OrderStatus.CLOSED
                        if isinstance(broker_result.get("opened_at"), datetime):
                            updates["opened_at"] = broker_result["opened_at"]
                        if isinstance(broker_result.get("closed_at"), datetime):
                            updates["closed_at"] = broker_result["closed_at"]
                        if broker_result.get("close_price") is not None:
                            updates["close_price"] = broker_result["close_price"]
                        if broker_result.get("pnl_account_currency") is not None:
                            updates["pnl_account_currency"] = broker_result["pnl_account_currency"]
                        if broker_result.get("close_reason"):
                            updates["close_reasoning"] = broker_result["close_reason"]
                        await _repository.update_order_book_entry(entry_id, updates)
                        for key, value in updates.items():
                            setattr(entry, key, value)
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Broker reconcile failed for entry %s — skipping", entry_id, exc_info=True
                )


def _serialize_analysis_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id", "")),
        "agent_id": str(record.get("agent_id", "")),
        "pair": record.get("pair"),
        "decision_type": record.get("decision_type"),
        "llm_model": record.get("llm_model") or "",
        "tokens_used": int(record.get("tokens_used") or 0),
        "latency_ms": record.get("latency_ms"),
        "decided_at": record.get("decided_at"),
        "analysis_text": record.get("analysis_text"),
        "analysis": record.get("analysis"),
        "decision": record.get("decision"),
        "confidence": record.get("confidence"),
        "order_start_signal": record.get("order_start_signal"),
        "entry_quality": record.get("entry_quality"),
        "setup_type": record.get("setup_type"),
        "bus_payload": record.get("bus_payload") if isinstance(record.get("bus_payload"), dict) else {},
        "input_context": record.get("input_context") if isinstance(record.get("input_context"), dict) else {},
        "output": record.get("output") if isinstance(record.get("output"), dict) else {},
        "market_snapshot": record.get("market_snapshot") if isinstance(record.get("market_snapshot"), dict) else {},
    }


def _filter_order_book_entries(entries: list[Any], status_filter: str) -> list[Any]:
    if status_filter == "open":
        return [e for e in entries if e.status.value in {"PENDING", "OPEN", "PARTIALLY_FILLED"}]
    exact_status_map = {
        "pending": "PENDING",
        "partially_filled": "PARTIALLY_FILLED",
        "closed": "CLOSED",
        "rejected": "REJECTED",
        "cancelled": "CANCELLED",
    }
    target_status = exact_status_map.get(status_filter)
    if target_status is None or status_filter == "all":
        return entries
    return [e for e in entries if e.status.value == target_status]


def _timeframe_delta(timeframe: str) -> timedelta:
    return {
        "M5": timedelta(minutes=5),
        "M15": timedelta(minutes=15),
        "M30": timedelta(minutes=30),
        "H1": timedelta(hours=1),
        "H4": timedelta(hours=4),
        "D1": timedelta(days=1),
    }[timeframe]


def _check_api_key(api_key: str | None = Depends(_API_KEY_HEADER)) -> None:
    if _EXPECTED_KEY and api_key != _EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# â"€â"€ Config masking â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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


def _resolve_snapshot_helpers_path() -> Path:
    return _project_root() / "config" / "snapshot_helpers.py"


def _validate_python_source(content: str, *, filename: str) -> None:
    try:
        compile(content, filename, "exec")
    except SyntaxError as exc:
        location = f"line {exc.lineno}"
        if exc.offset:
            location += f", column {exc.offset}"
        detail = f"Invalid Python syntax in {filename} at {location}: {exc.msg}"
        if exc.text:
            detail += f" | {exc.text.strip()}"
        raise HTTPException(status_code=400, detail=detail) from exc


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


def _emit_tool_executor_monitoring(
    event_type: str,
    *,
    tool_name: str,
    agent_id: str | None,
    broker_name: str | None,
    pair: str | None,
    payload: dict[str, Any],
) -> None:
    """Emit monitoring events for direct Tool Executor runs."""
    if _monitoring_bus is None:
        return
    try:
        from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType

        _monitoring_bus.emit(MonitoringEvent(
            timestamp=datetime.now(UTC),
            source_module="tool_executor",
            event_type=MonitoringEventType[event_type],
            broker_name=broker_name,
            pair=pair,
            payload={
                "tool_name": tool_name,
                "agent_id": agent_id,
                **payload,
            },
        ))
    except Exception:
        pass


# â"€â"€ Request / response models â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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
        description="Seconds to wait for the agent's response (5—300)",
    )
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Optional prior conversation turns [{role, content}] prepended before the question",
    )


class AgentQueryResponse(BaseModel):
    correlation_id: str
    agent_id: str
    response: str


class SnapshotPreviewRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID used as runtime broker/pair context.")
    pair_override: str | None = Field(
        default=None,
        description="Optional pair override for agents without a fixed pair in config.",
    )
    profile_name: str | None = Field(default=None, description="Optional snapshot profile display name.")
    profile_override: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional unsaved snapshot profile config override.",
    )


class SnapshotPreviewResponse(BaseModel):
    agent_id: str
    broker_name: str
    pair: str
    trigger_payload: dict[str, Any]
    effective_profile: dict[str, Any]
    snapshot: dict[str, Any]
    validation_errors: list[str] = Field(default_factory=list)
    decision_input: str


class SnapshotToolPreviewRequest(BaseModel):
    agent_id: str
    tool_block: dict[str, Any]
    pair_override: str | None = Field(default=None, description="Optional pair override for runtime context.")
    short_timeframe: str = "M5"
    long_timeframe: str = "H1"


class SnapshotToolPreviewResponse(BaseModel):
    agent_id: str
    broker_name: str
    pair: str
    runtime_context: dict[str, Any]
    tool_block: dict[str, Any]
    raw_output: Any = None
    transformed_output: Any = None
    errors: list[str] = Field(default_factory=list)


class SnapshotCalculationPreviewRequest(BaseModel):
    agent_id: str
    calculation_block: dict[str, Any]
    tool_results: dict[str, Any] = Field(default_factory=dict, description="Pre-fetched tool block results keyed by output_key.")
    pair_override: str | None = Field(default=None)
    strategy_aggressiveness: str = Field(default="BALANCED")
    short_timeframe: str = Field(default="M5")
    long_timeframe: str = Field(default="H1")


class SnapshotCalculationPreviewResponse(BaseModel):
    agent_id: str
    calculation_block: dict[str, Any]
    result: Any = None
    errors: list[str] = Field(default_factory=list)


class DecisionPromptScriptTestRequest(BaseModel):
    script: str
    snapshot: dict[str, Any]
    prompts: list[dict[str, Any]]


class DecisionPromptScriptTestResponse(BaseModel):
    result: int | None = None
    placeholders: dict[str, Any] = Field(default_factory=dict)
    matched_prompt: dict[str, Any] | None = None
    resolved_prompt: str | None = None
    error: str | None = None


class AgentExecuteRequest(BaseModel):
    input_text: str = Field(default="", description="Optional manual input for the execute run.")
    snapshot_profile_override: dict[str, Any] = Field(default_factory=dict)
    decision_prompt_profile_override: dict[str, Any] = Field(default_factory=dict)


class AgentExecuteResponse(BaseModel):
    run_id: str
    agent_id: str
    trigger: str
    source: str
    built_user_message: str
    final_response: str
    effective_system_prompt: str | None = None
    total_tokens: int = 0
    elapsed_ms: float = 0.0
    snapshot: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


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
    max_tokens: int | None = Field(default=None, ge=64, le=131072)
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


class UpdateStartRequest(BaseModel):
    version: str | None = None


class PackageMappingRequest(BaseModel):
    broker_map: dict[str, str] = Field(default_factory=dict)
    llm_map: dict[str, str] = Field(default_factory=dict)
    agent_id_map: dict[str, str] = Field(default_factory=dict)
    agent_id_prefix: str = ""


class PackageExportRequest(BaseModel):
    include_agents: bool = True
    agent_ids: list[str] = Field(default_factory=list)
    include_snapshot_profiles: bool = True
    include_decision_prompt_profiles: bool = True
    include_bridge_tools: bool = True
    include_event_routing: bool = True
    include_system_config: bool = False
    strict_dependencies: bool = False


class PackageValidateRequest(BaseModel):
    content: str
    mapping: PackageMappingRequest = Field(default_factory=PackageMappingRequest)
    replace_existing_agents: bool = False


class PackageImportRequest(BaseModel):
    content: str
    mapping: PackageMappingRequest = Field(default_factory=PackageMappingRequest)
    replace_existing_agents: bool = False
    import_agents: bool = True
    import_snapshot_profiles: bool = True
    import_decision_prompt_profiles: bool = True
    import_bridge_tools: bool = True
    import_event_routing: bool = True
    import_system_config: bool = False


# â"€â"€ Routers â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# WebSocket endpoints cannot use APIKeyHeader (no HTTP Request object in WS scope).
# They live on a separate router without the auth dependency.

router = APIRouter(dependencies=[Depends(_check_api_key)])
ws_router = APIRouter()   # no auth — WebSocket-compatible


@router.get("/system/ui-settings")
async def get_ui_settings() -> dict:
    """Public UI settings the frontend reads at startup.

    Currently exposes ui_utc — the UTC offset (hours) used to format every
    timestamp shown in the user interface.
    """
    system_cfg = _system_config.get("system", {}) if isinstance(_system_config, dict) else {}
    return {
        "ui_utc": int(system_cfg.get("ui_utc", 3)),
        "broker_candle_utc_offset_hours": int(system_cfg.get("broker_candle_utc_offset_hours", 3)),
    }


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


@router.get("/config/root")
async def get_config_root() -> dict[str, str]:
    """Return the absolute project root path so the UI can construct file paths dynamically."""
    return {"root": str(_project_root())}


@router.get("/image/{filename}")
async def get_doc_image(filename: str):  # type: ignore[return]
    """Serve an image file from the docs/image/ folder."""
    import mimetypes as _mimetypes
    import re as _re
    from fastapi.responses import FileResponse as _FileResponse
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]+\.(png|jpe?g|gif|webp|svg|bmp)", filename, _re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Invalid image filename")
    docs_image_dir = _project_root() / "docs" / "image"
    target = (docs_image_dir / filename).resolve()
    if not str(target).startswith(str(docs_image_dir.resolve())):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {filename}")
    media_type = _mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return _FileResponse(str(target), media_type=media_type)


@router.get("/docs/{filename}")
async def get_doc_file(filename: str) -> dict[str, str]:
    """Serve a markdown file from the docs/ folder."""
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]+\.md", filename):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid filename")
    docs_dir = _project_root() / "docs"
    target = (docs_dir / filename).resolve()
    if not str(target).startswith(str(docs_dir.resolve())):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not target.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return {"text": target.read_text(encoding="utf-8")}


@router.put("/docs/{filename}")
async def put_doc_file(filename: str, request: Request) -> dict[str, str]:
    """Overwrite a markdown file in the docs/ folder."""
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]+\.md", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    docs_dir = _project_root() / "docs"
    target = (docs_dir / filename).resolve()
    if not str(target).startswith(str(docs_dir.resolve())):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    body = await request.body()
    target.write_text(body.decode("utf-8"), encoding="utf-8")
    return {"status": "ok", "file": filename}


@router.get("/version")
async def get_version() -> dict:
    """Return the application version from system.json5."""
    version = _system_config.get("system", {}).get("version", "unknown")
    return {"version": version}


@router.get("/console/initial")
async def get_console_initial() -> dict[str, Any]:
    """Return startup overview for the web console initial page."""
    from openforexai.registry.runtime_registry import RuntimeRegistry

    modules = _system_config.get("modules", {}) if isinstance(_system_config, dict) else {}
    llm_cfg = modules.get("llm", {}) if isinstance(modules, dict) else {}
    broker_cfg = modules.get("broker", {}) if isinstance(modules, dict) else {}

    configured_llm = sorted(llm_cfg.keys()) if isinstance(llm_cfg, dict) else []
    configured_broker = sorted(broker_cfg.keys()) if isinstance(broker_cfg, dict) else []

    connected_llm = set(RuntimeRegistry.list_llm())
    connected_broker = set(_connected_brokers.keys())

    llm_items = [
        {
            "name": name,
            "status": "connected" if name in connected_llm else "missing",
        }
        for name in configured_llm
    ]
    broker_items = []
    for name in configured_broker:
        broker = _connected_brokers.get(name)
        short_name = str(getattr(broker, "short_name", "")).strip() if broker is not None else ""
        broker_items.append({
            "name": name,
            "short_name": short_name or None,
            "status": "connected" if name in connected_broker else "missing",
        })

    agents_cfg = _system_config.get("agents", {}) if isinstance(_system_config, dict) else {}
    agents: list[dict[str, Any]] = []
    now_utc = datetime.now(UTC)

    # Level 2: build last_error index from pinned events (keyed by agent_id).
    _ERROR_EVENT_TYPES = {
        "system_error", "llm_error", "llm_turn_failed",
        "ec_run_failed", "tool_call_failed",
    }
    pinned_by_agent: dict[str, dict[str, Any]] = {}
    if _monitoring_bus is not None:
        for pe in _monitoring_bus.pinned_events():
            source: str = pe.get("source_module", "")
            if not source.startswith("agent:"):
                continue
            if str(pe.get("event_type", "")) not in _ERROR_EVENT_TYPES:
                continue
            aid = source[len("agent:"):]
            existing = pinned_by_agent.get(aid)
            if existing is None or pe["timestamp"] > existing["timestamp"]:
                pinned_by_agent[aid] = {
                    "timestamp": pe["timestamp"],
                    "event_type": pe.get("event_type"),
                    "message": pe.get("payload", {}).get("message") or pe.get("payload", {}).get("error") or "",
                }

    if isinstance(agents_cfg, dict):
        for agent_id in sorted(agents_cfg.keys()):
            cfg = agents_cfg.get(agent_id)
            if not isinstance(cfg, dict):
                continue
            enabled = bool(cfg.get("enable", True))
            session_active = _compute_agent_session_active(cfg, now_utc)
            # Level 3: last active timestamp for stale detection.
            last_active: datetime | None = _monitoring_bus.agent_last_active(agent_id) if _monitoring_bus is not None else None
            agents.append({
                "agent_id": agent_id,
                "enabled": enabled,
                "type": cfg.get("type"),
                "pair": cfg.get("pair"),
                "broker": cfg.get("broker"),
                "llm": cfg.get("llm"),
                "snapshot_profile": cfg.get("snapshot_profile") or None,
                "decision_prompt_profile": cfg.get("decision_prompt_profile") or None,
                "session_active": session_active,
                "task": _agent_task_summary(cfg),
                "comment": cfg.get("comment") or None,
                "last_error": pinned_by_agent.get(agent_id),        # Level 2
                "last_active_at": last_active.isoformat() if last_active else None,  # Level 3
            })

    ec_cfg_all = _system_config.get("event_composers", {}) if isinstance(_system_config, dict) else {}
    composers: list[dict[str, Any]] = []
    if isinstance(ec_cfg_all, dict):
        for ec_id in sorted(ec_cfg_all.keys()):
            cfg = ec_cfg_all.get(ec_id)
            if not isinstance(cfg, dict):
                continue
            triggers = cfg.get("event_triggers") or []
            timer_cfg = cfg.get("timer") or {}
            trigger_summary: list[str] = list(triggers)
            if isinstance(timer_cfg, dict) and timer_cfg.get("enabled"):
                trigger_summary.append(f"timer/{timer_cfg.get('interval_seconds', 60)}s")
            composers.append({
                "ec_id": ec_id,
                "enabled": bool(cfg.get("enable", True)),
                "broker": cfg.get("broker"),
                "pair": cfg.get("pair"),
                "triggers": trigger_summary,
                "comment": cfg.get("comment") or None,
            })

    local_version = _system_config.get("system", {}).get("version", "unknown")
    remote = _fetch_remote_release_info()

    return {
        "logo": [
            "+-------------------------------------------------------------+",
            "|   ___                   _____                    _    ___   |",
            "|  / _ \\ _ __   ___ _ __ |  ___|__  _ __ _____  _ / \\  |_ _|  |",
            "| | | | | '_ \\ / _ \\ '_ \\| |_ / _ \\| '__/ _ \\ \\/ / _ \\  | |   |",
            "| | |_| | |_) |  __/ | | |  _| (_) | | |  __/>  < ___ \\ | |   |",
            "|  \\___/| .__/ \\___|_| |_|_|  \\___/|_|  \\___/_/\\_\\_/ \\_\\___|  |",
            "|       |_|                                                   |",
            "+-------------------------------------------------------------+",
        ],
        "llm": {
            "configured_count": len(configured_llm),
            "connected_count": sum(1 for i in llm_items if i["status"] == "connected"),
            "items": llm_items,
        },
        "broker": {
            "configured_count": len(configured_broker),
            "connected_count": sum(1 for i in broker_items if i["status"] == "connected"),
            "items": broker_items,
        },
        "agents": {
            "configured_count": len(agents),
            "enabled_count": sum(1 for a in agents if a["enabled"]),
            "items": agents,
        },
        "event_composers": {
            "configured_count": len(composers),
            "enabled_count": sum(1 for c in composers if c["enabled"]),
            "items": composers,
        },
        "version": {
            "local": local_version,
            "remote": remote.get("version"),
            "remote_prerelease": remote.get("prerelease"),
            "remote_published_at": remote.get("published_at"),
            "remote_url": remote.get("url"),
            "remote_error": remote.get("error"),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/system/update/status")
async def system_update_status() -> dict[str, Any]:
    return _update_status_payload()


@router.post("/system/update/start")
async def system_update_start(req: UpdateStartRequest) -> dict[str, Any]:
    global _update_task
    if _update_task is not None and not _update_task.done():
        raise HTTPException(status_code=409, detail="Update already running")

    requested_version = req.version.strip() if isinstance(req.version, str) and req.version.strip() else None
    _update_task = asyncio.create_task(_run_update_job(requested_version))
    return {
        "status": "started",
        "requested_version": requested_version,
    }


@router.post("/system/runtime/pause")
async def system_runtime_pause() -> dict[str, Any]:
    runtime_control.pause()
    return {"status": "paused", "runtime_paused": True}


@router.post("/system/runtime/resume")
async def system_runtime_resume() -> dict[str, Any]:
    runtime_control.resume()
    return {"status": "running", "runtime_paused": False}


@router.post("/system/restart-now")
async def system_restart_now() -> dict[str, Any]:
    if not _restart_supported():
        raise HTTPException(
            status_code=409,
            detail="Restart is not supported in this run mode. Use your external service manager.",
        )

    signal_path = _wrapper_restart_signal_path()
    assert signal_path is not None
    mode = "wrapper"

    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")

    async def _exit_soon() -> None:
        await asyncio.sleep(0.4)
        os._exit(0)

    asyncio.create_task(_exit_soon())
    return {"status": "restarting", "mode": mode, "signal": str(signal_path)}


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


@router.post("/config/snapshots/preview", response_model=SnapshotPreviewResponse)
async def preview_snapshot(req: SnapshotPreviewRequest) -> SnapshotPreviewResponse:
    agent = _resolve_active_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} is not active")

    context = getattr(getattr(agent, "_tool_dispatcher", None), "_context", None)
    broker_name, pair, trigger_payload = await _build_standard_agent_trigger_payload(
        req.agent_id,
        pair_override=req.pair_override,
        require_pair=False,
    )
    requested_name = str(req.profile_name or "").strip()
    if requested_name:
        cfg_path = _project_root() / "config" / "system.json5"
        try:
            raw_cfg = json5.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            raw_cfg = {}
        snap_profiles = raw_cfg.get("snapshot_profiles") or {}
        named = snap_profiles.get(requested_name)
        effective_profile = dict(named) if isinstance(named, dict) else {}
        effective_profile["name"] = requested_name
    else:
        effective_profile = dict(getattr(agent, "_snapshot_profile_config", {}) or {})
    if isinstance(req.profile_override, dict):
        effective_profile.update(req.profile_override)

    snapshot, errors = await build_analysis_snapshot(
        broker_name=broker_name,
        pair=pair,
        trigger_payload=trigger_payload,
        profile=effective_profile,
        strategy_aggressiveness=str(agent._config.get("strategy_aggressiveness", "BALANCED")),
        agent_id=agent.agent_id,
        repository=_repository,
        broker=None,
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
    )
    return SnapshotPreviewResponse(
        agent_id=req.agent_id,
        broker_name=broker_name,
        pair=pair,
        trigger_payload=trigger_payload,
        effective_profile=effective_profile,
        snapshot=snapshot,
        validation_errors=errors,
        decision_input=build_decision_only_user_message(snapshot, effective_profile),
    )


@router.post("/config/decision-prompt/test-script", response_model=DecisionPromptScriptTestResponse)
async def test_decision_prompt_script(req: DecisionPromptScriptTestRequest) -> DecisionPromptScriptTestResponse:
    prompts = req.prompts or []
    snap = req.snapshot
    locals_ = {
        "snapshot": snap,
        "tool_outputs": snap.get("tool_outputs") or {},
        "assembled": snap.get("assembled") or {},
        "placeholders": {},
        "result": 1,
    }
    try:
        exec(req.script, {"__builtins__": _SAFE_SCRIPT_BUILTINS}, locals_)
        selected_id = int(locals_.get("result", 1))
    except Exception as exc:
        return DecisionPromptScriptTestResponse(error=str(exc))
    matched = next((p for p in prompts if p.get("id") == selected_id), None)
    resolved: str | None = None
    if matched and matched.get("use_placeholders"):
        raw_text = str(matched.get("prompt", "")).strip()
        if raw_text:
            ph = locals_.get("placeholders")
            resolved = _substitute_placeholders(raw_text, ph if isinstance(ph, dict) else {})
    ph_result = locals_.get("placeholders")
    return DecisionPromptScriptTestResponse(
        result=selected_id,
        placeholders=ph_result if isinstance(ph_result, dict) else {},
        matched_prompt=matched,
        resolved_prompt=resolved,
    )


@router.post("/config/snapshots/tool-preview", response_model=SnapshotToolPreviewResponse)
async def preview_snapshot_tool(req: SnapshotToolPreviewRequest) -> SnapshotToolPreviewResponse:
    agent = _resolve_active_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} is not active")

    context = getattr(getattr(agent, "_tool_dispatcher", None), "_context", None)
    broker_name, pair, _ = await _build_standard_agent_trigger_payload(
        req.agent_id,
        pair_override=req.pair_override,
    )
    block = dict(req.tool_block or {})
    block.setdefault("enabled", True)
    preview = await preview_snapshot_tool_block(
        block=block,
        agent_id=agent.agent_id,
        broker_name=broker_name,
        pair=pair,
        repository=_repository,
        broker=None,
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
        short_timeframe=req.short_timeframe,
        long_timeframe=req.long_timeframe,
    )
    return SnapshotToolPreviewResponse(
        agent_id=req.agent_id,
        broker_name=broker_name,
        pair=pair,
        runtime_context={
            "agent_id": agent.agent_id,
            "broker_name": broker_name,
            "pair": pair,
        },
        tool_block=block,
        raw_output=preview.get("raw_output"),
        transformed_output=preview.get("transformed_output"),
        errors=[str(item) for item in preview.get("errors", [])],
    )


@router.post("/config/snapshots/calculation-preview", response_model=SnapshotCalculationPreviewResponse)
async def preview_snapshot_calculation(req: SnapshotCalculationPreviewRequest) -> SnapshotCalculationPreviewResponse:
    agent = _resolve_active_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} is not active")
    block = dict(req.calculation_block or {})
    block.setdefault("enabled", True)
    preview = await preview_calculation_block(
        block=block,
        tool_results_by_output_key=req.tool_results,
        strategy_aggressiveness=req.strategy_aggressiveness,
        short_timeframe=req.short_timeframe,
        long_timeframe=req.long_timeframe,
    )
    return SnapshotCalculationPreviewResponse(
        agent_id=req.agent_id,
        calculation_block=block,
        result=preview.get("result"),
        errors=[str(e) for e in preview.get("errors", [])],
    )


@router.post("/agents/{agent_id}/execute", response_model=AgentExecuteResponse)
async def execute_agent(agent_id: str, req: AgentExecuteRequest) -> AgentExecuteResponse:
    return await _execute_agent_inspection(
        agent_id=agent_id,
        input_text=req.input_text,
        snapshot_profile_override=req.snapshot_profile_override,
        decision_prompt_profile_override=req.decision_prompt_profile_override,
    )


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


class TriggerResponse(BaseModel):
    message_id: str
    status: str = "queued"
    broker_name: str
    pair: str
    candle_timestamp: str


def _build_adapter_source_id(broker_short_name: str, pair: str) -> str:
    b = broker_short_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


async def _trigger_m5_candle(broker_module_name: str | None, pair: str | None, label: str) -> TriggerResponse:
    if _data_container is None:
        raise HTTPException(status_code=503, detail="DataContainer not available")
    if not pair or not broker_module_name:
        raise HTTPException(status_code=400, detail=f"{label} has no broker/pair configured")
    broker_instance = _connected_brokers.get(broker_module_name)
    if broker_instance is None:
        raise HTTPException(status_code=404, detail=f"Broker adapter {broker_module_name!r} is not connected")

    candles = await _data_container.get_candles(
        broker_name=broker_instance.short_name,
        pair=str(pair).upper(),
        timeframe="M5",
        limit=1,
    )
    if not candles:
        raise HTTPException(status_code=404, detail=f"No M5 candles available for {pair} / {broker_instance.short_name}")

    candle = candles[-1]
    cd = candle.model_dump(mode="json")
    for k in ("open", "high", "low", "close"):
        if cd.get(k) is not None:
            cd[k] = round(float(cd[k]), 5)
    if cd.get("spread") is not None:
        cd["spread"] = round(float(cd["spread"]), 2)

    source_id = _build_adapter_source_id(broker_instance.short_name, str(pair))
    msg = AgentMessage(
        event_type=EventType.M5_CANDLE_TRIGGER,
        source_agent_id=source_id,
        payload={
            "broker_name": broker_instance.short_name,
            "pair": str(pair).upper(),
            "candle": cd,
            "is_null_candle": False,
        },
    )
    await _bus.publish(msg)
    return TriggerResponse(
        message_id=str(msg.id),
        broker_name=broker_instance.short_name,
        pair=str(pair).upper(),
        candle_timestamp=candle.timestamp.isoformat(),
    )


@router.post("/agents/{agent_id}/trigger", response_model=TriggerResponse, status_code=202)
async def trigger_agent(agent_id: str) -> TriggerResponse:
    """Fire an M5_CANDLE_TRIGGER for an AA agent using its latest stored candle."""
    agent_cfg = _system_config.get("agents", {}).get(agent_id)
    if not agent_cfg:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")
    if not agent_cfg.get("enable", True):
        raise HTTPException(status_code=400, detail=f"Agent {agent_id!r} is disabled")
    if agent_cfg.get("type") != "AA":
        raise HTTPException(status_code=400, detail=f"Agent {agent_id!r} is not an AA agent")
    return await _trigger_m5_candle(agent_cfg.get("broker"), agent_cfg.get("pair"), agent_id)


@router.post("/composers/{ec_id}/trigger", response_model=TriggerResponse, status_code=202)
async def trigger_composer(ec_id: str) -> TriggerResponse:
    """Fire an M5_CANDLE_TRIGGER for an EC that has m5_candle_trigger in its event_triggers."""
    ec_cfg = _system_config.get("event_composers", {}).get(ec_id)
    if not ec_cfg:
        raise HTTPException(status_code=404, detail=f"Composer {ec_id!r} not found")
    if not ec_cfg.get("enable", True):
        raise HTTPException(status_code=400, detail=f"Composer {ec_id!r} is disabled")
    triggers = ec_cfg.get("event_triggers") or []
    if "m5_candle_trigger" not in triggers:
        raise HTTPException(status_code=400, detail=f"Composer {ec_id!r} does not listen to m5_candle_trigger")
    return await _trigger_m5_candle(ec_cfg.get("broker"), ec_cfg.get("pair"), ec_id)


@router.get("/candles")
async def get_candles(
    pair: str,
    timeframe: str = "M5",
    count: int = 200,
    broker_name: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent candles for a pair/timeframe, broker-agnostic."""
    if _data_container is None:
        raise HTTPException(status_code=503, detail="DataContainer not available")

    tf = timeframe.upper().strip()
    if tf not in {"M5", "M15", "M30", "H1", "H4", "D1"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe!r}")
    limit = max(1, min(count, 2000))

    if broker_name:
        _, broker = _resolve_connected_broker(broker_name)
        if broker is None:
            raise HTTPException(status_code=404, detail=f"Broker {broker_name!r} not connected")
        short_name = broker.short_name
    else:
        if not _connected_brokers:
            raise HTTPException(status_code=503, detail="No broker connected")
        short_name = next(iter(_connected_brokers.values())).short_name

    candles = await _data_container.get_candles(
        broker_name=short_name,
        pair=pair.upper(),
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


@router.get("/orderbook")
async def get_orderbook_entries(
    broker_name: str | None = None,
    pair: str | None = None,
    status_filter: str = "all",
    limit: int = 200,
) -> list[dict[str, Any]]:
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")

    normalized_pair = pair.upper().strip() if isinstance(pair, str) and pair.strip() else None
    broker_names: list[str]
    if broker_name:
        _, broker_instance = _resolve_connected_broker(broker_name)
        if broker_instance is None:
            raise HTTPException(status_code=404, detail=f"Broker {broker_name!r} is not connected")
        broker_names = [str(broker_instance.short_name)]
    else:
        broker_names = _connected_broker_short_names()

    if not broker_names:
        return []

    per_broker_limit = max(1, min(limit, 1000))
    combined: list[Any] = []
    for short_name in broker_names:
        combined.extend(
            await _repository.get_order_book_entries(
                broker_name=short_name,
                pair=normalized_pair,
                limit=per_broker_limit,
            )
        )

    await _reconcile_order_book_entries_with_broker(combined)
    filtered = _filter_order_book_entries(combined, status_filter)
    filtered.sort(key=lambda entry: entry.requested_at, reverse=True)
    return [_serialize_order_book_entry(entry, include_analysis=False) for entry in filtered[:per_broker_limit]]


@router.get("/orderbook/{entry_id}")
async def get_orderbook_entry(entry_id: str) -> dict[str, Any]:
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")
    entry = await _repository.get_order_book_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Order book entry {entry_id!r} not found")
    await _reconcile_order_book_entries_with_broker([entry])
    return _serialize_order_book_entry(entry, include_analysis=True)


@router.get("/orderbook/{entry_id}/candles")
async def get_orderbook_entry_candles(
    entry_id: str,
    timeframe: str = "M5",
    count: int = 2000,
) -> list[dict[str, Any]]:
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")
    if _data_container is None:
        raise HTTPException(status_code=503, detail="DataContainer not available")

    tf = timeframe.upper().strip()
    if tf not in {"M5", "M15", "M30", "H1", "H4", "D1"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe!r}")

    entry = await _repository.get_order_book_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Order book entry {entry_id!r} not found")

    candles = await _data_container.get_candles(
        broker_name=entry.broker_name,
        pair=entry.pair,
        timeframe=tf,
        limit=max(200, min(count, 5000)),
    )
    candles = sorted(candles, key=lambda candle: candle.timestamp)
    if not candles:
        return []

    candle_delta = _timeframe_delta(tf)
    start_anchor = entry.opened_at or entry.requested_at
    end_anchor = entry.closed_at or candles[-1].timestamp
    pre_candles = max(80, min(count, 5000))
    window_start = start_anchor - (candle_delta * pre_candles)
    window_end = end_anchor + (candle_delta * 80)
    windowed = [candle for candle in candles if window_start <= candle.timestamp <= window_end]
    source = windowed or candles
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
        for c in source
    ]


@router.get("/analyses")
async def get_analysis_records(
    agent_id: str | None = None,
    pair: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")
    records = await _repository.get_analysis_records(
        agent_id=agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None,
        pair=pair.upper().strip() if isinstance(pair, str) and pair.strip() else None,
        limit=max(1, min(limit, 1000)),
    )
    return [_serialize_analysis_record(record) for record in records]


@router.get("/analyses/{record_id}")
async def get_analysis_record(record_id: str) -> dict[str, Any]:
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")
    record = await _repository.get_analysis_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Analysis record {record_id!r} not found")
    return _serialize_analysis_record(record)


@router.post("/agents/{agent_id}/ask", response_model=AgentQueryResponse)
async def ask_agent(agent_id: str, req: AgentQueryRequest) -> AgentQueryResponse:
    """Send a free-text question to a specific agent and wait for its response.

    The question is delivered directly to the target agent's inbox as an
    ``AGENT_QUERY`` event (``target_agent_id`` set â†’ routing table bypassed).
    The endpoint blocks until the agent publishes ``AGENT_QUERY_RESPONSE`` with
    the matching ``correlation_id``, or until *timeout* seconds have elapsed.

    Typical round-trip time is the agent's LLM latency (2—15 s depending on
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

    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    query_msg = AgentMessage(
        event_type=EventType.AGENT_QUERY,
        source_agent_id="MGMT_-ALL___-GA-MGMT",
        target_agent_id=agent_id,
        payload={"question": req.question, "history": req.history, "source": "management_api"},
    )
    future_key = str(query_msg.id)
    _bus.register_response_future(future_key, fut)
    await _bus.publish(query_msg)

    try:
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=req.timeout)
        return AgentQueryResponse(
            correlation_id=future_key,
            agent_id=result.get("agent_id", agent_id),
            response=result.get("response", ""),
        )
    except TimeoutError:
        _bus.cancel_response_future(future_key)
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
            "event_type":   e.event_type,
            "broker":       e.broker_name,
            "pair":         e.pair,
            "payload":      e.payload,
        }
        for e in events
    ]


@router.get("/monitoring/pinned")
async def get_pinned_events() -> list[dict[str, Any]]:
    """Return all pinned (protected) monitoring events, oldest first."""
    if _monitoring_bus is None:
        return []
    return _monitoring_bus.pinned_events()


@router.post("/monitoring/events/{event_id}/pin", status_code=200)
async def pin_monitoring_event(event_id: str) -> dict[str, Any]:
    """Manually pin a monitoring event so it survives ring-buffer eviction."""
    if _monitoring_bus is None:
        raise HTTPException(status_code=503, detail="Monitoring bus not available")
    found = _monitoring_bus.pin_event(event_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found in ring buffer or protected buffer")
    return {"event_id": event_id, "pinned": True}


@router.delete("/monitoring/events/{event_id}/pin", status_code=200)
async def unpin_monitoring_event(event_id: str) -> dict[str, Any]:
    """Remove pin protection from a monitoring event."""
    if _monitoring_bus is None:
        raise HTTPException(status_code=503, detail="Monitoring bus not available")
    existed = _monitoring_bus.unpin_event(event_id)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} is not pinned")
    return {"event_id": event_id, "pinned": False}


def _ws_safe_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the full payload for WebSocket monitoring without truncation."""
    return payload


def _build_ws_message(event: Any) -> str:
    """Serialise a MonitoringEvent to a JSON string safe for WebSocket sending."""
    et: str = event.event_type
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

    On first connect, the last 500 ring-buffer events are replayed so the
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
        # â"€â"€ Phase 1: replay recent ring-buffer history â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        recent = _monitoring_bus.recent_events(limit=1000)
        for hist_event in recent:
            if allowed_types and hist_event.event_type not in allowed_types:
                continue
            eid = str(hist_event.id)
            seen_ids.add(eid)
            try:
                await websocket.send_text(_build_ws_message(hist_event))
            except Exception:
                # Client disconnected during catchup — bail out immediately
                return

        # â"€â"€ Phase 2: live stream â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
            if allowed_types and event.event_type not in allowed_types:
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
        return ToolExecuteResponse(
            tool_name=req.tool_name,
            result={"error": f"Tool {req.tool_name!r} is not registered"},
            is_error=True,
        )

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

    argument_broker = None
    if isinstance(req.arguments, dict):
        broker_arg = req.arguments.get("broker")
        if isinstance(broker_arg, str) and broker_arg.strip():
            argument_broker = broker_arg.strip()

    broker_selector = req.broker_name or argument_broker or (
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
    # When no broker was explicitly requested, fall back to the first connected broker
    # so that tools like get_swing_levels work without requiring a broker_name argument.
    if broker_instance is None and _connected_brokers:
        broker_module_name, broker_instance = next(iter(_connected_brokers.items()))
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
    argument_pair = None
    if isinstance(req.arguments, dict):
        pair_arg = req.arguments.get("pair")
        if isinstance(pair_arg, str) and pair_arg.strip():
            argument_pair = pair_arg.strip().upper()
    manual_pair = req.pair.strip().upper() if isinstance(req.pair, str) and req.pair.strip() else None
    if manual_pair:
        derived_pair = manual_pair
    elif argument_pair:
        derived_pair = argument_pair
    elif selected_agent_cfg and selected_agent_cfg.get("pair"):
        derived_pair = str(selected_agent_cfg.get("pair")).upper()
    else:
        derived_pair = None

    context = ToolContext(
        agent_id=req.agent_id or "MGMT_-ALL___-GA-MGMT",
        broker_name=context_broker_name,
        pair=derived_pair,
        monitoring_bus=_monitoring_bus,
        event_bus=_bus,
        extra={
            "llm_name": llm_name,
            "llm": llm_instance,
            "agent_config": selected_agent_cfg or {},
            "broker_module_name": broker_module_name,
        },
    )

    effective_arguments = dict(req.arguments or {})
    if selected_agent_cfg:
        tool_cfg = selected_agent_cfg.get("tool_config", {})
        if isinstance(tool_cfg, dict):
            forced = tool_cfg.get("forced_arguments", {})
            if isinstance(forced, dict):
                forced_for_tool = forced.get(req.tool_name, {})
                if isinstance(forced_for_tool, dict):
                    placeholders = build_agent_placeholder_values(
                        agent_id=req.agent_id or "MGMT_-ALL___-GA-MGMT",
                        agent_config=selected_agent_cfg,
                        broker_name=context_broker_name,
                        pair=derived_pair,
                    )
                    effective_arguments.update(resolve_argument_templates(forced_for_tool, placeholders))

    _emit_tool_executor_monitoring(
        "TOOL_CALL_STARTED",
        tool_name=req.tool_name,
        agent_id=req.agent_id,
        broker_name=context_broker_name,
        pair=derived_pair,
        payload={"arguments": effective_arguments},
    )
    try:
        result = await tool.execute(effective_arguments, context)
        _emit_tool_executor_monitoring(
            "TOOL_CALL_COMPLETED",
            tool_name=req.tool_name,
            agent_id=req.agent_id,
            broker_name=context_broker_name,
            pair=derived_pair,
            payload={
                "arguments": effective_arguments,
                "result": json.dumps(result, default=str),
            },
        )
        return ToolExecuteResponse(tool_name=req.tool_name, result=result, is_error=False)
    except Exception as exc:
        _emit_tool_executor_monitoring(
            "TOOL_CALL_FAILED",
            tool_name=req.tool_name,
            agent_id=req.agent_id,
            broker_name=context_broker_name,
            pair=derived_pair,
            payload={
                "arguments": effective_arguments,
                "error": str(exc),
            },
        )
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
    """Return system.json5 with sensitive fields (api_key, password, â€¦) masked.

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
    return {"text": _read_text_file(cfg_path), "file": str(cfg_path)}


@router.get("/config/helpers/snapshot/text")
async def get_snapshot_helpers_text() -> dict[str, str]:
    """Return raw snapshot_helpers.py text for editing."""
    helper_path = _resolve_snapshot_helpers_path()
    if not helper_path.exists():
        return {"text": "", "file": str(helper_path)}
    return {"text": _read_text_file(helper_path), "file": str(helper_path)}


@router.put("/config/helpers/snapshot")
async def save_snapshot_helpers_text(content: str = Body(..., embed=False)) -> dict[str, str]:
    """Save config/snapshot_helpers.py after a Python syntax check."""
    helper_path = _resolve_snapshot_helpers_path()
    _validate_python_source(content, filename=str(helper_path))
    _write_text_file(helper_path, content)
    return {"status": "saved", "file": f"config/{helper_path.name}"}


@router.post("/config/packages/export")
async def export_agent_package(req: PackageExportRequest) -> dict[str, Any]:
    """Export a portable multi-agent package as JSON5 text."""
    project_root = _project_root()
    package = build_export_package(
        _system_config,
        selected_agent_ids=req.agent_ids,
        include_agents=req.include_agents,
        include_snapshot_profiles=req.include_snapshot_profiles,
        include_decision_prompt_profiles=req.include_decision_prompt_profiles,
        include_bridge_tools=req.include_bridge_tools,
        include_event_routing=req.include_event_routing,
        include_system_config=req.include_system_config,
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
        import_agents=req.import_agents,
        import_snapshot_profiles=req.import_snapshot_profiles,
        import_decision_prompt_profiles=req.import_decision_prompt_profiles,
        import_bridge_tools=req.import_bridge_tools,
        import_event_routing=req.import_event_routing,
        import_system_config=req.import_system_config,
        event_routing_path=project_root / "config" / "RunTime" / "event_routing.json5",
        agent_tools_path=project_root / "config" / "RunTime" / "agent_tools.json5",
    )

    _write_json_file(project_root / "config" / "system.json5", next_system)
    if req.import_event_routing:
        _write_json_file(project_root / "config" / "RunTime" / "event_routing.json5", next_routing)
    if req.import_bridge_tools:
        _write_json_file(project_root / "config" / "RunTime" / "agent_tools.json5", next_agent_tools)

    previous_system_config = copy.deepcopy(_system_config)
    _system_config = next_system

    if _config_service is not None and hasattr(_config_service, "update_config"):
        _config_service.update_config(_system_config)
    _apply_monitoring_detail_level()

    runtime_apply = await _apply_runtime_agent_changes(previous_system_config)
    composer_apply = await _apply_runtime_composer_changes(previous_system_config)

    if _routing_table is not None and req.import_event_routing:
        try:
            _routing_table.load_rules_from_file(project_root / "config" / "RunTime" / "event_routing.json5")
        except Exception:
            pass

    return {
        "status": "imported",
        "runtime_apply": runtime_apply,
        "composer_apply": composer_apply,
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


async def _run_runtime_ec(ec) -> None:
    try:
        await ec.start()
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def _apply_runtime_composer_changes(previous_system_config: dict[str, Any]) -> dict[str, Any]:
    """Start newly enabled ECs and stop dynamically started disabled ones."""
    if _bus is None:
        return {"started": 0, "stopped": 0}

    global _runtime_composers, _runtime_composer_tasks

    prev_ecs = previous_system_config.get("event_composers", {}) if isinstance(previous_system_config, dict) else {}
    next_ecs = _system_config.get("event_composers", {}) if isinstance(_system_config, dict) else {}

    prev_enabled = {
        ec_id
        for ec_id, cfg in prev_ecs.items()
        if isinstance(cfg, dict) and cfg.get("enable", True)
    }
    next_enabled = {
        ec_id
        for ec_id, cfg in next_ecs.items()
        if isinstance(cfg, dict) and cfg.get("enable", True)
    }

    registered = set(_bus.registered_agents())
    to_start = sorted(ec_id for ec_id in next_enabled if ec_id not in registered)

    started = 0
    for ec_id in to_start:
        from openforexai.composers.composer import EventComposer

        ec = EventComposer(
            ec_id=ec_id,
            bus=_bus,
            monitoring_bus=_monitoring_bus,
        )
        task = asyncio.create_task(_run_runtime_ec(ec), name=f"runtime:{ec_id}")
        _runtime_composers[ec_id] = ec
        _active_composers[ec_id] = ec
        _runtime_composer_tasks[ec_id] = task
        started += 1

    to_stop = sorted(
        ec_id
        for ec_id in prev_enabled
        if ec_id not in next_enabled and ec_id in _runtime_composers
    )

    stopped = 0
    for ec_id in to_stop:
        _runtime_composers.pop(ec_id, None)
        _active_composers.pop(ec_id, None)
        task = _runtime_composer_tasks.pop(ec_id, None)
        if task is not None:
            task.cancel()
        _bus.unregister_member(ec_id)
        stopped += 1

    return {"started": started, "stopped": stopped}


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
            repository=_repository,
            monitoring_bus=_monitoring_bus,
        )
        task = asyncio.create_task(_run_runtime_agent(agent), name=f"runtime:{agent_id}")
        _runtime_agents[agent_id] = agent
        _active_agents[agent_id] = agent
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
        _active_agents.pop(agent_id, None)
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
    _apply_monitoring_detail_level()

    runtime_apply = await _apply_runtime_agent_changes(previous_system_config)
    composer_apply = await _apply_runtime_composer_changes(previous_system_config)
    return {
        "status": "saved",
        "file": "config/system.json5",
        "runtime_apply": runtime_apply,
        "composer_apply": composer_apply,
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


# â"€â"€ Prompt Library â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

_PROMPT_LIBRARY_SCOPES = {"agent", "decision"}


@router.get("/config/prompt-library/{scope}")
async def get_prompt_library(scope: str) -> dict:
    """Return the scoped prompt library from config/prompt_library_{scope}.json5.

    Valid scopes: ``agent`` (system-prompt library used in Agent Config) and
    ``decision`` (decision-prompt library used in Decision Prompt Config).

    Returns an empty library dict when the file does not yet exist so the
    frontend can start writing entries without a manual bootstrap step.
    """
    if scope not in _PROMPT_LIBRARY_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown scope '{scope}'. Valid: {sorted(_PROMPT_LIBRARY_SCOPES)}")
    lib_path = _project_root() / "config" / f"prompt_library_{scope}.json5"
    if not lib_path.exists():
        return {"prompts": []}
    try:
        return json5.loads(lib_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"prompt_library_{scope}.json5 contains invalid JSON5: {exc}",
        )


@router.put("/config/prompt-library/{scope}")
async def save_prompt_library(scope: str, content: dict[str, Any]) -> dict:
    """Persist the scoped prompt library to config/prompt_library_{scope}.json5."""
    if scope not in _PROMPT_LIBRARY_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown scope '{scope}'. Valid: {sorted(_PROMPT_LIBRARY_SCOPES)}")
    lib_path = _project_root() / "config" / f"prompt_library_{scope}.json5"
    _write_json_file(lib_path, content)
    return {"status": "saved", "file": f"config/prompt_library_{scope}.json5"}


# â"€â"€ Snippet Library â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

_SNIPPET_LIBRARY_SCOPES = {"script", "snapshot", "decision_prompt", "ec"}


@router.get("/config/snippet-library/{scope}")
async def get_snippet_library(scope: str) -> dict:
    """Return the scoped snippet library from config/snippet_library_{scope}.json5.

    Currently only scope ``script`` is supported (shared Python snippet library
    for all script fields: transform_script, assembly_transform_script, selector
    script).

    Returns an empty library dict when the file does not yet exist.
    """
    if scope not in _SNIPPET_LIBRARY_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown scope '{scope}'. Valid: {sorted(_SNIPPET_LIBRARY_SCOPES)}")
    lib_path = _project_root() / "config" / f"snippet_library_{scope}.json5"
    if not lib_path.exists():
        return {"snippets": []}
    try:
        return json5.loads(lib_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"snippet_library_{scope}.json5 contains invalid JSON5: {exc}",
        )


@router.put("/config/snippet-library/{scope}")
async def save_snippet_library(scope: str, content: dict[str, Any]) -> dict:
    """Persist the scoped snippet library to config/snippet_library_{scope}.json5."""
    if scope not in _SNIPPET_LIBRARY_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown scope '{scope}'. Valid: {sorted(_SNIPPET_LIBRARY_SCOPES)}")
    lib_path = _project_root() / "config" / f"snippet_library_{scope}.json5"
    _write_json_file(lib_path, content)
    return {"status": "saved", "file": f"config/snippet_library_{scope}.json5"}


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
        resolved = load_json_config(cfg_path)
        return _deep_mask(resolved)
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


# â"€â"€ Frontend debug log â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

_DEBUG_LOG_PATH = Path("logs/frontend_debug.log")

class DebugLogRequest(BaseModel):
    message: str

@router.post("/debug/log")
async def debug_log(req: DebugLogRequest) -> dict:
    """Append a debug message from the frontend to logs/frontend_debug.log."""
    _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(req.message + "\n")
    return {"status": "ok"}


# â"€â"€ EventComposer endpoints â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

class ECExecuteRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)

class ECExecuteResponse(BaseModel):
    ec_id: str
    output: dict[str, Any] | None
    success: bool
    error: str | None
    latency_ms: float

@router.get("/composers")
async def list_composers() -> list[dict]:
    """List all running EC entities."""
    return [{"ec_id": ec_id} for ec_id in _active_composers]

@router.post("/composers/{ec_id}/execute")
async def execute_composer(ec_id: str, req: ECExecuteRequest) -> ECExecuteResponse:
    """Run an EC entity's script with the given input JSON and return the result."""
    ec = _active_composers.get(ec_id)
    if ec is None:
        raise HTTPException(status_code=404, detail=f"EventComposer '{ec_id}' not found or not running.")
    try:
        result = await ec.test_run(req.input)
        return ECExecuteResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── LLM Assistant ─────────────────────────────────────────────────────────────

class LLMAssistantMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class LLMAssistantChatRequest(BaseModel):
    context_file: str                         # e.g. "script_snapshot_calculation_context.md"
    script: str                               # current script shown in the editor
    question: str
    history: list[LLMAssistantMessage] = Field(default_factory=list)

class LLMAssistantChatResponse(BaseModel):
    answer: str
    error: str | None = None


def _resolve_assistant_llm():
    """Return (llm_instance, call_kwargs) for the assistant.

    Reads system.json5 -> llm_assistant for provider selection and optional
    parameter overrides (temperature, reasoning_effort, max_tokens).
    Falls back to first registered LLM when provider is not set or not found.
    Only non-None config values are forwarded to llm.complete() so the
    provider's own defaults remain in effect for anything not configured here.
    """
    from openforexai.registry.runtime_registry import RuntimeRegistry
    assistant_cfg: dict = {}
    if isinstance(_system_config, dict):
        raw = _system_config.get("llm_assistant")
        if isinstance(raw, dict):
            assistant_cfg = raw

    provider_name: str | None = (
        str(assistant_cfg["provider"]) if assistant_cfg.get("provider") else None
    )
    llm = None
    if provider_name:
        try:
            llm = RuntimeRegistry.get_llm(provider_name)
        except KeyError:
            pass
    if llm is None:
        llm_names = RuntimeRegistry.list_llm()
        if not llm_names:
            raise HTTPException(status_code=503, detail="No LLM provider available for assistant")
        llm = RuntimeRegistry.get_llm(llm_names[0])

    # Build call_kwargs — only include keys explicitly set (not null) in config
    call_kwargs: dict[str, Any] = {}
    for param in ("temperature", "reasoning_effort", "max_tokens"):
        val = assistant_cfg.get(param)
        if val is not None:
            call_kwargs[param] = val

    return llm, call_kwargs


@router.post("/llm-assistant/chat", response_model=LLMAssistantChatResponse)
async def llm_assistant_chat(req: LLMAssistantChatRequest) -> LLMAssistantChatResponse:
    """Answer a question about a script using the configured assistant LLM.

    Loads a context document from config/llm_contexts/{context_file},
    builds a conversation from history + question and returns the answer.
    """
    ctx_dir = _project_root() / "config" / "llm_contexts"
    ctx_path = (ctx_dir / req.context_file).resolve()
    try:
        ctx_path.relative_to(ctx_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid context_file path")

    if not ctx_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Context file not found: config/llm_contexts/{req.context_file}",
        )

    context_text = ctx_path.read_text(encoding="utf-8")

    suffix_path = ctx_dir / "assistant_system_suffix.md"
    suffix_text = suffix_path.read_text(encoding="utf-8").strip() if suffix_path.exists() else ""

    system_prompt = context_text.rstrip()
    if suffix_text:
        system_prompt += "\n\n" + suffix_text

    conversation_parts: list[str] = []
    for msg in req.history:
        role_label = "User" if msg.role == "user" else "Assistant"
        conversation_parts.append(f"{role_label}: {msg.content}")
    conversation_parts.append(f"User: {req.question}")

    script_block = f"```python\n{req.script}\n```\n\n" if req.script.strip() else ""
    user_message = script_block + "\n".join(conversation_parts)

    try:
        llm, call_kwargs = _resolve_assistant_llm()
        response = await llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            **call_kwargs,
        )
        return LLMAssistantChatResponse(answer=response.content)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        return LLMAssistantChatResponse(answer="", error=str(exc))


# ── LLM Context file management ───────────────────────────────────────────────

@router.get("/llm-contexts", response_model=list[str])
async def list_llm_contexts() -> list[str]:
    """List all .md files in config/llm_contexts/."""
    ctx_dir = _project_root() / "config" / "llm_contexts"
    if not ctx_dir.exists():
        return []
    return sorted(p.name for p in ctx_dir.iterdir() if p.is_file() and p.suffix == ".md")


@router.get("/llm-contexts/{filename}", response_model=dict)
async def get_llm_context(filename: str) -> dict:
    ctx_dir = _project_root() / "config" / "llm_contexts"
    ctx_path = (ctx_dir / filename).resolve()
    try:
        ctx_path.relative_to(ctx_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not ctx_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return {"filename": filename, "content": ctx_path.read_text(encoding="utf-8")}


@router.put("/llm-contexts/{filename}", response_model=dict)
async def save_llm_context(filename: str, body: dict) -> dict:
    ctx_dir = _project_root() / "config" / "llm_contexts"
    ctx_path = (ctx_dir / filename).resolve()
    try:
        ctx_path.relative_to(ctx_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    ctx_dir.mkdir(parents=True, exist_ok=True)
    ctx_path.write_text(body.get("content", ""), encoding="utf-8")
    return {"ok": True}


# â"€â"€ App factory â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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
    active_agents: dict[str, Any] | None = None,
    active_composers: dict[str, Any] | None = None,
    llm_services: list | None = None,
) -> FastAPI:
    """Build the FastAPI application and wire runtime dependencies."""
    global _bus, _routing_table, _tool_registry, _indicator_registry
    global _monitoring_bus, _system_config, _start_time
    global _data_container, _repository, _connected_brokers, _config_service
    global _active_agents, _active_composers, _llm_services
    global _runtime_agents, _runtime_agent_tasks, _active_agents
    global _runtime_composers, _runtime_composer_tasks

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

    from openforexai.management.handbook_router import router as kb_router, set_repository as kb_set_repo
    kb_set_repo(repository)
    _active_agents = dict(active_agents or {})
    _active_composers = dict(active_composers or {})
    _llm_services = {svc.module_name: svc for svc in (llm_services or [])}
    _runtime_agents = {}
    _runtime_agent_tasks = {}
    _runtime_composers = {}
    _runtime_composer_tasks = {}
    _start_time = time.monotonic()
    _apply_monitoring_detail_level()

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
    app.include_router(kb_router)
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





