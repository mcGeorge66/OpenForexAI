"""TradingAgent — per-pair LLM-driven trading agent.

One instance is created for each configured Forex pair.  The agent:

1. Wakes up on its cycle interval.
2. Calls the LLM via the native tool-use loop (``run_with_tools()``).
3. The LLM autonomously uses available tools to:
   - Fetch candles at any timeframe
   - Compute technical indicators
   - Check account status and open positions
   - Query the order book
   - Place or close orders (via supervisor approval)
   - Raise alarms
4. Persists the AgentDecision.
5. Sleeps until the next cycle.

Additionally, the agent processes inbound EventBus messages (routed via the
routing table) to handle:
- SIGNAL_APPROVED / SIGNAL_REJECTED responses from the SupervisorAgent
- PROMPT_UPDATED from the OptimizationAgent
- ORDER_BOOK_SYNC_DISCREPANCY from the broker sync loop

Agent ID format: ``{BROKER(5)}_{PAIR(6)}_AA_TRD1``
Example:         ``OANDA_EURUSD_AA_TRD1``
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from openforexai.agents.base import BaseAgent
from openforexai.agents.trading.prompt_templates import get_default_prompt
from openforexai.data.container import DataContainer
from openforexai.messaging.agent_id import AgentId
from openforexai.messaging.bus import EventBus
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider
from openforexai.tools.dispatcher import ToolDispatcher


class TradingAgent(BaseAgent):
    """Per-pair trading agent using native LLM tool-use."""

    def __init__(
        self,
        broker_name: str,
        pair: str,
        data_container: DataContainer,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        tool_dispatcher: ToolDispatcher,
        cycle_interval_seconds: int = 60,
        max_tokens: int = 4096,
        max_tool_turns: int = 10,
    ) -> None:
        aid = AgentId.build(
            broker=broker_name, pair=pair, agent_type="AA", name="TRD1"
        )
        super().__init__(
            agent_id=aid.format(),
            llm=llm,
            repository=repository,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            max_tool_turns=max_tool_turns,
            max_tokens=max_tokens,
        )
        self.pair = pair
        self.broker_name = broker_name
        self.data_container = data_container
        self.cycle_interval = cycle_interval_seconds

        self._system_prompt = get_default_prompt(pair)

    async def _on_start(self) -> None:
        self._logger.info("TradingAgent started", pair=self.pair, broker=self.broker_name)

    # ── Core cycle ───────────────────────────────────────────────────────────

    async def run_cycle(self) -> None:
        start = time.monotonic()

        try:
            now = datetime.now(timezone.utc).isoformat()
            user_message = (
                f"Current time: {now}\n"
                f"Pair: {self.pair} | Broker: {self.broker_name}\n\n"
                "Analyse the market for your pair and make a trading decision. "
                "Use the available tools to gather data (candles, indicators, "
                "account status, open positions, order book) as needed. "
                "If you decide to trade, use place_order. "
                "If you decide to close a position, use close_position. "
                "If you detect an anomaly, use raise_alarm. "
                "Always justify your decision clearly."
            )

            final_text, total_tokens = await self.run_with_tools(user_message)

            # Persist AgentDecision
            decision = AgentDecision(
                agent_id=self.agent_id,
                agent_role=AgentRole.TRADING,
                pair=self.pair,
                decision_type="cycle",
                input_context={"timestamp": now, "broker": self.broker_name},
                output={"summary": final_text[:2000]},  # truncate for storage
                llm_model=self.llm.model_id,
                tokens_used=total_tokens,
                latency_ms=(time.monotonic() - start) * 1000,
                decided_at=datetime.now(timezone.utc),
            )
            await self.repository.save_agent_decision(decision)

        except Exception as exc:
            self._logger.exception("Cycle error", error=str(exc))

        # Sleep until next cycle
        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0.0, self.cycle_interval - elapsed))

    # ── Inbound message handler ───────────────────────────────────────────────

    async def _handle_message(self, message: AgentMessage) -> None:
        """Process messages delivered to this agent's inbox via the EventBus."""
        event = message.event_type

        if event == EventType.PROMPT_UPDATED:
            new_prompt = message.payload.get("system_prompt", "")
            if new_prompt:
                self.load_prompt(new_prompt)
                self._logger.info("Prompt updated by OptimizationAgent")

        elif event == EventType.SIGNAL_APPROVED:
            self._logger.info(
                "Signal approved",
                signal_id=message.payload.get("signal_id"),
                correlation_id=message.correlation_id,
            )

        elif event == EventType.SIGNAL_REJECTED:
            self._logger.info(
                "Signal rejected",
                reason=message.payload.get("reason"),
                correlation_id=message.correlation_id,
            )

        elif event == EventType.ORDER_BOOK_SYNC_DISCREPANCY:
            payload = message.payload
            self._logger.warning(
                "Order book sync discrepancy",
                entry_id=payload.get("entry_id"),
                close_reason=payload.get("close_reason"),
                pnl=payload.get("pnl"),
            )
            # If the broker asks for close reasoning, publish it
            if payload.get("request_agent_reasoning"):
                await self._publish_close_reasoning(payload)

    async def _publish_close_reasoning(self, payload: dict) -> None:
        """Generate and publish reasoning for an unexpected position close."""
        try:
            entry_id = payload.get("entry_id", "")
            close_reason = payload.get("close_reason", "unknown")
            pnl = payload.get("pnl")

            reasoning_prompt = (
                f"A position (entry_id={entry_id}) was closed unexpectedly.\n"
                f"Close reason detected: {close_reason}\n"
                f"P&L: {pnl}\n\n"
                "Briefly explain in 1-2 sentences what likely happened and "
                "whether this outcome is acceptable."
            )
            text, _ = await self.run_with_tools(reasoning_prompt)

            await self.publish(AgentMessage(
                event_type=EventType.ORDER_BOOK_CLOSE_REASONING,
                source_agent_id=self.agent_id,
                payload={"entry_id": entry_id, "close_reasoning": text},
                correlation_id=payload.get("correlation_id"),
            ))
        except Exception as exc:
            self._logger.exception("Failed to generate close reasoning: %s", exc)
