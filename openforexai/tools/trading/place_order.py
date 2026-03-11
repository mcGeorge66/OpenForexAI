"""Tool: place_order — submit a trade order to the broker."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class PlaceOrderTool(BaseTool):
    name = "place_order"
    description = (
        "Submit a trade order for the current currency pair. "
        "Supported order types: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP. "
        "Always specify stop_loss and take_profit for risk management. "
        "Always specify stop_loss and take_profit for risk management."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "description": "Trade direction: 'buy' | 'sell'",
                "enum": ["buy", "sell"],
            },
            "order_type": {
                "type": "string",
                "description": "Order type: MARKET | LIMIT | STOP | STOP_LIMIT | TRAILING_STOP",
                "enum": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "TRAILING_STOP"],
            },
            "units": {
                "type": "integer",
                "description": (
                    "Position size in broker units (positive integer, not lots). "
                    "Provide EITHER units OR risk_pct (prefer one, not both). "
                    "If both are provided, units is used directly."
                ),
                "exclusiveMinimum": 0,
            },
            "entry_price": {
                "type": "number",
                "description": "Reference entry price. Optional for MARKET, recommended for pending orders.",
            },
            "risk_pct": {
                "type": "number",
                "description": (
                    "Risk-based sizing in percent of account equity (0.1–5.0). "
                    "Provide EITHER risk_pct OR units. "
                    "Used only to compute units before order placement."
                ),
                "minimum": 0.1,
                "maximum": 5.0,
            },
            "stop_loss": {
                "type": "number",
                "description": "Stop-loss price level. Strongly recommended.",
            },
            "take_profit": {
                "type": "number",
                "description": "Take-profit price level. Strongly recommended.",
            },
            "limit_price": {
                "type": "number",
                "description": "Limit price for LIMIT and STOP_LIMIT orders.",
            },
            "stop_price": {
                "type": "number",
                "description": "Stop trigger price for STOP and STOP_LIMIT orders.",
            },
            "trailing_stop_distance": {
                "type": "number",
                "description": "Trailing stop distance in pips for TRAILING_STOP orders.",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "Optional documentation text for logs/analysis. "
                    "No direct effect on broker execution."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Optional documentation score 0.0–1.0 for audit/analysis. "
                    "No direct effect on broker execution."
                ),
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["direction", "order_type"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.models.trade import OrderType, TradeDirection, TradeOrder, TradeSignal

        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        direction_raw = str(arguments["direction"]).strip().lower()
        if direction_raw not in {"buy", "sell"}:
            raise ValueError("direction must be 'buy' or 'sell'")
        direction = TradeDirection.BUY if direction_raw == "buy" else TradeDirection.SELL

        order_type = OrderType(arguments.get("order_type", "MARKET").upper())
        units_arg = arguments.get("units")

        stop_loss = Decimal(str(arguments["stop_loss"])) if arguments.get("stop_loss") is not None else Decimal("0")
        take_profit = Decimal(str(arguments["take_profit"])) if arguments.get("take_profit") is not None else Decimal("0")
        entry_price = Decimal(str(arguments["entry_price"])) if arguments.get("entry_price") is not None else Decimal("0")

        signal = TradeSignal(
            pair=context.pair,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=float(arguments.get("confidence", 0.5)),
            reasoning=arguments.get("reasoning", ""),
            generated_at=datetime.now(timezone.utc),
            agent_id=context.agent_id,
        )

        limit_price = Decimal(str(arguments["limit_price"])) if arguments.get("limit_price") is not None else None
        stop_price = Decimal(str(arguments["stop_price"])) if arguments.get("stop_price") is not None else None
        trailing_stop_distance = (
            Decimal(str(arguments["trailing_stop_distance"]))
            if arguments.get("trailing_stop_distance") is not None
            else None
        )

        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if order_type == OrderType.STOP and stop_price is None:
            raise ValueError("STOP order requires stop_price")
        if order_type == OrderType.STOP_LIMIT and (limit_price is None or stop_price is None):
            raise ValueError("STOP_LIMIT order requires both limit_price and stop_price")
        if order_type == OrderType.TRAILING_STOP and trailing_stop_distance is None:
            raise ValueError("TRAILING_STOP order requires trailing_stop_distance")

        # Trading guardrail: if account state cannot be read or trading is not allowed,
        # order placement is blocked.
        account = await context.broker.get_account_status()
        if account is None:
            raise RuntimeError("Account status unavailable; trading is blocked.")
        if not account.trade_allowed:
            raise RuntimeError("Broker reports trading is not allowed; order blocked.")

        # units can be provided directly, or derived from risk_pct + stop distance.
        if units_arg is not None and str(units_arg) != "":
            units = int(units_arg)
            if units <= 0:
                raise ValueError("units must be > 0")
        else:
            risk_pct = arguments.get("risk_pct")
            if risk_pct is None:
                raise ValueError("Either units or risk_pct must be provided.")
            risk_pct_f = float(risk_pct)
            if risk_pct_f <= 0:
                raise ValueError("risk_pct must be > 0 when units is omitted.")
            if stop_loss <= 0:
                raise ValueError("stop_loss is required for risk-based unit sizing.")

            # Derive a reference entry price.
            entry_ref = entry_price
            if entry_ref <= 0:
                if order_type == OrderType.LIMIT and limit_price is not None:
                    entry_ref = limit_price
                elif order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price is not None:
                    entry_ref = stop_price
                elif order_type == OrderType.MARKET:
                    latest = await context.broker.fetch_latest_m5_candle(context.pair)
                    if latest is not None:
                        entry_ref = latest.close
            if entry_ref <= 0:
                raise RuntimeError(
                    "Cannot derive entry price for risk sizing; provide entry_price (or price fields by order type)."
                )

            pair = context.pair.upper()
            if len(pair) >= 6:
                quote_ccy = pair[3:6]
                if quote_ccy != str(account.currency).upper():
                    raise RuntimeError(
                        "Automatic risk-based unit sizing currently requires pair quote currency "
                        "to match account currency. Provide units explicitly."
                    )

            risk_amount = account.equity * Decimal(str(risk_pct_f / 100.0))
            per_unit_risk = abs(entry_ref - stop_loss)
            if per_unit_risk <= 0:
                raise ValueError("Invalid stop distance; stop_loss must differ from entry price.")

            units = int(risk_amount / per_unit_risk)
            if units <= 0:
                raise RuntimeError("Computed units <= 0 from risk inputs; order blocked.")

        order = TradeOrder(
            signal=signal,
            order_type=order_type,
            units=units,
            risk_pct=float(arguments.get("risk_pct", 1.0)),
            limit_price=limit_price,
            stop_price=stop_price,
            trailing_stop_distance=trailing_stop_distance,
            approved_by="supervisor",
        )

        result = await context.broker.place_order(order)
        return {
            "success": result.status != "REJECTED",
            "order_id": result.broker_order_id,
            "status": result.status,
            "fill_price": float(result.fill_price) if result.fill_price else None,
            "broker_name": result.broker_name,
        }

