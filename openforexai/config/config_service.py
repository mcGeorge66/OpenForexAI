"""ConfigService — answers AGENT_CONFIG_REQUESTED events.

The ConfigService registers as agent ``SYSTM-ALL___-GA-CFGSV`` on the EventBus.
When an agent starts and sends an AGENT_CONFIG_REQUESTED message, the service
looks up the agent's config in system.json5 and replies with AGENT_CONFIG_RESPONSE
(directed directly to the requesting agent via target_agent_id).

The response payload contains:
    config   — the full agent config dict from system.json5
    modules  — resolved module configs (llm, broker) for this agent

Usage::

    svc = ConfigService(system_config, bus, repository)
    asyncio.create_task(svc.run())
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openforexai.config.json_loader import load_json_config
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.database import AbstractRepository
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

CONFIG_SERVICE_ID = "SYSTM-ALL___-GA-CFGSV"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ConfigService:
    """Listens for AGENT_CONFIG_REQUESTED and replies with the agent's full config."""

    def __init__(
        self,
        system_config: dict[str, Any],
        bus: EventBus,
        repository: AbstractRepository,
    ) -> None:
        self._cfg = system_config
        self._bus = bus
        self._repository = repository
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(CONFIG_SERVICE_ID)

    def update_config(self, system_config: dict[str, Any]) -> None:
        """Replace in-memory system config snapshot used for future responses."""
        self._cfg = system_config

    @staticmethod
    def merge_system_prompt(static_prompt: str | None, sub_prompt: str | None) -> str:
        """Merge static config prompt with the DB-backed sub-prompt."""
        static = str(static_prompt or "")
        sub = str(sub_prompt or "")

        if not static:
            return sub
        if "{subPrompt}" in static:
            return static.replace("{subPrompt}", sub)
        if sub:
            return f"{static}\n\n{sub}"
        return static

    @staticmethod
    def sanitize_agent_tool_config(tool_cfg: dict[str, Any] | None) -> dict[str, Any]:
        """Remove deprecated tool tier keys from agent config at runtime."""
        raw = tool_cfg if isinstance(tool_cfg, dict) else {}
        return {
            key: value
            for key, value in raw.items()
            if key not in {"context_tiers", "tier_tools"}
        }

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
            elif msg.event_type == EventType.EC_CONFIG_REQUESTED:
                await self._handle_ec_request(msg)

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

        response_cfg = dict(agent_cfg)
        sub_prompt = await self._repository.get_sub_prompt(str(agent_id))
        response_cfg["system_prompt"] = self.merge_system_prompt(
            response_cfg.get("system_prompt"),
            sub_prompt,
        )
        response_cfg["tool_config"] = self.sanitize_agent_tool_config(
            response_cfg.get("tool_config") if isinstance(response_cfg.get("tool_config"), dict) else None
        )
        snapshot_profiles = self._cfg.get("snapshot_profiles", {})
        selected_snapshot_profile = response_cfg.get("snapshot_profile")
        if (
            isinstance(selected_snapshot_profile, str)
            and isinstance(snapshot_profiles, dict)
            and isinstance(snapshot_profiles.get(selected_snapshot_profile), dict)
        ):
            resolved_snapshot = dict(snapshot_profiles[selected_snapshot_profile])
            resolved_snapshot.setdefault("name", selected_snapshot_profile)
            response_cfg["snapshot_profile_config"] = resolved_snapshot

        decision_prompt_profiles = self._cfg.get("decision_prompt_profiles", {})
        selected_decision_prompt_profile = response_cfg.get("decision_prompt_profile")
        if (
            isinstance(selected_decision_prompt_profile, str)
            and isinstance(decision_prompt_profiles, dict)
            and isinstance(decision_prompt_profiles.get(selected_decision_prompt_profile), dict)
        ):
            resolved_prompt = dict(decision_prompt_profiles[selected_decision_prompt_profile])
            resolved_prompt.setdefault("name", selected_decision_prompt_profile)
            response_cfg["decision_prompt_profile_config"] = resolved_prompt
            # Resolve fallback snapshot profile referenced by the decision prompt profile
            fallback_name = str(resolved_prompt.get("fallback_snapshot_profile") or "").strip()
            if (
                fallback_name
                and isinstance(snapshot_profiles, dict)
                and isinstance(snapshot_profiles.get(fallback_name), dict)
            ):
                fallback_snapshot = dict(snapshot_profiles[fallback_name])
                fallback_snapshot.setdefault("name", fallback_name)
                response_cfg["decision_prompt_fallback_snapshot_config"] = fallback_snapshot

        response = AgentMessage(
            event_type=EventType.AGENT_CONFIG_RESPONSE,
            source_agent_id=CONFIG_SERVICE_ID,
            target_agent_id=agent_id,
            payload={
                "agent_id": agent_id,
                "config": response_cfg,
                "modules": modules,
            },
            correlation_id=str(msg.id),
        )
        await self._bus.publish(response)
        _log.debug("ConfigService: sent config to %s", agent_id)

    async def _handle_ec_request(self, msg: AgentMessage) -> None:
        ec_id = msg.payload.get("ec_id", msg.source_agent_id)
        ec_cfg = self._cfg.get("event_composers", {}).get(ec_id)

        if ec_cfg is None:
            _log.warning("ConfigService: no event_composer config found for %r", ec_id)
            return
        if not ec_cfg.get("enable", True):
            _log.info("ConfigService: config for disabled EC %r ignored", ec_id)
            return

        response = AgentMessage(
            event_type=EventType.EC_CONFIG_RESPONSE,
            source_agent_id=CONFIG_SERVICE_ID,
            target_agent_id=ec_id,
            payload={
                "ec_id": ec_id,
                "config": dict(ec_cfg),
            },
            correlation_id=str(msg.id),
        )
        await self._bus.publish(response)
        _log.debug("ConfigService: sent EC config to %s", ec_id)
