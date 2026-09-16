"""Fill the market-key tables from the stored candles.

Run once per parameter set; re-running is safe (INSERT OR REPLACE on
timestamp + param_set) and only rewrites what it recomputes.

    .venv/Scripts/python.exe scripts/backfill_market_keys.py --list
    .venv/Scripts/python.exe scripts/backfill_market_keys.py --broker OXS_T --pair USDJPY
    .venv/Scripts/python.exe scripts/backfill_market_keys.py --all --lookback 24
    .venv/Scripts/python.exe scripts/backfill_market_keys.py --all --gaps
    .venv/Scripts/python.exe scripts/backfill_market_keys.py --broker OXS_T --pair USDJPY --verify 80

`--gaps` reports closed candles that have no key row, `--verify N` re-asks the
running system for N random stored rows and compares. Use them when a number
looks wrong: a table that disagrees with the tool is worse than no table,
because then the agent decides on one value and the analysis reports another.
Both mismatches found while building this — a one-candle shift and a wrong
higher-timeframe bar count — were caught exactly this way and by nothing else.

Only closed candles exist in history, so nothing here has to guess at
completeness — unlike the live path, where the trailing bar is still growing.

A row's `timestamp` is the moment the key becomes valid, i.e. the close time
of the newest candle it is built from. Looking up "the key at time X" is
therefore the largest timestamp <= X, and it returns exactly what the live
agent would have computed at X.

The higher timeframe is resampled once for the whole series instead of per
candle: computing it inside the loop made a single key cost ~10 ms, almost all
of it re-aggregating the same 450 candles over and over.
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openforexai.data.market_keys import (
    CREATE_SQL,
    INSERT_SQL,
    keys_table,
    param_set,
    row_for,
)
from openforexai.tools.market._fopok_core import FopokInputError, compute_fopok
from openforexai.tools.market.swing_levels import compute_swing_levels
from openforexai.models.market import Candle
from decimal import Decimal
from openforexai.tools.market._fomak_core import (
    EMA_STATE_PERIOD,
    FomakInputError,
    compute_fomak,
    warmup_for,
)

DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "openforexai.db")
TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

# FOPOK settings, taken from the live snapshot profile Paul_Tudor_Jones_V1.
# Changing them here without changing them there would store a key the agent
# never sees — the parameter set in the row makes that visible, not harmless.
FOPOK_TF, FOPOK_HIGHER = "M15", "H1"
FOPOK_LOOKBACK, FOPOK_PROM_ATR, FOPOK_ATR_PERIOD = 100, 0.25, 14


def series_tables(con: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """(broker, pair, timeframe) for every candle table, ignoring key tables."""
    out = []
    for (name,) in con.execute(
        "select name from sqlite_master where type='table' and name not like '%\\_keys' escape '\\'"
    ):
        parts = name.split("_")
        if len(parts) < 3 or parts[-1] not in TF_MINUTES:
            continue
        out.append(("_".join(parts[:-2]), parts[-2], parts[-1]))
    return sorted(out)


def resample(m5: list[dict], minutes: int) -> list[dict]:
    """Aggregate M5 rows into *minutes* bars, keeping the bar's own open time."""
    out: list[dict] = []
    cur: dict | None = None
    for c in m5:
        slot = int(c["_t"] // (minutes * 60)) * minutes * 60
        if cur is None or cur["_slot"] != slot:
            if cur:
                out.append(cur)
            cur = {"_slot": slot, "timestamp": c["timestamp"], "open": c["open"],
                   "high": c["high"], "low": c["low"], "close": c["close"],
                   "tick_volume": c["tick_volume"]}
        else:
            cur["high"] = max(float(cur["high"]), float(c["high"]))
            cur["low"] = min(float(cur["low"]), float(c["low"]))
            cur["close"] = c["close"]
            cur["tick_volume"] = int(cur["tick_volume"] or 0) + int(c["tick_volume"] or 0)
    if cur:
        out.append(cur)
    return out


def as_candles(rows: list[dict], timeframe: str) -> list:
    """dicts -> Candle objects, the shape compute_swing_levels expects."""
    return [
        Candle(
            timestamp=datetime.fromisoformat(r["timestamp"]),
            open=Decimal(str(r["open"])), high=Decimal(str(r["high"])),
            low=Decimal(str(r["low"])), close=Decimal(str(r["close"])),
            tick_volume=int(r["tick_volume"] or 0), spread=Decimal("0"),
            timeframe=timeframe,
        )
        for r in rows
    ]


def fopok_at(levels_tf: list, levels_higher: list, price: float) -> tuple:
    """(code, raw) or (None, None) when a barrier is missing.

    Runs the tool's own computation — compute_swing_levels is the function
    GetSwingLevelsTool calls, not a copy of it.
    """
    own = compute_swing_levels(
        levels_tf, timeframe=FOPOK_TF, lookback=FOPOK_LOOKBACK,
        current_price=price, current_price_source="M5",
        prominence_atr=FOPOK_PROM_ATR, atr_period=FOPOK_ATR_PERIOD,
    )
    hi = compute_swing_levels(
        levels_higher, timeframe=FOPOK_HIGHER, lookback=FOPOK_LOOKBACK,
        current_price=price, current_price_source="M5",
        prominence_atr=FOPOK_PROM_ATR, atr_period=FOPOK_ATR_PERIOD,
    )
    try:
        res = compute_fopok(
            current_price=price,
            nearest_resistance=own.get("nearest_resistance"),
            nearest_support=own.get("nearest_support"),
            atr=own.get("atr") or 0.0,
            higher_resistance=hi.get("nearest_resistance"),
            higher_support=hi.get("nearest_support"),
        )
    except FopokInputError:
        return None, None
    return res.get("fopok"), res.get("raw_values")


def backfill(con: sqlite3.Connection, broker: str, pair: str, timeframe: str,
             lookback: int, higher: str, dry: bool) -> None:
    src = f"{broker}_{pair}_{timeframe}"
    rows = con.execute(
        f"select timestamp, open, high, low, close, tick_volume from {src} "
        "where cast(close as real) != 0 order by timestamp"
    ).fetchall()
    if not rows:
        print(f"{src}: keine Kerzen")
        return
    m5 = [{"timestamp": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4],
           "tick_volume": r[5], "_t": datetime.fromisoformat(r[0]).timestamp()} for r in rows]

    hi_minutes = TF_MINUTES[higher]
    hi_bars = resample(m5, hi_minutes)
    hi_times = [b["_slot"] for b in hi_bars]
    import bisect

    # FOPOK reads two other timeframes. Resampled once for the whole series
    # instead of per candle — the same reason the higher timeframe above is.
    f_tf = resample(m5, TF_MINUTES[FOPOK_TF])
    f_hi = resample(m5, TF_MINUTES[FOPOK_HIGHER])
    f_tf_times = [b["_slot"] for b in f_tf]
    f_hi_times = [b["_slot"] for b in f_hi]
    f_tf_c = as_candles(f_tf, FOPOK_TF)
    f_hi_c = as_candles(f_hi, FOPOK_HIGHER)

    warm = warmup_for()
    need = lookback + warm
    params = param_set(timeframe=timeframe, lookback_candles=lookback, higher_timeframe=higher)
    table = keys_table(broker, pair, timeframe)

    print(f"{src}: {len(m5)} Kerzen, Parametersatz {params}")
    if dry:
        print("   Probelauf, nichts geschrieben")
        return

    con.execute(CREATE_SQL.format(table=table))
    out, failed, t0 = [], 0, time.perf_counter()
    for i in range(need, len(m5) + 1):
        window = m5[i - lookback:i]
        warmup = m5[i - need:i - lookback]
        end_t = window[-1]["_t"]
        # Higher-timeframe bars strictly up to the window's end. The bar the
        # window's last candle sits in is only complete when the window ends on
        # its final candle — otherwise it would be a partial bar, the exact
        # thing the live path now refuses to use.
        j = bisect.bisect_right(hi_times, end_t)
        if j and hi_times[j - 1] + hi_minutes * 60 > end_t + 300:
            j -= 1
        # Exactly as many higher-timeframe bars as the tool requests
        # (EMA_STATE_PERIOD + 10). More bars change the EMA and with it the
        # alignment character — that was the single mismatch in a 40-point
        # spot check against the live tool.
        higher_bars = hi_bars[max(0, j - (EMA_STATE_PERIOD + 10)):j]
        if len(higher_bars) < 25:
            continue
        try:
            res = compute_fomak(window, warmup, higher_bars)
        except FomakInputError:
            failed += 1
            continue
        # The row is stamped with the moment the key becomes VALID — the close
        # time of the last candle in the window, not that candle's open time.
        # This is the tool's own meaning: asked with anchor T it uses candles
        # closed by T, so the candle opening at T (still forming at T) is not
        # in it. Stamping the open time instead shifts the whole table one
        # candle against the live path, which a 25-point spot check caught:
        # 17 of 25 matched, and every mismatch was this exact swap.
        valid_from = datetime.fromtimestamp(
            window[-1]["_t"] + TF_MINUTES[timeframe] * 60, UTC,
        ).isoformat()
        # FOPOK on the same moment: only bars closed by end_t, same rule as
        # everything else here.
        fopok = fopok_raw = None
        a = bisect.bisect_right(f_tf_times, end_t)
        if a and f_tf_times[a - 1] + TF_MINUTES[FOPOK_TF] * 60 > end_t + 300:
            a -= 1
        b = bisect.bisect_right(f_hi_times, end_t)
        if b and f_hi_times[b - 1] + TF_MINUTES[FOPOK_HIGHER] * 60 > end_t + 300:
            b -= 1
        if a >= 20 and b >= 20:
            fopok, fopok_raw = fopok_at(
                f_tf_c[max(0, a - FOPOK_LOOKBACK):a],
                f_hi_c[max(0, b - FOPOK_LOOKBACK):b],
                float(window[-1]["close"]),
            )
        out.append(row_for(
            timestamp=valid_from, params=params, fomak=res["fomak"],
            raw_values=res.get("raw_values"), computed_at=datetime.now(UTC).isoformat(),
            fopok=fopok, fopok_raw=fopok_raw,
        ))
        if len(out) >= 5000:
            con.executemany(INSERT_SQL.format(table=table), out)
            con.commit()
            print(f"   {i - need + 1}/{len(m5) - need + 1} ...", flush=True)
            out = []
    if out:
        con.executemany(INSERT_SQL.format(table=table), out)
        con.commit()
    n = con.execute(f"select count(*) from {table} where param_set=?", (params,)).fetchone()[0]
    nf = con.execute(f"select count(*) from {table} where param_set=? and fopok is not null",
                     (params,)).fetchone()[0]
    print(f"   fertig in {time.perf_counter()-t0:.0f}s — {n} Zeilen, davon {nf} mit FOPOK"
          + (f", {failed} nicht berechenbar" if failed else ""))


