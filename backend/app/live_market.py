"""On-demand Finnhub quotes for validated stock tickers."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from threading import Lock

import requests

_cache: dict[str, tuple[float, dict]] = {}
_lock = Lock()
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def valid_symbol(symbol: str) -> bool:
    """Accept ticker-shaped input, but never pass arbitrary text to Finnhub."""
    return bool(_SYMBOL.fullmatch(symbol.strip().upper()))


def live_quote(symbol: str) -> dict:
    symbol = symbol.strip().upper()
    if not valid_symbol(symbol):
        raise ValueError("Enter a valid stock ticker.")
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Live quotes are not configured. Set FINNHUB_API_KEY on the server.")
    now = time.time()
    with _lock:
        cached = _cache.get(symbol)
        if cached and now - cached[0] < 30:
            return cached[1]
    response = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol},
        headers={"X-Finnhub-Token": token},
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    price = data.get("c")
    if not isinstance(price, (int, float)) or price <= 0:
        raise RuntimeError(f"Finnhub did not return a current quote for {symbol}.")
    timestamp = data.get("t")
    result = {
        "symbol": symbol,
        "price": price,
        "change": data.get("d"),
        "change_pct": data.get("dp"),
        "previous_close": data.get("pc"),
        "open": data.get("o"),
        "high": data.get("h"),
        "low": data.get("l"),
        "market_timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "provider": "Finnhub",
    }
    with _lock:
        _cache[symbol] = (now, result)
    return result
