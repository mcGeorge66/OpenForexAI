"""Tool: seed_demo_order — create-and-close a synthetic order for demos/testing.

DEMO/TEST ONLY. Never grant this via any agent's allowed_tools — it exists so a
human (via /tools/execute, bypassing the per-agent allow-list, exactly like any
other manual Tool Executor call) can exercise the real close-trigger pipeline
(RepositoryService.update_order_book_entry -> POSITION_CLOSED -> an Examiner
agent's event_triggers) without touching a real broker or placing a real order.
Everything here goes through the same repo_request path a genuine trade uses,
so the resulting POSITION_CLOSED event is indistinguishable from a real one.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class SeedDemoOrderTool(BaseTool):
    name = "seed_demo_order"
    description = (
        "DEMO/TEST ONLY: creates a synthetic order-book entry and immediately closes it, "
        "triggering the real POSITION_CLOSED event (same path a genuine trade close uses). "
        "Never touches a broker. Intended for manual invocation via /tools/execute, not for "
        "any agent's allowed_tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent id to attribute the (fabricated) opening decision to."},
            "pair": {"type": "string"},
            "direction": {"type": "string", "enum": ["BUY", "SELL"], "default": "BUY"},
            "entry_price": {"type": "number", "default": 1.1000},
            "close_price": {"type": "number", "default": 1.1050},
            "entry_reasoning": {"type": "string"},
        },
        "required": ["agent_id", "pair"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")

        agent_id = str(arguments["agent_id"])
        pair = str(arguments["pair"]).upper()
        direction = str(arguments.get("direction", "BUY")).upper()
        entry_price = Decimal(str(arguments.get("entry_price", "1.1000")))
        close_price = Decimal(str(arguments.get("close_price", "1.1050")))
        entry_reasoning = str(arguments.get(
            "entry_reasoning",
            f"Demo entry: {direction} {pair} on a clean H1 breakout with M15 confirmation.",
        ))

        now = datetime.now(UTC)
        entry_id = str(uuid4())

        entry_payload = {
            "id": entry_id,
            "broker_name": context.broker_name,
            "pair": pair,
            "direction": direction,
            "order_type": "MARKET",
            "units": 1000,
            "requested_price": str(entry_price),
            "fill_price": str(entry_price),
            "status": "OPEN",
            "agent_id": agent_id,
            "entry_reasoning": entry_reasoning,
            "signal_confidence": 0.78,
            "market_context_snapshot": {"demo": True, "note": "Synthetic data seeded by seed_demo_order."},
            "requested_at": now.isoformat(),
            "opened_at": now.isoformat(),
        }
        await repo_request(context, "save_order_book_entry", {"entry": entry_payload})

        direction_won = (direction == "BUY" and close_price > entry_price) or (
            direction == "SELL" and close_price < entry_price
        )
        pnl_pips = abs(close_price - entry_price) * Decimal("10000")
        if not direction_won:
            pnl_pips = -pnl_pips

        await repo_request(context, "update_order_book_entry", {
            "entry_id": entry_id,
            "updates": {
                "status": "CLOSED",
                "close_price": str(close_price),
                "close_reason": "TP_HIT" if direction_won else "SL_HIT",
                "close_reasoning": "Demo close seeded by seed_demo_order for testing the Examiner agent.",
                "pnl_pips": str(pnl_pips),
                "close_requested_at": now.isoformat(),
                "closed_at": now.isoformat(),
            },
        })

        return {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "pair": pair,
            "direction": direction,
            "entry_price": str(entry_price),
            "close_price": str(close_price),
            "pnl_pips": str(pnl_pips),
            "note": "POSITION_CLOSED published — any agent with it in event_triggers should react now.",
        }
