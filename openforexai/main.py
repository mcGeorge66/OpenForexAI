from __future__ import annotations

import asyncio
import os
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path

from openforexai.agents.agent import Agent
from openforexai.bootstrap import bootstrap
from openforexai.config.json_loader import load_json_config
from openforexai.management.server import ManagementServer
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.utils.logging import configure_logging, get_logger

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "system.json"
_log = get_logger("main")


async def _run_agent_safe(agent: Agent, monitoring_bus: MonitoringBus) -> None:
    """Run agent.start(), catching all exceptions.

    A single agent crash must never bring down the whole system.
    The exception is emitted as a SYSTEM_ERROR monitoring event so it appears
    in the console monitor even though the management server stays alive.
    """
    try:
        await agent.start()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.exception("Agent task crashed", agent_id=agent.agent_id, error=str(exc))
        try:
            monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(timezone.utc),
                source_module=f"agent:{agent.agent_id}",
                event_type=MonitoringEventType.SYSTEM_ERROR,
                payload={
                    "agent_id": agent.agent_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            ))
        except Exception:
            pass


async def main() -> None:
    # ── Load config ───────────────────────────────────────────────────────────
    cfg = load_json_config(_CONFIG_PATH)
    sys_cfg = cfg.get("system", {})
    configure_logging(sys_cfg.get("log_level", "INFO"))

    from openforexai.utils.logging import get_logger
    logger = get_logger("main")
    logger.info("Starting OpenForexAI", config=str(_CONFIG_PATH))

    # ── Monitoring bus (created first so bootstrap can wire it through) ───────
    monitoring_bus = MonitoringBus()

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    agents, config_service, bus = await bootstrap(cfg, monitoring_bus=monitoring_bus)
    api_cfg = sys_cfg.get("management_api", {})
    mgmt_server = ManagementServer(
        bus=bus,
        routing_table=bus._routing,
        tool_registry=DEFAULT_REGISTRY,
        monitoring_bus=monitoring_bus,
        host=api_cfg.get("host", "127.0.0.1"),
        port=api_cfg.get("port", 8765),
    )

    # ── Run everything concurrently ───────────────────────────────────────────
    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.start_dispatch_loop(), name="event-bus")
        tg.create_task(config_service.run(), name="config-service")
        tg.create_task(mgmt_server.serve(), name="mgmt-api")
        for agent in agents:
            tg.create_task(
                _run_agent_safe(agent, monitoring_bus),
                name=agent.agent_id,
            )


def run() -> None:
    """Entry point for the ``openforexai`` console script."""

    # ── Ctrl+C confirmation handler ───────────────────────────────────────────
    # We replace Python's default SIGINT handler BEFORE asyncio.run() so that
    # the event loop is NOT cancelled when the user presses Ctrl+C.  The loop
    # keeps running while we ask the confirmation question in a background
    # thread.  On "y" we call os._exit(0) which terminates the process
    # immediately — including any non-daemon threads (uvicorn, broker streams)
    # that would otherwise keep the process alive after asyncio.run() returns.

    _asking = threading.Event()  # True while the prompt is on screen

    def _sigint_handler(sig: int, frame: object) -> None:  # noqa: ANN001
        if _asking.is_set():
            # Second Ctrl+C while prompt is active → force-kill immediately
            print("\nForce quit.")
            os._exit(1)
        _asking.set()

        def _ask() -> None:
            print()  # newline so the prompt appears below the "^C"
            try:
                answer = input("Stop OpenForexAI? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                answer = "y"

            if answer.strip().lower() in ("y", "yes"):
                print("Shutting down...")
                os._exit(0)
            else:
                print("Continuing...")
                _asking.clear()

        threading.Thread(target=_ask, daemon=True).start()

    signal.signal(signal.SIGINT, _sigint_handler)

    # ── Run ───────────────────────────────────────────────────────────────────
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # should not happen — our handler above prevents it, but guard anyway

    # If we reach here all asyncio tasks ended on their own (unexpected).
    # os._exit forces termination even if non-daemon threads are still alive.
    print("\nOpenForexAI stopped.")
    os._exit(0)


if __name__ == "__main__":
    run()
