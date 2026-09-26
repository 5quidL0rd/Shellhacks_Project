"""Build a full Story for one symbol, end to end."""
from __future__ import annotations

from ..cache import load, save
from ..config import STORY_LOOKBACK_DAYS
from ..sources import edgar, news, prices
from ..universe import get as get_company
from . import evidence as ev
from .detect import significant_moves
from .generate import narrate
from .schema import Story


def _story_key(symbol: str) -> str:
    return f"story_{symbol}"


def news_for_move(move_date: str, finnhub_news: list[dict]) -> list[dict]:
    """News evidence for one move date.

    Finnhub is the only news source. Its free tier returns roughly the last
    three days regardless of the date range requested, so older moves get no
    news here and are explained from price, peer and SEC filing evidence
    instead - or reported as unexplained. Adding a historical news provider is
    the single change that would most improve explanation quality; this
    function is the seam for it.
    """
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for item in news.news_near(finnhub_news, move_date, window_days=1):
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
    peer_bars = {}
    for peer in company.peers:
        try:
            peer_bars[peer] = prices.daily_bars(peer, days)
        except Exception:
            continue  # a missing peer weakens the sector signal but is survivable

    moves = significant_moves(bars, peer_bars)

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
            news_for_move(move["date"], all_news),
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
