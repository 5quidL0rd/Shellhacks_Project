"""Turn each company's recent news into a few cited "events" with Gemini.

Runs ahead of time (scripts.build_feed), like Story Mode, so the feed serves
from a saved file and never makes a live call during the demo. Events describe
what happened to one company and do not depend on anyone's portfolio; why an
event matters to a particular portfolio is worked out later from the knowledge
graph (feed/rank.py), without AI.

Same citation contract as Story Mode: Gemini sees numbered articles, never
URLs, and must cite the articles each event rests on. Citations to articles we
did not supply are dropped, and an event left with none is discarded.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from google import genai
from google.genai import types

from ..cache import load, save
from ..config import GEMINI_API_KEY, GEMINI_MODEL
from ..sources import news
from ..story.build import _mentions, rank_news
from ..universe import COMPANIES, get as get_company

FEED_KEY = "feed_events"
WINDOW_DAYS = 7          # "what changed" = the last week of coverage
MAX_ARTICLES = 40        # per company, after ranking by relevance
MAX_EVENTS = 5           # per company

EVENT_TYPES = ["earnings", "guidance", "product", "supply_chain", "regulation",
               "legal", "deal", "analyst", "management", "market_move", "other"]

_SYSTEM = """You summarise a week of news about one public company for experienced investors.

You receive the company and a numbered list of articles (id, date, publisher,
headline, summary). Group articles that report the same development into one
event, and return up to {max_events} of the most material events.

Hard rules:
- Use ONLY the articles supplied. Never add facts, figures, or context from
  outside knowledge.
- Every event must list the article ids it rests on in citation_ids.
- Skip generic market roundups, listicles, and "should you buy" pieces unless
  they report a concrete development about this company.
- NEVER advise buying, selling, or holding, and never predict prices or call
  a stock cheap, expensive, or a good or bad investment. Describe what happened.
- headline: under 80 characters, concrete, no hype.
- summary: 1-2 plain sentences on what happened, naming the key figures the
  articles give.
- tone: how the development reads for the company itself: "positive",
  "negative", "mixed", or "neutral". Describe the news, not the stock.
- importance: "high" for earnings, guidance, major deals, regulation, supply
  disruptions, or anything that clearly moved the business; "medium" for notable
  but smaller news; "low" for minor items.
- Order events from most to least important.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "event_type": {"type": "string", "enum": EVENT_TYPES},
                    "tone": {"type": "string", "enum": ["positive", "negative", "mixed", "neutral"]},
                    "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["headline", "summary", "event_type", "tone", "importance",
                             "citation_ids"],
            },
        },
    },
    "required": ["events"],
}


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set; add it to .env")
    return genai.Client(api_key=GEMINI_API_KEY)


def recent_articles(symbol: str, items: list[dict], as_of: date) -> list[dict]:
    """The last WINDOW_DAYS of articles that actually concern the company,
    most relevant first, one per URL."""
    company = get_company(symbol)
    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    in_window = [i for i in items if start <= date.fromisoformat(i["date"]) <= as_of]
    about = [i for i in in_window
             if _mentions(company, i["headline"]) or _mentions(company, i.get("summary", ""))]
    seen, out = set(), []
    for item in rank_news(company, about):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        out.append(item)
    return out[:MAX_ARTICLES]


def verify_events(raw: list[dict], articles: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Keep events whose citations point at supplied articles; drop the rest."""
    kept, warnings = [], []
    for event in raw:
        good = [c for c in event.get("citation_ids", []) if c in articles]
        invented = set(event.get("citation_ids", [])) - set(good)
        if invented:
            warnings.append(f"dropped uncitable reference(s) {sorted(invented)}")
        if not good:
            warnings.append(f"removed an uncited event: {event.get('headline', '')[:60]}")
            continue
        kept.append({**event, "citation_ids": good})
    return kept, warnings


def events_for(symbol: str, articles: list[dict]) -> tuple[list[dict], list[str]]:
    """Ask Gemini to group one company's articles into cited events."""
    if not articles:
        return [], []
    company = get_company(symbol)
    numbered = {f"a{i}": a for i, a in enumerate(articles)}
    payload = {
        "company": {"symbol": symbol, "name": company.name},
        "articles": [{"id": aid, "date": a["date"], "publisher": a["publisher"],
                      "headline": a["headline"], "summary": a.get("summary", "")[:500]}
                     for aid, a in numbered.items()],
    }
    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=json.dumps(payload, indent=2),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM.format(max_events=MAX_EVENTS),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.2,
        ),
    )
    raw = json.loads(response.text or '{"events": []}').get("events", [])
    kept, warnings = verify_events(raw, numbered)

    events = []
    for index, event in enumerate(kept[:MAX_EVENTS]):
        sources = [numbered[c] for c in event["citation_ids"]]
        dates = sorted(s["date"] for s in sources)
        events.append({
            "id": f"{symbol}_{dates[-1]}_{index}",
            "symbol": symbol,
            "headline": event["headline"],
            "summary": event["summary"],
            "event_type": event["event_type"],
            "tone": event["tone"],
            "importance": event["importance"],
            "first_seen": dates[0],
            "last_seen": dates[-1],
            "sources": [{"headline": s["headline"], "publisher": s["publisher"],
                         "url": s["url"], "date": s["date"]} for s in sources],
        })
    return events, warnings


def build(symbols: list[str] | None = None, log=print) -> dict:
    """Fetch recent news and build events for each company; save and return.

    Run by scripts.build_feed. Companies not rebuilt keep their saved events.
    """
    symbols = symbols or list(COMPANIES)
    saved = load(FEED_KEY) or {"companies": {}}
    fetched = {s: news.company_news(s, days=WINDOW_DAYS + 2) for s in symbols}
    newest = max((date.fromisoformat(i["date"]) for items in fetched.values() for i in items),
                 default=date.today())

    for symbol in symbols:
        articles = recent_articles(symbol, fetched[symbol], newest)
        events, warnings = events_for(symbol, articles)
        saved["companies"][symbol] = {
            "as_of": newest.isoformat(), "articles_read": len(articles),
            "events": events, "warnings": warnings,
        }
        log(f"{symbol}: {len(articles)} articles -> {len(events)} events"
            + (f" ({len(warnings)} warnings)" if warnings else ""))

    saved["as_of"] = max(c["as_of"] for c in saved["companies"].values())
    saved["generated_at"] = datetime.now(timezone.utc).isoformat()
    save(FEED_KEY, saved)
    return saved


def load_events() -> dict:
    """The saved events, or an empty feed if the build has not been run."""
    return load(FEED_KEY) or {"as_of": None, "companies": {}}
