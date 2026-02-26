from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from openforexai.models.market import Candle


def normalize_candle(raw: dict[str, Any], pair: str, timeframe: str) -> Candle:
    """Convert broker-specific OHLCV dict to a canonical Candle."""
    from datetime import datetime, timezone

    ts = raw.get("time") or raw.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, tz=timezone.utc)

    return Candle(
        timestamp=ts,
        open=Decimal(str(raw.get("open") or raw["o"])),
        high=Decimal(str(raw.get("high") or raw["h"])),
        low=Decimal(str(raw.get("low") or raw["l"])),
        close=Decimal(str(raw.get("close") or raw["c"])),
        volume=int(raw.get("volume", 0) or raw.get("v", 0)),
        timeframe=timeframe,
    )


async def retry_async(coro_fn, attempts: int = 3, base_delay: float = 1.0):
    """Retry an async callable with exponential back-off."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    raise RuntimeError(f"All {attempts} attempts failed") from last_exc
