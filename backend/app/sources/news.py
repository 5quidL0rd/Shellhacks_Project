"""Company news from Finnhub.

This is the citation workhorse: every item carries a publisher URL the investor
can click straight through to. Free tier is 60 calls/minute, and one call
covers a whole date range for one symbol, so the whole universe costs 5 calls.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from ..cache import cached
from ..config import FINNHUB_API_KEY

SOURCE_NAME = "Finnhub company news"
_ENDPOINT = "https://finnhub.io/api/v1/company-news"


def _fetch(symbol: str, start: str, end: str) -> list[dict]:
    if not FINNHUB_API_KEY:
        raise RuntimeError("FINNHUB_API_KEY is not set; add it to backend/.env")
    response = requests.get(
        _ENDPOINT,
        params={"symbol": symbol, "from": start, "to": end, "token": FINNHUB_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Finnhub payload for {symbol}: {payload!r}")
    return payload


def company_news(symbol: str, days: int = 180) -> list[dict]:
    """Normalised news, newest first. Items with no URL are dropped: an
    uncitable article cannot support a claim in the story."""
    end = date.today()
    start = end - timedelta(days=days)
    raw = cached(
        f"news_{symbol}_{start.isoformat()}_{end.isoformat()}",
        lambda: _fetch(symbol, start.isoformat(), end.isoformat()),
        max_age_seconds=6 * 3600,
    )

    items: list[dict] = []
    from datetime import datetime, timezone

    for entry in raw:
        url = entry.get("url")
        if not url:
            continue
        stamp = entry.get("datetime")
        if not stamp:
            continue
        published = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        items.append({
            "headline": (entry.get("headline") or "").strip(),
            "summary": (entry.get("summary") or "").strip(),
            "publisher": entry.get("source") or "unknown",
            "url": url,
            "published_at": published.isoformat(),
            "date": published.date().isoformat(),
        })
    items.sort(key=lambda i: i["published_at"], reverse=True)
    return items


def news_near(items: list[dict], target_date: str, window_days: int = 1) -> list[dict]:
    """News published on the move date or shortly before it.

    A one-day lookback matters because a Sunday press release moves Monday's
    price, and an after-hours print moves the next session.
    """
    from datetime import date as _date

    target = _date.fromisoformat(target_date)
    lo = target - timedelta(days=window_days)
    return [i for i in items if lo <= _date.fromisoformat(i["date"]) <= target]
