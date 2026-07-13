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
            # Route to a REGISTERED adapter (the agent's own pair). There is no
            # "{BROKER}-ALL___-AD-ADPT" member; passing no instrument means the broker
            # returns every open position across all pairs without filtering.
            close_all_pair = context.pair or pair_arg
            if not close_all_pair or close_all_pair == "ALL___":
                raise ValueError(
                    "Emergency close-all (position_id='0') requires an agent pair context "
                    "to reach a broker adapter."
                )
            positions_resp = await bus_request(
                context=context,
                event_type=EventType.POSITIONS_REQUEST,
                target_id=_broker_adapter_id(context.broker_name, close_all_pair),
                payload={},
                timeout=20.0,
            )
            positions = positions_resp.get("positions", [])
            results: list[dict[str, Any]] = []
            for pos in positions:
                bpid = str(pos.get("broker_position_id", "") or "")
                if not bpid:
                    continue
                result = await self.execute(
                    {"position_id": bpid, "units": close_units, "reasoning": reasoning},
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
                instrument=pair_arg,
                payload={},
                timeout=20.0,
            )
            positions = positions_resp.get("positions", [])
            results: list[dict[str, Any]] = []
            for pos in positions:
                bpid = str(pos.get("broker_position_id", "") or "")
                if not bpid:
                    continue
                result = await self.execute(
                    {"position_id": bpid, "units": close_units, "reasoning": reasoning},
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
            instrument=context.pair,
            payload={"position_id": position_id, "units": close_units},
            timeout=30.0,
        )

        if response.get("error"):
            raise RuntimeError(f"Close position failed: {response['error']}")

        result_status = response.get("status", "UNKNOWN")
        # The broker close result is a serialized TradeResult: the realised close
        # fill price is `fill_price` and the broker id is `broker_order_id`
        # (there is no `close_price` / `order_id` key).
        close_price = response.get("fill_price")
        pnl = response.get("pnl")
        broker_order_id = response.get("broker_order_id")
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
                            "close_price": close_price,
                            "pnl_account_currency": pnl,
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
            "order_id": broker_order_id,
            "close_price": close_price,
            "pnl": pnl,
            "closed_units": close_units,
            "remaining_units": None,  # broker TradeResult does not report this
            "broker_name": context.broker_name,
            "order_book_entry_id": order_book_entry_id,
        }
