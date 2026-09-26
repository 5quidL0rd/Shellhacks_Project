"""Company news from Finnhub.

This is the citation workhorse: every item carries a publisher URL the investor
can click straight through to. Free tier is 60 calls/minute and ~250 articles
per call. Story Mode makes one recent-news call per company plus one call per
move date (about 13 per company per build); past windows are cached for good.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

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


# Finnhub's free tier returns at most ~250 articles per request, newest first,
# within the requested date range. One 180-day request therefore covers only
# the last few days for heavily covered companies; asking for each move's own
# dates (news_between) reaches the news around older moves.
_MIN_SECONDS_BETWEEN_CALLS = 1.1  # stays under the 60 calls/minute free limit
_last_call = 0.0


def _paced_fetch(symbol: str, start: str, end: str, retries: int = 4) -> list[dict]:
    global _last_call
    for attempt in range(retries):
        wait = _MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            return _fetch(symbol, start, end)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429 and attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    return []


def _normalise(raw: list[dict]) -> list[dict]:
    """Newest first. Items with no URL are dropped: an uncitable article
    cannot support a claim in the story."""
    items: list[dict] = []
    for entry in raw:
        url = entry.get("url")
        stamp = entry.get("datetime")
        if not url or not stamp:
            continue
        published = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        items.append({
            "id": entry.get("id"),
            "category": entry.get("category") or "",
            "headline": (entry.get("headline") or "").strip(),
            "summary": (entry.get("summary") or "").strip(),
            "publisher": entry.get("source") or "unknown",
            "url": url,
            "published_at": published.isoformat(),
            "date": published.date().isoformat(),
        })
    items.sort(key=lambda i: i["published_at"], reverse=True)
    return items


def company_news(symbol: str, days: int = 180) -> list[dict]:
    """The ~250 most recent articles in the last `days` days."""
    end = date.today()
    start = end - timedelta(days=days)
    raw = cached(
        f"news_{symbol}_{start.isoformat()}_{end.isoformat()}",
        lambda: _paced_fetch(symbol, start.isoformat(), end.isoformat()),
        max_age_seconds=6 * 3600,
    )
    return _normalise(raw)


def news_between(symbol: str, start: str, end: str) -> list[dict]:
    """News published between two ISO dates (inclusive), up to ~250 articles.

    A window that ended before today cannot change, so it is cached for good;
    one that includes today is refreshed every few hours.
    """
    max_age = None if date.fromisoformat(end) < date.today() else 6 * 3600
    raw = cached(
        f"news_{symbol}_{start}_{end}",
        lambda: _paced_fetch(symbol, start, end),
        max_age_seconds=max_age,
    )
    return _normalise(raw)


def news_near(items: list[dict], target_date: str, window_days: int = 1) -> list[dict]:
    """News published on the move date or shortly before it.

    A one-day lookback matters because a Sunday press release moves Monday's
    price, and an after-hours print moves the next session.
    """
    from datetime import date as _date

    target = _date.fromisoformat(target_date)
    lo = target - timedelta(days=window_days)
    return [i for i in items if lo <= _date.fromisoformat(i["date"]) <= target]
