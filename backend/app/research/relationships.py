"""Read a searched company's annual report and find its suppliers, customers,
competitors and countries, on demand.

Why this exists: the knowledge graph covers 13 companies, but Research accepts
any of ~10,400 filers, so for almost anything the investor searches the two
graph-based overlap checks had nothing to work with and reported "unknown". That
left the product's whole point - revealing shared supply-chain risk - missing
exactly when someone is considering something new.

This runs the same idea as kg/extract.py against one company, live:
  1. fetch its latest 10-K or 20-F
  2. cut it to the passages that could describe a relationship
  3. one Gemini call to extract them, each with a quote from the filing
  4. check every quote really appears in the filing, and drop it if not
  5. match the counterparties against the investor's holdings

Step 4 matters. The model is reading a real document, so a fabricated quote is
the failure mode to guard against, and it is cheap to check exactly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ..cache import cached
from ..config import GEMINI_API_KEY, GEMINI_MODEL
from ..sources import filing
from ..universe import COMPANIES


class Relationship(BaseModel):
    type: Literal["SUPPLIER", "CUSTOMER", "COMPETITOR", "OPERATES_IN"] = Field(
        description="How the counterparty relates to the filing company.")
    counterparty_name: Optional[str] = Field(
        default=None,
        description="Company name exactly as written in the text. Null if unnamed.")
    country: Optional[str] = Field(
        default=None, description="Country in plain English. Required for OPERATES_IN.")
    operates_kind: Optional[Literal["headquarters", "manufacturing", "major_market"]] = Field(
        default=None, description="Only for OPERATES_IN.")
    detail: Optional[str] = Field(
        default=None, description="What is supplied, bought or competed on, in a few words.")
    evidence: str = Field(description="Exact quote from the text, 40 words or fewer.")
    confidence: Literal["high", "medium", "low"]
    is_named: bool = Field(description="True only if the text names the counterparty.")


class Extraction(BaseModel):
    relationships: list[Relationship]


_PROMPT = """You are mapping company relationships from an SEC filing.

Below are passages from the annual report of {name} ("the filing company"). List
every relationship the text states between the filing company and another
company or a country.

Types, always from the filing company's point of view:
- SUPPLIER: the counterparty sells to or makes things for the filing company.
- CUSTOMER: the counterparty buys from the filing company.
- COMPETITOR: the text names the counterparty as a competitor.
- OPERATES_IN: the filing company has headquarters, manufacturing, or a major
  market in a country. Set counterparty_name to null.

Rules:
- Only extract what the text states. Never use outside knowledge about this
  company, however well you know it.
- evidence must be copied word for word from the text. Do not paraphrase,
  tidy, or join separate sentences.
- If a supplier or customer is described but not named ("a single supplier in
  Asia"), include it with counterparty_name=null and is_named=false. Never
  guess a name.
- Use the company name as written in the text, not a ticker.
- One entry per counterparty per type.
- Skip the filing company's own subsidiaries and brands.
- confidence: high = explicit and direct; medium = clear but indirect; low = implied.

PASSAGES:
{text}
"""


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set; add it to backend/.env")
    return genai.Client(api_key=GEMINI_API_KEY)


def _normalise(text: str) -> str:
    """Collapse to letters and digits, so quote checking survives whitespace and
    punctuation differences between the model's copy and the filing."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _squash_name(name: str) -> str:
    noise = re.compile(r"\b(inc|corp|corporation|company|co|ltd|limited|plc|holdings?|"
                       r"group|the|sa|ag|nv|se|technologies|technology)\b", re.I)
    return re.sub(r"[^a-z0-9]", "", noise.sub(" ", name.lower()))


@dataclass
class Extracted:
    """What one filing said, after quote verification."""
    form: str
    filing_date: str
    url: str
    relationships: list[dict] = field(default_factory=list)
    dropped_unverified: int = 0
    passage_chars: int = 0

    def as_dict(self) -> dict:
        return {
            "form": self.form, "filing_date": self.filing_date, "url": self.url,
            "relationships": self.relationships,
            "dropped_unverified": self.dropped_unverified,
            "passage_chars": self.passage_chars,
        }


def _holding_names() -> list[str]:
    """Names and aliases of every company we cover, to steer passage selection."""
    names: list[str] = []
    for company in COMPANIES.values():
        names.append(company.name.split(",")[0])
        names.extend(company.aliases)
    return names


def _extract(cik: str, name: str, self_names: list[str]) -> dict:
    meta = filing.latest_annual_report(cik)
    if meta is None:
        return {"available": False, "reason": "no_annual_report"}

    text = filing.full_text(cik, meta["url"], meta["accession"])
    passages = filing.relevant_passages(text, _holding_names(), self_names)
    if len(passages) < 500:
        return {"available": False, "reason": "no_relevant_passages",
                "form": meta["form"], "url": meta["url"]}

    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=_PROMPT.format(name=name, text=passages),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction,
            temperature=0,
        ),
    )
    parsed = Extraction.model_validate_json(response.text or '{"relationships": []}')

    # Every quote must really appear in the filing. A relationship resting on a
    # fabricated quote is worse than no relationship at all.
    haystack = _normalise(text)
    verified, dropped = [], 0
    for rel in parsed.relationships:
        if len(_normalise(rel.evidence)) < 20 or _normalise(rel.evidence) not in haystack:
            dropped += 1
            continue
        verified.append(rel.model_dump())

    return {
        "available": True,
        **Extracted(meta["form"], meta["filing_date"], meta["url"],
                    verified, dropped, len(passages)).as_dict(),
    }


