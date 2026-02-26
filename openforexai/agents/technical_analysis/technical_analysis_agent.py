from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from openforexai.agents.base import BaseAgent
from openforexai.agents.technical_analysis.prompt_templates import get_system_prompt
from openforexai.data.container import DataContainer
from openforexai.data.indicators import atr, bollinger_bands, ema, rsi, sma
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

# Mapping snapshot dict keys → candle lists per timeframe
_SNAPSHOT_TF_KEY: dict[str, str] = {
    "M5": "candles_m5",
    "M15": "candles_m15",
    "M30": "candles_m30",
    "H1": "candles_h1",
    "H4": "candles_h4",
    "D1": "candles_d1",
}

# How many candles to include per TF in the TA context
_TA_CONTEXT_CANDLES: dict[str, int] = {
    "M5": 30,
    "M15": 20,
    "M30": 10,
    "H1": 10,
    "H4": 5,
}


class TechnicalAnalysisAgent(BaseAgent):
    """Singleton reactive agent for deep technical analysis.

    Does NOT run on a timer.  It subscribes exclusively to
    ``ANALYSIS_REQUESTED`` events and responds with ``ANALYSIS_RESULT``
    carrying the same ``correlation_id``.

    Analysis uses a two-phase LLM call:
      Phase 1 — LLM declares which indicators it needs, expressed as
                 ``{indicator, period, timeframe}`` triples, e.g.
                 ``{"indicator": "MA", "period": 20, "timeframe": "M15"}``.
      Phase 2 — Agent computes those indicators from the snapshot candles
                 and feeds the results back.  LLM gives the final analysis.
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
        self._data_container = data_container
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
            # ── Phase 1: ask which indicators are needed ─────────────────────
            phase1_context = self._build_phase1_context(pair, snapshot_dict)
            raw_phase1 = await self.llm.complete_structured(
                system_prompt=get_system_prompt(pair),
                user_message=phase1_context,
                response_schema=_IndicatorRequest,
            )
            indicator_request = _IndicatorRequest(**raw_phase1)

            # ── Compute requested indicators from snapshot candles ────────────
            computed = self._compute_indicators(
                pair, indicator_request.indicators_needed, snapshot_dict
            )

            # ── Phase 2: full analysis with computed indicator values ─────────
            phase2_context = self._build_phase2_context(
                pair, snapshot_dict, indicator_request.preliminary_observations, computed
            )
            raw_phase2 = await self.llm.complete_structured(
                system_prompt=get_system_prompt(pair),
                user_message=phase2_context,
                response_schema=_AnalysisLLMOutput,
            )
            output = _AnalysisLLMOutput(**raw_phase2)

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
        """Build the Phase-1 context: candle data + pre-computed indicators."""
        lines = [
            f"Pair: {pair}",
            "",
            "PHASE 1 — Indicator selection",
            "List the indicators you need to compute (name + period + timeframe).",
            "Available indicators: MA, EMA, RSI, ATR, BB",
            "Available timeframes: M5, M15, M30, H1, H4",
            "",
        ]

        # Pre-computed indicators from the snapshot
        indicators = snapshot.get("indicators", {})
        if indicators:
            lines.append("Pre-computed indicators (H1 basis):")
            for k, v in indicators.items():
                lines.append(f"  {k}: {v}")

        # Candle data per configured TF
        for tf, count in _TA_CONTEXT_CANDLES.items():
            key = _SNAPSHOT_TF_KEY.get(tf, "")
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
        snapshot: dict,
        preliminary_observations: str,
        computed: dict[str, float | None],
    ) -> str:
        """Build the Phase-2 context: Phase-1 observations + computed indicator values."""
        lines = [
            f"Pair: {pair}",
            "",
            "PHASE 2 — Final analysis",
            "",
            f"Preliminary observations:\n{preliminary_observations}",
            "",
            "Computed indicators:",
        ]
        for name, value in computed.items():
            val_str = f"{value:.6f}" if value is not None else "N/A"
            lines.append(f"  {name}: {val_str}")

        return "\n".join(lines)

    # ── Indicator computation ─────────────────────────────────────────────────

    def _compute_indicators(
        self,
        pair: str,
        requests: list[dict[str, Any]],
        snapshot: dict,
    ) -> dict[str, float | None]:
        """Compute each requested indicator from snapshot candle data.

        Each request dict must have keys: ``indicator``, ``period``, ``timeframe``.
        Optionally ``pair`` (defaults to the current pair).
        """
        from openforexai.models.market import Candle as CandleModel

        results: dict[str, float | None] = {}

        for req in requests:
            indicator = req.get("indicator", "MA").upper()
            period = int(req.get("period", 14))
            timeframe = req.get("timeframe", "H1").upper()
            req_pair = req.get("pair", pair).upper()

            label = f"{indicator}({period},{timeframe},{req_pair})"

            # Fetch candles: from snapshot (same pair) or from DataContainer (other pairs)
            if req_pair == pair.upper():
                raw_key = _SNAPSHOT_TF_KEY.get(timeframe, "")
                raw_list = snapshot.get(raw_key, [])
                # Snapshot candles are dicts; convert to Candle models
                candles = [
                    CandleModel(**c) if isinstance(c, dict) else c for c in raw_list
                ]
            else:
                candles = self._data_container.get_candles(req_pair, timeframe)

            if not candles:
                results[label] = None
                continue

            value: float | None = None
            if indicator in ("MA", "SMA"):
                value = sma(candles, period)
            elif indicator == "EMA":
                value = ema(candles, period)
            elif indicator == "RSI":
                value = rsi(candles, period)
            elif indicator == "ATR":
                value = atr(candles, period)
            elif indicator == "BB":
                bb = bollinger_bands(candles, period)
                if bb:
                    upper, middle, lower = bb
                    results[f"BB_upper({period},{timeframe},{req_pair})"] = upper
                    results[f"BB_middle({period},{timeframe},{req_pair})"] = middle
                    results[f"BB_lower({period},{timeframe},{req_pair})"] = lower
                else:
                    results[f"BB_upper({period},{timeframe},{req_pair})"] = None
                    results[f"BB_middle({period},{timeframe},{req_pair})"] = None
                    results[f"BB_lower({period},{timeframe},{req_pair})"] = None
                continue
            else:
                results[label] = None
                continue

            results[label] = value

        return results


# ── Internal response schemas ─────────────────────────────────────────────────

from pydantic import BaseModel


class _IndicatorRequest(BaseModel):
    """Phase-1 LLM output: which indicators to compute."""

    preliminary_observations: str = ""
    indicators_needed: list[dict] = []
    # Example entry:
    # {"indicator": "MA", "period": 20, "timeframe": "M15", "pair": "USDJPY"}
    # Supported indicators: MA | EMA | RSI | ATR | BB
    # pair is optional — defaults to the current pair


class _AnalysisLLMOutput(BaseModel):
    """Phase-2 LLM output: final technical analysis result."""

    signal: str
    confidence: float
    reasoning: str
    timeframe_signals: dict[str, str] = {}
    chart_patterns: list[dict] = []
    support_resistance: list[dict] = []
    trend_assessments: list[dict] = []
