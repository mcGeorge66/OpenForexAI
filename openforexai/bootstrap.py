"""Bootstrap — wires all system components from system.json5.

Flow
----
1. Load config/system.json5 (with env-var substitution)
2. Import adapter packages → self-registration in PluginRegistry
3. Create database repository
4. Create LLM instances from modules config, register in RuntimeRegistry
5. Create broker instances from modules config, connect, register in RuntimeRegistry
6. Build EventBus + RoutingTable
7. Create DataContainer (shared market data cache)
8. Create ConfigService (answers AGENT_CONFIG_REQUESTED events)
9. Create one Agent per entry in system.json5["agents"]
10. Start broker background tasks (M5 streaming, account poll)
11. Return (agents, config_service, bus, management_server)
"""
from __future__ import annotations

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
from openforexai.tools.config_loader import AgentToolConfig
from openforexai.tools.system.agent_bridge import register_bridge_tools_from_config
from openforexai.utils.logging import get_logger

_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _ROOT / "config"
_RUNTIME_CONFIG_DIR = _CONFIG_DIR / "RunTime"
_ROUTING_PATH = _RUNTIME_CONFIG_DIR / "event_routing.json5"
_AGENT_TOOLS_PATH = _RUNTIME_CONFIG_DIR / "agent_tools.json5"

_log = get_logger("bootstrap")


