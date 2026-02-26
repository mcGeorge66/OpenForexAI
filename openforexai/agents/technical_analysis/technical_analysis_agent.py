from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from openforexai.agents.base import BaseAgent
from openforexai.agents.technical_analysis.prompt_templates import get_system_prompt
from openforexai.data.container import DataContainer
from openforexai.data.indicator_tools import IndicatorToolset
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

# How many candles to show per TF in the Phase-1 context
_TA_CONTEXT_CANDLES: dict[str, int] = {
    "M5":  30,
    "M15": 20,
    "M30": 10,
    "H1":  10,
    "H4":   5,
}

# Maps timeframe key → MarketSnapshot dict key
_SNAPSHOT_KEY: dict[str, str] = {
    "M5":  "candles_m5",
    "M15": "candles_m15",
    "M30": "candles_m30",
    "H1":  "candles_h1",
    "H4":  "candles_h4",
    "D1":  "candles_d1",
}


class TechnicalAnalysisAgent(BaseAgent):
    """Singleton reactive agent for deep technical analysis.

    Does NOT run on a timer.  It subscribes exclusively to
    ``ANALYSIS_REQUESTED`` events and responds with ``ANALYSIS_RESULT``
    carrying the same ``correlation_id``.

    Analysis uses a two-phase LLM call:

      Phase 1 — LLM receives candle data and declares which indicators it
                 needs, as ``{indicator, period, timeframe, pair}`` triples.
                 Example: ``{"indicator": "ATR", "period": 14,
                              "timeframe": "M15", "pair": "USDJPY"}``

      Phase 2 — Agent computes those indicators via the shared
                 IndicatorToolset (same tool used by every other agent)
                 and feeds results back.  LLM returns the final analysis.
    """

    def __init__(
        self,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        data_container: DataContainer,
        max_concurrent_requests: int = 3,
    ) -> None:
        super().__init__(
            agent_id="technical_analysis",
            llm=llm,
            repository=repository,
            bus=bus,
        )
        self.indicators = IndicatorToolset(data_container)
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def run_cycle(self) -> None:
        """No-op: purely reactive."""
        await asyncio.sleep(60)

    # ── Event handler ────────────────────────────────────────────────────────

    async def on_analysis_requested(self, message: AgentMessage) -> None:
        async with self._semaphore:
            await self._process_request(message)

    async def _process_request(self, message: AgentMessage) -> None:
        start = time.monotonic()
        pair = message.payload.get("pair", "UNKNOWN")
        snapshot_dict = message.payload.get("snapshot", {})
        correlation_id = message.correlation_id or ""

        self._logger.info("Analysis requested", pair=pair, correlation_id=correlation_id)

        try:
            # ── Phase 1: LLM declares which indicators it needs ───────────────
            phase1_context = self._build_phase1_context(pair, snapshot_dict)
            raw1 = await self.llm.complete_structured(
                system_prompt=get_system_prompt(pair),
                user_message=phase1_context,
                response_schema=_IndicatorRequest,
            )
            req = _IndicatorRequest(**raw1)

            # ── Compute requested indicators via shared IndicatorToolset ──────
            computed: dict[str, str] = {}
            for item in req.indicators_needed:
                indicator = item.get("indicator", "")
                period    = int(item.get("period", 14))
                timeframe = item.get("timeframe", "H1").upper()
                req_pair  = item.get("pair", pair).upper()
                history   = int(item.get("history", 1))

                base_label = f"{indicator.upper()}({period},{timeframe},{req_pair})"
                label = f"{base_label}[hist={history}]" if history > 1 else base_label
                try:
                    result = self.indicators.calculate(
                        indicator, period, timeframe, req_pair, history=history
                    )
                    if result is None:
                        computed[label] = "N/A (not enough data)"
                    elif isinstance(result, list):
                        # history > 1: series of values
                        if result and isinstance(result[0], dict):
                            # BB series — expand each snapshot
                            for i, entry in enumerate(result, 1):
                                for k, v in entry.items():
                                    computed[f"BB_{k}({period},{timeframe},{req_pair})[{i}]"] = f"{v:.6f}"
                        else:
                            formatted = ", ".join(f"{v:.6f}" for v in result)
                            computed[label] = f"[{formatted}]"
                    elif isinstance(result, dict):
                        # BB single snapshot — expand into separate entries
                        for k, v in result.items():
                            computed[f"BB_{k}({period},{timeframe},{req_pair})"] = f"{v:.6f}"
                    else:
                        computed[label] = f"{result:.6f}"
                except ValueError as exc:
                    computed[label] = f"ERROR: {exc}"

            # ── Phase 2: final analysis with computed values ──────────────────
            phase2_context = self._build_phase2_context(
                pair, req.preliminary_observations, computed
            )
            raw2 = await self.llm.complete_structured(
                system_prompt=get_system_prompt(pair),
                user_message=phase2_context,
                response_schema=_AnalysisLLMOutput,
            )
            output = _AnalysisLLMOutput(**raw2)

            result = AnalysisResult(
                pair=pair,
                correlation_id=correlation_id,
                signal=SignalDirection(output.signal),
                confidence=output.confidence,
                reasoning=output.reasoning,
                timeframe_signals=output.timeframe_signals,
                chart_patterns=[ChartPattern(**p) for p in (output.chart_patterns or [])],
                support_resistance=[
                    SupportResistanceLevel(**s) for s in (output.support_resistance or [])
                ],
                trend_assessments=[
                    TrendAssessment(**t) for t in (output.trend_assessments or [])
                ],
            )

            latency_ms = (time.monotonic() - start) * 1000

            await self.repository.save_agent_decision(
                AgentDecision(
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
            )

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

    # ── Context builders ─────────────────────────────────────────────────────

    def _build_phase1_context(self, pair: str, snapshot: dict) -> str:
        available = ", ".join(self.indicators.available_indicators())
        lines = [
            f"Pair: {pair}",
            "",
            "PHASE 1 — Declare the indicators you need to complete your analysis.",
            "For each indicator specify: indicator, period, timeframe, pair.",
            "Optionally add 'history' (int) to request the last N values as a series",
            "(oldest → newest) — useful for spotting trends or divergences.",
            f"Available indicators: {available}",
            "Available timeframes: M5, M15, M30, H1, H4, D1",
            "",
        ]

        # Raw candle data per timeframe
        for tf, count in _TA_CONTEXT_CANDLES.items():
            key = _SNAPSHOT_KEY.get(tf, "")
            candles = snapshot.get(key, [])
            if not candles:
                continue
            lines += ["", f"{tf} candles (last {count}):"]
            for c in candles[-count:]:
                lines.append(
                    f"  {c.get('timestamp', '')}  "
                    f"O={c.get('open')}  H={c.get('high')}  "
                    f"L={c.get('low')}  C={c.get('close')}"
                )

        return "\n".join(lines)

    def _build_phase2_context(
        self,
        pair: str,
        preliminary_observations: str,
        computed: dict[str, str],
    ) -> str:
        lines = [
            f"Pair: {pair}",
            "",
            "PHASE 2 — Produce the final analysis.",
            "",
            f"Preliminary observations:\n{preliminary_observations}",
            "",
            "Computed indicators:",
        ]
        for name, value in computed.items():
            lines.append(f"  {name}: {value}")
        return "\n".join(lines)


# ── Internal response schemas ─────────────────────────────────────────────────

from pydantic import BaseModel


class _IndicatorRequest(BaseModel):
    """Phase-1 output: which indicators to compute."""

    preliminary_observations: str = ""
    indicators_needed: list[dict] = []
    # Each entry: {
    #   "indicator": "ATR", "period": 14, "timeframe": "M15",
    #   "pair": "USDJPY", "history": 5
    # }
    # `pair`    is optional — defaults to the current pair when omitted.
    # `history` is optional — defaults to 1 (single latest value).


class _AnalysisLLMOutput(BaseModel):
    """Phase-2 output: final technical analysis."""

    signal: str
    confidence: float
    reasoning: str
    timeframe_signals: dict[str, str] = {}
    chart_patterns: list[dict] = []
    support_resistance: list[dict] = []
    trend_assessments: list[dict] = []
