"""Bootstrap — wires all system components from system.json.

Flow
----
1. Load config/system.json (with env-var substitution)
2. Import adapter packages → self-registration in PluginRegistry
3. Create database repository
4. Create LLM instances from modules config, register in RuntimeRegistry
5. Create broker instances from modules config, connect, register in RuntimeRegistry
6. Build EventBus + RoutingTable
7. Create DataContainer (shared market data cache)
8. Create ConfigService (answers AGENT_CONFIG_REQUESTED events)
9. Create one Agent per entry in system.json["agents"]
10. Start broker background tasks (M5 streaming, account poll)
11. Return (agents, config_service, bus, management_server)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openforexai.agents.agent import Agent
from openforexai.config.config_service import ConfigService
from openforexai.config.json_loader import load_json_config
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.messaging.routing import RoutingTable
from openforexai.registry.plugin_registry import PluginRegistry
from openforexai.registry.runtime_registry import RuntimeRegistry
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.utils.logging import get_logger

_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _ROOT / "config"
_ROUTING_PATH = Path(__file__).parent / "config" / "event_routing.json"

_log = get_logger("bootstrap")


async def bootstrap(system_config: dict[str, Any]) -> tuple[list[Agent], ConfigService, EventBus]:
    """Wire all components from *system_config* and return (agents, config_service, bus).

    Pass the result of ``load_json_config('config/system.json')``.
    """
    # ── Trigger adapter self-registration ────────────────────────────────────
    import openforexai.adapters.brokers   # noqa: F401
    import openforexai.adapters.llm       # noqa: F401
    import openforexai.adapters.database  # noqa: F401

    db_cfg    = system_config.get("database", {})
    mod_cfg   = system_config.get("modules",  {})
    agent_cfg = system_config.get("agents",   {})

    # ── Database repository ───────────────────────────────────────────────────
    backend = db_cfg.get("backend", "sqlite")
    RepoClass = PluginRegistry.get_repository(backend)
    if backend == "sqlite":
        repository = RepoClass(db_path=db_cfg.get("sqlite_path", "./data/openforexai.db"))
    else:
        repository = RepoClass(
            database_url=db_cfg.get("database_url", ""),
            pool_size=db_cfg.get("pool_size", 5),
        )
    await repository.initialize()

    # ── LLM instances ─────────────────────────────────────────────────────────
    llm_module_paths = mod_cfg.get("llm", {})
    for llm_name, cfg_path in llm_module_paths.items():
        llm_mod = load_json_config(_ROOT / cfg_path)
        adapter  = llm_mod.get("adapter", llm_name)
        LLMClass = PluginRegistry.get_llm_provider(adapter)
        if adapter == "anthropic":
            llm_instance = LLMClass(
                api_key=llm_mod.get("api_key", ""),
                model=llm_mod.get("model", "claude-opus-4-6"),
            )
        elif adapter == "lmstudio":
            llm_instance = LLMClass(
                base_url=llm_mod.get("base_url", "http://localhost:1234"),
                model=llm_mod.get("model", "local-model"),
            )
        else:  # openai
            llm_instance = LLMClass(
                api_key=llm_mod.get("api_key", ""),
                model=llm_mod.get("model", "gpt-4o"),
            )
        RuntimeRegistry.register_llm(llm_name, llm_instance)
        _log.info("LLM module loaded", name=llm_name, adapter=adapter)

    # ── Broker instances ──────────────────────────────────────────────────────
    broker_module_paths = mod_cfg.get("broker", {})
    connected_brokers: dict[str, Any] = {}

    for broker_name, cfg_path in broker_module_paths.items():
        broker_mod = load_json_config(_ROOT / cfg_path)
        adapter = broker_mod.get("adapter", broker_name)
        try:
            BrokerClass = PluginRegistry.get_broker(adapter)
        except ValueError:
            _log.warning("Broker adapter %r not registered — skipping %r", adapter, broker_name)
            continue

        if adapter == "oanda":
            broker_instance = BrokerClass(
                api_key=broker_mod.get("api_key", ""),
                account_id=broker_mod.get("account_id", ""),
                practice=broker_mod.get("practice", True),
            )
        elif adapter == "mt5":
            broker_instance = BrokerClass(
                login=int(broker_mod.get("login", 0)),
                password=broker_mod.get("password", ""),
                server=broker_mod.get("server", ""),
            )
        else:
            _log.warning("Unknown broker adapter %r — skipping", adapter)
            continue

        await broker_instance.connect()
        RuntimeRegistry.register_broker(broker_name, broker_instance)
        connected_brokers[broker_name] = broker_instance
        _log.info("Broker module connected", name=broker_name, adapter=adapter)

    # ── EventBus + RoutingTable ───────────────────────────────────────────────
    routing = RoutingTable()
    if _ROUTING_PATH.exists():
        routing.load(_ROUTING_PATH)
    bus = EventBus(routing=routing)

    # ── DataContainer ─────────────────────────────────────────────────────────
    data_cfg = system_config.get("data", {})
    data_container = DataContainer(repository=repository, event_bus=bus)

    # Register each unique broker + its pairs (derived from agent configs)
    broker_pairs: dict[str, set[str]] = {}
    for cfg in agent_cfg.values():
        b = cfg.get("broker")
        p = cfg.get("pair")
        if b and p:
            broker_pairs.setdefault(b, set()).add(p)

    for broker_name, pairs in broker_pairs.items():
        broker_instance = connected_brokers.get(broker_name)
        if broker_instance is None:
            _log.warning("No connected broker for %r — skipping DataContainer registration", broker_name)
            continue
        data_container.register_broker(broker_instance, list(pairs))

    data_container.subscribe_to_bus()
    await data_container.initialize()

    # ── ConfigService ─────────────────────────────────────────────────────────
    config_service = ConfigService(system_config, bus)

    # ── Agents ────────────────────────────────────────────────────────────────
    agents: list[Agent] = []
    for agent_id in agent_cfg:
        agent = Agent(
            agent_id=agent_id,
            bus=bus,
            data_container=data_container,
            repository=repository,
        )
        agents.append(agent)
        _log.info("Agent created", agent_id=agent_id)

    # ── Broker background tasks ────────────────────────────────────────────────
    for broker_name, pairs in broker_pairs.items():
        broker_instance = connected_brokers.get(broker_name)
        if broker_instance is None:
            continue
        for pair in pairs:
            broker_instance.start_background_tasks(
                pair=pair,
                event_bus=bus,
                repository=repository,
            )

    return agents, config_service, bus
