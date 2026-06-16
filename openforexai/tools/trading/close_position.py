"""Tool: close_position — close an open position via broker adapter bus request."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openforexai.models.messaging import EventType
from openforexai.models.trade import CloseReason, OrderStatus
from openforexai.tools.base import BaseTool, ToolContext, bus_request, repo_request


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class ClosePositionTool(BaseTool):
    name = "close_position"
    description = (
        "Close an open position. Provide EITHER position_id (specific position) "
        "OR pair (closes all open positions for that pair). "
        "Special: position_id='0' closes ALL positions across ALL pairs (emergency). "
        "Use get_open_positions to retrieve position IDs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Currency pair, e.g. EURUSD. If given without position_id, closes ALL open positions for this pair."},
            "position_id": {"type": "string", "description": "Broker-assigned position ID to close. If omitted, pair is required."},
            "units": {"type": "integer", "description": "Optional partial close size in broker units.", "exclusiveMinimum": 0},
            "lots": {"type": "number", "description": "Optional partial close size in lots.", "exclusiveMinimum": 0},
            "reasoning": {"type": "string", "description": "Brief explanation (logged)."},
        },
        "required": [],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")

        position_id = arguments.get("position_id")
        pair_arg = arguments.get("pair") or context.pair
        reasoning = str(arguments.get("reasoning", "")).strip() or None
        lots_arg = arguments.get("lots")
        units_arg = arguments.get("units")
        close_units: int | None = None
        if lots_arg is not None and str(lots_arg) != "":
            lots = float(lots_arg)
            if lots <= 0:
                raise ValueError("lots must be > 0")
            close_units = int(lots * 100_000)
        elif units_arg is not None and str(units_arg) != "":
            close_units = int(units_arg)
            if close_units <= 0:
                raise ValueError("units must be > 0")

        # position_id="0" → emergency: close ALL positions across ALL pairs (no pair filter).
        if str(position_id or "") == "0":
            positions_resp = await bus_request(
                context=context,
                event_type=EventType.POSITIONS_REQUEST,
                target_id=_broker_adapter_id(context.broker_name, "ALL___"),
                payload={},
                timeout=20.0,
            )
            positions = positions_resp.get("positions", [])
            results: list[dict[str, Any]] = []
            for pos in positions:
                result = await self.execute(
                    {"position_id": pos.get("position_id", ""), "units": close_units, "reasoning": reasoning},
                    context,
                )
                results.append(result)
            return {
                "success": all(bool(item.get("success")) for item in results),
                "status": "BATCH_ALL",
                "closed_count": len(results),
                "results": results,
            }

        # Either/or: close by pair (all positions for that pair) or by specific position_id.
        if not position_id:
            if not pair_arg or pair_arg == "ALL___":
                raise ValueError("Either position_id or pair must be provided.")
            # Close all positions for the given pair
            positions_resp = await bus_request(
                context=context,
                event_type=EventType.POSITIONS_REQUEST,
                target_id=_broker_adapter_id(context.broker_name, pair_arg),
                payload={"pair": pair_arg},
                timeout=20.0,
            )
            positions = positions_resp.get("positions", [])
            results: list[dict[str, Any]] = []
            for pos in positions:
                result = await self.execute(
                    {"position_id": pos.get("position_id", ""), "units": close_units, "reasoning": reasoning},
                    context,
                )
                results.append(result)
            return {
                "success": all(bool(item.get("success")) for item in results),
                "status": "BATCH",
                "closed_count": len(results),
                "pair": pair_arg,
                "results": results,
            }

        pair = pair_arg or "ALL___"
        response = await bus_request(
            context=context,
            event_type=EventType.POSITION_CLOSE_REQUEST,
            target_id=_broker_adapter_id(context.broker_name, pair),
            payload={"position_id": position_id, "pair": context.pair, "units": close_units},
            timeout=30.0,
        )

        if response.get("error"):
            raise RuntimeError(f"Close position failed: {response['error']}")

        result_status = response.get("status", "UNKNOWN")
        order_book_entry_id: str | None = None

        # Update order book entry via RepositoryService
        if context.broker_name:
            local_open = await repo_request(
                context, "get_open_order_book_entries",
                {"broker_name": context.broker_name, "pair": context.pair},
            ) or []
            matching_entry = next(
                (e for e in local_open if e.get("broker_order_id") == position_id),
                None,
            )
            if matching_entry is not None:
                order_book_entry_id = str(matching_entry.get("id"))
                now = datetime.now(UTC)
                if result_status == "CLOSED":
                    await repo_request(context, "update_order_book_entry", {
                        "entry_id": order_book_entry_id,
                        "updates": {
                            "status": OrderStatus.CLOSED.value,
                            "close_reason": CloseReason.AGENT_CLOSED.value,
                            "close_reasoning": reasoning,
                            "close_price": response.get("close_price"),
                            "pnl_account_currency": response.get("pnl"),
                            "close_requested_at": now.isoformat(),
                            "closed_at": now.isoformat(),
                            "last_broker_sync": now.isoformat(),
                            "sync_confirmed": True,
                            "confirmed_by_broker": True,
                        },
                    })
                elif result_status == "OPEN" and close_units is not None:
                    existing_units = int(matching_entry.get("units", 0))
                    remaining = max(existing_units - close_units, 0)
                    await repo_request(context, "update_order_book_entry", {
                        "entry_id": order_book_entry_id,
                        "updates": {
                            "units": remaining,
                            "close_requested_at": now.isoformat(),
                            "last_broker_sync": now.isoformat(),
                            "sync_confirmed": False,
                            "confirmed_by_broker": False,
                        },
                    })

        return {
            "success": result_status != "REJECTED",
            "position_id": position_id,
            "status": result_status,
            "order_id": response.get("order_id"),
            "close_price": response.get("close_price"),
            "pnl": response.get("pnl"),
            "closed_units": close_units,
            "remaining_units": response.get("remaining_units"),
            "broker_name": context.broker_name,
            "order_book_entry_id": order_book_entry_id,
        }
