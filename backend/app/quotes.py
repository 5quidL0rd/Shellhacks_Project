"""Brokerage-style quote facts for each supported company, as of the last close.

Prices come from the precomputed stories (data/cache/story_*.json), the same
daily bars Story Mode charts, so quotes never trigger a live download during
the demo and always agree with the charts. Everything here is a plain fact
(price, change, range, volume); nothing is a recommendation.
"""
from __future__ import annotations

from .cache import load
from .universe import SYMBOLS

SPARKLINE_DAYS = 30
# Trading days per period; "6M" is the whole saved window (~6 months).
PERIODS = {"1W": 5, "1M": 21, "3M": 63}


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 3) if old else None


def quote_from_bars(symbol: str, bars: list[dict]) -> dict | None:
    """Quote facts from daily bars, oldest first. None if there are too few."""
    if len(bars) < 2:
        return None
    last, prev = bars[-1], bars[-2]
    closes = [b["close"] for b in bars]
    returns = {name: _pct(last["close"], bars[-1 - n]["close"])
               for name, n in PERIODS.items() if len(bars) > n}
    returns["6M"] = _pct(last["close"], bars[0]["close"])
    recent = bars[-31:-1] or bars[:-1]  # the 30 sessions before the last one
    avg_volume = sum(b["volume"] for b in recent) / len(recent)
    return {
        "symbol": symbol,
        "as_of": last["date"],
        "price": last["close"],
        "prev_close": prev["close"],
        "change": round(last["close"] - prev["close"], 4),
        "change_pct": _pct(last["close"], prev["close"]),
        "returns": returns,
        "range": {"low": min(closes), "high": max(closes), "days": len(bars),
                  "from": bars[0]["date"], "to": last["date"]},
        "volume": last["volume"],
        "volume_vs_avg": round(last["volume"] / avg_volume, 2) if avg_volume else None,
        "sparkline": [{"date": b["date"], "close": b["close"]} for b in bars[-SPARKLINE_DAYS:]],
    }


def quotes(symbols: list[str] | None = None) -> dict:
    """Quotes for the requested supported symbols (all by default). Symbols
    without a saved story are listed in `missing` instead of failing."""
    wanted = [s for s in (symbols or SYMBOLS) if s in SYMBOLS]
    out, missing = {}, []
    for symbol in wanted:
        story = load(f"story_{symbol}")
        q = quote_from_bars(symbol, story["bars"]) if story else None
        if q:
            out[symbol] = q
        else:
            missing.append(symbol)
    as_of = max((q["as_of"] for q in out.values()), default=None)
    return {"as_of": as_of, "quotes": out, "missing": missing}
