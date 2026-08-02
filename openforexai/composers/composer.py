"""EventComposer — EC container.

An EC entity is a first-class peer to LLM agents (AA/BA/GA) with an identical
lifecycle, trigger wiring, tool access, event-bus integration, and DB logging.
The difference: its core is an async Python script instead of an LLM.

Script contract
---------------
Every EC script must implement::

    async def main(input: dict, config: dict, tools) -> dict | None:
        ...

The container calls ``await main(input, config, tools_proxy)`` where:

- ``input``       — parsed payload from the triggering event (or start JSON)
- ``config``      — parsed config_json from the EC entity configuration
- ``tools_proxy`` — async ToolsProxy; call ``await tools.call("tool_name", **kwargs)``

The return value is published on the EventBus as EC_OUTPUT if not None.
Returning None is valid — no output event is emitted.

Timeout
-------
``tool_config.script_timeout_seconds`` (default 60, 0 = no timeout).
Timeout is handled like any other exception: EC_RUN_FAILED on the monitoring
bus, DB entry written, system continues running.
"""
from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

from openforexai.messaging.bus import EventBus
from openforexai.messaging.llm_helpers import make_ask_llm
from openforexai.models.composer import ECRun, ECToolCall
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext
from openforexai.tools.dispatcher import ToolDispatcher
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

_CONFIG_TIMEOUT = 30.0  # seconds to wait for EC_CONFIG_RESPONSE


class ToolsProxy:
    """Async proxy exposing a single ``call()`` method to EC scripts.

    Wraps ToolDispatcher so scripts never touch ToolCall/ToolResult directly.
    Logs every call to the monitoring bus (container responsibility, not script).
    """

    def __init__(
        self,
        dispatcher: ToolDispatcher,
        tool_calls_log: list[ECToolCall],
    ) -> None:
        self._dispatcher = dispatcher
        self._log = tool_calls_log

    async def call(self, tool_name: str, **kwargs: Any) -> Any:
        import json as _json
        from openforexai.ports.llm import ToolCall

        tc = ToolCall(
            id=str(uuid.uuid4()),
            name=tool_name,
            arguments=kwargs,
        )
        results = await self._dispatcher.execute_all([tc])
        result = results[0]

        parsed: Any = None
        try:
            parsed = _json.loads(result.content)
        except Exception:
            parsed = result.content

        self._log.append(ECToolCall(
            tool=tool_name,
            arguments=kwargs,
            result=parsed,
            success=not result.is_error,
            error=str(parsed.get("error", "")) if result.is_error and isinstance(parsed, dict) else (None if not result.is_error else result.content),
        ))
        return parsed


def _make_emit_fn(event_bus: Any, ec_id: str):
    """Return an async ``emit(event_type, payload)`` function for EC scripts.

    Injected into the script namespace so scripts can publish events to the
    EventBus without holding a direct reference to it.

    Usage in EC scripts::

        await emit("ec_guard_block", {"reason": "tool_error", "pair": symbol})

    The message is published with ``source_agent_id`` set to the EC's own ID.
    """
    async def emit(event_type: str, payload: dict | None = None, instrument: str | None = None) -> None:
        from openforexai.models.messaging import AgentMessage
        await event_bus.publish(AgentMessage(
            event_type=event_type,
            source_agent_id=ec_id,
            instrument=instrument,
            payload=payload or {},
        ))
    return emit


def _make_log_fn(monitoring_bus: Any, ec_id: str, broker_name: str | None, pair: str | None):
    """Return a synchronous ``log(message, level, pin)`` function for EC scripts.

    Injected into the script namespace so scripts can emit structured messages
    to the monitoring bus without holding a direct reference to it.

    Usage in EC scripts::

        log("Open position found — blocking signal", level="info", pin=True)
        log("Tool call failed", level="error")

    ``level`` accepts ``"info"`` (default), ``"warning"``, or ``"error"``.
    ``pin=True`` marks the event as pinned so monitors can keep it visible.
    Filter in the monitoring CLI via event_type ``ec_script_log``.
    """
    def log(message: str, level: str = "info", pin: bool = False) -> None:
        if monitoring_bus is None:
            return
        from datetime import UTC, datetime as _dt
        from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
        monitoring_bus.emit(MonitoringEvent(
            timestamp=_dt.now(UTC),
            source_module=f"ec:{ec_id}",
            event_type=MonitoringEventType.EC_SCRIPT_LOG,
            broker_name=broker_name,
            pair=pair,
            payload={
                "message": message,
                "level": level,
                "pinned": pin,
                "ec_id": ec_id,
            },
        ))
    return log


