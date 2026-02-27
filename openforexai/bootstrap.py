from __future__ import annotations

from pathlib import Path

from openforexai.agents.optimization.optimization_agent import OptimizationAgent
from openforexai.agents.supervisor.supervisor_agent import SupervisorAgent
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.agents.trading.trading_agent import TradingAgent
from openforexai.config.settings import Settings
from openforexai.data.container import DataContainer
from openforexai.messaging.agent_id import AgentId
from openforexai.messaging.bus import EventBus
from openforexai.messaging.routing import RoutingTable
from openforexai.models.risk import RiskParameters
from openforexai.registry.plugin_registry import PluginRegistry
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext
from openforexai.tools.config_loader import AgentToolConfig
from openforexai.tools.dispatcher import ToolDispatcher

_CONFIG_DIR = Path(__file__).parent / "config"


async def bootstrap(settings: Settings) -> tuple[list, EventBus]:
    """Wire up all components from *settings* and return (agents, bus).

    Importing the adapter sub-packages triggers plugin self-registration via
    each package's ``__init__.py``.
    """
    settings.validate_pairs()

    # ── Trigger plugin registration ──────────────────────────────────────────
    import openforexai.adapters.brokers  # noqa: F401
    import openforexai.adapters.llm  # noqa: F401
    import openforexai.adapters.database  # noqa: F401

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLMClass = PluginRegistry.get_llm_provider(settings.llm.provider)
    if settings.llm.provider == "anthropic":
        llm = LLMClass(api_key=settings.llm.api_key, model=settings.llm.model)
    elif settings.llm.provider == "lmstudio":
        llm = LLMClass(base_url=settings.llm.base_url, model=settings.llm.model)
    else:  # openai
        llm = LLMClass(api_key=settings.llm.api_key, model=settings.llm.model)

    # ── Repository ────────────────────────────────────────────────────────────
    RepoClass = PluginRegistry.get_repository(settings.database.backend)
    if settings.database.backend == "sqlite":
        repository = RepoClass(db_path=settings.database.sqlite_path)
    else:
        repository = RepoClass(
            database_url=settings.database.database_url or "",
            pool_size=settings.database.pool_size,
        )
    await repository.initialize()

    # ── Broker ────────────────────────────────────────────────────────────────
    BrokerClass = PluginRegistry.get_broker(settings.broker.name)
    if settings.broker.name == "oanda":
        broker = BrokerClass(
            api_key=settings.broker.oanda.api_key,
            account_id=settings.broker.oanda.account_id,
            practice=settings.broker.oanda.practice,
        )
    else:  # mt5
        broker = BrokerClass(
            login=settings.broker.mt5.login,
            password=settings.broker.mt5.password,
            server=settings.broker.mt5.server,
        )
    await broker.connect()

    # ── Event bus (with routing table) ────────────────────────────────────────
    routing = RoutingTable()
    routing_path = _CONFIG_DIR / "event_routing.json"
    if routing_path.exists():
        routing.load(routing_path)
    bus = EventBus(routing=routing)

    # ── Data container ────────────────────────────────────────────────────────
    data_container = DataContainer(repository=repository, event_bus=bus)
    data_container.register_broker(broker, settings.pairs)
    data_container.subscribe_to_bus()
    await data_container.initialize()

    # ── Per-agent tool configuration ──────────────────────────────────────────
    tool_config = AgentToolConfig.load(_CONFIG_DIR / "agent_tools.json")

    # ── Risk parameters ───────────────────────────────────────────────────────
    risk_params = RiskParameters(**settings.risk.model_dump())

    # ── SupervisorAgent (one per broker) ─────────────────────────────────────
    supervisor = SupervisorAgent(
        broker_name=broker.short_name,
        risk_params=risk_params,
        broker=broker,
        data_container=data_container,
        pairs=settings.pairs,
        llm=llm,
        repository=repository,
        bus=bus,
    )

    # ── TradingAgents — one per configured pair (min. 1) ─────────────────────
    trading_agents: list[TradingAgent] = []
    for pair in settings.pairs:
        aid = AgentId.build(broker=broker.short_name, pair=pair, agent_type="AA", name="TRD1")
        agent_id_str = aid.format()
        context = ToolContext(
            agent_id=agent_id_str,
            broker_name=broker.short_name,
            pair=pair,
            data_container=data_container,
            repository=repository,
            broker=broker,
            event_bus=bus,
        )
        dispatcher = ToolDispatcher(
            registry=DEFAULT_REGISTRY,
            context=context,
            agent_tool_config=tool_config.for_agent(agent_id_str),
        )
        trading_agents.append(TradingAgent(
            broker_name=broker.short_name,
            pair=pair,
            data_container=data_container,
            llm=llm,
            repository=repository,
            bus=bus,
            tool_dispatcher=dispatcher,
            cycle_interval_seconds=settings.agents.trading.cycle_interval_seconds,
        ))

    # ── TechnicalAnalysisAgent (global singleton) ─────────────────────────────
    technical_analysis_agent = TechnicalAnalysisAgent(
        llm=llm,
        repository=repository,
        bus=bus,
        data_container=data_container,
        broker_name=broker.short_name,
        max_concurrent_requests=settings.agents.technical_analysis.max_concurrent_requests,
    )

    # ── OptimizationAgent (global singleton) ──────────────────────────────────
    optimization_agent = OptimizationAgent(
        pairs=settings.pairs,
        data_container=data_container,
        llm=llm,
        repository=repository,
        bus=bus,
        min_trades_before_run=settings.agents.optimization.min_trades_before_run,
        optimization_interval_hours=settings.optimization_interval_hours,
    )

    # ── Start broker background tasks (M5 streaming, account poll, sync) ──────
    # One background-task set per pair (one adapter = one pair)
    for pair in settings.pairs:
        broker.start_background_tasks(
            pair=pair,
            event_bus=bus,
            repository=repository,
        )

    all_agents = [supervisor, *trading_agents, technical_analysis_agent, optimization_agent]
    return all_agents, bus