def for_company(cik: str, name: str, self_names: list[str]) -> dict:
    """Relationships from this company's latest annual report.

    Cached forever against the filing, since a filed report never changes.
    Returns {"available": False, "reason": ...} when there is nothing to read.
    """
    if not cik:
        return {"available": False, "reason": "no_cik"}
    return cached(f"rels_{cik}", lambda: _extract(cik, name, self_names),
                  max_age_seconds=None)


def match_to_holdings(relationships: list[dict], holdings: list[str]) -> list[dict]:
    """Which extracted relationships point at a company the investor holds.

    Matching is on squashed names, so "Apple Inc." in a filing lines up with our
    "Apple Inc." and with the alias list from data/companies.json.
    """
    index: dict[str, str] = {}
    for ticker in holdings:
        company = COMPANIES.get(ticker)
        if not company:
            continue
        for candidate in (company.name, company.name.split(",")[0], *company.aliases):
            squashed = _squash_name(candidate)
            if len(squashed) > 2:
                index[squashed] = ticker

    hits = []
    for rel in relationships:
        counterparty = rel.get("counterparty_name")
        if not counterparty:
            continue
        squashed = _squash_name(counterparty)
        ticker = index.get(squashed)
        if ticker is None:
            # A filing may write "Apple" where our name is "Apple Inc.".
            ticker = next((t for key, t in index.items()
                           if len(squashed) > 3 and (squashed in key or key in squashed)), None)
        if ticker:
            hits.append({**rel, "holding": ticker})
    return hits


def dependencies(relationships: list[dict]) -> set[tuple[str, str]]:
    """What the company relies on, in the same shape the graph uses.

    Named suppliers and the countries it operates in, excluding headquarters for
    the same reason the X-Ray excludes them.
    """
    deps: set[tuple[str, str]] = set()
    for rel in relationships:
        if rel["type"] == "SUPPLIER" and rel.get("counterparty_name"):
            deps.add(("supplier", rel["counterparty_name"]))
        elif rel["type"] == "OPERATES_IN" and rel.get("country") \
                and rel.get("operates_kind") != "headquarters":
            deps.add(("country", rel["country"]))
    return deps


def summarise(result: dict) -> str:
    """One line for the UI about what was read."""
    if not result.get("available"):
        return {"no_annual_report": "This company files no annual report with the SEC.",
                "no_relevant_passages": "Its annual report names no suppliers, customers "
                                        "or competitors we could identify.",
                "no_cik": "We could not find this company in SEC's records."}.get(
                    result.get("reason", ""), "Its filings could not be read.")
    count = len(result["relationships"])
    return (f"Read its {result['form']} filed {result['filing_date']} and found "
            f"{count} stated relationship{'s' if count != 1 else ''}.")
