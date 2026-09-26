"""A company we can analyse, whether or not it is one of the 13 we cover.

Research now takes anything the investor types, so the rest of the module can no
longer assume `universe.get()` will find the company. A Subject supplies the
four things the analysis needs - CIK, a comparable sector, a daily price series,
and a knowledge-graph id if one exists - and is honest when a piece is missing.

Sectors come from Yahoo rather than SEC's SIC code. SIC classifies BMW's ADR as
"American Depositary Receipts", which tells an investor nothing, and our own
companies.json sectors ("Semiconductors", "Internet & Cloud") cannot be compared
with an outside company's. Yahoo's taxonomy is the only one that covers both
sides of the comparison, so it is used for every company including our own.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from ..cache import cached, load
from ..config import GRAPH_COMPANIES_CSV
from ..sources import prices
from ..universe import COMPANIES
from .lookup import Match, _normalise

UNKNOWN_SECTOR = "Unknown"


@dataclass(frozen=True)
class Subject:
    ticker: str
    name: str
    cik: str | None
    sector: str
    industry: str
    country: str
    in_universe: bool
    graph_id: str | None

    @property
    def in_graph(self) -> bool:
        return self.graph_id is not None

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker, "name": self.name, "cik": self.cik,
            "sector": self.sector, "industry": self.industry, "country": self.country,
            "in_universe": self.in_universe, "in_graph": self.in_graph,
            "graph_id": self.graph_id,
        }


def _fetch_profile(ticker: str) -> dict:
    """Sector, industry and country from Yahoo. Empty dict rather than a raise:
    a missing profile should thin the analysis, not fail it."""
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    return {
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "country": info.get("country") or "",
        "name": info.get("shortName") or info.get("longName") or "",
        "currency": info.get("currency") or "",
        # Fallback ratios for companies with no SEC XBRL at all. BMW's SEC
        # presence is an ADR registration with no financials, so without these
        # three axes of its radar would simply be blank.
        "revenue_growth_pct": (None if info.get("revenueGrowth") is None
                               else round(info["revenueGrowth"] * 100, 2)),
        "profit_margin_pct": (None if info.get("profitMargins") is None
                              else round(info["profitMargins"] * 100, 2)),
        # Yahoo reports debt-to-equity as a percentage; our axis is a multiple.
        "debt_to_equity": (None if info.get("debtToEquity") is None
                           else round(info["debtToEquity"] / 100, 3)),
    }


def profile(ticker: str) -> dict:
    return cached(f"profile_{ticker}", lambda: _fetch_profile(ticker),
                  max_age_seconds=7 * 24 * 3600) or {}


def sector_of(ticker: str) -> str:
    """Yahoo's sector for any ticker, so candidate and holdings compare."""
    return profile(ticker).get("sector") or UNKNOWN_SECTOR


@lru_cache(maxsize=1)
def _graph_companies() -> tuple[dict, ...]:
    if not GRAPH_COMPANIES_CSV.exists():
        return ()
    with GRAPH_COMPANIES_CSV.open(encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


def graph_id_for(ticker: str, name: str) -> str | None:
    """The knowledge-graph node for this company, if the filings name it.

    Worth trying even for companies outside our 13: the graph holds 61 outside
    companies that our holdings' filings name, so a searched company can already
    be in there as somebody's supplier.
    """
    rows = _graph_companies()
    for row in rows:
        if row.get("ticker", "").upper() == ticker.upper():
            return row["ticker"]

    wanted = _normalise(name)
    if not wanted:
        return None
    for row in rows:
        node_name = _normalise(row.get("name", ""))
        if node_name and (node_name == wanted
                          or node_name.startswith(wanted)
                          or wanted.startswith(node_name)):
            return row["ticker"]
    return None


def from_match(match: Match) -> Subject:
    """Build a Subject from a search hit."""
    known = COMPANIES.get(match.ticker)
    info = profile(match.ticker)
    return Subject(
        ticker=match.ticker,
        name=known.name if known else (match.name or info.get("name") or match.ticker),
        cik=known.cik if known else match.cik,
        sector=info.get("sector") or (known.sector if known else UNKNOWN_SECTOR),
        industry=info.get("industry") or "",
        country=info.get("country") or "",
        in_universe=match.ticker in COMPANIES,
        graph_id=graph_id_for(match.ticker, match.name or (known.name if known else "")),
    )


def for_holding(ticker: str) -> Subject:
    """A Subject for a company we already cover."""
    company = COMPANIES[ticker]
    info = profile(ticker)
    return Subject(
        ticker=ticker, name=company.name, cik=company.cik,
        sector=info.get("sector") or company.sector,
        industry=info.get("industry") or "", country=info.get("country") or "",
        in_universe=True, graph_id=graph_id_for(ticker, company.name),
    )


def bars(ticker: str, days: int = 180) -> list[dict]:
    """Daily bars, from the precomputed story when we have one.

    Our 13 come from the saved stories, so nothing downloads during the demo.
    Anything else is fetched once and cached, which is the one live call this
    feature makes - unavoidable, since an arbitrary ticker cannot be precomputed.
    """
    if ticker in COMPANIES:
        story = load(f"story_{ticker}")
        if story:
            return story["bars"]
    try:
        return prices.daily_bars(ticker, days)
    except Exception:
        return []
