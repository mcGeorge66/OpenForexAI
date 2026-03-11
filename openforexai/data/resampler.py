from __future__ import annotations

from datetime import datetime, timedelta, timezone

from openforexai.models.market import Candle

_TF_MINUTES: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _bucket_start(ts: datetime, target_mins: int) -> datetime:
    """Floor *ts* down to the nearest *target_mins* boundary (UTC)."""
    total_mins = int((ts - _EPOCH).total_seconds() / 60)
    bucketed_mins = (total_mins // target_mins) * target_mins
    return _EPOCH + timedelta(minutes=bucketed_mins)


def resample_candles(candles: list[Candle], target_tf: str) -> list[Candle]:
    """Aggregate *candles* (oldest-first) into *target_tf* OHLCV bars.

    The source timeframe is inferred from ``candles[0].timeframe``.
    *target_tf* must have an integer-multiple relationship with the source
    (e.g. M5 → M15, M5 → M30, M5 → H1, M15 → H1).

    Returns an empty list when *candles* is empty.
    """
    if not candles:
        return []

    source_tf = candles[0].timeframe
    source_mins = _TF_MINUTES.get(source_tf)
    target_mins = _TF_MINUTES.get(target_tf)

    if source_mins is None:
        raise ValueError(f"Unknown source timeframe: {source_tf!r}")
    if target_mins is None:
        raise ValueError(f"Unknown target timeframe: {target_tf!r}")
    if target_mins <= source_mins:
        raise ValueError(
            f"Cannot resample {source_tf} → {target_tf}: target must be larger"
        )
    if target_mins % source_mins != 0:
        raise ValueError(
            f"target_tf {target_tf} ({target_mins}m) is not an integer multiple "
            f"of source {source_tf} ({source_mins}m)"
        )

    buckets: dict[datetime, list[Candle]] = {}
    for c in candles:
        key = _bucket_start(c.timestamp, target_mins)
        buckets.setdefault(key, []).append(c)

    result: list[Candle] = []
    for key in sorted(buckets):
        group = buckets[key]
        result.append(
            Candle(
                timestamp=key,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                # tick_volume: sum all source-bar counts — proxy for total activity
                tick_volume=sum(c.tick_volume for c in group),
                # spread: closing bar's spread — represents end-of-period liquidity
                spread=group[-1].spread,
                timeframe=target_tf,
            )
        )
    return result

