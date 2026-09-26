"""Build a full Story for one symbol, end to end."""
from __future__ import annotations

import re
from datetime import date, timedelta

from ..cache import load, save
from ..connections import connections
from ..config import STORY_LOOKBACK_DAYS
from ..sources import edgar, news, prices
from ..universe import get as get_company
from . import evidence as ev
from .detect import significant_moves
from .generate import narrate
from .schema import Story


def _story_key(symbol: str) -> str:
    return f"story_{symbol}"


def _mentions(company, text: str) -> bool:
    names = [company.symbol, company.name.split(",")[0], *company.aliases]
    return any(re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE) for n in names if len(n) > 2)


def rank_news(company, items: list[dict]) -> list[dict]:
    """Articles that name the company in the headline first, then in the
    summary, then the rest; newest first within each group. A two-day window
    for a heavily covered stock holds ~250 articles, many of them market
    roundups, and only the first few become evidence."""
    def score(item: dict) -> int:
        if _mentions(company, item["headline"]):
            return 2
        return 1 if _mentions(company, item.get("summary", "")) else 0
    return sorted(items, key=lambda i: (score(i), i["published_at"]), reverse=True)


def news_for_move(company, move_date: str, recent_news: list[dict]) -> list[dict]:
    """News evidence for one move: the move day and the day before.

    Finnhub's free tier caps each request at ~250 articles, so the single
    recent-news request only reaches back a few days for heavily covered
    stocks. A request for the move's own dates reaches older moves. If that
    request fails, the move falls back to whatever recent news covers it.
    """
    lo = (date.fromisoformat(move_date) - timedelta(days=1)).isoformat()
    candidates = news.news_near(recent_news, move_date, window_days=1)
    try:
        candidates += news.news_between(company.symbol, lo, move_date)
    except Exception:
        pass
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for item in rank_news(company, candidates):
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        merged.append({**item, "via": news.SOURCE_NAME})
    return merged


def build_story(
    symbol: str,
    days: int = STORY_LOOKBACK_DAYS,
    portfolio_context: dict | None = None,
) -> Story:
    company = get_company(symbol)
    symbol = company.symbol

    bars = prices.daily_bars(symbol, days)
    # Peers are the companies the knowledge graph connects this one to.
    links = {c.symbol: c for c in connections(symbol)}
    peer_bars = {}
    for peer in links:
        try:
            peer_bars[peer] = prices.daily_bars(peer, days)
        except Exception:
            continue  # a missing peer weakens the sector signal but is survivable

    moves = significant_moves(bars, peer_bars)
    for move in moves:
        # Say how each peer is connected, so the explanation can name it:
        # "fell the same day its supplier TSMC fell 6%".
        move["peer_relations"] = {
            peer: {"relationship": links[peer].label, "detail": links[peer].detail,
                   "source": links[peer].source}
            for peer in move["peer_moves"]
        }

    warnings: list[str] = []
    try:
        all_news = news.company_news(symbol, days)
    except Exception as exc:
        all_news = []
        warnings.append(f"News unavailable ({exc}); explanations will be thinner.")

    try:
        all_filings = edgar.recent_filings(symbol)
    except Exception as exc:
        all_filings = []
        warnings.append(f"SEC filings unavailable ({exc}).")

    try:
        fundamentals = edgar.quarterly_fundamentals(symbol)
    except Exception as exc:
        fundamentals = {}
        warnings.append(f"SEC fundamentals unavailable ({exc}).")

    evidence_by_move = {
        move["date"]: ev.bundle_for_move(
            symbol, move,
            news_for_move(company, move["date"], all_news),
            all_filings,
        )
        for move in moves
    }
    extra = {item.id: item for item in ev.fundamental_evidence(symbol, fundamentals)}
    # Sector backdrop supports the arc, not any single beat.
    extra.update({item.id: item
                  for item in ev.sector_evidence(symbol, company.sector)})

    if not moves:
        return Story(
            symbol=symbol, company_name=company.name,
            generated_at="", bars=bars, beats=[],
            evidence=extra,
            arc=f"{company.name} had no single-day move over the threshold in the "
                f"last {days} days.",
            warnings=warnings,
        )

    narration = narrate(
        symbol, company.name, moves, evidence_by_move,
        extra_evidence=extra, portfolio_context=portfolio_context,
    )

    return Story(
        symbol=symbol,
        company_name=company.name,
        generated_at=narration["generated_at"],
        bars=bars,
        beats=narration["beats"],
        evidence=narration["evidence"],
        arc=narration["arc"],
        arc_citation_ids=narration["arc_citation_ids"],
        warnings=warnings + narration["warnings"],
    )


def get_story(symbol: str, refresh: bool = False) -> Story:
    """Serve the precomputed story. plans.md requires the demo not depend on
    live calls, so the API reads the cache and only builds on a miss."""
    symbol = get_company(symbol).symbol
    if not refresh:
        cached_story = load(_story_key(symbol))
        if cached_story is not None:
            return Story.model_validate(cached_story)

    story = build_story(symbol)
    save(_story_key(symbol), story.model_dump(mode="json"))
    return story