async def bootstrap(
    system_config: dict[str, Any],
    monitoring_bus=None,
) -> tuple[list[Agent], ConfigService, EventBus]:
    """Wire all components from *system_config* and return (agents, config_service, bus).

    Pass the result of ``load_json_config('config/system.json5')``.
    Optionally pass a *monitoring_bus* so broker tasks and agents can emit events.
    """
    # ── Trigger adapter self-registration ────────────────────────────────────
    import openforexai.adapters.brokers  # noqa: F401
    import openforexai.adapters.database  # noqa: F401
    import openforexai.adapters.llm  # noqa: F401

    db_cfg    = system_config.get("database", {})
    data_cfg  = system_config.get("data", {})
    mod_cfg   = system_config.get("modules",  {})
    agent_cfg = system_config.get("agents",   {})
    enabled_agent_cfg = {
        agent_id: cfg
        for agent_id, cfg in agent_cfg.items()
        if cfg.get("enable", True)
    }
    disabled_agent_ids = [agent_id for agent_id in agent_cfg if agent_id not in enabled_agent_cfg]
    for agent_id in disabled_agent_ids:
        _log.info("Agent disabled via config; skipping startup", agent_id=agent_id)

    # ── Database repository ───────────────────────────────────────────────────
    backend = db_cfg.get("backend", "sqlite")
    RepoClass = PluginRegistry.get_repository(backend)
    if backend == "sqlite":
        sqlite_path_raw = str(db_cfg.get("sqlite_path", "./data/openforexai.db"))
        sqlite_path = Path(sqlite_path_raw)
        if not sqlite_path.is_absolute():
            sqlite_path = (_ROOT / sqlite_path).resolve()
        repository = RepoClass(db_path=str(sqlite_path))
        _log.info("SQLite path resolved", path=str(sqlite_path))
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
        llm_instance = LLMClass.from_config(llm_mod)
        RuntimeRegistry.register_llm(llm_name, llm_instance)
        _log.info("LLM module loaded", name=llm_name, adapter=adapter)

    # ── Broker instances ──────────────────────────────────────────────────────
    broker_module_paths = mod_cfg.get("broker", {})
    connected_brokers: dict[str, Any] = {}
    broker_task_cfg: dict[str, dict[str, Any]] = {}
    broker_short_name_owner: dict[str, str] = {}

    def _int_at_least_one(value: Any, default: int) -> int:
        if isinstance(value, int):
            return value if value >= 1 else default
        if isinstance(value, str):
            try:
                parsed = int(value)
                return parsed if parsed >= 1 else default
            except ValueError:
                return default
        return default

    for broker_name, cfg_path in broker_module_paths.items():
        broker_mod = load_json_config(_ROOT / cfg_path)
        adapter = broker_mod.get("adapter", broker_name)
        try:
            BrokerClass = PluginRegistry.get_broker(adapter)
        except ValueError:
            _log.warning("Broker adapter %r not registered — skipping %r", adapter, broker_name)
            continue

        broker_instance = BrokerClass.from_config(broker_mod)
        short_name = str(getattr(broker_instance, "short_name", "")).strip()
        if not short_name:
            raise ValueError(
                f"Broker module {broker_name!r} produced an empty short_name. "
                "Set a unique short_name (1-5 chars) in the broker module config."
            )
        existing_owner = broker_short_name_owner.get(short_name)
        if existing_owner and existing_owner != broker_name:
            raise ValueError(
                "Duplicate broker short_name detected: "
                f"{short_name!r} is used by both {existing_owner!r} and {broker_name!r}. "
                "Broker short_name must be globally unique."
            )
        broker_short_name_owner[short_name] = broker_name

        bg_cfg_raw = broker_mod.get("background_tasks", {})
        bg_cfg = bg_cfg_raw if isinstance(bg_cfg_raw, dict) else {}
        account_poll_interval = _int_at_least_one(
            bg_cfg.get("account_poll_interval_seconds", 60),
            60,
        )
        sync_interval = _int_at_least_one(
            bg_cfg.get("sync_interval_seconds", 60),
            60,
        )
        request_agent_reasoning = bool(bg_cfg.get("request_agent_reasoning", False))
        broker_task_cfg[broker_name] = {
            "account_poll_interval": account_poll_interval,
            "sync_interval": sync_interval,
            "request_agent_reasoning": request_agent_reasoning,
        }

        await broker_instance.connect()
        RuntimeRegistry.register_broker(broker_name, broker_instance)
        connected_brokers[broker_name] = broker_instance
        _log.info(
            "Broker module connected",
            name=broker_name,
            short_name=short_name,
            adapter=adapter,
            account_poll_interval=account_poll_interval,
            sync_interval=sync_interval,
            request_agent_reasoning=request_agent_reasoning,
        )

    # ── EventBus + RoutingTable ───────────────────────────────────────────────
    routing = RoutingTable()
    if _ROUTING_PATH.exists():
        routing.load(_ROUTING_PATH)
    bus = EventBus(routing=routing, monitoring_bus=monitoring_bus)

    # ── Config-driven bridge tools (visible in ToolExecutor immediately) ─────
    agent_tool_cfg = AgentToolConfig.load(_AGENT_TOOLS_PATH)
    bridge_count = register_bridge_tools_from_config(
        agent_tool_cfg.raw_bridge_tools(),
        DEFAULT_REGISTRY,
    )
    if bridge_count:
        _log.info("Registered bridge tools from config", count=bridge_count)

    # ── DataContainer ─────────────────────────────────────────────────────────
    data_container = DataContainer(
        store=repository,
        event_bus=bus,
        monitoring_bus=monitoring_bus,
        resample_bucket_offset_hours=int(data_cfg.get("resample_bucket_offset_hours", 0)),
    )

    # Register each unique broker + its pairs (derived from agent configs)
    broker_pairs: dict[str, set[str]] = {}
    for cfg in enabled_agent_cfg.values():
        b = cfg.get("broker")
        p = cfg.get("pair")
        if b and p:
            broker_pairs.setdefault(b, set()).add(p)

    for broker_name, broker_instance in connected_brokers.items():
        pairs = sorted(broker_pairs.get(broker_name, set()))
        data_container.register_broker(broker_instance, pairs)
        if not pairs:
            _log.info(
                "Broker registered in DataContainer without startup pairs",
                broker=broker_name,
            )

    data_container.subscribe_to_bus()
    await data_container.initialize()

    # ── ConfigService ─────────────────────────────────────────────────────────
    config_service = ConfigService(system_config, bus)

    # ── Agents ────────────────────────────────────────────────────────────────
    agents: list[Agent] = []
    for agent_id in enabled_agent_cfg:
        agent = Agent(
            agent_id=agent_id,
            bus=bus,
            data_container=data_container,
            repository=repository,
            monitoring_bus=monitoring_bus,
        )
        agents.append(agent)
        _log.info("Agent created", agent_id=agent_id)

    # ── Broker background tasks ────────────────────────────────────────────────
    for broker_name, pairs in broker_pairs.items():
        broker_instance = connected_brokers.get(broker_name)
        if broker_instance is None:
            continue
        task_cfg = broker_task_cfg.get(broker_name, {})
        for pair in pairs:
            broker_instance.start_background_tasks(
                pair=pair,
                event_bus=bus,
                repository=repository,
                account_poll_interval=task_cfg.get("account_poll_interval", 60),
                sync_interval=task_cfg.get("sync_interval", 60),
                request_agent_reasoning=task_cfg.get("request_agent_reasoning", False),
                monitoring_bus=monitoring_bus,
            )

    return agents, config_service, bus, data_container, repository, connected_brokers
