"""Tool: chartshot — render a candlestick chart as a PNG image (backend, no browser).

Always writes a file to disk and returns an image marker string so the LLM
adapter can inject the image automatically:

    output_mode: keep  →  image[path]     file is kept after the LLM call
    output_mode: temp  →  imagetmp[path]  file is deleted after the LLM call
"""
from __future__ import annotations

import io
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext

_log = logging.getLogger(__name__)

_VALID_TIMEFRAMES = {"M5", "M15", "M30", "H1", "H4", "D1"}
_TF_MINUTES: dict[str, int] = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
_OSCILLATOR_NAMES = {"RSI", "ATR", "SLOPE_E", "SLOPE_S"}


def _load_chartshot_cfg(config_name: str) -> tuple[str, str, dict[str, Any]]:
    """Return (output_dir, output_mode, named_config) from system.json5 chartshot block."""
    path = Path(__file__).parents[3] / "config" / "system.json5"
    try:
        import json5
        data = json5.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("chartshot: could not load system.json5: %s", exc)
        data = {}

    cs = data.get("chartshot", {}) if isinstance(data, dict) else {}
    output_dir = str(cs.get("output_dir", "data/chartshots"))
    configs = cs.get("configs", {})
    named = configs.get(config_name) or configs.get("default") or {}
    output_mode = str(named.get("output_mode", "temp"))
    return output_dir, output_mode, named


def _make_mpf_style(style: str) -> Any:
    """Build a mplfinance style with standard red/green candles."""
    import mplfinance as mpf

    mc = mpf.make_marketcolors(
        up='#00b050', down='#e03030',
        edge='inherit', wick='inherit',
        volume={'up': '#00b050', 'down': '#e03030'},
    )
    if style == 'dark':
        return mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc)
    else:
        return mpf.make_mpf_style(
            base_mpf_style='default',
            marketcolors=mc,
            facecolor='white',
            figcolor='white',
            gridcolor='#bbbbbb',
            gridstyle=':',
            gridaxis='both',
        )


def _compute_xticks(df: Any, timeframe: str) -> tuple[list[int], list[str]]:
    """Return (positions, labels) aligned to clean time boundaries."""
    tf = timeframe.upper()
    interval_min: int | None = {
        'M5': 60, 'M15': 120, 'M30': 240, 'H1': 480, 'H4': 1440, 'D1': None,
    }.get(tf, 60)

    positions: list[int] = []
    labels: list[str] = []

    for i, dt in enumerate(df.index):
        if interval_min is None:
            if dt.weekday() == 0:
                positions.append(i)
                labels.append(dt.strftime('%d.%m.%Y'))
        else:
            total_min = dt.hour * 60 + dt.minute
            if total_min % interval_min == 0:
                positions.append(i)
                if tf in ('H4', 'D1'):
                    labels.append(dt.strftime('%d.%m.%Y'))
                else:
                    labels.append(dt.strftime('%d.%m %H:%M'))

    return positions, labels