def report_gaps(con, broker: str, pair: str, timeframe: str,
                lookback: int, higher: str) -> None:
    """Closed candles with no key row — a gap is a silent hole otherwise."""
    params = param_set(timeframe=timeframe, lookback_candles=lookback, higher_timeframe=higher)
    table, src = keys_table(broker, pair, timeframe), f"{broker}_{pair}_{timeframe}"
    exists = con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
    if not exists:
        print(f"{src}: keine Schluesseltabelle")
        return
    rows = con.execute(
        f"select count(*) from {src} where cast(close as real)!=0").fetchone()[0]
    have = con.execute(
        f"select count(*), min(timestamp), max(timestamp) from {table} where param_set=?",
        (params,)).fetchone()
    missing = con.execute(
        f"""select count(*) from {src} c where cast(c.close as real)!=0
            and c.timestamp >= (select min(timestamp) from {table} where param_set=?)
            and not exists (select 1 from {table} k where k.param_set=?
                            and k.timestamp = strftime('%Y-%m-%dT%H:%M:%S+00:00',
                                                       c.timestamp, '+{TF_MINUTES[timeframe]} minutes'))""",
        (params, params)).fetchone()[0]
    nofopok = con.execute(
        f"select count(*) from {table} where param_set=? and fopok is null", (params,)).fetchone()[0]
    span = con.execute(
        f"select min(timestamp), max(timestamp) from {table} where param_set=? and fopok is null",
        (params,)).fetchone()
    print(f"{src}: {rows} Kerzen | {have[0]} Schluessel {str(have[1])[:16]}..{str(have[2])[:16]}")
    if nofopok:
        print(f"   ohne FOPOK: {nofopok} ({str(span[0])[:16]}..{str(span[1])[:16]})")
    if missing:
        print(f"   ACHTUNG: {missing} Kerzen im abgedeckten Zeitraum ohne Schluessel")


