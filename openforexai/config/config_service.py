"""ConfigService — answers AGENT_CONFIG_REQUESTED events.

The ConfigService registers as agent ``SYSTM-ALL___-GA-CFGSV`` on the EventBus.
When an agent starts and sends an AGENT_CONFIG_REQUESTED message, the service
looks up the agent's config in system.json5 and replies with AGENT_CONFIG_RESPONSE
(directed directly to the requesting agent via target_agent_id).

The response payload contains:
    config   — the full agent config dict from system.json5
    modules  — resolved module configs (llm, broker) for this agent

Usage::

    svc = ConfigService(system_config, bus)
    asyncio.create_task(svc.run())
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openforexai.config.json_loader import load_json_config
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

CONFIG_SERVICE_ID = "SYSTM-ALL___-GA-CFGSV"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ConfigService:
    """Listens for AGENT_CONFIG_REQUESTED and replies with the agent's full config."""

    def __init__(self, system_config: dict[str, Any], bus: EventBus) -> None:
        self._cfg = system_config
        self._bus = bus
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(CONFIG_SERVICE_ID)

    def update_config(self, system_config: dict[str, Any]) -> None:
        """Replace in-memory system config snapshot used for future responses."""
        self._cfg = system_config


    async def run(self) -> None:
        """Run until cancelled."""
        _log.info("ConfigService started", agent_id=CONFIG_SERVICE_ID)
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type == EventType.AGENT_CONFIG_REQUESTED:
                await self._handle_request(msg)

    def _resolve_module_config(self, module_type: str, module_name: str) -> dict[str, Any]:
        """Resolve a module name to its loaded config dict.

        modules.<type>.<name> in system config contains a relative config path.
        """
        module_path = self._cfg.get("modules", {}).get(module_type, {}).get(module_name)
        if not module_path:
            return {}

        cfg_file = (_PROJECT_ROOT / str(module_path)).resolve()
        if not cfg_file.exists():
            _log.warning(
                "ConfigService: module config missing on disk",
                extra={"module_type": module_type, "module_name": module_name, "path": str(cfg_file)},
            )
            return {}

        try:
            loaded = load_json_config(cfg_file)
            return loaded if isinstance(loaded, dict) else {}
        except Exception as exc:
            _log.warning(
                "ConfigService: failed loading module config %s/%s: %s",
                module_type,
                module_name,
                exc,
            )
            return {}

    async def _handle_request(self, msg: AgentMessage) -> None:
        agent_id = msg.payload.get("agent_id", msg.source_agent_id)
        agent_cfg = self._cfg.get("agents", {}).get(agent_id)

        if agent_cfg is None:
            _log.warning("ConfigService: no config found for agent %r", agent_id)
            return
        if not agent_cfg.get("enable", True):
            _log.info("ConfigService: config for disabled agent %r ignored", agent_id)
            return

        # Resolve module configs for this agent
        modules: dict[str, Any] = {}
        llm_name = agent_cfg.get("llm")
        broker_name = agent_cfg.get("broker")

        if llm_name:
            modules["llm"] = self._resolve_module_config("llm", str(llm_name))
        if broker_name:
            modules["broker"] = self._resolve_module_config("broker", str(broker_name))

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
