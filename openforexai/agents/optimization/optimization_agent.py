from __future__ import annotations

import asyncio
import time

from openforexai.agents.base import BaseAgent
from openforexai.agents.optimization.backtester import backtest_prompt
from openforexai.agents.optimization.pattern_detector import detect_patterns
from openforexai.agents.optimization.prompt_evolver import evolve_prompt
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider


class OptimizationAgent(BaseAgent):
    """Runs on a slow schedule.

    Workflow per cycle:
      1. For each pair: load recent trades.
      2. Detect patterns via PatternDetector.
      3. Evolve a new PromptCandidate via LLM (if enough patterns found).
      4. Backtest candidate against historical trades.
      5. If it outperforms the baseline: mark active, publish PROMPT_UPDATED.
    """

    def __init__(
        self,
        pairs: list[str],
        data_container: DataContainer,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        min_trades_before_run: int = 20,
        optimization_interval_hours: int = 6,
    ) -> None:
        super().__init__(
            agent_id="optimization",
            llm=llm,
            repository=repository,
            bus=bus,
        )
        self.pairs = pairs
        self.data_container = data_container
        self.min_trades = min_trades_before_run
        self.interval_seconds = optimization_interval_hours * 3600

    async def on_position_closed(self, message: AgentMessage) -> None:
        """Accumulate closed trade count; no immediate action."""
        self._logger.debug(
            "Position closed event received", pair=message.payload.get("pair")
        )

    async def run_cycle(self) -> None:
        self._logger.info("Optimization cycle starting")
        for pair in self.pairs:
            try:
                await self._optimize_pair(pair)
            except Exception as exc:
                self._logger.exception("Optimization error", pair=pair, error=str(exc))
        self._logger.info("Optimization cycle complete")
        await asyncio.sleep(self.interval_seconds)

    async def _optimize_pair(self, pair: str) -> None:
        trades = await self.repository.get_trades(pair=pair, limit=200)
        closed = [t for t in trades if t.pnl is not None]

        if len(closed) < self.min_trades:
            self._logger.debug("Not enough trades yet", pair=pair, count=len(closed))
            return

        # ── Detect patterns ────────────────────────────────────────────────
        patterns = detect_patterns(closed)
        for p in patterns:
            await self.repository.save_pattern(p)
        self._logger.info("Patterns detected", pair=pair, count=len(patterns))

        if not patterns:
            return

        # ── Get current best prompt ────────────────────────────────────────
        current_candidate = await self.repository.get_best_prompt(pair)
        current_prompt = current_candidate.system_prompt if current_candidate else ""
        current_version = current_candidate.version if current_candidate else 0

        # Baseline PnL
        baseline_pnl = sum(float(t.pnl or 0) for t in closed)

        # ── Evolve candidate ───────────────────────────────────────────────
        candidate = await evolve_prompt(
            current_prompt=current_prompt,
            patterns=patterns,
            pair=pair,
            llm=self.llm,
            current_version=current_version,
        )
        await self.repository.save_prompt_candidate(candidate)

        # ── Backtest ───────────────────────────────────────────────────────
        result = backtest_prompt(candidate, closed)
        result.vs_baseline_pnl_delta = result.total_pnl - baseline_pnl
        await self.repository.save_backtest_result(result)

        # ── Promote if better ──────────────────────────────────────────────
        if result.vs_baseline_pnl_delta > 0:
            candidate.is_active = True
            await self.repository.save_prompt_candidate(candidate)

            await self.publish(
                AgentMessage(
                    event_type=EventType.PROMPT_UPDATED,
                    source_agent_id=self.agent_id,
                    payload={
                        "pair": pair,
                        "system_prompt": candidate.system_prompt,
                        "version": candidate.version,
                        "delta_pnl": result.vs_baseline_pnl_delta,
                    },
                )
            )
            self._logger.info(
                "New prompt deployed",
                pair=pair,
                version=candidate.version,
                delta_pnl=result.vs_baseline_pnl_delta,
            )
        else:
            self._logger.info(
                "Candidate did not improve, keeping current prompt",
                pair=pair,
                delta_pnl=result.vs_baseline_pnl_delta,
            )
