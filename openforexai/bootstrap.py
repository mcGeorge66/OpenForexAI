from __future__ import annotations

from openforexai.agents.optimization.optimization_agent import OptimizationAgent
from openforexai.agents.supervisor.supervisor_agent import SupervisorAgent
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.agents.trading.trading_agent import TradingAgent
from openforexai.config.settings import Settings
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.messaging.handlers import wire_subscriptions
from openforexai.models.risk import RiskParameters
from openforexai.registry.plugin_registry import PluginRegistry


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

    # ── Data container ────────────────────────────────────────────────────────
    data_container = DataContainer(
        broker=broker,
        repository=repository,
        pairs=settings.pairs,
        rolling_weeks=settings.data.rolling_weeks,
        timeframes=settings.data.timeframes,
    )
    await data_container.initialize()

    # ── Event bus ─────────────────────────────────────────────────────────────
    bus = EventBus()

    # ── Agents ────────────────────────────────────────────────────────────────
    risk_params = RiskParameters(**settings.risk.model_dump())

    supervisor = SupervisorAgent(
        risk_params=risk_params,
        broker=broker,
        data_container=data_container,
        pairs=settings.pairs,
        llm=llm,
        repository=repository,
        bus=bus,
    )

    # One TradingAgent per configured pair (variabel, min. 1)
    trading_agents: list[TradingAgent] = [
        TradingAgent(
            pair=pair,
            broker=broker,
            data_container=data_container,
            llm=llm,
            repository=repository,
            bus=bus,
            cycle_interval_seconds=settings.agents.trading.cycle_interval_seconds,
            analysis_timeout_seconds=settings.agents.trading.analysis_timeout_seconds,
            context_candles=settings.agents.trading.context_candles or None,
        )
        for pair in settings.pairs
    ]

    # Singleton technical analysis agent (needs DataContainer for cross-TF indicator calls)
    technical_analysis_agent = TechnicalAnalysisAgent(
        llm=llm,
        repository=repository,
        bus=bus,
        data_container=data_container,
        max_concurrent_requests=settings.agents.technical_analysis.max_concurrent_requests,
    )

    optimization_agent = OptimizationAgent(
        pairs=settings.pairs,
        data_container=data_container,
        llm=llm,
        repository=repository,
        bus=bus,
        min_trades_before_run=settings.agents.optimization.min_trades_before_run,
        optimization_interval_hours=settings.optimization_interval_hours,
    )

    # ── Wire subscriptions ────────────────────────────────────────────────────
    wire_subscriptions(
        bus=bus,
        supervisor=supervisor,
        trading_agents=trading_agents,
        technical_analysis_agent=technical_analysis_agent,
        optimization_agent=optimization_agent,
    )

    all_agents = [supervisor, *trading_agents, technical_analysis_agent, optimization_agent]
    return all_agents, bus
