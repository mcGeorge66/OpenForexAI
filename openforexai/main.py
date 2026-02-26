from __future__ import annotations

import asyncio
from pathlib import Path

from openforexai.bootstrap import bootstrap
from openforexai.config.loader import load_yaml_config, merge_configs
from openforexai.config.settings import Settings
from openforexai.utils.logging import configure_logging


async def main() -> None:
    # ── Config loading ────────────────────────────────────────────────────────
    base_config = load_yaml_config(Path(__file__).parent.parent / "config" / "default.yaml")
    settings = Settings(**base_config)

    configure_logging(settings.log_level)

    from openforexai.utils.logging import get_logger
    logger = get_logger("main")
    logger.info(
        "Starting OpenForexAI",
        pairs=settings.pairs,
        broker=settings.broker.name,
        llm=settings.llm.provider,
    )

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    agents, bus = await bootstrap(settings)

    # ── Run all agents + event bus concurrently ───────────────────────────────
    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.start_dispatch_loop(), name="event-bus")
        for agent in agents:
            tg.create_task(agent.start(), name=agent.agent_id)


def run() -> None:
    """Entry point for the ``openforexai`` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
