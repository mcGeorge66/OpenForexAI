from __future__ import annotations

import asyncio
from pathlib import Path

from openforexai.bootstrap import bootstrap
from openforexai.config.json_loader import load_json_config
from openforexai.management.server import ManagementServer
from openforexai.monitoring.bus import MonitoringBus
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.utils.logging import configure_logging

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "system.json"


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
            tg.create_task(agent.start(), name=agent.agent_id)


def run() -> None:
    """Entry point for the ``openforexai`` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
