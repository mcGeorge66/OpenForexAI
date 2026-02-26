from __future__ import annotations

from typing import Awaitable, Callable

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType

Handler = Callable[[AgentMessage], Awaitable[None]]


def wire_subscriptions(
    bus: EventBus,
    supervisor: object,
    trading_agents: list[object],
    technical_analysis_agent: object,
    optimization_agent: object,
) -> None:
    """Register all inter-agent event subscriptions on the bus.

    Called once from ``bootstrap.py`` after all agents are instantiated.
    """
    # Market data → trading agents (each handles its own pair)
    for ta in trading_agents:
        bus.subscribe(EventType.MARKET_DATA_UPDATED, ta.on_market_updated)  # type: ignore[attr-defined]

    # Trading agents → supervisor
    bus.subscribe(EventType.SIGNAL_GENERATED, supervisor.on_signal_generated)  # type: ignore[attr-defined]

    # Supervisor → trading agents (pair-filtered inside each handler)
    for ta in trading_agents:
        bus.subscribe(EventType.SIGNAL_APPROVED, ta.on_signal_approved)  # type: ignore[attr-defined]
        bus.subscribe(EventType.SIGNAL_REJECTED, ta.on_signal_rejected)  # type: ignore[attr-defined]

    # Technical analysis request/response
    bus.subscribe(
        EventType.ANALYSIS_REQUESTED,
        technical_analysis_agent.on_analysis_requested,  # type: ignore[attr-defined]
    )
    for ta in trading_agents:
        bus.subscribe(EventType.ANALYSIS_RESULT, ta.on_analysis_result)  # type: ignore[attr-defined]

    # Position lifecycle → optimization agent
    bus.subscribe(EventType.POSITION_CLOSED, optimization_agent.on_position_closed)  # type: ignore[attr-defined]

    # Prompt updates → trading agents
    for ta in trading_agents:
        bus.subscribe(EventType.PROMPT_UPDATED, ta.on_prompt_updated)  # type: ignore[attr-defined]
