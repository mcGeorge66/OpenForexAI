"""Demo data adapter template.

This demonstrates a practical pattern:
- Extend an existing concrete adapter (SQLiteDataContainer)
- Add custom behavior in selected methods
- Keep compatibility with AbstractDataContainer contract
"""
from __future__ import annotations

from datetime import datetime, timezone

from openforexai.adapters.data.sqlite import SQLiteDataContainer


class DemoDataContainer(SQLiteDataContainer):
    """Example extension of SQLiteDataContainer.

    Use this pattern when you need extra auditing/behavior without rewriting
    the full persistence backend.
    """

    async def initialize(self) -> None:
        await super().initialize()
        # Custom startup hook (example): write a marker row/log/event.
        # Keep it non-blocking and safe.

    async def save_agent_decision_with_reasoning(
        self,
        agent_id: str,
        pair: str | None,
        decision_type: str,
        reasoning: str,
        llm_model: str,
        input_tokens: int,
        output_tokens: int,
        market_snapshot: dict,
        prompt_version: str | None = None,
        latency_ms: float | None = None,
        decided_at: datetime | None = None,
    ) -> str:
        """Override example: append metadata then delegate to base."""
        snapshot = dict(market_snapshot)
        snapshot["demo_data_container_marker"] = "written_by_demo_adapter"
        return await super().save_agent_decision_with_reasoning(
            agent_id=agent_id,
            pair=pair,
            decision_type=decision_type,
            reasoning=reasoning,
            llm_model=llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            market_snapshot=snapshot,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            decided_at=decided_at or datetime.now(timezone.utc),
        )

