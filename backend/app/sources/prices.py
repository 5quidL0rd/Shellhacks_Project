"""Daily OHLCV from Yahoo via yfinance.

Unofficial and unkeyed, so it can break without warning. Everything is cached
and the shape below is the only thing the rest of the app depends on, which
keeps a swap to Finnhub or FMP to a single file.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..cache import cached
from ..config import STORY_LOOKBACK_DAYS

SOURCE_NAME = "Yahoo Finance (via yfinance)"


def _source_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{symbol}/history"


def _fetch(symbol: str, days: int) -> list[dict]:
    import yfinance as yf

    start = date.today() - timedelta(days=days + 10)  # pad for weekends/holidays
    frame = yf.Ticker(symbol).history(start=start.isoformat(), interval="1d",
                                      auto_adjust=False)
    if frame.empty:
        raise RuntimeError(f"yfinance returned no rows for {symbol}")

    frame = frame.reset_index()
    rows: list[dict] = []
    for _, row in frame.iterrows():
        rows.append({
            "date": row["Date"].date().isoformat(),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        })
    return rows


def daily_bars(symbol: str, days: int = STORY_LOOKBACK_DAYS) -> list[dict]:
    """Bars oldest-first, each with a percent change against the prior close."""
    rows = cached(f"prices_{symbol}_{days}", lambda: _fetch(symbol, days),
                  max_age_seconds=6 * 3600)
    for prev, cur in zip(rows, rows[1:]):
        prior = prev["close"]
        cur["pct_change"] = round((cur["close"] - prior) / prior * 100, 3) if prior else 0.0
        cur["prev_close"] = prior
    if rows:
        rows[0].setdefault("pct_change", 0.0)
        rows[0].setdefault("prev_close", rows[0]["open"])
    return rows


def average_volume(bars: list[dict], window: int = 30) -> float:
    tail = bars[-window:] or bars
    return sum(b["volume"] for b in tail) / len(tail) if tail else 0.0