def _make_debug_fn(
    monitoring_bus: Any,
    ec_id: str,
    broker_name: str | None,
    pair: str | None,
    is_test: bool,
    start_monotonic: float,
):
    """Return a ``debug(message)`` function for EC scripts — test runs only.

    Active only when the current run was started via the Test button
    (``trigger == "test"``); a true no-op otherwise, so ``debug()`` calls have
    zero effect and zero cost in live/production runs. Reports the exact
    source line of the call (matches the line numbers shown everywhere else
    in the editor/LLM tooling) and elapsed seconds since the script started,
    so slow sections are visible without print()-style trial and error, and
    partial output survives even if the script later times out.

    Usage in EC scripts::

        resp = await tools.call("get_open_positions", pair=pair)
        debug(resp)  # streamed live to the Test tab, JSON-formatted if applicable

    Filter in the monitoring stream via event_type ``ec_debug_log``.
    """
    if not is_test or monitoring_bus is None:
        def debug_noop(message: Any) -> None:
            return None
        return debug_noop

    def debug(message: Any) -> None:
        import inspect as _inspect
        from datetime import UTC, datetime as _dt
        from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType

        caller = _inspect.currentframe()
        line = caller.f_back.f_lineno if caller is not None and caller.f_back is not None else None
        elapsed = asyncio.get_event_loop().time() - start_monotonic
        safe_message = message if isinstance(message, (dict, list, str, int, float, bool, type(None))) else str(message)

        monitoring_bus.emit(MonitoringEvent(
            timestamp=_dt.now(UTC),
            source_module=f"ec:{ec_id}",
            event_type=MonitoringEventType.EC_DEBUG_LOG,
            broker_name=broker_name,
            pair=pair,
            payload={
                "ec_id": ec_id,
                "line": line,
                "message": safe_message,
                "elapsed_seconds": round(elapsed, 3),
            },
        ))
    return debug


