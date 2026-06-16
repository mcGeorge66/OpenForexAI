from __future__ import annotations

import asyncio
import dataclasses
import json
import importlib.util
import re
import traceback
from copy import deepcopy
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import math
import statistics
from decimal import Decimal

from openforexai.models.market import Candle
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext

SNAPSHOT_SCHEMA_VERSION = "1.1"
DEFAULT_DECISION_INPUT_PREFIX = (
    "Runtime-prepared market decision snapshot.\n"
    "Use the snapshot as the complete market context.\n"
    "Return strict JSON only."
)
DEFAULT_IDENTITY_TRANSFORM_SCRIPT = "result = tool_output"
DEFAULT_CANDLE_TRANSFORM_SCRIPT = (
    'result = normalize_candle_tool_output(tool_output, timeframe=tool_input.get("timeframe"))'
)
DEFAULT_INDICATOR_TRANSFORM_SCRIPT = """result = dict(tool_output)
points = tool_output.get("values") or tool_output.get("value") or []
values = []
for item in points:
    if isinstance(item, dict):
        raw_value = item.get("value")
    else:
        raw_value = item
    if raw_value is not None:
        values.append(float(raw_value))
indicator_name = str(tool_output.get("indicator") or tool_input.get("indicator") or "").upper()
result["indicator"] = indicator_name or result.get("indicator")
result["latest"] = latest_value(values)
result["direction"] = classify_indicator_direction(values, indicator_name)
result["values"] = points
if "value" in result:
    del result["value"]"""

def _substitute_placeholders(text: str, placeholders: dict[str, Any]) -> str:
    def resolve(key: str) -> str:
        if key in placeholders:
            val = placeholders[key]
            return "" if val is None else str(val)
        return "{" + key + "}"
    return re.sub(r"\{([^{}]+)\}", lambda m: resolve(m.group(1)), text)


_SAFE_SCRIPT_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "callable": callable,
    "complex": complex,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,

    # Exceptions explizit erlauben:
    "TypeError": TypeError,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "Exception": Exception,    
}

safe_globals = {
    "__builtins__": _SAFE_SCRIPT_BUILTINS,
    "math": math,
    "statistics": statistics,
    "Decimal": Decimal,
}


def default_transform_script_for_tool(tool_name: str) -> str:
    if tool_name == "get_candles":
        return DEFAULT_CANDLE_TRANSFORM_SCRIPT
    if tool_name == "calculate_indicator":
        return DEFAULT_INDICATOR_TRANSFORM_SCRIPT
    return DEFAULT_IDENTITY_TRANSFORM_SCRIPT

_SNAPSHOT_HELPER_MODULE: Any | None = None


def _load_snapshot_helper_module() -> Any | None:
    global _SNAPSHOT_HELPER_MODULE
    if _SNAPSHOT_HELPER_MODULE is not None:
        return _SNAPSHOT_HELPER_MODULE
    helper_path = Path(__file__).resolve().parents[2] / "config" / "snapshot_helpers.py"
    if not helper_path.exists():
        _SNAPSHOT_HELPER_MODULE = False
        return None
    spec = importlib.util.spec_from_file_location("openforexai_config_snapshot_helpers", helper_path)
    if spec is None or spec.loader is None:
        _SNAPSHOT_HELPER_MODULE = False
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _SNAPSHOT_HELPER_MODULE = module
    return module


def _get_config_snapshot_helper(name: str) -> Any | None:
    module = _load_snapshot_helper_module()
    if module is None:
        return None
    helper = getattr(module, name, None)
    return helper if callable(helper) else None


