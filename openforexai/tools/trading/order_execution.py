"""Shared order execution helpers for trading tools."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from openforexai.data.indicators import atr
from openforexai.models.trade import CloseReason, OrderBookEntry, OrderStatus
from openforexai.tools.base import ToolContext
from openforexai.utils.time_utils import is_market_open, utcnow
from openforexai.utils.sync_keys import generate_sync_key


AUTO_ORDER_DEFAULTS: dict[str, Any] = {
    "order_type": "MARKET",
    "risk_pct": 1.0,
    "confidence": 0.5,
    "reasoning": "",
    "entry_price": None,
    "stop_loss": 0.0,
    "take_profit": 0.0,
    "limit_price": None,
    "stop_price": None,
    "trailing_stop_distance": None,
}

_PAIR_PRICE_PATTERN = re.compile(
    r"(support|resistance)[^0-9]{0,40}([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_INDICATOR_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMA20": re.compile(r"EMA20(?:\s*\(|\s*=)\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
    "EMA50": re.compile(r"EMA50(?:\s*\(|\s*=)\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
    "RSI7": re.compile(r"RSI(?:\(7\))?(?:\s*=\s*|\s*~\s*|\s*≈\s*|\s*is\s+)([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
    "ATR7": re.compile(r"ATR(?:\(7\))?(?:\s*=\s*|\s*~\s*|\s*≈\s*|\s*is\s+)([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
}

_MAX_M5_DATA_AGE = timedelta(minutes=20)


def build_auto_place_order_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    merged = dict(AUTO_ORDER_DEFAULTS)
    merged.update(arguments)
    merged["_auto_defaults"] = True
    return merged


def _parse_analysis_response(raw_text: Any) -> dict[str, Any] | None:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_indicator_snapshot(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    indicator_sources = {
        "EMA20": str(analysis.get("trend_assessment") or ""),
        "EMA50": str(analysis.get("trend_assessment") or ""),
        "RSI7": str(analysis.get("momentum_assessment") or ""),
        "ATR7": str(analysis.get("volatility_assessment") or ""),
    }
    indicators: list[dict[str, Any]] = []
    for name, pattern in _INDICATOR_PATTERNS.items():
        source_text = indicator_sources.get(name, "")
        match = pattern.search(source_text)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        indicators.append(
            {
                "name": name,
                "timeframe": "H1",
                "value": value,
                "source": source_text,
            }
        )
    return indicators


def _extract_support_resistance_levels(analysis: dict[str, Any]) -> dict[str, list[float]]:
    text = str(analysis.get("support_resistance_assessment") or "")
    levels: dict[str, list[float]] = {"support": [], "resistance": []}
    for level_type, raw_value in _PAIR_PRICE_PATTERN.findall(text):
        try:
            parsed_value = float(raw_value)
        except ValueError:
            continue
        bucket = "support" if level_type.lower() == "support" else "resistance"
        if parsed_value not in levels[bucket]:
            levels[bucket].append(parsed_value)
    return levels


def _extract_analysis_overlays(analysis: dict[str, Any]) -> dict[str, Any]:
    levels = _extract_support_resistance_levels(analysis)
    invalidation_level = analysis.get("invalidation_level")
    first_target = analysis.get("first_target")
    if isinstance(invalidation_level, (int, float)):
        levels.setdefault("invalidation", []).append(float(invalidation_level))
    if isinstance(first_target, (int, float)):
        levels.setdefault("target", []).append(float(first_target))
    return {
        "levels": levels,
        "indicators": _extract_indicator_snapshot(analysis),
    }


def _build_market_context_snapshot(
    *,
    arguments: dict[str, Any],
    context: ToolContext,
    direction_value: str,
    order_type_value: str,
) -> dict[str, Any]:
    extra = context.extra if isinstance(context.extra, dict) else {}
    analysis_raw = extra.get("analysis_response_text")
    analysis_obj = extra.get("analysis_response_object")
    if not isinstance(analysis_obj, dict):
        analysis_obj = _parse_analysis_response(analysis_raw)

    snapshot: dict[str, Any] = {
        "source": "place_order_tool",
        "pair": context.pair,
        "direction": direction_value,
        "order_type": order_type_value,
        "risk_pct": float(arguments.get("risk_pct", 1.0)),
        "analysis_source_agent_id": extra.get("analysis_source_agent_id"),
        "analyst_recommendation_raw": analysis_raw if isinstance(analysis_raw, str) else None,
        "analyst_recommendation": analysis_obj,
        "analysis_overlays": _extract_analysis_overlays(analysis_obj) if isinstance(analysis_obj, dict) else {
            "levels": {},
            "indicators": [],
        },
    }
    if isinstance(analysis_obj, dict):
        snapshot["decision_context"] = {
            "symbol": analysis_obj.get("symbol"),
            "decision": analysis_obj.get("decision"),
            "confidence": analysis_obj.get("confidence"),
            "order_start_signal": analysis_obj.get("order_start_signal"),
            "entry_quality": analysis_obj.get("entry_quality"),
            "setup_type": analysis_obj.get("setup_type"),
            "analysis_summary": analysis_obj.get("analysis_summary"),
            "conflict_flags": analysis_obj.get("conflict_flags") or [],
        }
    return snapshot


async def _assert_trading_window_open(context: ToolContext) -> None:
    if not is_market_open():
        raise RuntimeError("Forex market session is currently closed; order blocked.")

    if context.data_container is None or not context.broker_name or not context.pair:
        return

    candles = await context.data_container.get_candles(
        context.broker_name,
        context.pair,
        "M5",
        limit=1,
    )
    if not candles:
        raise RuntimeError("No recent M5 candle data available; order blocked.")

    latest = candles[-1]
    age = utcnow() - latest.timestamp
    if age > _MAX_M5_DATA_AGE:
        raise RuntimeError(
            f"Latest M5 candle is stale ({int(age.total_seconds() // 60)} min old); order blocked."
        )


async def _load_m5_candles(context: ToolContext, count: int):
    if context.broker_name and context.pair and context.data_container is not None:
        candles = await context.data_container.get_candles(context.broker_name, context.pair, "M5", limit=count)
        if candles:
            return candles
    if context.broker is None or not context.pair:
        return []
    return await context.broker.get_historical_m5_candles(context.pair, count)


async def _apply_auto_sl_tp_defaults(
    *,
    arguments: dict[str, Any],
    context: ToolContext,
    direction_value: str,
    order_type: str,
    entry_price_value: Decimal,
    limit_price_value: Decimal | None,
    stop_price_value: Decimal | None,
) -> None:
    stop_loss_raw = arguments.get("stop_loss")
    take_profit_raw = arguments.get("take_profit")
    has_stop_loss = stop_loss_raw is not None and Decimal(str(stop_loss_raw)) > 0
    has_take_profit = take_profit_raw is not None and Decimal(str(take_profit_raw)) > 0
    if has_stop_loss and has_take_profit:
        return

    entry_ref = entry_price_value
    if entry_ref <= 0:
        if order_type == "LIMIT" and limit_price_value is not None:
            entry_ref = limit_price_value
        elif order_type in {"STOP", "STOP_LIMIT"} and stop_price_value is not None:
            entry_ref = stop_price_value

    candles = await _load_m5_candles(context, 30)
    if entry_ref <= 0 and candles:
        entry_ref = candles[-1].close
    if entry_ref <= 0:
        raise RuntimeError("Cannot derive entry reference price for automatic SL/TP defaults.")

    atr_value = atr(candles, period=14) if candles else None
    if atr_value is None or atr_value <= 0:
        raise RuntimeError("Cannot derive ATR for automatic SL/TP defaults.")

    stop_distance = Decimal(str(atr_value)) * Decimal("1.5")
    rr_multiple = Decimal("2.0")

    if direction_value == "BUY":
        derived_stop_loss = entry_ref - stop_distance
        derived_take_profit = entry_ref + (stop_distance * rr_multiple)
    else:
        derived_stop_loss = entry_ref + stop_distance
        derived_take_profit = entry_ref - (stop_distance * rr_multiple)

    if not has_stop_loss:
        arguments["stop_loss"] = float(derived_stop_loss)
    if not has_take_profit:
        arguments["take_profit"] = float(derived_take_profit)


async def execute_place_order_arguments(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    from openforexai.models.trade import OrderType, TradeDirection, TradeOrder, TradeSignal

    if context.broker is None:
        raise RuntimeError("Broker adapter not available in tool context")
    if not context.pair:
        raise RuntimeError("pair not set in tool context")

    direction_raw = str(arguments["direction"]).strip().lower()
    if direction_raw not in {"buy", "sell"}:
        raise ValueError("direction must be 'buy' or 'sell'")
    direction = TradeDirection.BUY if direction_raw == "buy" else TradeDirection.SELL

    order_type = OrderType(str(arguments.get("order_type", "MARKET")).upper())
    units_arg = arguments.get("units")
    lots_arg = arguments.get("lots")
    entry_price = (
        Decimal(str(arguments["entry_price"]))
        if arguments.get("entry_price") is not None
        else Decimal("0")
    )
    limit_price = (
        Decimal(str(arguments["limit_price"]))
        if arguments.get("limit_price") is not None
        else None
    )
    stop_price = (
        Decimal(str(arguments["stop_price"]))
        if arguments.get("stop_price") is not None
        else None
    )
    if arguments.get("_auto_defaults"):
        await _apply_auto_sl_tp_defaults(
            arguments=arguments,
            context=context,
            direction_value=direction.value,
            order_type=order_type.value,
            entry_price_value=entry_price,
            limit_price_value=limit_price,
            stop_price_value=stop_price,
        )

    stop_loss = (
        Decimal(str(arguments["stop_loss"]))
        if arguments.get("stop_loss") is not None
        else Decimal("0")
    )
    take_profit = (
        Decimal(str(arguments["take_profit"]))
        if arguments.get("take_profit") is not None
        else Decimal("0")
    )

    signal = TradeSignal(
        pair=context.pair,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence=float(arguments.get("confidence", 0.5)),
        reasoning=str(arguments.get("reasoning", "")),
        generated_at=datetime.now(UTC),
        agent_id=context.agent_id,
    )

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

    account = await context.broker.get_account_status()
    if account is None:
        raise RuntimeError("Account status unavailable; trading is blocked.")
    if not account.trade_allowed:
        raise RuntimeError("Broker reports trading is not allowed; order blocked.")
    await _assert_trading_window_open(context)

    if lots_arg is not None and str(lots_arg) != "":
        lots = float(lots_arg)
        if lots <= 0:
            raise ValueError("lots must be > 0")
        units = int(lots * 100_000)
        if units <= 0:
            raise ValueError("lots produced units <= 0")
    elif units_arg is not None and str(units_arg) != "":
        units = int(units_arg)
        if units <= 0:
            raise ValueError("units must be > 0")
    else:
        risk_pct = arguments.get("risk_pct")
        if risk_pct is None:
            raise ValueError("Either lots, units, or risk_pct must be provided.")
        risk_pct_f = float(risk_pct)
        if risk_pct_f <= 0:
            raise ValueError("risk_pct must be > 0 when units is omitted.")
        if stop_loss <= 0:
            raise ValueError("stop_loss is required for risk-based unit sizing.")

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
        sync_key=generate_sync_key(),
    )

    requested_price = entry_price
    if requested_price <= 0:
        if order_type == OrderType.LIMIT and limit_price is not None:
            requested_price = limit_price
        elif order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price is not None:
            requested_price = stop_price

    entry = OrderBookEntry(
        broker_name=context.broker.short_name,
        broker_order_id=None,
        sync_key=order.sync_key,
        pair=context.pair,
        direction=direction,
        order_type=order_type,
        units=units,
        requested_price=requested_price,
        fill_price=None,
        stop_loss=stop_loss if stop_loss > 0 else None,
        take_profit=take_profit if take_profit > 0 else None,
        trailing_stop_distance=trailing_stop_distance,
        limit_price=limit_price,
        stop_price=stop_price,
        status=OrderStatus.PENDING,
        agent_id=context.agent_id,
        prompt_version=signal.prompt_version,
        entry_reasoning=signal.reasoning,
        signal_confidence=signal.confidence,
        market_context_snapshot=_build_market_context_snapshot(
            arguments=arguments,
            context=context,
            direction_value=direction.value,
            order_type_value=order_type.value,
        ),
        requested_at=datetime.now(UTC),
        sync_confirmed=False,
    )
    if context.repository is not None:
        await context.repository.save_order_book_entry(entry)

    result = await context.broker.place_order(order)
    if context.repository is not None:
        if result.status == "REJECTED":
            await context.repository.update_order_book_entry(
                str(entry.id),
                {
                    "status": OrderStatus.REJECTED,
                    "broker_order_id": result.broker_order_id or None,
                    "closed_at": datetime.now(UTC),
                    "last_broker_sync": datetime.now(UTC),
                    "close_reason": "REJECTED",
                    "close_reasoning": result.close_reason or "Broker rejected order",
                    "sync_confirmed": True,
                },
            )
        elif result.broker_order_id:
            await context.repository.update_order_book_entry(
                str(entry.id),
                {
                    "broker_order_id": result.broker_order_id,
                },
            )
    return {
        "success": result.status != "REJECTED",
        "order_id": result.broker_order_id,
        "status": result.status,
        "fill_price": float(result.fill_price) if result.fill_price else None,
        "broker_name": result.broker_name,
        "broker_message": result.close_reason,
        "sync_key": order.sync_key,
        "order_book_entry_id": str(entry.id),
    }