class EventComposer:
    """Container for an EC entity.

    Lifecycle identical to Agent: EC_CONFIG_REQUESTED → EC_CONFIG_RESPONSE →
    timer loop + message loop → _run_cycle().
    """

    def __init__(
        self,
        ec_id: str,
        bus: EventBus,
        monitoring_bus: Any = None,
    ) -> None:
        self.ec_id = ec_id
        self._bus = bus
        self._monitoring_bus = monitoring_bus
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_member(ec_id)
        self._run_lock = asyncio.Lock()

        # populated by _apply_config
        self._script: str = ""
        self._config_json: dict = {}
        self._tool_config: dict = {}
        self._event_triggers: list[str] = []
        self._timer_enabled: bool = False
        self._timer_interval: int = 60
        self._session_filter: list[dict] = []
        self._any_candle: int = 1
        self._compiled: Any = None  # compiled script code object
        self._running: bool = False
        self._snapshot_profile_name: str | None = None
        self._snapshot_profile_config: dict = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def stop(self) -> None:
        self._running = False

    async def start(self) -> None:
        """Request config, wait for response, then run loops."""
        _log.info("EventComposer starting", ec_id=self.ec_id)
        await self._bus.publish(AgentMessage(
            event_type=EventType.EC_CONFIG_REQUESTED,
            source_agent_id=self.ec_id,
            payload={"ec_id": self.ec_id},
        ))

        deadline = asyncio.get_event_loop().time() + _CONFIG_TIMEOUT
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                _log.error("EventComposer: config response timed out", ec_id=self.ec_id)
                return
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=remaining)
            except TimeoutError:
                _log.error("EventComposer: config response timed out", ec_id=self.ec_id)
                return

            if msg.event_type == EventType.EC_CONFIG_RESPONSE:
                self._apply_config(msg.payload.get("config", {}))
                break

        _log.info("EventComposer config applied", ec_id=self.ec_id)
        self._running = True
        async with asyncio.TaskGroup() as tg:
            if self._timer_enabled:
                tg.create_task(self._run_timer_loop(), name=f"{self.ec_id}:timer")
            tg.create_task(self._run_message_loop(), name=f"{self.ec_id}:messages")

    def _apply_config(self, cfg: dict) -> None:
        self._script = str(cfg.get("script", ""))
        try:
            import json
            raw_cfg_json = cfg.get("config_json", "{}")
            if isinstance(raw_cfg_json, dict):
                self._config_json = raw_cfg_json
            else:
                self._config_json = json.loads(str(raw_cfg_json))
        except Exception:
            self._config_json = {}

        self._tool_config = cfg.get("tool_config", {}) if isinstance(cfg.get("tool_config"), dict) else {}
        self._event_triggers = [str(t) for t in cfg.get("event_triggers", [])]

        # Resolve broker short_name for ToolContext (optional — only needed when tools require it)
        self._broker_name: str | None = None
        self._pair: str | None = cfg.get("pair") or None
        broker_module = cfg.get("broker")
        if broker_module:
            try:
                from openforexai.registry.runtime_registry import RuntimeRegistry
                broker_instance = RuntimeRegistry.get_broker(str(broker_module))
                self._broker_name = str(getattr(broker_instance, "short_name", "")).strip() or None
            except Exception:
                pass
        timer_cfg = cfg.get("timer", {}) if isinstance(cfg.get("timer"), dict) else {}
        self._timer_enabled = bool(timer_cfg.get("enabled", False))
        self._timer_interval = int(timer_cfg.get("interval_seconds", 60)) or 60
        self._session_filter = cfg.get("session_filter", []) if isinstance(cfg.get("session_filter"), list) else []
        self._any_candle = max(1, int(cfg.get("AnyCandle", 1)))

        # Resolved by ConfigService._handle_ec_request from the named `snapshot_profile`
        # (same mechanism as Agent) — a dict, never a bare name, by the time it reaches here.
        self._snapshot_profile_name = (
            str(cfg.get("snapshot_profile")).strip()
            if isinstance(cfg.get("snapshot_profile"), str) and str(cfg.get("snapshot_profile")).strip()
            else None
        )
        self._snapshot_profile_config = (
            dict(cfg.get("snapshot_profile_config"))
            if isinstance(cfg.get("snapshot_profile_config"), dict)
            else {}
        )

        # Pre-compile script for reuse
        try:
            self._compiled = compile(self._script, f"<ec:{self.ec_id}>", "exec")
        except SyntaxError as exc:
            _log.error("EventComposer: script syntax error", ec_id=self.ec_id, error=str(exc))
            self._compiled = None

    # ── Loops ─────────────────────────────────────────────────────────────────

    async def _run_timer_loop(self) -> None:
        await self._run_cycle(trigger="timer", payload={}, source=None, correlation_id=None)
        while self._running:
            await asyncio.sleep(self._timer_interval)
            if not self._running:
                break
            await self._run_cycle(trigger="timer", payload={}, source=None, correlation_id=None)

    async def _run_message_loop(self) -> None:
        _candle_counter: int = 0
        while self._running:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type == EventType.EC_CONFIG_RESPONSE:
                self._apply_config(msg.payload.get("config", {}))
                continue

            if msg.event_type.value not in self._event_triggers:
                continue

            if msg.event_type == EventType.M5_CANDLE_TRIGGER:
                _candle_counter += 1
                if _candle_counter % self._any_candle != 0:
                    continue

            await self._run_cycle(
                trigger=msg.event_type.value,
                payload=msg.payload,
                source=msg.source_agent_id,
                correlation_id=msg.correlation_id,
                triggering_msg=msg,
            )

    # ── Run cycle ─────────────────────────────────────────────────────────────

    async def test_run(self, input_json: dict) -> dict:
        """Execute the script directly with the given input and return the result.

        Runs the full cycle (monitoring, DB logging) and returns a summary dict.
        Does not acquire the run lock — intended for on-demand test calls.
        """
        output, success, error_msg, latency_ms = await self._execute(
            trigger="test", payload=input_json, source="management_api", correlation_id=None
        )
        return {
            "ec_id": self.ec_id,
            "output": output,
            "success": success,
            "error": error_msg,
            "latency_ms": latency_ms,
        }

    async def _run_cycle(
        self,
        trigger: str,
        payload: dict,
        source: str | None,
        correlation_id: str | None,
        triggering_msg=None,
    ) -> None:
        async with self._run_lock:
            await self._execute(trigger, payload, source, correlation_id, triggering_msg)

    async def _execute(
        self,
        trigger: str,
        payload: dict,
        source: str | None,
        correlation_id: str | None,
        triggering_msg=None,
    ) -> tuple[dict | None, bool, str | None, float]:
        """Run the EC script. Returns (output, success, error_msg, latency_ms)."""
        if self._compiled is None:
            self._emit(MonitoringEventType.EC_RUN_FAILED, {
                "ec_id": self.ec_id,
                "trigger": trigger,
                "error": "Script has a syntax error — not executed.",
                "correlation_id": correlation_id,
            })
            return None, False, "Script has a syntax error — not executed.", 0.0

        start_ts = datetime.now(UTC)
        start_monotonic = asyncio.get_event_loop().time()
        input_json = dict(payload)
        config_snapshot = dict(self._config_json)

        self._emit(MonitoringEventType.EC_RUN_STARTED, {
            "ec_id": self.ec_id,
            "trigger": trigger,
            "source": source,
            "input_json": input_json,
            "config_snapshot": config_snapshot,
            "correlation_id": correlation_id,
        })
        await self._bus.publish(AgentMessage(
            event_type=EventType.EC_CYCLE_START,
            source_agent_id=self.ec_id,
            instrument=self._pair,
            payload={"ec_id": self.ec_id, "trigger": trigger, "source": source, "input": input_json},
        ), triggered_by=triggering_msg)

        # Build ToolContext + ToolDispatcher
        context = ToolContext(
            agent_id=self.ec_id,
            broker_name=self._broker_name,
            pair=self._pair,
            monitoring_bus=self._monitoring_bus,
            event_bus=self._bus,
            extra={"ec_config": config_snapshot},
            triggering_message=triggering_msg,
        )
        dispatcher = ToolDispatcher(DEFAULT_REGISTRY, context, self._tool_config)
        tool_calls_log: list[ECToolCall] = []
        tools_proxy = ToolsProxy(dispatcher, tool_calls_log)

        # Execute script
        output: dict | None = None
        success = True
        error_msg: str | None = None

        # Inject helpers into script namespace so scripts never hold direct refs
        # to internal buses or adapters.
        ask_llm_fn = make_ask_llm(event_bus=self._bus, source_id=self.ec_id)
        log_fn = _make_log_fn(self._monitoring_bus, self.ec_id, self._broker_name, self._pair)
        emit_fn = _make_emit_fn(self._bus, self.ec_id)
        debug_fn = _make_debug_fn(
            self._monitoring_bus, self.ec_id, self._broker_name, self._pair,
            is_test=(trigger == "test"), start_monotonic=start_monotonic,
        )

        # Build message context dict for scripts
        message_ctx: dict = {
            "id": str(triggering_msg.id) if triggering_msg is not None else None,
            "event_type": str(triggering_msg.event_type) if triggering_msg is not None else trigger,
            "source_agent_id": str(triggering_msg.source_agent_id) if triggering_msg is not None else source,
            "instrument": (triggering_msg.instrument if triggering_msg is not None else None) or self._pair,
            "chain": [str(u) for u in triggering_msg.chain] if triggering_msg is not None else [],
            "correlation_id": triggering_msg.correlation_id if triggering_msg is not None else correlation_id,
            "payload": input_json,
        }

        skip_script = False
        try:
            ns: dict[str, Any] = {
                "ask_llm": ask_llm_fn,
                "log": log_fn,
                "emit": emit_fn,
                "debug": debug_fn,
                "message": message_ctx,
            }

            if self._snapshot_profile_config:
                if not self._pair:
                    raise RuntimeError(
                        "snapshot_profile is configured but this EC has no pair set - "
                        "Snapshot Profiles need a pair to build tool_blocks against."
                    )
                from openforexai.agents.analysis_snapshot import build_analysis_snapshot
                snapshot, snapshot_errors = await build_analysis_snapshot(
                    broker_name=self._broker_name,
                    pair=self._pair,
                    trigger_payload=input_json,
                    profile=self._snapshot_profile_config,
                    strategy_aggressiveness=str(config_snapshot.get("strategy_aggressiveness", "BALANCED")),
                    agent_id=self.ec_id,
                    repository=None,
                    broker=None,
                    monitoring_bus=self._monitoring_bus,
                    event_bus=self._bus,
                )
                if snapshot_errors:
                    raise RuntimeError("Snapshot invalid: " + "; ".join(snapshot_errors))
                ns["snapshot"] = snapshot
                if snapshot.get("cancel"):
                    # Assembly transform script asked to skip this cycle — same semantics
                    # as an Agent decision cycle cancelling itself; not an error.
                    skip_script = True
                    log_fn(
                        f"EC cycle cancelled by snapshot assembly script: "
                        f"{snapshot.get('cancel_reason', '') or '(no reason given)'}",
                        level="info", pin=True,
                    )

            exec(self._compiled, ns)  # noqa: S102
            main_fn = ns.get("main")
            if not callable(main_fn):
                raise RuntimeError("EC script must define 'async def main(input, config, tools)'")

            if not skip_script:
                timeout_s = self._tool_config.get("script_timeout_seconds", 60)
                if timeout_s and timeout_s > 0:
                    result = await asyncio.wait_for(
                        main_fn(input_json, config_snapshot, tools_proxy),
                        timeout=float(timeout_s),
                    )
                else:
                    result = await main_fn(input_json, config_snapshot, tools_proxy)

                if result is not None:
                    if not isinstance(result, dict):
                        result = {"value": result}
                    output = result

        except asyncio.TimeoutError:
            success = False
            error_msg = f"EC script timed out after {self._tool_config.get('script_timeout_seconds', 60)}s"
            _log.error("EventComposer: script timeout", ec_id=self.ec_id, trigger=trigger)
        except Exception:
            success = False
            error_msg = traceback.format_exc()
            _log.error("EventComposer: script exception", ec_id=self.ec_id, trigger=trigger, exc_info=True)

        latency_ms = (asyncio.get_event_loop().time() - start_monotonic) * 1000.0

        # Monitoring events
        if not success:
            self._emit(MonitoringEventType.EC_RUN_FAILED, {
                "ec_id": self.ec_id,
                "trigger": trigger,
                "error": error_msg,
                "correlation_id": correlation_id,
            })
            self._emit(MonitoringEventType.SYSTEM_ERROR, {
                "ec_id": self.ec_id,
                "message": error_msg,
                "trigger": trigger,
            })
        else:
            if output is not None:
                self._emit(MonitoringEventType.EC_RUN_OUTPUT, {
                    "ec_id": self.ec_id,
                    "trigger": trigger,
                    "output": output,
                    "correlation_id": correlation_id,
                })
                # Publish output on EventBus for routing
                await self._bus.publish(
                    AgentMessage(
                        event_type=EventType.EC_OUTPUT,
                        source_agent_id=self.ec_id,
                        instrument=self._pair or (triggering_msg.instrument if triggering_msg else None),
                        payload=output,
                        correlation_id=correlation_id,
                    ),
                    triggered_by=triggering_msg,
                )
            self._emit(MonitoringEventType.EC_RUN_COMPLETED, {
                "ec_id": self.ec_id,
                "trigger": trigger,
                "success": True,
                "latency_ms": latency_ms,
                "output_provided": output is not None,
                "correlation_id": correlation_id,
            })

        await self._bus.publish(AgentMessage(
            event_type=EventType.EC_CYCLE_END,
            source_agent_id=self.ec_id,
            payload={
                "ec_id": self.ec_id,
                "trigger": trigger,
                "success": success,
                "elapsed_ms": round(latency_ms, 1),
                "output_event_type": "ec_output" if (success and output is not None) else None,
                **({"error": error_msg} if error_msg else {}),
            },
        ), triggered_by=triggering_msg)

        # DB logging via RepositoryService bus
        try:
            run = ECRun(
                ec_id=self.ec_id,
                trigger=trigger,
                input_json=input_json,
                config_snapshot=config_snapshot,
                tool_calls=tool_calls_log,
                output_json=output,
                success=success,
                error=error_msg,
                latency_ms=latency_ms,
                run_at=start_ts,
                correlation_id=correlation_id,
            )
            from openforexai.repository_service import REPO_SERVICE_ID
            await self._bus.publish(AgentMessage(
                event_type=EventType.REPO_REQUEST,
                source_agent_id=self.ec_id,
                target_agent_id=REPO_SERVICE_ID,
                payload={"operation": "save_ec_run", "args": {"run": run.model_dump(mode="json")}},
            ), triggered_by=triggering_msg)
        except Exception:
            _log.error("EventComposer: failed to persist run log", ec_id=self.ec_id, exc_info=True)

        return output, success, error_msg, latency_ms

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit(self, event_type: MonitoringEventType, payload: dict) -> None:
        if self._monitoring_bus is None:
            return
        try:
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"ec:{self.ec_id}",
                event_type=event_type,
                payload=payload,
            ))
        except Exception:
            pass