def _to_float(value: Decimal | float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _slope_direction(values: Sequence[float], *, flat_epsilon: float = 1e-6) -> str:
    if len(values) < 2:
        return "flat"
    delta = values[-1] - values[0]
    if delta > flat_epsilon:
        return "rising"
    if delta < -flat_epsilon:
        return "falling"
    return "flat"


def _compact_candle(candle: Candle) -> dict[str, Any]:
    return {
        "timestamp": candle.timestamp.isoformat().replace("+00:00", "Z"),
        "open": _round(_to_float(candle.open)),
        "high": _round(_to_float(candle.high)),
        "low": _round(_to_float(candle.low)),
        "close": _round(_to_float(candle.close)),
        "spread": _round(_to_float(candle.spread), 2),
        "tick_volume": candle.tick_volume,
    }



def _json_snapshot(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _has_meaningful_mapping_data(value: dict[str, Any], *, ignore_keys: set[str] | None = None) -> bool:
    ignored = ignore_keys or set()
    for key, item in value.items():
        if key in ignored:
            continue
        if isinstance(item, dict):
            if _has_meaningful_mapping_data(item):
                return True
            continue
        if isinstance(item, list):
            if len(item) > 0:
                return True
            continue
        if item is None:
            continue
        if isinstance(item, str) and item in {"", "unknown", "neutral", "flat", "indeterminate"}:
            continue
        return True
    return False


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _candle_from_mapping(row: Any, timeframe: str) -> Candle | None:
    if not isinstance(row, dict):
        return None
    timestamp = _parse_timestamp(row.get("timestamp"))
    open_price = _to_float(row.get("open"))
    high = _to_float(row.get("high"))
    low = _to_float(row.get("low"))
    close = _to_float(row.get("close"))
    if timestamp is None or open_price is None or high is None or low is None or close is None:
        return None
    spread = _to_float(row.get("spread")) or 0.0
    tick_volume_raw = row.get("tick_volume", 0)
    try:
        tick_volume = int(tick_volume_raw)
    except (TypeError, ValueError):
        tick_volume = 0
    return Candle(
        timestamp=timestamp,
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        tick_volume=tick_volume,
        spread=Decimal(str(spread)),
        timeframe=timeframe,
    )


def _series_from_tool_result(result: Any) -> list[float]:
    if isinstance(result, dict):
        value = result.get("values")
        if value is None:
            value = result.get("value")
    else:
        value = result
    if isinstance(value, list):
        series: list[float] = []
        for item in value:
            raw_value = item.get("value") if isinstance(item, dict) else item
            numeric = _to_float(raw_value)
            if numeric is not None:
                series.append(float(numeric))
        return series
    scalar = _to_float(value)
    return [scalar] if scalar is not None else []


def _normalize_candle_tool_output(tool_output: Any, *, timeframe: str | None = None) -> list[dict[str, Any]]:
    helper = _get_config_snapshot_helper("normalize_candle_tool_output")
    if helper is not None:
        return helper(tool_output, timeframe=timeframe)
    rows = tool_output if isinstance(tool_output, list) else []
    normalized: list[dict[str, Any]] = []
    resolved_timeframe = str(timeframe or "M5").upper()
    for row in rows:
        candle = _candle_from_mapping(row, resolved_timeframe)
        if candle is None:
            continue
        payload = _compact_candle(candle)
        payload["timeframe"] = resolved_timeframe
        normalized.append(payload)
    return normalized


def _indicator_direction_from_values(values: Sequence[float], indicator_name: str) -> str:
    helper = _get_config_snapshot_helper("classify_indicator_direction")
    if helper is not None:
        return str(helper(list(values), indicator_name))
    indicator = str(indicator_name or "").upper()
    if indicator == "ATR":
        slope = _slope_direction(values, flat_epsilon=1e-5)
        return "expanding" if slope == "rising" else ("contracting" if slope == "falling" else "stable")
    return _slope_direction(values, flat_epsilon=0.1 if indicator == "RSI" else 1e-6)


def _build_indicator_tool_output(
    tool_output: Any,
    *,
    tool_input: dict[str, Any] | None = None,
    all_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    helper = _get_config_snapshot_helper("build_indicator_tool_output")
    if helper is not None:
        return helper(tool_output, tool_input=tool_input, all_outputs=all_outputs)
    row = tool_output if isinstance(tool_output, dict) else {}
    input_row = tool_input if isinstance(tool_input, dict) else {}
    indicator_name = str(row.get("indicator") or input_row.get("indicator") or "").upper()
    period = row.get("period", input_row.get("period"))
    history = row.get("history", input_row.get("history"))
    raw_points = row.get("values")
    if not isinstance(raw_points, list):
        raw_points = row.get("value")
    points = raw_points if isinstance(raw_points, list) else []
    values = _series_from_tool_result(row)
    latest = _round(values[-1], 6) if values else None
    payload: dict[str, Any] = {
        "indicator": indicator_name or None,
        "period": period,
        "timeframe": row.get("timeframe", input_row.get("timeframe")),
        "history": history,
        "latest": latest,
    }
    if values:
        payload["direction"] = _indicator_direction_from_values(values, indicator_name)
        payload["values"] = points
    return payload


def _run_transform_script(
    script: str,
    *,
    locals_payload: dict[str, Any],
    script_name: str = "<script>",
) -> Any:
    code = str(script or "").strip()
    if not code:
        return locals_payload.get("result", locals_payload.get("out"))
    compiled = compile(code, script_name, "exec")
    exec(compiled, safe_globals, locals_payload)
    if "result" in locals_payload:
        return locals_payload["result"]
    return locals_payload.get("out")


def _normalize_tool_blocks(profile: dict[str, Any], *, strategy_aggressiveness: str) -> list[dict[str, Any]]:
    key_present = "tool_blocks" in profile
    raw_blocks = profile.get("tool_blocks")
    if isinstance(raw_blocks, list) and raw_blocks:
        blocks: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_blocks):
            if not isinstance(raw, dict):
                continue
            tool_name = str(raw.get("tool_name", "")).strip()
            if not tool_name:
                continue
            block_id = str(raw.get("id", f"block_{index + 1}")).strip() or f"block_{index + 1}"
            arguments = raw.get("arguments")
            blocks.append(
                {
                    "id": block_id,
                    "tool_name": tool_name,
                    "enabled": bool(raw.get("enabled", True)),
                    "output_key": str(raw.get("output_key", "")).strip() or None,
                    "arguments": arguments if isinstance(arguments, dict) else {},
                    "transform_script": str(
                        raw.get("transform_script", default_transform_script_for_tool(tool_name))
                        or default_transform_script_for_tool(tool_name)
                    ),
                }
            )
        if blocks:
            return blocks
    return []


async def _execute_tool_blocks(
    *,
    blocks: Sequence[dict[str, Any]],
    agent_id: str,
    broker_name: str,
    pair: str,
    repository: Any = None,
    broker: Any = None,
    monitoring_bus: Any = None,
    event_bus: Any = None,
    short_timeframe: str = "M5",
    long_timeframe: str = "H1",
) -> tuple[list[dict[str, Any]], list[str]]:
    context = ToolContext(
        agent_id=agent_id,
        broker_name=broker_name,
        pair=pair,
        monitoring_bus=monitoring_bus,
        event_bus=event_bus,
    )
    errors: list[str] = []

    # Phase 1: resolve metadata for every enabled block in original order.
    # Each entry: (block_dict, block_id, tool_name, output_key, arguments, tool_or_None)
    _ResolvedBlock = tuple[dict[str, Any], str, str, str, dict[str, Any], Any]
    resolved: list[_ResolvedBlock] = []
    for index, block in enumerate(blocks):
        if not block.get("enabled", True):
            continue
        block_id = str(block.get("id", f"block_{index + 1}")).strip() or f"block_{index + 1}"
        tool_name = str(block.get("tool_name", "")).strip()
        output_key = str(block.get("output_key", "")).strip() or block_id
        arguments = dict(block.get("arguments") if isinstance(block.get("arguments"), dict) else {})

        # Resolve SHORT_TF / LONG_TF placeholders in timeframe arguments.
        tf = str(arguments.get("timeframe", "")).strip().upper()
        if tf == "SHORT_TF":
            arguments["timeframe"] = short_timeframe
        elif tf == "LONG_TF":
            arguments["timeframe"] = long_timeframe

        if not tool_name:
            errors.append(f"{block_id}:missing_tool_name")
            continue
        tool = DEFAULT_REGISTRY.get(tool_name)
        if tool is None:
            errors.append(f"{block_id}:unknown_tool:{tool_name}")
        resolved.append((block, block_id, tool_name, output_key, arguments, tool))

    # Phase 2: execute all tool calls in parallel to minimise I/O latency.
    async def _call_tool(
        tool: Any, arguments: dict[str, Any], block_id: str
    ) -> tuple[Any, str | None]:
        if tool is None:
            return None, "unknown_tool"
        try:
            # Stage 3: pair/broker in block arguments override the agent context.
            override_pair   = str(arguments.get("pair")   or "").strip().upper() or None
            override_broker = str(arguments.get("broker") or "").strip()         or None
            effective_context = (
                dataclasses.replace(
                    context,
                    pair=override_pair         if override_pair   else context.pair,
                    broker_name=override_broker if override_broker else context.broker_name,
                )
                if override_pair or override_broker
                else context
            )
            return await tool.execute(dict(arguments), effective_context), None
        except Exception as exc:
            return None, f"{type(exc).__name__}:{exc}"

    call_results: list[tuple[Any, str | None]] = list(
        await asyncio.gather(
            *[_call_tool(tool, args, bid) for _, bid, _, _, args, tool in resolved]
        )
    )

    # Phase 3: apply transforms sequentially in original order so that
    # all_outputs accumulates correctly for scripts that reference prior outputs.
    transformed_outputs: dict[str, Any] = {}
    block_results: list[dict[str, Any]] = []

    for (block, block_id, tool_name, output_key, arguments, _tool), (raw_result, exec_error) in zip(
        resolved, call_results
    ):
        transform_script = str(block.get("transform_script", "") or "")
        if exec_error is not None:
            if exec_error != "unknown_tool":
                errors.append(f"{block_id}:tool_failed:{exec_error}")
            block_results.append(
                {
                    "id": block_id,
                    "tool_name": tool_name,
                    "output_key": output_key,
                    "arguments": arguments,
                    "error": exec_error,
                }
            )
            continue

        transformed_result = raw_result
        transform_error: str | None = None
        try:
            transform_locals: dict[str, Any] = {
                "tool_input": deepcopy(arguments),
                "tool_output": deepcopy(raw_result),
                "all_outputs": deepcopy(transformed_outputs),
                "in_": deepcopy(raw_result),
                "out": deepcopy(raw_result),
                "result": deepcopy(raw_result),
            }
            for helper_name, helper_value in (
                ("normalize_candle_tool_output", _get_config_snapshot_helper("normalize_candle_tool_output")),
                ("latest_value", _get_config_snapshot_helper("latest_value")),
                ("classify_series_direction", _get_config_snapshot_helper("classify_series_direction")),
                ("classify_indicator_direction", _get_config_snapshot_helper("classify_indicator_direction")),
                ("build_indicator_tool_output", _get_config_snapshot_helper("build_indicator_tool_output")),
            ):
                if callable(helper_value):
                    transform_locals[helper_name] = helper_value
            transformed_result = _run_transform_script(
                transform_script,
                locals_payload=transform_locals,
                script_name=f"transform:{block_id}",
            )
        except Exception as exc:
            transform_error = traceback.format_exc().strip()
            errors.append(f"{block_id}:transform_failed:\n{transform_error}")
        transformed_outputs[output_key] = transformed_result
        block_results.append(
            {
                "id": block_id,
                "tool_name": tool_name,
                "output_key": output_key,
                "arguments": arguments,
                "transform_script": transform_script,
                "raw_result": raw_result,
                "result": transformed_result,
                **({"transform_error": transform_error} if transform_error else {}),
            }
        )

    return block_results, errors


async def preview_snapshot_tool_block(
    *,
    block: dict[str, Any],
    agent_id: str,
    broker_name: str,
    pair: str,
    repository: Any = None,
    broker: Any = None,
    monitoring_bus: Any = None,
    event_bus: Any = None,
    short_timeframe: str = "M5",
    long_timeframe: str = "H1",
) -> dict[str, Any]:
    block_results, errors = await _execute_tool_blocks(
        blocks=[block],
        agent_id=agent_id,
        broker_name=broker_name,
        pair=pair,
        repository=repository,
        broker=broker,
        monitoring_bus=monitoring_bus,
        event_bus=event_bus,
        short_timeframe=short_timeframe,
        long_timeframe=long_timeframe,
    )
    if not block_results:
        return {
            "raw_output": None,
            "transformed_output": None,
            "errors": errors or ["tool_preview_failed"],
        }
    row = block_results[0]
    preview_errors = list(errors)
    if row.get("error"):
        preview_errors.append(str(row.get("error")))
    if row.get("transform_error"):
        preview_errors.append(str(row.get("transform_error")))
    return {
        "raw_output": row.get("raw_result"),
        "transformed_output": row.get("result"),
        "errors": preview_errors,
    }


def _normalize_candle_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        candle = _candle_from_mapping(row, str(row.get("timeframe", "M5")) if isinstance(row, dict) else "M5")
        if candle is None:
            continue
        normalized.append(_compact_candle(candle))
    return normalized







def _calc_script(
    script: str,
    tool_outputs: dict[str, Any],
    *,
    strategy_aggressiveness: str = "BALANCED",
    short_timeframe: str = "M5",
    long_timeframe: str = "H1",
    block_id: str = "<calc>",
) -> dict[str, Any]:
    """Execute a free-form Python script as a calculation block.

    The script has access to:
    - ``tool_outputs``: all transformed tool block outputs keyed by output_key
    - ``strategy_aggressiveness``: profile-level aggressiveness setting
    - ``short_timeframe``: profile-level short timeframe (e.g. "M5")
    - ``long_timeframe``: profile-level long timeframe (e.g. "H1")
    - ``result``: empty dict that the script populates (returned to caller)
    """
    code = str(script or "").strip()
    if not code:
        return {}
    locals_payload: dict[str, Any] = {
        "tool_outputs": deepcopy(tool_outputs),
        "strategy_aggressiveness": strategy_aggressiveness,
        "short_timeframe": short_timeframe,
        "long_timeframe": long_timeframe,
        "result": {},
    }
    try:
        compiled = compile(code, f"calc:{block_id}", "exec")
        exec(compiled, safe_globals, locals_payload)
        out = locals_payload.get("result")
        return out if isinstance(out, dict) else {}
    except Exception as exc:
        tb = traceback.format_exc().strip()
        return {"error": f"{type(exc).__name__}: {exc}", "traceback": tb}


CALCULATION_HANDLERS: dict[str, Any] = {}

# Slot names that indicate a primary candle source for output grouping.
_CANDLE_PRIMARY_SLOTS = {"candles"}
# All script blocks go to the "global" group.
_GLOBAL_CALC_TYPES = {"script"}


def _execute_calculation_blocks(
    *,
    calculation_blocks: list[dict[str, Any]],
    tool_results_by_output_key: dict[str, Any],
    strategy_aggressiveness: str = "BALANCED",
    short_timeframe: str = "M5",
    long_timeframe: str = "H1",
) -> dict[str, Any]:
    """Execute configured calculation blocks and return snapshot["calculations"] dict."""
    calculations: dict[str, Any] = {}
    calc_results_by_id: dict[str, Any] = {}

    for block in calculation_blocks:
        if not block.get("enabled", True):
            continue
        calc_type = str(block.get("type", "")).strip()
        block_id = str(block.get("id", calc_type)).strip() or calc_type
        handler = CALCULATION_HANDLERS.get(calc_type)
        # "script" blocks are handled inline below — no handler entry needed.
        if handler is None and calc_type != "script":
            continue

        # Resolve sources: each slot maps to an output_key (tool block result)
        # or a calculation block ID (calc result from earlier in the list).
        sources_cfg = block.get("sources") if isinstance(block.get("sources"), dict) else {}
        resolved_sources: dict[str, Any] = {}
        primary_candles_key: str | None = None
        for slot_name, source_ref in sources_cfg.items():
            ref = str(source_ref).strip()
            if ref in tool_results_by_output_key:
                resolved_sources[slot_name] = tool_results_by_output_key[ref]
            elif ref in calc_results_by_id:
                resolved_sources[slot_name] = calc_results_by_id[ref]
            if slot_name in _CANDLE_PRIMARY_SLOTS and ref:
                primary_candles_key = ref

        config = block.get("config") if isinstance(block.get("config"), dict) else {}

        try:
            if calc_type == "script":
                result = _calc_script(
                    str(block.get("script", "") or ""),
                    {**tool_results_by_output_key, **calc_results_by_id},
                    strategy_aggressiveness=strategy_aggressiveness,
                    short_timeframe=short_timeframe,
                    long_timeframe=long_timeframe,
                    block_id=block_id,
                )
            else:
                result = handler(resolved_sources, config)
        except Exception as exc:
            tb = traceback.format_exc().strip()
            result = {"error": f"{type(exc).__name__}: {exc}", "traceback": tb}

        calc_results_by_id[block_id] = result

        if calc_type in _GLOBAL_CALC_TYPES or primary_candles_key is None:
            group_key = "global"
        else:
            group_key = primary_candles_key

        if group_key not in calculations:
            calculations[group_key] = {}
        calculations[group_key][block_id] = result

    return calculations


async def preview_calculation_block(
    *,
    block: dict[str, Any],
    tool_results_by_output_key: dict[str, Any],
    strategy_aggressiveness: str = "BALANCED",
    short_timeframe: str = "M5",
    long_timeframe: str = "H1",
) -> dict[str, Any]:
    """Execute a single calculation block against resolved tool outputs and return the result."""
    calc_type = str(block.get("type", "")).strip()

    block_id = str(block.get("id", calc_type)).strip() or calc_type

    # script blocks are handled separately — they receive all tool_outputs directly.
    if calc_type == "script":
        try:
            result = _calc_script(
                str(block.get("script", "") or ""),
                tool_results_by_output_key,
                strategy_aggressiveness=strategy_aggressiveness,
                short_timeframe=short_timeframe,
                long_timeframe=long_timeframe,
                block_id=block_id,
            )
            return {"result": result, "errors": []}
        except Exception as exc:
            tb = traceback.format_exc().strip()
            return {"result": None, "errors": [f"{type(exc).__name__}: {exc}\n{tb}"]}

    handler = CALCULATION_HANDLERS.get(calc_type)
    if handler is None:
        return {"error": f"unknown_calculation_type:{calc_type}"}
    sources_cfg = block.get("sources") if isinstance(block.get("sources"), dict) else {}
    resolved_sources: dict[str, Any] = {}
    for slot_name, source_ref in sources_cfg.items():
        ref = str(source_ref).strip()
        if ref in tool_results_by_output_key:
            resolved_sources[slot_name] = tool_results_by_output_key[ref]
    config = block.get("config") if isinstance(block.get("config"), dict) else {}
    try:
        result = handler(resolved_sources, config)
        return {"result": result, "errors": []}
    except Exception as exc:
        tb = traceback.format_exc().strip()
        return {"result": None, "errors": [f"{type(exc).__name__}: {exc}\n{tb}"]}


def _build_decision_payload(
    snapshot: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the payload forwarded to the LLM as the decision input.

    If an assembly transform script produced an ``assembled`` dict, it is returned
    directly — the script is responsible for constructing the full payload.
    Fallback: return the raw snapshot dict when no assembly script ran.
    """
    assembled = snapshot.get("assembled")
    if isinstance(assembled, dict):
        return assembled
    # Fallback for profiles without an assembly transform script.
    return dict(snapshot)


async def build_analysis_snapshot(
    *,
    broker_name: str,
    pair: str,
    trigger_payload: dict[str, Any],
    profile: dict[str, Any] | None = None,
    strategy_aggressiveness: str = "BALANCED",
    agent_id: str = "snapshot_builder",
    repository: Any = None,
    broker: Any = None,
    monitoring_bus: Any = None,
    event_bus: Any = None,
) -> tuple[dict[str, Any], list[str]]:
    profile = profile if isinstance(profile, dict) else {}
    pair = pair.upper()
    aggressiveness = str(
        profile.get("strategy_aggressiveness", strategy_aggressiveness)
    ).upper().strip() or "BALANCED"
    if aggressiveness not in {"CONSERVATIVE", "BALANCED", "AGGRESSIVE"}:
        aggressiveness = "BALANCED"

    short_timeframe = str(profile.get("short_timeframe", "M5")).upper().strip() or "M5"
    long_timeframe  = str(profile.get("long_timeframe",  "H1")).upper().strip() or "H1"

    tool_blocks = _normalize_tool_blocks(profile, strategy_aggressiveness=aggressiveness)
    block_results, tool_errors = await _execute_tool_blocks(
        blocks=tool_blocks,
        agent_id=agent_id,
        broker_name=broker_name,
        pair=pair,
        repository=repository,
        broker=broker,
        monitoring_bus=monitoring_bus,
        event_bus=event_bus,
        short_timeframe=short_timeframe,
        long_timeframe=long_timeframe,
    )

    errors: list[str] = list(tool_errors)

    # Resolve trigger candle and current price.
    trigger_candle = trigger_payload.get("candle") if isinstance(trigger_payload, dict) else {}
    current_price = _to_float(trigger_candle.get("close")) if isinstance(trigger_candle, dict) else None
    latest_spread = _to_float(trigger_candle.get("spread")) if isinstance(trigger_candle, dict) else None

    transformed_tool_outputs = {
        str(block.get("output_key") or block.get("id")): block.get("result")
        for block in block_results
        if "result" in block
    }
    raw_tool_outputs = {
        str(block.get("output_key") or block.get("id")): block.get("raw_result")
        for block in block_results
        if "raw_result" in block
    }

    # current_price fallback: use the close of the most recent available candle
    # from any raw tool output, if the trigger candle did not supply it.
    if current_price is None:
        for raw_output in raw_tool_outputs.values():
            if isinstance(raw_output, list) and raw_output:
                last = raw_output[-1]
                if isinstance(last, dict):
                    candidate = _to_float(last.get("close"))
                    if candidate is not None:
                        current_price = candidate
                        if latest_spread is None:
                            latest_spread = _to_float(last.get("spread"))
                        break
    if current_price is None:
        current_price = 0.0

    snapshot = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_profile_name": profile.get("name"),
        "symbol": pair,
        "broker_name": broker_name,
        "timestamp": (
            trigger_candle.get("timestamp")
            if isinstance(trigger_candle, dict) and isinstance(trigger_candle.get("timestamp"), str)
            else None
        ),
        "strategy_aggressiveness": aggressiveness,
        "latest_price": _round(current_price),
        "latest_spread": _round(latest_spread, 2),
        "tool_blocks": [
            {
                "id": block.get("id"),
                "tool_name": block.get("tool_name"),
                "output_key": block.get("output_key"),
                "arguments": block.get("arguments"),
                "has_result": "result" in block,
                "has_error": "error" in block,
            }
            for block in block_results
        ],
    }

    # trigger_candle is always written.
    snapshot["trigger_candle"] = trigger_candle if isinstance(trigger_candle, dict) else {}

    snapshot["tool_outputs"] = transformed_tool_outputs

    raw_calculation_blocks = profile.get("calculation_blocks")
    if isinstance(raw_calculation_blocks, list) and raw_calculation_blocks:
        calc_section = _execute_calculation_blocks(
            calculation_blocks=raw_calculation_blocks,
            tool_results_by_output_key=transformed_tool_outputs,
            strategy_aggressiveness=aggressiveness,
            short_timeframe=short_timeframe,
            long_timeframe=long_timeframe,
        )
        if calc_section:
            snapshot["calculations"] = calc_section

    assembly_script = str(profile.get("assembly_transform_script", "") or "").strip()
    if assembly_script:
        try:
            assembly_locals: dict[str, Any] = {
                "tool_outputs": deepcopy(transformed_tool_outputs),
                "raw_tool_outputs": deepcopy(raw_tool_outputs),
                "snapshot": deepcopy(snapshot),
                "profile": deepcopy(profile),
                "agent_context": {
                    "agent_id": agent_id,
                    "broker_name": broker_name,
                    "pair": pair,
                    "strategy_aggressiveness": aggressiveness,
                },
                "in_": deepcopy(snapshot),
                "out": deepcopy(snapshot),
                "result": deepcopy(snapshot),
                "cancel": False,
                "cancel_reason": "",
            }
            snapshot["assembled"] = _run_transform_script(
                assembly_script,
                locals_payload=assembly_locals,
                script_name="assembly_transform",
            )
            if assembly_locals.get("cancel"):
                snapshot["cancel"] = True
                snapshot["cancel_reason"] = str(assembly_locals.get("cancel_reason", ""))
        except Exception as exc:
            tb = traceback.format_exc().strip()
            errors.append(f"assembly_transform_failed:\n{tb}")
    return snapshot, errors


def build_snapshot_system_prompt(
    base_system_prompt: str,
    profile: dict[str, Any] | None = None,
    *,
    allow_tools: bool,
    snapshot: dict[str, Any] | None = None,
) -> str:
    profile = profile if isinstance(profile, dict) else {}
    prompts = profile.get("prompts")
    if isinstance(prompts, list) and prompts:
        script = str(profile.get("script", "result = 1")).strip() or "result = 1"
        snap = snapshot or {}
        locals_ = {
            "snapshot": snap,
            "tool_outputs": snap.get("tool_outputs") or {},
            "assembled": snap.get("assembled") or {},
            "placeholders": {},
            "result": 1,
        }
        try:
            exec(script, safe_globals, locals_)
            selected_id = int(locals_.get("result", 1))
        except Exception as _exc:
            selected_id = 1
            locals_["placeholders"] = {}  # reset — partial execution may have left stale values
        entry = next((p for p in prompts if p.get("id") == selected_id), prompts[0])
        prompt_override = str(entry.get("prompt", "")).strip()
        mode = str(entry.get("mode", "replace")).strip().lower()
        if entry.get("use_placeholders") and prompt_override:
            ph = locals_.get("placeholders")
            prompt_override = _substitute_placeholders(prompt_override, ph if isinstance(ph, dict) else {})
    else:
        prompt_override = str(profile.get("prompt", "")).strip()
        mode = str(profile.get("mode", "replace")).strip().lower()
    if prompt_override:
        if mode == "append":
            effective_prompt = f"{base_system_prompt}\n\n{prompt_override}".strip()
        else:
            effective_prompt = prompt_override
    else:
        effective_prompt = base_system_prompt
    override_lines = [
        "RUNTIME OVERRIDE",
        "- The runtime has already fetched, validated, and summarized the required context data.",
        "- Use the supplied snapshot as the primary runtime context.",
    ]
    if allow_tools:
        override_lines.extend(
            [
                "- Do not re-fetch information that is already present in the snapshot.",
                "- Use tools only for explicit actions or genuinely missing information.",
            ]
        )
    else:
        override_lines.extend(
            [
                "- Do not request tools.",
                "- Do not ask for raw candles or recompute context that already exists in the snapshot.",
                "- Return the final strict JSON decision only.",
            ]
        )
    return f"{effective_prompt}\n\n" + "\n".join(override_lines) + "\n"


def build_decision_only_system_prompt(
    base_system_prompt: str,
    profile: dict[str, Any] | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> str:
    return build_snapshot_system_prompt(base_system_prompt, profile, allow_tools=False, snapshot=snapshot)


def build_snapshot_user_message(
    snapshot: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> str:
    profile = profile if isinstance(profile, dict) else {}
    prefix = str(profile.get("decision_input_prefix", "")).strip() or DEFAULT_DECISION_INPUT_PREFIX
    payload = _build_decision_payload(snapshot, profile)
    return f"{prefix}\n\n{_json_snapshot(payload)}"


def build_decision_only_user_message(snapshot: dict[str, Any], profile: dict[str, Any] | None = None) -> str:
    return build_snapshot_user_message(snapshot, profile)
