"""Tool: get_order_trace — resolve an order id to its causal event chain.

An order's open and close are causally UNRELATED event trees, not one continuous
chain: the decision that opened it and whatever later triggered its close (a
fresh m5_candle_trigger -> AA/EC cycle) start from two different root events.
`read_trace()` only walks ancestors/descendants of one event, so it can never
bridge open -> close by itself. This tool resolves and traces BOTH sides
independently:

- Open side: same heuristic the Orderbook UI's trace viewer already uses
  client-side (Orderbook.tsx's OrderTraceViewer) — exact correlation match,
  falling back to scanning order_request/order_placed events for a
  payload.entry_id match.
- Close side: close_position never publishes an event carrying this order's
  internal id (only the broker's own position_id), so it's matched via
  position_close_request events by payload.position_id == broker_order_id.
  The event's source_agent is whichever agent/EC actually issued the close.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetOrderTraceTool(BaseTool):
    name = "get_order_trace"
    description = (
        "Resolve an order id to its causal event history on BOTH sides: 'open_trace' (the "
        "decision that opened it and everything in that causal chain) and, if closed, "
        "'close_trace' + 'closed_by_agent' (the event chain and the exact agent/EventComposer "
        "that issued the close — trailing-stop, risk-guard, relay, or an AA itself). Use this "
        "when close_reasoning alone doesn't explain what happened, or to find out WHICH "
        "agent/EC to inspect next with get_agent_config/get_ec_config/get_ec_runs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order book entry id (UUID)."},
        },
        "required": ["order_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        order_id = str(arguments.get("order_id", "")).strip()
        if not order_id:
            return {"error": "Argument 'order_id' is required."}

        from openforexai.messaging.event_log import read_events, read_trace

        result: dict[str, Any] = {}

        # ── Open side ────────────────────────────────────────────────────────
        open_matches = read_events(correlation=order_id, limit=1)
        open_event_id = open_matches[0]["id"] if open_matches else None
        if open_event_id is None:
            candidates = (
                read_events(event_type="order_request", limit=200)
                + read_events(event_type="order_placed", limit=200)
            )
            match = next(
                (
                    e for e in candidates
                    if e.get("payload", {}).get("entry_id") == order_id or e.get("correlation") == order_id
                ),
                None,
            )
            open_event_id = match["id"] if match else None
        if open_event_id is not None:
            result["open_trace"] = read_trace(open_event_id)

        # ── Close side ───────────────────────────────────────────────────────
        entry = await repo_request(context, "get_order_book_entry", {"entry_id": order_id})
        broker_order_id = (entry or {}).get("broker_order_id")
        if broker_order_id:
            close_candidates = read_events(event_type="position_close_request", limit=200)
            close_event = next(
                (
                    e for e in close_candidates
                    if str(e.get("payload", {}).get("position_id")) == str(broker_order_id)
                ),
                None,
            )
            if close_event is not None:
                result["closed_by_agent"] = close_event.get("source_agent")
                result["close_trace"] = read_trace(close_event["id"])

        if not result:
            return {
                "error": f"No event trace found for order {order_id!r} — it may predate event "
                         "logging, or wasn't created/closed via the event bus.",
            }
        return result
