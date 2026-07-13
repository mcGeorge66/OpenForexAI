"""Tool: get_news — retrieve economic calendar events for the current pair."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import json5

from openforexai.tools.base import BaseTool, ToolContext

_log = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "system.json5"


def _load_system_config() -> dict[str, Any]:
    try:
        return json5.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("Could not load system.json5: %s", exc)
        return {}


def _split_pair(symbol: str) -> list[str]:
    s = symbol.upper().replace("/", "").replace("_", "").replace("-", "")
    if len(s) >= 6:
        return [s[:3], s[3:6]]
    return [s]


class GetNewsTool(BaseTool):
    name = "get_news"
    description = (
        "Retrieve economic calendar events relevant to the current currency pair. "
        "Fetches events from the MQL5 economic calendar JSON written by MetaTrader "
        "and enriches each event with the full detail page from mql5.com. "
        "Returns a Markdown document with all matching events."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "hoursBack": {
                "type": "number",
                "description": "Hours before now (broker time) to include. Default: 1.",
                "default": 1,
            },
            "hoursFor": {
                "type": "number",
                "description": "Hours after now (broker time) to include. Default: 4.",
                "default": 4,
            },
            "pair": {
                "type": "string",
                "description": "Currency pair, e.g. EURUSD. Falls back to context pair when omitted.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.adapters.news.mql5_calendar_lib import (
            create_events_markdown,
            find_event_ids,
        )

        cfg = _load_system_config()
        system_cfg = cfg.get("system", {})

        utc_offset_hours: int = int(system_cfg.get("broker_candle_utc_offset_hours", 3))
        news_cfg: dict = system_cfg.get("news", {})

        json_file = news_cfg.get("economic_calendar_file", "")
        if not json_file:
            raise RuntimeError(
                "system.news.economic_calendar_file is not configured in system.json5"
            )

        output_dir = Path(
            news_cfg.get(
                "output_dir",
                str(_PROJECT_ROOT / "data" / "news"),
            )
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        hours_back: float = float(arguments.get("hoursBack") or 1)
        hours_for: float = float(arguments.get("hoursFor") or 4)
        symbol: str = (
            str(arguments.get("pair") or "").strip()
            or (context.pair or "")
        )
        if not symbol:
            raise RuntimeError("pair not provided and not set in tool context")

        broker_tz = timezone(timedelta(hours=utc_offset_hours))
        now_broker = datetime.now(tz=broker_tz)
        time_from = now_broker - timedelta(hours=hours_back)
        time_to = now_broker + timedelta(hours=hours_for)

        currencies = _split_pair(symbol)

        # find_event_ids parses a JSON file and create_events_markdown performs
        # blocking HTTP requests to mql5.com (one per event). Run them in a worker
        # thread so the shared asyncio event loop is never frozen for the duration.
        event_ids = await asyncio.to_thread(
            find_event_ids,
            json_file=json_file,
            time_op="between",
            time_from=time_from,
            time_to=time_to,
            currencies=currencies,
        )

        if not event_ids:
            return (
                f"No economic calendar events found for {symbol.upper()} "
                f"between {time_from.strftime('%Y-%m-%d %H:%M')} and "
                f"{time_to.strftime('%Y-%m-%d %H:%M')} (UTC+{utc_offset_hours})."
            )

        ts_str = now_broker.strftime("%Y%m%d_%H%M%S")
        out_file = output_dir / f"{symbol.upper()}_{ts_str}.md"

        await asyncio.to_thread(
            create_events_markdown,
            json_file=json_file,
            event_ids=event_ids,
            out_file=out_file,
        )

        return await asyncio.to_thread(out_file.read_text, encoding="utf-8")
