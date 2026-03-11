from __future__ import annotations

import asyncio
import os
import sys
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

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "system.json5"
_log = get_logger("main")


def _install_windows_asyncio_workarounds() -> None:
    """Avoid noisy Proactor transport resets on Windows (WinError 10054)."""
    if sys.platform != "win32":
        return

    # Proactor can emit spurious "Exception in callback ... _call_connection_lost"
    # when remote peers close sockets. Selector loop avoids that class of noise.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
    agents, config_service, bus, data_container, repository, connected_brokers = await bootstrap(
        cfg, monitoring_bus=monitoring_bus
    )
    api_cfg = sys_cfg.get("management_api", {})
    mgmt_server = ManagementServer(
        bus=bus,
        routing_table=bus._routing,
        tool_registry=DEFAULT_REGISTRY,
        monitoring_bus=monitoring_bus,
        system_config=cfg,
        data_container=data_container,
        repository=repository,
        connected_brokers=connected_brokers,
        config_service=config_service,
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
    _install_windows_asyncio_workarounds()
    # ── Run (default Ctrl+C behavior) ─────────────────────────────────────────
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOpenForexAI stopped.")
        # Ensure process termination even if background non-daemon threads remain.
        os._exit(0)


if __name__ == "__main__":
    run()



