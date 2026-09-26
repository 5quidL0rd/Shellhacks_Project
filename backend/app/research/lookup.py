"""Resolve what someone typed into a company we can analyse.

The search box accepts a ticker ("F"), a company name ("ford motor"), or a brand
("alienware"). Everything is matched against SEC's public ticker directory -
10,400-odd filers, no key, one download cached for a day.

Three outcomes worth distinguishing, because each needs different words on
screen:
  a single confident match      analyse it
  several plausible matches     ask which one
  nothing                       say so, and suggest the closest names

Brands are the interesting failure. "Alienware" is a Dell product line, not a
filer, so the directory has no row for it; BRAND_ALIASES maps the ones people
actually type onto the company that files.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache

import requests

from ..cache import cached
from ..config import SEC_USER_AGENT
from ..universe import COMPANIES

_TICKER_DIRECTORY = "https://www.sec.gov/files/company_tickers.json"

# Brands and short names people type that are not the filer's name. The value
# is the ticker that actually files with the SEC.
BRAND_ALIASES = {
    "alienware": "DELL", "dell technologies": "DELL",
    "google": "GOOGL", "alphabet": "GOOGL", "youtube": "GOOGL", "waymo": "GOOGL",
    "instagram": "META", "whatsapp": "META", "facebook": "META", "meta": "META",
    "aws": "AMZN", "amazon web services": "AMZN", "twitch": "AMZN",
    "xbox": "MSFT", "azure": "MSFT", "github": "MSFT", "linkedin": "MSFT",
    "iphone": "AAPL", "mac": "AAPL", "ipad": "AAPL",
    "geforce": "NVDA", "nvidia": "NVDA",
    "ryzen": "AMD", "radeon": "AMD",
    "tsmc": "TSM", "taiwan semi": "TSM",
    "playstation": "SONY", "sony": "SONY",
    "bmw": "BAMXF", "mercedes": "MBGAF", "volkswagen": "VWAGY",
    "ford": "F", "ford motor": "F",
    "supermicro": "SMCI", "super micro": "SMCI", "super micro computer": "SMCI",
    "hpe": "HPE", "hewlett packard enterprise": "HPE", "hp": "HPQ",
    "tesla": "TSLA", "coca cola": "KO", "coke": "KO", "pepsi": "PEP",
    "walmart": "WMT", "costco": "COST", "target": "TGT",
}

# Words that add nothing when comparing names.
_NOISE = re.compile(
    r"\b(inc|inc\.|corp|corp\.|corporation|company|co|co\.|ltd|ltd\.|limited|plc|"
    r"holdings?|group|the|sa|ag|nv|se|adr|class [abc])\b", re.I)


@dataclass(frozen=True)
class Match:
    ticker: str
    cik: str            # zero-padded to 10 digits
    name: str
    in_universe: bool   # do we already have a story and graph edges for it
    score: float        # 0-1, how well it matched the query

    def as_dict(self) -> dict:
        return {"ticker": self.ticker, "cik": self.cik, "name": self.name,
                "in_universe": self.in_universe, "match_score": round(self.score, 3)}


def _fetch_directory() -> list[dict]:
    response = requests.get(
        _TICKER_DIRECTORY,
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return [{"ticker": row["ticker"].upper(),
             "cik": f"{int(row['cik_str']):010d}",
             "name": row["title"]}
            for row in payload.values() if row.get("ticker")]


class SearchUnavailable(Exception):
    """SEC's ticker directory could not be downloaded, and no cached copy exists."""


@lru_cache(maxsize=1)
def directory() -> tuple[dict, ...]:
    """Every SEC filer with a ticker. Cached on disk for a day."""
    try:
        return tuple(cached("sec_ticker_directory", _fetch_directory,
                            max_age_seconds=24 * 3600))
    except Exception as exc:  # network down, SEC 403 without a contact email, ...
        raise SearchUnavailable(
            "Company search needs SEC's public ticker directory, which could not be "
            f"downloaded ({type(exc).__name__}). Check the internet connection and that "
            "SEC_USER_AGENT in .env has a real contact email.") from exc


def _normalise(text: str) -> str:
    text = _NOISE.sub(" ", text.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9 ]", " ", text).strip()


def _tidy_name(name: str) -> str:
    """SEC writes 'NVIDIA CORP' and 'COCA COLA CO'; title-case the shouted ones."""
    return name.title().replace("/Adr", " ADR") if name.isupper() else name


# Preferred shares, warrants and units file under the same company name as the
# common stock ("F", "F-PB", "F-PC" are all FORD MOTOR CO), which left "ford
# motor" looking ambiguous. Someone searching a company wants the common stock,
# so these classes are pushed down rather than excluded.
_NOT_COMMON_STOCK = re.compile(r"[-.]|W[SI]?$")


def _match(row: dict, score: float) -> Match:
    ticker = row["ticker"]
    if len(ticker) > 4 and _NOT_COMMON_STOCK.search(ticker):
        score *= 0.7
    elif _NOT_COMMON_STOCK.search(ticker) and ("-" in ticker or "." in ticker):
        score *= 0.7
    return Match(ticker, row["cik"], _tidy_name(row["name"]),
                 ticker in COMPANIES, score)


def search(query: str, limit: int = 8) -> list[Match]:
    """Best matches for a typed query, most confident first.

    A ticker typed exactly always wins. Otherwise names are compared with the
    company-suffix noise stripped, so "ford motor" and "FORD MOTOR CO" line up.
    """
    query = (query or "").strip()
    if not query:
        return []

    rows = directory()
    by_ticker = {row["ticker"]: row for row in rows}

    # 1. An exact ticker, or a brand alias that points at one.
    alias = BRAND_ALIASES.get(_normalise(query))
    for candidate in (query.upper(), alias):
        if candidate and candidate in by_ticker:
            exact = _match(by_ticker[candidate], 1.0)
            others = [m for m in _by_name(query, rows, limit) if m.ticker != exact.ticker]
            return [exact] + others[: limit - 1]

    return _by_name(query, rows, limit)


def _by_name(query: str, rows: tuple[dict, ...], limit: int) -> list[Match]:
    wanted = _normalise(query)
    if not wanted:
        return []

    scored: list[Match] = []
    for row in rows:
        name = _normalise(row["name"])
        if not name:
            continue
        if name == wanted:
            score = 0.99
        elif name.startswith(wanted) or wanted.startswith(name):
            score = 0.9
        elif wanted in name:
            score = 0.8
        else:
            ratio = difflib.SequenceMatcher(None, wanted, name).ratio()
            if ratio < 0.7:
                continue
            score = ratio * 0.75  # a fuzzy hit never outranks a substring hit
        scored.append(_match(row, score))

    # Prefer the shorter name when scores tie: "FORD MOTOR CO" over
    # "FORD MOTOR CREDIT CO LLC" for the query "ford".
    scored.sort(key=lambda m: (-m.score, len(m.name)))
    return scored[:limit]


def resolve(query: str) -> tuple[Match | None, list[Match]]:
    """(confident match, alternatives).

    A match is confident when it scored at least 0.9 and nothing else came
    close, so an ambiguous query returns None and lets the caller ask.
    """
    matches = search(query)
    if not matches:
        return None, []
    best = matches[0]
    runner_up = matches[1].score if len(matches) > 1 else 0.0
    confident = best.score >= 0.9 and best.score - runner_up > 0.05
    return (best if confident else None), matches