def _candles_to_dataframe(candles: list) -> Any:
    """Convert candle dicts (from get_candles) to a mplfinance-compatible DataFrame."""
    import pandas as pd

    rows = []
    for c in candles:
        ts = c.get("timestamp")
        if isinstance(ts, str):
            ts = ts.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
        elif isinstance(ts, datetime):
            dt = ts
        else:
            continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.replace(tzinfo=None)

        rows.append({
            "Date":   dt,
            "Open":   float(c.get("open", 0)),
            "High":   float(c.get("high", 0)),
            "Low":    float(c.get("low", 0)),
            "Close":  float(c.get("close", 0)),
            "Volume": float(c.get("tick_volume") or 0),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Date").sort_index()
    return df


# ─── Indicator helpers ────────────────────────────────────────────────────────

def _linestyle_str(style_int: int) -> str:
    """Map LineStyle enum int (from frontend) to matplotlib linestyle string."""
    return {0: '-', 1: '--', 2: '--', 3: ':', 4: ':'}.get(int(style_int), '-')


def _align_to_df(df: Any, values: list) -> Any:
    """Align indicator values to df.index using ffill (handles cross-timeframe)."""
    import numpy as np
    import pandas as pd

    if not values:
        return np.full(len(df), np.nan)

    idx: list[datetime] = []
    vals: list[float] = []

    for v in values:
        if isinstance(v, dict):
            ts  = v.get("timestamp") or v.get("time")
            val = v.get("value")
        else:
            ts  = getattr(v, "timestamp", None)
            val = getattr(v, "value", None)

        if ts is None or val is None or not isinstance(val, (int, float)):
            continue
        if isinstance(ts, str):
            ts = ts.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
        elif isinstance(ts, datetime):
            dt = ts
        else:
            continue

        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        idx.append(dt)
        vals.append(float(val))

    if not idx:
        return np.full(len(df), np.nan)

    ind_series = pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
    aligned = (
        ind_series
        .reindex(df.index.union(ind_series.index))
        .sort_index()
        .ffill()
        .reindex(df.index)
    )
    return aligned.values


def _align_bb_to_df(df: Any, values: list) -> tuple[Any, Any, Any]:
    """Split BB values (upper/middle/lower dicts) and align each to df.index."""
    upper_raw: list = []
    middle_raw: list = []
    lower_raw: list = []

    for v in values:
        if isinstance(v, dict):
            ts  = v.get("timestamp") or v.get("time")
            val = v.get("value")
        else:
            ts  = getattr(v, "timestamp", None)
            val = getattr(v, "value", None)

        if not isinstance(val, dict):
            continue
        upper_raw.append({"timestamp": ts, "value": val.get("upper", 0)})
        middle_raw.append({"timestamp": ts, "value": val.get("middle", 0)})
        lower_raw.append({"timestamp": ts, "value": val.get("lower", 0)})

    return (
        _align_to_df(df, upper_raw),
        _align_to_df(df, middle_raw),
        _align_to_df(df, lower_raw),
    )


# ─── Async data fetchers ──────────────────────────────────────────────────────

async def _fetch_indicators(
    indicators: list[dict],
    candle_count: int,
    timeframe: str,
    context: ToolContext,
) -> list[tuple[dict, list]]:
    """Fetch indicator data for each visible indicator config."""
    from openforexai.tools import DEFAULT_REGISTRY

    calc_tool = DEFAULT_REGISTRY.get("calculate_indicator")
    if not calc_tool:
        _log.warning("chartshot: calculate_indicator not registered, skipping indicators")
        return []

    chart_min = candle_count * _TF_MINUTES.get(timeframe, 5)
    results: list[tuple[dict, list]] = []

    for ind in indicators:
        if not ind.get("visible", True):
            continue
        name   = str(ind.get("name", "")).upper()
        period = max(0, int(ind.get("period", 20)))
        ind_tf = str(ind.get("timeframe", timeframe)).upper()
        smooth = max(1, int(ind.get("smooth_period") or ind.get("smoothPeriod") or 1))

        history = min(500, max(10, int(chart_min / _TF_MINUTES.get(ind_tf, 60)) + period))

        args: dict[str, Any] = {
            "indicator": name,
            "period":    period,
            "timeframe": ind_tf,
            "history":   history,
        }
        if smooth > 1:
            args["smooth_period"] = smooth

        try:
            result = await calc_tool.execute(args, context)
            values = result.get("values") if isinstance(result, dict) else []
            results.append((ind, values or []))
        except Exception as exc:
            _log.warning("chartshot: indicator %s failed: %s", name, exc)

    return results


async def _fetch_swing_levels(
    swing_cfg: dict,
    candle_count: int,
    timeframe: str,
    context: ToolContext,
) -> dict | None:
    """Fetch swing levels if enabled in the swing config."""
    if not swing_cfg.get("enabled"):
        return None

    from openforexai.tools import DEFAULT_REGISTRY

    swing_tool = DEFAULT_REGISTRY.get("get_swing_levels")
    if not swing_tool:
        _log.warning("chartshot: get_swing_levels not registered, skipping swing levels")
        return None

    chart_min = candle_count * _TF_MINUTES.get(timeframe, 5)
    swing_tf  = str(swing_cfg.get("timeframe", "H1")).upper()
    lookback  = max(10, int(chart_min / _TF_MINUTES.get(swing_tf, 60)))

    args: dict[str, Any] = {
        "timeframe":    swing_tf,
        "max_levels":   int(swing_cfg.get("count", 5)),
        "lookback":     lookback,
        "atr_period":   int(swing_cfg.get("atr_period", 14)),
        "min_gap_atr":  float(swing_cfg.get("min_gap_atr", 0.3)),
        "price_source": str(swing_cfg.get("price_source", "HL")),
        "sort_by":      str(swing_cfg.get("sort_by", "nearest")),
    }

    try:
        return await swing_tool.execute(args, context)
    except Exception as exc:
        _log.warning("chartshot: swing levels failed: %s", exc)
        return None


# ─── Tool ─────────────────────────────────────────────────────────────────────

class ChartShotTool(BaseTool):
    name = "chartshot"
    description = (
        "Render a candlestick chart as a PNG image for a given pair and timeframe. "
        "Returns a file path and image marker for LLM context injection. "
        "Indicators and swing levels from the named config are rendered automatically."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: M5 | M15 | M30 | H1 | H4 | D1",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "candles": {
                "type": "integer",
                "description": "Number of candles to render (10–500). Default: 200.",
                "minimum": 10, "maximum": 500,
            },
            "pair": {
                "type": "string",
                "description": "Currency pair override, e.g. EURUSD. Defaults to agent pair.",
            },
            "filename": {
                "type": "string",
                "description": "Output filename (without path). Auto-generated if omitted.",
            },
            "config": {
                "type": "string",
                "description": "Named chartshot config from system.json5 chartshot.configs. Default: 'default'.",
            },
        },
        "required": ["timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        import asyncio
        from time import perf_counter as _perf
        import numpy as np
        import mplfinance as mpf
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from openforexai.tools import DEFAULT_REGISTRY

        timeframe     = str(arguments.get("timeframe", "M5")).upper()
        candle_count  = max(10, min(int(arguments.get("candles") or 200), 500))
        config_name   = str(arguments.get("config") or "default")
        pair_override = str(arguments.get("pair") or "").strip().upper() or None
        filename_arg  = arguments.get("filename")
        _cs_started   = _perf()

        if timeframe not in _VALID_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(sorted(_VALID_TIMEFRAMES))}"
            )

        # Load named config from system.json5
        output_dir, output_mode, named_cfg = _load_chartshot_cfg(config_name)
        style       = str(named_cfg.get("style", "dark"))
        description = str(
            arguments.get("_description_override")
            or named_cfg.get("description")
            or ""
        ).strip()

        # Resolve effective pair
        effective_pair = pair_override or context.pair
        if not effective_pair:
            raise RuntimeError("pair not set — provide via argument or agent context")

        _bus = context.event_bus
        if _bus is not None:
            from openforexai.models.messaging import AgentMessage, EventType
            try:
                await _bus.publish(AgentMessage(
                    event_type=EventType.CHARTSHOT_START,
                    source_agent_id=context.agent_id,
                    instrument=effective_pair,
                    payload={"agent_id": context.agent_id,
                             "timeframe": timeframe, "candles": candle_count},
                ), triggered_by=context.triggering_message)
            except Exception:
                pass

        # ── Fetch candles ─────────────────────────────────────────────────────
        get_candles = DEFAULT_REGISTRY.get("get_candles")
        if get_candles is None:
            raise RuntimeError("get_candles tool is not registered")

        effective_ctx = replace(context, pair=effective_pair) if pair_override else context
        candle_data = await get_candles.execute(
            {"timeframe": timeframe, "count": candle_count},
            effective_ctx,
        )

        if not candle_data:
            raise RuntimeError(f"No candle data returned for {effective_pair} {timeframe}")

        # ── Build DataFrame ───────────────────────────────────────────────────
        df = _candles_to_dataframe(candle_data)
        if df.empty:
            raise RuntimeError("Candle data could not be parsed into a DataFrame")

        candle_from = df.index[0].isoformat()
        candle_to   = df.index[-1].isoformat()

        # ── Resolve indicator / swing configs ─────────────────────────────────
        # _indicators_override / _swing_levels_override are passed by the UI preview
        # when it wants the current (unsaved) config applied.
        indicators_cfg: list[dict] = (
            arguments.get("_indicators_override")  # type: ignore[assignment]
            or named_cfg.get("indicators")
            or []
        )
        swing_cfg: dict = (
            arguments.get("_swing_levels_override")  # type: ignore[assignment]
            or named_cfg.get("swing_levels")
            or {}
        )

        # ── Fetch indicator data and swing levels concurrently ────────────────
        ind_data_result, swing_result = await asyncio.gather(
            _fetch_indicators(indicators_cfg, candle_count, timeframe, effective_ctx),
            _fetch_swing_levels(swing_cfg, candle_count, timeframe, effective_ctx),
            return_exceptions=True,
        )
        ind_data: list[tuple[dict, list]] = ind_data_result if not isinstance(ind_data_result, Exception) else []
        swing_data: dict | None = swing_result if not isinstance(swing_result, Exception) else None
        if isinstance(ind_data_result, Exception):
            _log.warning("chartshot: indicator fetch error: %s", ind_data_result)
        if isinstance(swing_result, Exception):
            _log.warning("chartshot: swing level fetch error: %s", swing_result)

        # ── Build mplfinance addplots ─────────────────────────────────────────
        addplots: list[Any] = []
        osc_types_seen: list[str] = []   # ordered unique oscillator types → panel index

        for ind_cfg, values in ind_data:
            if not values:
                continue
            name  = str(ind_cfg.get("name", "")).upper()
            color = str(ind_cfg.get("color", "#10b981"))
            ls    = _linestyle_str(int(ind_cfg.get("line_style", 0)))
            lw    = float(ind_cfg.get("line_width", 1))

            if name in _OSCILLATOR_NAMES:
                if name not in osc_types_seen:
                    osc_types_seen.append(name)
                panel_idx = 2 + osc_types_seen.index(name)
                arr = _align_to_df(df, values)
                if np.all(np.isnan(arr)):
                    continue
                addplots.append(mpf.make_addplot(arr, panel=panel_idx, color=color, linestyle=ls, width=lw))

            elif name == "BB":
                upper, middle, lower = _align_bb_to_df(df, values)
                if np.all(np.isnan(middle)):
                    continue
                addplots.append(mpf.make_addplot(upper,  panel=0, color=color, linestyle='--', width=lw))
                addplots.append(mpf.make_addplot(middle, panel=0, color=color, linestyle=ls,   width=lw))
                addplots.append(mpf.make_addplot(lower,  panel=0, color=color, linestyle='--', width=lw))

            else:
                # EMA, SMA, VWAP → overlay on price panel
                arr = _align_to_df(df, values)
                if np.all(np.isnan(arr)):
                    continue
                addplots.append(mpf.make_addplot(arr, panel=0, color=color, linestyle=ls, width=lw))

        # ── Render chart via mplfinance ───────────────────────────────────────
        last_ts = df.index[-1].strftime('%Y-%m-%d %H:%M')
        title   = f"{effective_pair} · {timeframe} · {len(df)} candles · latest: {last_ts}"

        n_osc_panels = len(osc_types_seen)
        plot_kwargs: dict[str, Any] = dict(
            type="candle",
            style=_make_mpf_style(style),
            volume=True,
            title=title,
            figsize=(14, 7),
            returnfig=True,
        )
        if addplots:
            plot_kwargs["addplot"] = addplots
        if n_osc_panels > 0:
            plot_kwargs["panel_ratios"] = (6, 1) + (2,) * n_osc_panels

        fig, axes = mpf.plot(df, **plot_kwargs)

        # Remove y-axis labels (Volume / Price) — they add no value in the PNG
        for ax in fig.axes:
            ax.set_ylabel('')

        # Apply clean x-axis ticks
        tick_pos, tick_labels = _compute_xticks(df, timeframe)
        if tick_pos:
            for ax in fig.axes:
                ax.set_xticks(tick_pos)
                ax.set_xticklabels([])
            fig.axes[-1].set_xticklabels(tick_labels, rotation=30, ha='right', fontsize=7)

        # ── Draw swing levels as horizontal lines ─────────────────────────────
        if isinstance(swing_data, dict):
            sw_ls = _linestyle_str(int(swing_cfg.get("line_style", 1)))
            sw_lw = float(swing_cfg.get("line_width", 2))
            ax0   = axes[0]
            for level in (swing_data.get("highs") or []):
                ax0.axhline(level["price"], color='#10b981', linestyle=sw_ls, linewidth=sw_lw, alpha=0.85)
            for level in (swing_data.get("lows") or []):
                ax0.axhline(level["price"], color='#ef4444', linestyle=sw_ls, linewidth=sw_lw, alpha=0.85)
            for level in (swing_data.get("confluence") or []):
                ax0.axhline(level["price"], color='#f97316', linestyle=sw_ls, linewidth=min(sw_lw + 1, 5), alpha=0.85)

        buf = io.BytesIO()
        fig.savefig(buf, dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        png_bytes = buf.read()
        buf.close()

        # ── Auto filename ─────────────────────────────────────────────────────
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = filename_arg or f"{effective_pair}_{timeframe}_{len(df)}_{ts_str}.png"

        # ── Write file ────────────────────────────────────────────────────────
        root    = Path(__file__).parents[3]
        out_dir = root / output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / safe_filename
        out_path.write_bytes(png_bytes)
        _log.info("chartshot: saved %s", out_path)

        rel_path    = out_path.relative_to(root).as_posix()
        marker_type = "imagetmp" if output_mode == "temp" else "image"
        image_marker = f"{marker_type}[{rel_path}]"

        result: dict[str, Any] = {
            "pair":         effective_pair,
            "timeframe":    timeframe,
            "candles":      len(df),
            "config":       config_name,
            "candle_from":  candle_from,
            "candle_to":    candle_to,
            "file_path":    str(out_path),
            "image_marker": image_marker,
        }
        result["description"] = description

        if _bus is not None:
            from openforexai.models.messaging import AgentMessage, EventType
            try:
                await _bus.publish(AgentMessage(
                    event_type=EventType.CHARTSHOT_END,
                    source_agent_id=context.agent_id,
                    instrument=effective_pair,
                    payload={"agent_id": context.agent_id, "success": True,
                             "elapsed_ms": round((_perf() - _cs_started) * 1000, 1),
                             "image_marker": image_marker},
                ), triggered_by=context.triggering_message)
            except Exception:
                pass

        return result