def verify(con, broker: str, pair: str, timeframe: str,
           lookback: int, higher: str, n: int) -> None:
    """Ask the running system for the same moments and compare."""
    import json as _json
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    params = param_set(timeframe=timeframe, lookback_candles=lookback, higher_timeframe=higher)
    table = keys_table(broker, pair, timeframe)
    rows = con.execute(
        f"select timestamp, fomak from {table} where param_set=? order by random() limit ?",
        (params, n)).fetchall()
    if not rows:
        print(f"{table}: nichts gespeichert")
        return
    agent = f"{broker}-{pair}-AA-PTJ"

    def ask(r):
        body = _json.dumps({"tool_name": "compute_fomak", "arguments": {
            "timeframe": timeframe, "lookback_candles": lookback,
            "higher_timeframe": higher, "anchor": r[0]}, "agent_id": agent}).encode()
        req = urllib.request.Request("http://localhost:7654/tools/execute", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return r[0], r[1], (_json.loads(resp.read()).get("result") or {}).get("fomak", "")
        except Exception as exc:
            return r[0], r[1], f"FEHLER {type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(ask, rows))
    ok = sum(1 for _, a, b in res if a == b)
    print(f"{table}: {ok} von {len(res)} stimmen mit dem laufenden System ueberein")
    for ts, a, b in res:
        if a != b:
            print(f"   {ts[:16]}: Tabelle {a}, System {b}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker")
    ap.add_argument("--pair")
    ap.add_argument("--timeframe", default="M5")
    ap.add_argument("--lookback", type=int, default=24)
    ap.add_argument("--higher", default="M30")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gaps", action="store_true",
                    help="report closed candles without a key row")
    ap.add_argument("--verify", type=int, metavar="N",
                    help="compare N random stored rows against the running system")
    a = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    tables = series_tables(con)
    if a.list:
        for b, p, tf in tables:
            n = con.execute(f"select count(*) from {b}_{p}_{tf}").fetchone()[0]
            print(f"   {b:8s} {p:8s} {tf:4s} {n:7d} Kerzen")
        return
    targets = [t for t in tables if t[2] == a.timeframe.upper()]
    if not a.all:
        if not (a.broker and a.pair):
            ap.error("--broker und --pair, oder --all, oder --list")
        targets = [t for t in targets
                   if t[0].upper() == a.broker.upper() and t[1].upper() == a.pair.upper()]
        if not targets:
            ap.error(f"keine Tabelle fuer {a.broker} {a.pair} {a.timeframe}")
    for b, p, tf in targets:
        if a.gaps:
            report_gaps(con, b, p, tf, a.lookback, a.higher.upper())
        elif a.verify:
            verify(con, b, p, tf, a.lookback, a.higher.upper(), a.verify)
        else:
            backfill(con, b, p, tf, a.lookback, a.higher.upper(), a.dry_run)
    con.close()


if __name__ == "__main__":
    main()
