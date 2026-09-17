"""Filling the reporting database from production, incrementally.

One function, used by both callers: the DataContainer in the background and
the repair tool by hand. Two implementations of the same copy would drift, and
a reporting copy that disagrees with production is worse than none.

Incremental by watermark per table. A restart, a crash or a week of downtime
all look the same to it: everything after the watermark is missing, so
everything after the watermark is written. That is the automatic repair — not
a special mode, just what the normal path does.

Nothing here raises at the caller. A failure is recorded in `sync_state` and
logged; the next pass tries again from the same watermark.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from openforexai.data import reporting_db as rdb
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

#: Rows per table per pass. The container's loop is sequential and the repair
#: tool has all the time in the world, so the cap only shapes latency, never
#: completeness — the watermark picks up where the pass stopped.
BATCH = 20_000


def _prod(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def pairs_in(prod: sqlite3.Connection) -> list[tuple[str, str]]:
    """(broker, pair) for every M5 candle table in production."""
    out = []
    for (name,) in prod.execute(
        "select name from sqlite_master where type='table' and name like '%\\_M5' escape '\\'"
    ):
        parts = name.split("_")
        if len(parts) >= 3:
            out.append(("_".join(parts[:-2]), parts[-2]))
    return sorted(set(out))


def sync_m5(prod, rep, broker: str, pair: str) -> int:
    """Copy new M5 candles. The base every other timeframe is built from."""
    src = rdb.table_name(broker, pair, "M5")
    rep.execute(rdb.CANDLE_SQL.format(table=src))
    mark = rdb.watermark(rep, src)
    rows = prod.execute(
        f"select timestamp, open, high, low, close, tick_volume, spread from {src} "
        + ("where timestamp > ? " if mark else "")
        + "order by timestamp limit ?",
        ((mark, BATCH) if mark else (BATCH,)),
    ).fetchall()
    if not rows:
        return 0
    rep.executemany(
        f"INSERT OR REPLACE INTO {src} "
        "(timestamp, open, high, low, close, tick_volume, spread) VALUES (?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )
    total = rep.execute(f"select count(*) from {src}").fetchone()[0]
    rdb.set_state(rep, src, rows[-1]["timestamp"], total)
    return len(rows)


def sync_derived(prod, rep, broker: str, pair: str, timeframe: str) -> int:
    """Materialise one higher timeframe from the mirrored M5.

    Uses production's own resampler, so a bar here and a bar the agent sees
    are the same bar. Only complete bars are written: the newest bucket is
    still filling as long as M5 has not reached its end.
    """
    from openforexai.data.resampler import resample_candles
    from openforexai.models.market import Candle

    src = rdb.table_name(broker, pair, "M5")
    dst = rdb.table_name(broker, pair, timeframe)
    rep.execute(rdb.CANDLE_SQL.format(table=dst))
    minutes = rdb.TF_MINUTES[timeframe]
    mark = rdb.watermark(rep, dst)

    # Re-read from one bar before the watermark: the bar at the watermark may
    # have been incomplete when it was written.
    since = None
    if mark:
        from datetime import timedelta
        since = (datetime.fromisoformat(mark) - timedelta(minutes=minutes)).isoformat()
    rows = rep.execute(
        f"select timestamp, open, high, low, close, tick_volume, spread from {src} "
        + ("where timestamp >= ? " if since else "")
        + "order by timestamp",
        ((since,) if since else ()),
    ).fetchall()
    if len(rows) < 2:
        return 0

    candles = [
        Candle(
            timestamp=datetime.fromisoformat(r["timestamp"]),
            open=_dec(r["open"]), high=_dec(r["high"]), low=_dec(r["low"]),
            close=_dec(r["close"]), tick_volume=int(r["tick_volume"] or 0),
            spread=_dec(r["spread"]), timeframe="M5",
        )
        for r in rows
    ]
    bars = resample_candles(candles, timeframe)
    if not bars:
        return 0
    # Drop the newest bar unless M5 actually reaches its end.
    from datetime import timedelta
    last_m5 = candles[-1].timestamp + timedelta(minutes=5)
    if bars[-1].timestamp + timedelta(minutes=minutes) > last_m5:
        bars = bars[:-1]
    if not bars:
        return 0

    rep.executemany(
        f"INSERT OR REPLACE INTO {dst} "
        "(timestamp, open, high, low, close, tick_volume, spread) VALUES (?,?,?,?,?,?,?)",
        [(b.timestamp.isoformat(), str(b.open), str(b.high), str(b.low), str(b.close),
          int(b.tick_volume or 0), str(b.spread)) for b in bars],
    )
    total = rep.execute(f"select count(*) from {dst}").fetchone()[0]
    rdb.set_state(rep, dst, bars[-1].timestamp.isoformat(), total)
    return len(bars)


def sync_keys(prod, rep, broker: str, pair: str) -> int:
    """Mirror the market keys so a sweep needs one database, not two."""
    src = rdb.table_name(broker, pair, "M5") + "_keys"
    exists = prod.execute(
        "select 1 from sqlite_master where type='table' and name=?", (src,)
    ).fetchone()
    if not exists:
        return 0
    rep.execute(rdb.KEYS_SQL.format(table=src))
    mark = rdb.watermark(rep, src)
    rows = prod.execute(
        f"select timestamp, param_set, fomak, fomak_text, fopok, fopok_text, "
        f"raw_values, computed_at from {src} "
        + ("where timestamp > ? " if mark else "")
        + "order by timestamp limit ?",
        ((mark, BATCH) if mark else (BATCH,)),
    ).fetchall()
    if not rows:
        return 0
    rep.executemany(
        f"INSERT OR REPLACE INTO {src} (timestamp, param_set, fomak, fomak_text, "
        "fopok, fopok_text, raw_values, computed_at) VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )
    total = rep.execute(f"select count(*) from {src}").fetchone()[0]
    rdb.set_state(rep, src, rows[-1]["timestamp"], total)
    return len(rows)


def sync_trades(prod, rep) -> int:
    """One flat row per trade, with the market state at entry already joined.

    Every analysis so far did this join by hand and each one had to get the
    "largest key timestamp <= entry" rule right on its own.
    """
    import bisect
    import json

    rep.execute(rdb.TRADES_SQL.format())
    keyseries: dict[str, tuple[list[float], list[sqlite3.Row]]] = {}

    def keys_for(broker: str, pair: str):
        if pair not in keyseries:
            tbl = rdb.table_name(broker, pair, "M5") + "_keys"
            try:
                rows = rep.execute(
                    f"select timestamp, fomak, fopok from {tbl} order by timestamp"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            keyseries[pair] = (
                [datetime.fromisoformat(r["timestamp"]).timestamp() for r in rows], rows,
            )
        return keyseries[pair]

    # The candle the entry fell into, for its spread. Trade authorisation is
    # meant to hang on the FOMAK group and the spread, so the spread has to be
    # measurable per trade — this is where that number comes from.
    spreadseries: dict[str, tuple[list[float], list[sqlite3.Row]]] = {}

    def spread_for(broker: str, pair: str):
        if pair not in spreadseries:
            tbl = rdb.table_name(broker, pair, "M5")
            try:
                rows = rep.execute(
                    f"select timestamp, spread from {tbl} order by timestamp"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            spreadseries[pair] = (
                [datetime.fromisoformat(r["timestamp"]).timestamp() for r in rows], rows,
            )
        return spreadseries[pair]

    written = 0
    for r in prod.execute(
        """select broker_order_id, broker_name, pair, direction, requested_at, opened_at,
                  closed_at, units, fill_price, stop_loss, take_profit, close_price,
                  close_reason, pnl_pips, pnl_account_currency, market_context_snapshot
           from order_book_entries where broker_order_id is not null"""
    ):
        at = r["requested_at"] or r["opened_at"]
        if not at:
            continue
        times, rows = keys_for(r["broker_name"], r["pair"])
        fomak = fopok = None
        if times:
            i = bisect.bisect_right(times, datetime.fromisoformat(at).timestamp()) - 1
            if i >= 0:
                fomak, fopok = rows[i]["fomak"], rows[i]["fopok"]
        stimes, srows = spread_for(r["broker_name"], r["pair"])
        spread = None
        if stimes:
            j = bisect.bisect_right(stimes, datetime.fromisoformat(at).timestamp()) - 1
            if j >= 0:
                spread = _f(srows[j]["spread"])

        trig = stop = target = None
        try:
            snap = json.loads(r["market_context_snapshot"] or "{}") or {}
            plan = json.loads(snap.get("analyst_recommendation_raw") or "{}")
            side = plan.get("short_case" if r["direction"] == "SELL" else "long_case") or {}
            trig = _f(side.get("trigger_level")) or _f(side.get("entry_zone"))
            stop, target = _f(side.get("stop_loss")), _f(side.get("take_profit"))
        except Exception:
            pass
        rep.execute(
            "INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["broker_order_id"], r["pair"], r["direction"], at, r["opened_at"],
             r["closed_at"], _f(r["units"]), _f(r["fill_price"]), _f(r["stop_loss"]),
             _f(r["take_profit"]), _f(r["close_price"]), r["close_reason"],
             _f(r["pnl_pips"]), _f(r["pnl_account_currency"]),
             trig, stop, target, fomak, fopok, spread),
        )
        written += 1
    rdb.set_state(rep, "trades", None, written)
    return written


def sync_all(prod_path: str | Path, rep_path: str | Path | None = None) -> dict[str, int]:
    """One full pass. Never raises — a reporting copy must not cost a candle."""
    counts: dict[str, int] = {}
    try:
        prod = _prod(prod_path)
        pairs = pairs_in(prod)
    except Exception as exc:
        # Missing, locked or corrupt production file. Nothing to mirror this
        # round; the next pass tries again from the same watermarks.
        _log.warning("Reporting sync could not read production — skipping this pass",
                     error=str(exc))
        return counts
    rep = rdb.connect(rep_path)
    try:
        for broker, pair in pairs:
            try:
                counts[f"{pair} M5"] = sync_m5(prod, rep, broker, pair)
                for tf in rdb.TIMEFRAMES[1:]:
                    counts[f"{pair} {tf}"] = sync_derived(prod, rep, broker, pair, tf)
                counts[f"{pair} keys"] = sync_keys(prod, rep, broker, pair)
                rep.commit()
            except Exception as exc:
                rep.rollback()
                rdb.set_state(rep, rdb.table_name(broker, pair, "M5"), None, 0, str(exc))
                rep.commit()
                _log.warning("Reporting sync failed for a pair — continuing",
                             pair=pair, error=str(exc))
        try:
            counts["trades"] = sync_trades(prod, rep)
            rep.commit()
        except Exception as exc:
            rep.rollback()
            rdb.set_state(rep, "trades", None, 0, str(exc))
            rep.commit()
            _log.warning("Reporting sync failed for trades — continuing", error=str(exc))
    finally:
        rep.close()
        prod.close()
    return counts


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dec(v: Any):
    from decimal import Decimal
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")
