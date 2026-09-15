"""Trigger-aware staleness: did an agent fail to act on something it should have?

Deliberately not a fixed "idle for N minutes" rule. Agents driven by rare
business events (the examiner runs only on position_closed) are idle for hours
by design, and a badge that cries wolf all day gets ignored — which is exactly
when it would have mattered.

An agent logs a skip for every deliberate pass (AnyCandle divider, llm busy,
outside session, paused), and that clears its pending entry. So anything still
pending was never processed at all — no divider arithmetic needed, and no
reason to wait for a second occurrence before saying so.

Pure functions here; the API renders them into the dashboard and
``stale_watch_loop`` turns them into bus events for notification rules.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

# Triggers a human fires by hand — never a sign the agent is stuck.
MANUAL_AGENT_TRIGGERS = {"agent_query", "prompt_updated"}
# How long a delivered trigger may sit unanswered before it counts as missed.
# A cycle announces itself (AGENT_INPUT_BUILT) within seconds, so this only has
# to cover dispatch and queueing, not the cycle's runtime (measured up to ~65s) —
# a running cycle has already cleared the pending entry.
STALE_GRACE_SECONDS = 60


def compute_agent_stale(
    cfg: dict[str, Any],
    now_utc: datetime,
    last_active: datetime | None,
    pending_triggers: dict[str, tuple[int, datetime]],
) -> tuple[bool, str | None]:
    """Return (is_stale, reason) for one agent."""
    timer_cfg = cfg.get("timer") if isinstance(cfg.get("timer"), dict) else {}
    if timer_cfg and bool(timer_cfg.get("enabled", False)):
        interval = max(int(timer_cfg.get("interval_seconds", 300) or 300), 1)
        if last_active is None:
            return False, None  # never ran yet — startup, not a stall
        idle = (now_utc - last_active).total_seconds()
        if idle - interval > STALE_GRACE_SECONDS:
            return True, f"Timer every {interval}s, but no cycle started for {int(idle)}s"
        return False, None

    configured = {str(t) for t in (cfg.get("event_triggers") or [])} - MANUAL_AGENT_TRIGGERS
    if not configured:
        return False, None

    for event_type, (count, last_seen) in (pending_triggers or {}).items():
        if event_type not in configured:
            continue  # a response to the agent's own request, not a trigger
        waited = (now_utc - last_seen).total_seconds()
        if waited > STALE_GRACE_SECONDS:
            return True, (
                f"{count}x '{event_type}' delivered, but neither processed "
                f"nor skipped — no reaction for {int(waited)}s"
            )
    return False, None


async def stale_watch_loop(
    bus: Any,
    monitoring_bus: Any,
    system_config: dict[str, Any],
    interval_seconds: int = 60,
) -> None:
    """Publish agent_stale events so staleness can drive notification rules.

    The dashboard computes this on demand, which only helps someone who is
    looking. Publishing it makes it durable and actionable — the point of the
    2026-09-14 incident was that nobody was looking for three days.

    Reports an agent once per stall; a fresh event is only sent after it
    recovered, so a permanently stuck agent does not emit every minute.
    """
    reported: set[str] = set()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            agents_cfg = system_config.get("agents", {}) or {}
            now = datetime.now(UTC)
            for agent_id, cfg in agents_cfg.items():
                if not isinstance(cfg, dict) or not cfg.get("enable", True):
                    continue
                stale, reason = compute_agent_stale(
                    cfg,
                    now,
                    monitoring_bus.agent_last_active(agent_id),
                    monitoring_bus.agent_pending_triggers(agent_id),
                )
                if stale and agent_id not in reported:
                    reported.add(agent_id)
                    await bus.publish(AgentMessage(
                        event_type=EventType.AGENT_STALE,
                        source_agent_id="agent-health",
                        payload={"agent_id": agent_id, "reason": reason or ""},
                    ))
                elif not stale:
                    reported.discard(agent_id)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            # A watchdog that dies silently is worse than none at all.
            _log.error("Stale watch loop error", error=str(exc))
