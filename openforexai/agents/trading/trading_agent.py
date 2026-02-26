from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from openforexai.agents.base import BaseAgent
from openforexai.agents.trading.context_builder import build_trading_context
from openforexai.agents.trading.prompt_templates import get_default_prompt
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.analysis import AnalysisResult
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.trade import TradeDirection, TradeSignal
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider


class TradingAgent(BaseAgent):
    """Per-pair trading agent.

    One instance is created for every entry in ``config.pairs``.

    Cycle:
      1. Pull MarketSnapshot from DataContainer.
      2. Quick first-pass LLM call.
      3. If ``needs_deep_analysis``, request a TA analysis via the EventBus
         and wait up to *analysis_timeout_seconds*.
      4. Build final TradeSignal (or HOLD).
      5. Publish SIGNAL_GENERATED.
      6. Persist AgentDecision.
    """

    def __init__(
        self,
        pair: str,
        broker: AbstractBroker,
        data_container: DataContainer,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        cycle_interval_seconds: int = 60,
        analysis_timeout_seconds: float = 15.0,
        context_candles: dict[str, int] | None = None,
    ) -> None:
        super().__init__(
            agent_id=f"trading_{pair}",
            llm=llm,
            repository=repository,
            bus=bus,
        )
        self.pair = pair
        self.broker = broker
        self.data_container = data_container
        self.cycle_interval = cycle_interval_seconds
        self.analysis_timeout = analysis_timeout_seconds
        self.context_candles = context_candles  # None → context_builder uses its default

        # Pending analysis responses keyed by correlation_id
        self._pending_analyses: dict[str, asyncio.Future[AnalysisResult]] = {}

        self._system_prompt = get_default_prompt(pair)

    async def _on_start(self) -> None:
        self._logger.info("TradingAgent started", pair=self.pair)

    # ── Event handlers (called by EventBus) ─────────────────────────────────

    async def on_market_updated(self, message: AgentMessage) -> None:
        """Triggered by DataContainer on fresh market data; no-op here (cycle-driven)."""

    async def on_signal_approved(self, message: AgentMessage) -> None:
        payload = message.payload
        if payload.get("pair") != self.pair:
            return
        self._logger.info("Signal approved", signal_id=payload.get("signal_id"))

    async def on_signal_rejected(self, message: AgentMessage) -> None:
        payload = message.payload
        if payload.get("pair") != self.pair:
            return
        self._logger.info(
            "Signal rejected",
            reason=payload.get("rejection_reason"),
        )

    async def on_analysis_result(self, message: AgentMessage) -> None:
        """Resolve the pending Future for the matching correlation_id."""
        cid = message.correlation_id
        if cid and cid in self._pending_analyses:
            result = AnalysisResult(**message.payload)
            fut = self._pending_analyses.pop(cid)
            if not fut.done():
                fut.set_result(result)

    async def on_prompt_updated(self, message: AgentMessage) -> None:
        payload = message.payload
        if payload.get("pair") != self.pair:
            return
        new_prompt = payload.get("system_prompt", "")
        if new_prompt:
            self.load_prompt(new_prompt)

    # ── Core cycle ───────────────────────────────────────────────────────────

    async def run_cycle(self) -> None:
        start = time.monotonic()

        try:
            snapshot = await self.data_container.get_snapshot(self.pair)
            positions = await self.broker.get_open_positions()
            balance = await self.broker.get_account_balance()
            recent_trades = await self.repository.get_trades(pair=self.pair, limit=10)

            # ── First-pass LLM call ──────────────────────────────────────────
            context = build_trading_context(
                snapshot=snapshot,
                recent_trades=recent_trades,
                open_positions_count=len(positions),
                account_balance=balance,
                analysis=None,
                context_candles=self.context_candles,
            )
            first_response = await self.llm.complete_structured(
                system_prompt=self._system_prompt,
                user_message=context,
                response_schema=_TradingDecision,
            )
            decision_data = _TradingDecision(**first_response)

            # ── Optional on-demand candle fetch ──────────────────────────────
            extra_candles: dict[str, list] = {}
            if decision_data.requested_candles:
                for req in decision_data.requested_candles:
                    pair_req = req.get("pair", self.pair)
                    tf = req.get("timeframe", "M5")
                    count = min(int(req.get("count", 50)), 500)
                    raw = self.data_container.get_candles(pair_req, tf)
                    extra_candles[f"{pair_req}_{tf}"] = raw[-count:]

            # ── Optional deep analysis ───────────────────────────────────────
            analysis: AnalysisResult | None = None
            if decision_data.needs_deep_analysis:
                analysis = await self._request_analysis(snapshot.model_dump(mode="json"))

            # ── Final decision if anything enriched the context ──────────────
            if analysis is not None or extra_candles:
                enriched_context = build_trading_context(
                    snapshot=snapshot,
                    recent_trades=recent_trades,
                    open_positions_count=len(positions),
                    account_balance=balance,
                    analysis=analysis,
                    context_candles=self.context_candles,
                    extra_candles=extra_candles or None,
                )
                final_response = await self.llm.complete_structured(
                    system_prompt=self._system_prompt,
                    user_message=enriched_context,
                    response_schema=_TradingDecision,
                )
                decision_data = _TradingDecision(**final_response)

            latency_ms = (time.monotonic() - start) * 1000

            # ── Persist decision ─────────────────────────────────────────────
            agent_decision = AgentDecision(
                agent_id=self.agent_id,
                agent_role=AgentRole.TRADING,
                pair=self.pair,
                decision_type="signal" if decision_data.action != "HOLD" else "hold",
                input_context={"snapshot_time": snapshot.snapshot_time.isoformat()},
                output=decision_data.model_dump(),
                llm_model=self.llm.model_id,
                tokens_used=0,
                latency_ms=latency_ms,
                decided_at=datetime.now(timezone.utc),
            )
            await self.repository.save_agent_decision(agent_decision)

            # ── Publish signal ───────────────────────────────────────────────
            if decision_data.action in ("BUY", "SELL") and decision_data.confidence >= 0.65:
                signal = TradeSignal(
                    pair=self.pair,
                    direction=TradeDirection(decision_data.action),
                    entry_price=Decimal(str(decision_data.entry_price or 0)),
                    stop_loss=Decimal(str(decision_data.stop_loss or 0)),
                    take_profit=Decimal(str(decision_data.take_profit or 0)),
                    confidence=decision_data.confidence,
                    reasoning=decision_data.reasoning,
                    generated_at=datetime.now(timezone.utc),
                    agent_id=self.agent_id,
                )
                await self.publish(
                    AgentMessage(
                        event_type=EventType.SIGNAL_GENERATED,
                        source_agent_id=self.agent_id,
                        payload={
                            "pair": self.pair,
                            "signal_id": str(signal.id),
                            "signal": signal.model_dump(mode="json"),
                        },
                    )
                )
                self._logger.info(
                    "Signal generated",
                    direction=decision_data.action,
                    confidence=decision_data.confidence,
                )
            else:
                self._logger.debug("Holding", pair=self.pair)

        except Exception as exc:
            self._logger.exception("Cycle error", error=str(exc))

        # ── Wait for next cycle ──────────────────────────────────────────────
        elapsed = time.monotonic() - start
        sleep_for = max(0.0, self.cycle_interval - elapsed)
        await asyncio.sleep(sleep_for)

    # ── Analysis request helper ──────────────────────────────────────────────

    async def _request_analysis(self, snapshot_dict: dict) -> AnalysisResult | None:
        correlation_id = str(uuid4())
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[AnalysisResult] = loop.create_future()
        self._pending_analyses[correlation_id] = fut

        await self.publish(
            AgentMessage(
                event_type=EventType.ANALYSIS_REQUESTED,
                source_agent_id=self.agent_id,
                payload={"pair": self.pair, "snapshot": snapshot_dict},
                correlation_id=correlation_id,
            )
        )

        try:
            return await asyncio.wait_for(fut, timeout=self.analysis_timeout)
        except asyncio.TimeoutError:
            self._pending_analyses.pop(correlation_id, None)
            self._logger.warning("Analysis request timed out", pair=self.pair)
            return None


# ── Internal response schema ─────────────────────────────────────────────────

from pydantic import BaseModel


class _TradingDecision(BaseModel):
    action: str  # BUY | SELL | HOLD
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: float = 0.0
    reasoning: str = ""
    needs_deep_analysis: bool = False
    # Optional on-demand candle request. Each entry: {pair, timeframe, count}.
    # Example: [{"pair": "USDJPY", "timeframe": "M5", "count": 50}]
    requested_candles: list[dict] | None = None
