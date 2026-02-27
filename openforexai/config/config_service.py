"""ConfigService — answers AGENT_CONFIG_REQUESTED events.

The ConfigService registers as agent ``SYSTM_ALL..._GA_CFGSV`` on the EventBus.
When an agent starts and sends an AGENT_CONFIG_REQUESTED message, the service
looks up the agent's config in system.json and replies with AGENT_CONFIG_RESPONSE
(directed directly to the requesting agent via target_agent_id).

The response payload contains:
    config   — the full agent config dict from system.json
    modules  — resolved module configs (llm, broker) for this agent

Usage::

    svc = ConfigService(system_config, bus)
    asyncio.create_task(svc.run())
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType

_log = logging.getLogger(__name__)

CONFIG_SERVICE_ID = "SYSTM_ALL..._GA_CFGSV"


class ConfigService:
    """Listens for AGENT_CONFIG_REQUESTED and replies with the agent's full config."""

    def __init__(self, system_config: dict[str, Any], bus: EventBus) -> None:
        self._cfg = system_config
        self._bus = bus
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(CONFIG_SERVICE_ID)

    async def run(self) -> None:
        """Run until cancelled."""
        _log.info("ConfigService started as %s", CONFIG_SERVICE_ID)
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type == EventType.AGENT_CONFIG_REQUESTED:
                await self._handle_request(msg)

    async def _handle_request(self, msg: AgentMessage) -> None:
        agent_id = msg.payload.get("agent_id", msg.source_agent_id)
        agent_cfg = self._cfg.get("agents", {}).get(agent_id)

        if agent_cfg is None:
            _log.warning("ConfigService: no config found for agent %r", agent_id)
            return

        # Resolve module configs for this agent
        modules: dict[str, Any] = {}
        llm_name = agent_cfg.get("llm")
        broker_name = agent_cfg.get("broker")

        if llm_name:
            modules["llm"] = self._cfg.get("modules", {}).get("llm", {}).get(llm_name, {})
        if broker_name:
            modules["broker"] = self._cfg.get("modules", {}).get("broker", {}).get(broker_name, {})

        response = AgentMessage(
            event_type=EventType.AGENT_CONFIG_RESPONSE,
            source_agent_id=CONFIG_SERVICE_ID,
            target_agent_id=agent_id,
            payload={
                "agent_id": agent_id,
                "config": agent_cfg,
                "modules": modules,
            },
            correlation_id=str(msg.id),
        )
        await self._bus.publish(response)
        _log.debug("ConfigService: sent config to %s", agent_id)
