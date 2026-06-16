"""Port: AbstractDataContainer — unified, technology-agnostic data store.

This is the single interface the entire system uses to access persistent data.
All concrete storage backends (SQLite, PostgreSQL, MariaDB, …) must implement
this class.  The interface is intentionally wide so the system never needs to
import a concrete adapter — only this port.

Design principles
-----------------
* **Zero truncation** — all data is stored in full, no field length limits.
* **Restart-safe** — every write is committed immediately; a power outage must
  not cause data loss.
* **Agent memory** — every LLM conversation, every agent decision (including the
  full reasoning text), and aggregated performance metrics are persisted so that
  agents can resume meaningfully after a restart.
* **Technology-agnostic** — the concrete backend (SQLite vs PostgreSQL vs …) is
  resolved by the PluginRegistry at bootstrap time.

Extends AbstractRepository (backward compat)
---------------------------------------------
``AbstractDataContainer`` is a **superset** of the old ``AbstractRepository``.
All existing code that type-hints ``AbstractRepository`` continues to work because
every ``AbstractDataContainer`` implementation IS an ``AbstractRepository``.
"""
from __future__ import annotations

from datetime import datetime

from openforexai.ports.database import AbstractRepository


class AbstractDataContainer(AbstractRepository):
    """Unified persistent data store — extends AbstractRepository with agent memory.

    Implementations must be registered in PluginRegistry:

        PluginRegistry.register_data_container("sqlite", SQLiteDataContainer)

    Bootstrap selects the implementation via system.json5 ``database.backend``.
    """

    # ── Agent decision memory ──────────────────────────────────────────────────

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
        """Persist a full agent decision including the complete LLM reasoning text.

        Returns the new record UUID as a string.

        Parameters
        ----------
        agent_id:        Canonical agent ID (e.g. ``OAPR1-EURUSD-AA-ANLYS``)
        pair:            Currency pair or None for broker-wide decisions
        decision_type:   One of: ``no_action`` | ``signal_buy`` | ``signal_sell``
                         | ``close_position`` | ``analysis`` | ``other``
        reasoning:       Full LLM response text — NOT truncated
        llm_model:       Model identifier (e.g. ``claude-opus-4-5``)
        input_tokens:    Token count for the prompt
        output_tokens:   Token count for the response
        market_snapshot: Complete market context dict at decision time
        prompt_version:  Prompt candidate version if applicable
        latency_ms:      LLM call latency in milliseconds
        decided_at:      UTC timestamp; defaults to now if omitted
        """
        ...

    async def get_recent_agent_decisions(
        self,
        agent_id: str,
        limit: int = 20,
        pair: str | None = None,
    ) -> list[dict]:
        """Return recent decisions for *agent_id*, newest first.

        Each dict contains all persisted fields including ``reasoning``,
        ``market_snapshot`` (as dict), and ``decided_at`` (ISO string).
        ``pair`` filters by currency pair when provided.
        """
        ...

    # ── LLM conversation memory ────────────────────────────────────────────────

    async def save_llm_conversation(
        self,
        agent_id: str,
        session_id: str,
        messages: list[dict],
        turn_count: int,
        started_at: datetime | None = None,
    ) -> None:
        """Persist the complete LLM messages list for one trading cycle.

        ``messages`` is the full OpenAI/Anthropic-format list — no truncation.
        If a record for (agent_id, session_id) already exists it is updated
        (upsert semantics).

        Parameters
        ----------
        agent_id:    Canonical agent ID
        session_id:  UUID string — one per trading cycle / run_cycle() call
        messages:    Complete conversation history (list of dicts)
        turn_count:  Number of LLM API turns completed
        started_at:  When this cycle started; defaults to now if omitted
        """
        ...

    async def get_last_llm_conversation(
        self,
        agent_id: str,
    ) -> list[dict] | None:
        """Return the messages list from the most recent session for *agent_id*.

        Returns ``None`` if no prior conversation exists (e.g. first run).
        This allows an agent to resume with context from the previous cycle
        after a system restart.
        """
        ...

    # ── Performance metrics ────────────────────────────────────────────────────

    async def save_performance_snapshot(
        self,
        agent_id: str,
        pair: str,
        total_decisions: int,
        trades_opened: int,
        trades_closed: int,
        win_count: int,
        loss_count: int,
        total_pnl: float,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """Persist a performance metrics snapshot for *agent_id*.

        Snapshots are append-only; each call creates a new row.
        Use ``get_performance_summary()`` to read aggregated history.
        """
        ...

    async def get_performance_summary(
        self,
        agent_id: str,
        pair: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return performance snapshots for *agent_id*, newest first.

        Optionally filter by *pair* and/or *since* (UTC datetime).
        Each dict contains all metric fields plus ``period_start``,
        ``period_end``, and ``recorded_at`` as ISO strings.
        """
        ...

