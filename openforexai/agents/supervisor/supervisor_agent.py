from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from openforexai.agents.base import BaseAgent
from openforexai.agents.supervisor.correlation_checker import CorrelationChecker
from openforexai.agents.supervisor.risk_engine import RiskEngine
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.risk import RiskParameters
from openforexai.models.trade import TradeOrder, TradeSignal
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider


class SupervisorAgent(BaseAgent):
    """Orchestration + risk gate.

    Reactive: does not tick on a timer.  Subscribes to SIGNAL_GENERATED,
    evaluates risk, and either approves (places the order) or rejects.
    """

    def __init__(
        self,
        risk_params: RiskParameters,
        broker: AbstractBroker,
        data_container: DataContainer,
        pairs: list[str],
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
    ) -> None:
        super().__init__(
            agent_id="supervisor",
            llm=llm,
            repository=repository,
            bus=bus,
        )
        self.broker = broker
        self.data_container = data_container
        self.pairs = pairs
        self.risk_engine = RiskEngine(risk_params)
        self.correlation_checker = CorrelationChecker()
        self._daily_pnl: float = 0.0

    async def run_cycle(self) -> None:
        """Periodic background task: refresh correlation matrix & monitor positions."""
        try:
            candle_sets = {
                pair: self.data_container.get_candles(pair, "H1")
                for pair in self.pairs
            }
            self.correlation_checker.update(candle_sets)
            await self._monitor_positions()
        except Exception as exc:
            self._logger.exception("Supervisor cycle error", error=str(exc))
        await asyncio.sleep(300)  # refresh every 5 minutes

    # ── Event handlers ────────────────────────────────────────────────────────

    async def on_signal_generated(self, message: AgentMessage) -> None:
        start = time.monotonic()
        payload = message.payload
        pair = payload.get("pair", "")
        signal_data = payload.get("signal", {})

        try:
            signal = TradeSignal(**signal_data)
        except Exception as exc:
            self._logger.error("Could not parse signal", error=str(exc))
            return

        try:
            positions = await self.broker.get_open_positions()
            balance = await self.broker.get_account_balance()

            assessment = self.risk_engine.assess(
                signal=signal,
                open_positions=positions,
                account_balance=balance,
                daily_pnl=self._daily_pnl,
                correlation_matrix=self.correlation_checker.matrix,
            )

            latency_ms = (time.monotonic() - start) * 1000

            if assessment.approved:
                order = TradeOrder(
                    signal=signal,
                    units=assessment.adjusted_units or 1000,
                    risk_pct=self.risk_engine.params.max_risk_per_trade_pct,
                    approved_by=self.agent_id,
                )
                trade_result = await self.broker.place_order(order)
                await self.repository.save_trade(trade_result)

                await self.publish(
                    AgentMessage(
                        event_type=EventType.SIGNAL_APPROVED,
                        source_agent_id=self.agent_id,
                        payload={
                            "pair": pair,
                            "signal_id": str(signal.id),
                            "order_id": trade_result.broker_order_id,
                        },
                    )
                )
                self._logger.info("Signal approved and order placed", pair=pair)

            else:
                await self.publish(
                    AgentMessage(
                        event_type=EventType.SIGNAL_REJECTED,
                        source_agent_id=self.agent_id,
                        payload={
                            "pair": pair,
                            "signal_id": str(signal.id),
                            "rejection_reason": assessment.rejection_reason,
                        },
                    )
                )
                self._logger.info(
                    "Signal rejected",
                    pair=pair,
                    reason=assessment.rejection_reason,
                )

            await self.repository.save_agent_decision(
                AgentDecision(
                    agent_id=self.agent_id,
                    agent_role=AgentRole.SUPERVISOR,
                    pair=pair,
                    decision_type="approve" if assessment.approved else "reject",
                    input_context={"signal_id": str(signal.id)},
                    output=assessment.model_dump(),
                    llm_model="none",
                    tokens_used=0,
                    latency_ms=latency_ms,
                    decided_at=datetime.now(timezone.utc),
                )
            )

        except Exception as exc:
            self._logger.exception("Error processing signal", pair=pair, error=str(exc))

    async def _monitor_positions(self) -> None:
        """Check for SL/TP hits on open positions."""
        try:
            positions = await self.broker.get_open_positions()
            for pos in positions:
                snapshot = await self.data_container.get_snapshot(pos.pair)
                current = float(snapshot.current_tick.mid)
                if self._is_sl_hit(pos, current) or self._is_tp_hit(pos, current):
                    result = await self.broker.close_position(pos.broker_position_id)
                    await self.repository.save_trade(result)
                    if result.pnl:
                        self._daily_pnl += float(result.pnl)
                    await self.publish(
                        AgentMessage(
                            event_type=EventType.POSITION_CLOSED,
                            source_agent_id=self.agent_id,
                            payload={
                                "pair": pos.pair,
                                "pnl": float(result.pnl or 0),
                                "close_reason": result.close_reason,
                            },
                        )
                    )
        except Exception as exc:
            self._logger.warning("Position monitoring error", error=str(exc))

    @staticmethod
    def _is_sl_hit(pos, current_price: float) -> bool:
        return False  # Broker-side SL; left as hook for manual override

    @staticmethod
    def _is_tp_hit(pos, current_price: float) -> bool:
        return False  # Same
