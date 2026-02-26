from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from openforexai.agents.base import BaseAgent
from openforexai.agents.technical_analysis.prompt_templates import get_system_prompt
from openforexai.messaging.bus import EventBus
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.analysis import (
    AnalysisResult,
    ChartPattern,
    SignalDirection,
    SupportResistanceLevel,
    TrendAssessment,
)
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider


class TechnicalAnalysisAgent(BaseAgent):
    """Singleton reactive agent for deep technical analysis.

    Does NOT run on a timer.  It subscribes exclusively to
    ``ANALYSIS_REQUESTED`` events and responds with ``ANALYSIS_RESULT``
    carrying the same ``correlation_id``.

    Multiple concurrent requests are handled transparently through
    ``asyncio.gather`` inside the EventBus dispatch loop.
    """

    def __init__(
        self,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        max_concurrent_requests: int = 3,
    ) -> None:
        super().__init__(
            agent_id="technical_analysis",
            llm=llm,
            repository=repository,
            bus=bus,
        )
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def run_cycle(self) -> None:
        """No-op: this agent is purely reactive, driven by bus events."""
        await asyncio.sleep(60)

    # ── Event handler ────────────────────────────────────────────────────────

    async def on_analysis_requested(self, message: AgentMessage) -> None:
        """Handle an ``ANALYSIS_REQUESTED`` event from a TradingAgent."""
        async with self._semaphore:
            await self._process_request(message)

    async def _process_request(self, message: AgentMessage) -> None:
        start = time.monotonic()
        pair = message.payload.get("pair", "UNKNOWN")
        snapshot_dict = message.payload.get("snapshot", {})
        correlation_id = message.correlation_id or ""

        self._logger.info("Analysis requested", pair=pair, correlation_id=correlation_id)

        try:
            context = self._build_context(pair, snapshot_dict)
            raw = await self.llm.complete_structured(
                system_prompt=get_system_prompt(pair),
                user_message=context,
                response_schema=_AnalysisLLMOutput,
            )
            output = _AnalysisLLMOutput(**raw)

            result = AnalysisResult(
                pair=pair,
                correlation_id=correlation_id,
                signal=SignalDirection(output.signal),
                confidence=output.confidence,
                reasoning=output.reasoning,
                timeframe_signals=output.timeframe_signals,
                chart_patterns=[
                    ChartPattern(**p) for p in (output.chart_patterns or [])
                ],
                support_resistance=[
                    SupportResistanceLevel(**s) for s in (output.support_resistance or [])
                ],
                trend_assessments=[
                    TrendAssessment(**t) for t in (output.trend_assessments or [])
                ],
            )

            latency_ms = (time.monotonic() - start) * 1000

            # Persist decision
            decision = AgentDecision(
                agent_id=self.agent_id,
                agent_role=AgentRole.TECHNICAL_ANALYSIS,
                pair=pair,
                decision_type="analyze",
                input_context={"pair": pair},
                output=result.model_dump(mode="json"),
                llm_model=self.llm.model_id,
                tokens_used=0,
                latency_ms=latency_ms,
                decided_at=datetime.now(timezone.utc),
            )
            await self.repository.save_agent_decision(decision)

            # Respond on bus with matching correlation_id
            await self.publish(
                AgentMessage(
                    event_type=EventType.ANALYSIS_RESULT,
                    source_agent_id=self.agent_id,
                    target_agent_id=message.source_agent_id,
                    payload=result.model_dump(mode="json"),
                    correlation_id=correlation_id,
                )
            )
            self._logger.info(
                "Analysis complete",
                pair=pair,
                signal=output.signal,
                confidence=output.confidence,
            )

        except Exception as exc:
            self._logger.exception("Analysis failed", pair=pair, error=str(exc))

    def _build_context(self, pair: str, snapshot: dict) -> str:
        lines = [f"Pair: {pair}", ""]
        indicators = snapshot.get("indicators", {})
        if indicators:
            lines.append("Indicators:")
            for k, v in indicators.items():
                lines.append(f"  {k}: {v}")
        candles_h1 = snapshot.get("candles_h1", [])
        if candles_h1:
            lines += ["", "H1 candles (last 10):"]
            for c in candles_h1[-10:]:
                lines.append(f"  {c.get('timestamp','')}  O={c.get('open')} H={c.get('high')} L={c.get('low')} C={c.get('close')}")
        candles_h4 = snapshot.get("candles_h4", [])
        if candles_h4:
            lines += ["", "H4 candles (last 5):"]
            for c in candles_h4[-5:]:
                lines.append(f"  {c.get('timestamp','')}  O={c.get('open')} H={c.get('high')} L={c.get('low')} C={c.get('close')}")
        return "\n".join(lines)


# ── Internal response schema ─────────────────────────────────────────────────

from pydantic import BaseModel


class _AnalysisLLMOutput(BaseModel):
    signal: str
    confidence: float
    reasoning: str
    timeframe_signals: dict[str, str] = {}
    chart_patterns: list[dict] = []
    support_resistance: list[dict] = []
    trend_assessments: list[dict] = []
