"""detect_impulse_pullback — Impuls, Abweisung, Rückbruch.

Meldet Tatsachen, keine Bewertung: wie groß der Impuls war, welches Level er
gebrochen hat, ob der Kurs durch dieses Level zurückgefallen ist und wie weit
die Rückgabe schon gelaufen ist. Was das wert ist, gehört in den Prompt, wo es
sichtbar und änderbar ist — nicht als Prozentzahl in den Code.

Die Erkennung ist dieselbe wie im Backtest, der die Variante gemessen hat:
Impuls von mindestens `impulse_atr` ATR innerhalb von `impulse_candles` Kerzen,
das Level ist der letzte Swing-Punkt vor dem Impuls zwischen Start und Extrem,
und der Rückbruch ist der erste Schluss auf der anderen Seite dieses Levels.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, fetch_candles

# Vorgabe, nicht Gesetz: als Argument ueberschreibbar. 14 ist der uebliche
# Wert, aber der Indikator-Baustein im PTJ-Profil rechnet mit 7 — wer die
# beiden vergleichen will, muss dieselbe Periode einstellen koennen.
_ATR_PERIOD_DEFAULT = 14
_PRE_LOOKBACK = 60          # Kerzen vor dem Impuls, in denen das Level gesucht wird


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class DetectImpulsePullbackTool(BaseTool):
    name = "detect_impulse_pullback"
    description = (
        "Detect the impulse/pullback constellation on the trading timeframe: a move of at "
        "least N ATR, the level that move broke through, whether price has since fallen back "
        "through that level, and how much of the move has been given back so far. Reports "
        "measurements only — impulse size in ATR, the level, the origin, the 50% mark and the "
        "retracement reached — so the decision stays with the agent. Returns state 'none' when "
        "no impulse is present, 'rejected' when the impulse stalled but the level still holds, "
        "and 'break_confirmed' once price has closed back through it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name."},
            "pair": {"type": "string", "description": "Currency pair, e.g. EURUSD."},
            "timeframe": {
                "type": "string",
                "description": "Trading timeframe the impulse is read on. Default M5.",
                "enum": ["M5", "M15", "M30", "H1"],
                "default": "M5",
            },
            "impulse_atr": {
                "type": "number",
                "description": "How many ATR the move must span to count as an impulse. Default 3.0.",
                "minimum": 1.0,
                "default": 3.0,
            },
            "impulse_candles": {
                "type": "integer",
                "description": "Within how many candles that span must occur. Default 8.",
                "minimum": 2,
                "maximum": 30,
                "default": 8,
            },
            "atr_period": {
                "type": "integer",
                "description": (
                    "ATR period the impulse size is measured against. Default 14. "
                    "Set it to match whatever other block you want to compare against — "
                    "the snapshot's own atr_m15 block uses 7."
                ),
                "minimum": 2,
                "maximum": 200,
                "default": 14,
            },
            "wait_candles": {
                "type": "integer",
                "description": "How many candles after the extreme the setup stays valid. Default 24.",
                "minimum": 1,
                "maximum": 100,
                "default": 24,
            },
        },
        "required": ["timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        timeframe = str(arguments.get("timeframe") or "M5").upper()
        impulse_atr = float(arguments.get("impulse_atr") or 3.0)
        impulse_candles = int(arguments.get("impulse_candles") or 8)
        wait_candles = int(arguments.get("wait_candles") or 24)
        atr_period = int(arguments.get("atr_period") or _ATR_PERIOD_DEFAULT)

        need = _PRE_LOOKBACK + impulse_candles + wait_candles + atr_period + 5
        candles = await fetch_candles(context, timeframe, min(need, 500))
        if len(candles) < _PRE_LOOKBACK + impulse_candles + atr_period:
            return {"state": "none", "reason": "not enough candles", "candles": len(candles)}

        import pandas as pd
        from scipy.signal import find_peaks

        df = pd.DataFrame(candles)
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        df = df.reset_index(drop=True)

        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(atr_period).mean().iloc[-1])
        if not atr or atr != atr:
            return {"state": "none", "reason": "atr unavailable"}

        pip = 0.01 if (context.pair or "").upper().endswith("JPY") else 0.0001
        price = float(df["close"].iloc[-1])

        # Den jüngsten Impuls suchen: Fenster, das am Extrem endet.
        best = None
        for end in range(len(df) - 1, max(len(df) - 1 - wait_candles, impulse_candles), -1):
            win = df.iloc[end - impulse_candles:end + 1]
            span = win["high"].max() - win["low"].min()
            if span < impulse_atr * atr:
                continue
            lo_i, hi_i = win["low"].idxmin(), win["high"].idxmax()
            up = hi_i > lo_i
            extreme_i = hi_i if up else lo_i
            if extreme_i < end - 1:
                continue
            best = (extreme_i, up, float(win["low"].min() if up else win["high"].max()))
            break
        if best is None:
            return {"state": "none", "atr_pips": round(atr / pip, 1), "current_price": price}

        extreme_i, up, origin = best
        extreme = float(df.loc[extreme_i, "high" if up else "low"])

        pre = df.iloc[max(0, extreme_i - _PRE_LOOKBACK):max(0, extreme_i - impulse_candles)]
        level = None
        if len(pre) >= 15:
            if up:
                idx, _ = find_peaks(pre["high"].values)
                cands = [c for c in (float(pre["high"].values[j]) for j in idx) if origin < c < extreme]
                level = max(cands) if cands else None
            else:
                idx, _ = find_peaks(-pre["low"].values)
                cands = [c for c in (float(pre["low"].values[j]) for j in idx) if extreme < c < origin]
                level = min(cands) if cands else None

        move = abs(extreme - origin)
        target_50 = extreme - move * 0.5 if up else extreme + move * 0.5
        retraced = (extreme - price) / move if up else (price - extreme) / move

        after = df.iloc[extreme_i + 1:]
        broke_out = bool(len(after) and ((up and (after["close"] > extreme).any())
                                         or (not up and (after["close"] < extreme).any())))
        break_confirmed = bool(
            level is not None and len(after)
            and ((up and (after["close"] < level).any()) or (not up and (after["close"] > level).any()))
        )
        state = "none" if broke_out else ("break_confirmed" if break_confirmed else "rejected")

        return {
            "state": state,
            "direction_of_impulse": "up" if up else "down",
            "trade_side_if_taken": "SELL" if up else "BUY",
            "impulse_atr": round(move / atr, 2),
            "impulse_pips": round(move / pip, 1),
            "candles_since_extreme": int(len(df) - 1 - extreme_i),
            "origin": round(origin, 5),
            "extreme": round(extreme, 5),
            "level_broken_by_impulse": round(level, 5) if level is not None else None,
            "target_50_percent": round(target_50, 5),
            "retraced_percent": round(retraced * 100, 1),
            "atr_pips": round(atr / pip, 1),
            "atr_period": atr_period,
            "current_price": price,
        }
