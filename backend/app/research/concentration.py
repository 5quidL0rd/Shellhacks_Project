"""How concentrated a company's revenue, customers, suppliers and geography are,
read out of its own filing.

The knowledge graph says a dependency exists. It does not say how much the
dependency matters, and that is the difference between "NVIDIA supplies Apple"
and "one unnamed customer is 22% of NVIDIA's revenue". Bloomberg's supply-chain
product sells that magnitude as proprietary estimates; companies disclose a lot
of it themselves, in a sentence, for free.

Same integrity contract as everything else here: one Gemini call over passages
we selected, a strict schema, and every quote checked against the filing text
before it is allowed on screen.

A negative disclosure is kept too. "No customer accounted for at least 10% of
revenue" is a real finding about a diversified business, not a missing value.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ..cache import cached
from ..config import GEMINI_API_KEY, GEMINI_MODEL
from ..sources import filing

KIND_LABEL = {
    "customer_concentration": "Customer concentration",
    "supplier_concentration": "Supplier concentration",
    "geographic_concentration": "Geographic concentration",
    "single_source": "Single-source dependency",
    "none_above_threshold": "No concentration disclosed",
}


class Earlier(BaseModel):
    period: str = Field(description="An earlier period the same quote gives, e.g. '2024'.")
    percent: float = Field(description="The share stated for that period.")


class Fact(BaseModel):
    kind: Literal["customer_concentration", "supplier_concentration",
                  "geographic_concentration", "single_source",
                  "none_above_threshold"]
    subject: Optional[str] = Field(
        default=None,
        description="Who or what is concentrated, as the text puts it: "
                    "'one direct customer', 'the United States', 'a single supplier'.")
    counterparty_name: Optional[str] = Field(
        default=None, description="Name only if the text names it. Usually null.")
    percent: Optional[float] = Field(
        default=None, description="The percentage stated. Null if none is given.")
    at_least: bool = Field(
        default=False,
        description="True when the text gives the percentage as a floor, not an "
                    "amount: '10% or more', 'more than 10%', 'at least 10%'.")
    scope: Literal["single", "group"] = Field(
        default="single",
        description="'single' for one counterparty or one region; 'group' for a set "
                    "of them: 'our ten largest customers', 'distributors', 'carriers'.")
    basis: Literal["direct", "indirect", "unspecified"] = Field(
        default="unspecified",
        description="'indirect' when the text says the customer buys through others "
                    "(an end customer buying via distributors or partners), so its "
                    "share overlaps the direct customers' shares.")
    metric: Optional[str] = Field(
        default=None,
        description="What the percentage is of: 'total revenue', 'net sales', "
                    "'trade receivables'.")
    period: Optional[str] = Field(
        default=None, description="Period stated, e.g. 'fiscal 2026'.")
    threshold: Optional[float] = Field(
        default=None,
        description="For none_above_threshold, the level nobody exceeded, e.g. 10.")
    earlier: list[Earlier] = Field(
        default_factory=list,
        description="Earlier years the same quote states for the same counterparty, "
                    "e.g. '25%, 22% and 19% in 2023, 2024 and 2025' gives 2023: 25 and "
                    "2024: 22 here, with 2025: 19 as percent and period.")
    evidence: str = Field(description="Exact quote from the text, 40 words or fewer.")
    confidence: Literal["high", "medium", "low"]


class Extraction(BaseModel):
    facts: list[Fact]


_PROMPT = """You are extracting concentration risk disclosures from an SEC filing.

Below are passages from the annual report of {name}. Find every statement about
how concentrated its business is.

Kinds:
- customer_concentration: a customer, client or group of them is a stated share
  of revenue, sales or receivables.
- supplier_concentration: a supplier or group of them is a stated share of
  purchases or cost.
- geographic_concentration: a country or region is a stated share of revenue,
  sales or assets.
- single_source: it depends on a sole or single source, or a small number of
  suppliers, for something. Often no percentage is given.
- none_above_threshold: it states that NO customer or supplier exceeded some
  level, e.g. "no customer accounted for more than 10% of revenue". Record the
  threshold. This is a real finding about a diversified business, so include it.

Rules:
- Only extract what the text states. Never use outside knowledge, and never
  compute or estimate a percentage the text does not give.
- evidence must be copied word for word from the text.
- Do not name a counterparty the text leaves unnamed. Filings very often say
  "one direct customer" without naming them; leave counterparty_name null.
- Use the most recent period when a sentence gives several years, and put the
  earlier years it states for the same counterparty in earlier.
- When the text gives a floor ("10% or more", "more than 10%"), record 10 as
  percent and set at_least to true. Never record a floor as an exact share.
- When one sentence names several customers who each passed a level ("Apple,
  Samsung and Xiaomi each accounted for 10% or more"), make one entry per
  customer, each with its own name.
- A table of customers' shares is a disclosure too: make one entry per row for
  the most recent year, and quote just that row word for word, e.g.
  "Customer/licensee (y) 20 19 21". Put the table's years in period and earlier.
- One entry per distinct disclosure. Do not repeat the same fact.
- Skip percentages that are not about concentration, such as tax rates, interest
  rates, growth rates, or margins.

PASSAGES:
{text}
"""


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set; add it to backend/.env")
    return genai.Client(api_key=GEMINI_API_KEY)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


_YEAR = re.compile(r"(?:19|20)\d{2}")
_STATED_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent\b|per cent\b)", re.I)
_FLOOR_BEFORE = re.compile(r"(?:at least|more than|greater than|in excess of|over|"
                           r"exceed(?:ed|s|ing)?)\s+(?:approximately\s+)?$", re.I)
_FLOOR_AFTER = re.compile(r"^\s*or (?:more|greater|higher)\b", re.I)


def _states(quote: str, percent: float, before: str = "") -> bool:
    """Whether the quote states this percentage.

    A table row carries bare numbers ("Customer (y) 20 19 21") under a heading
    that says they are percentages, so a bare number counts only when a
    percentage appears in the quote or just before it in the filing (`before`).
    """
    if any(abs(float(m.group(1)) - percent) < 0.05 for m in _STATED_PERCENT.finditer(quote)):
        return True
    return bool((_STATED_PERCENT.search(quote) or _STATED_PERCENT.search(before))
                and re.search(rf"(?<![\d.]){percent:g}(?![\d.%])", quote))


def _text_before(text: str, quote: str, chars: int = 600) -> str:
    """The filing text just before the quote, for a table row's heading."""
    flat = re.sub(r"\s+", " ", text)
    at = flat.find(re.sub(r"\s+", " ", quote).strip())
    return flat[max(0, at - chars):at] if at > 0 else ""


def _check(fact: Fact, before: str = "") -> dict | None:
    """The fact as a dict once its numbers and names are backed by its own quote.

    The quote is checked against the filing separately. This makes sure the
    fields agree with the quote: a percentage the quote does not state is
    dropped, a name the quote does not contain is removed rather than guessed
    at, and a floor ("10% or more") is never charted as an exact share, even if
    the model missed the wording.
    """
    out = fact.model_dump()
    if fact.percent is not None:
        stated = [m for m in _STATED_PERCENT.finditer(fact.evidence)
                  if abs(float(m.group(1)) - fact.percent) < 0.05]
        if not _states(fact.evidence, fact.percent, before):
            return None
        if any(_FLOOR_BEFORE.search(fact.evidence[:m.start()])
               or _FLOOR_AFTER.search(fact.evidence[m.end():]) for m in stated):
            out["at_least"] = True
    out["earlier"] = [e.model_dump() for e in fact.earlier
                      if _states(fact.evidence, e.percent, before) and _YEAR.search(e.period)]
    if fact.counterparty_name:
        name = _normalise(fact.counterparty_name)
        first_word = _normalise(fact.counterparty_name.split()[0])
        quote = _normalise(fact.evidence)
        if name not in quote and (len(first_word) < 4 or first_word not in quote):
            out["counterparty_name"] = None
    return out


def _extract(cik: str, name: str) -> dict:
    meta = filing.latest_annual_report(cik)
    if meta is None:
        return {"available": False, "reason": "no_annual_report"}

    text = filing.full_text(cik, meta["url"], meta["accession"])
    passages = filing.concentration_passages(text)
    if len(passages) < 200:
        return {"available": False, "reason": "no_concentration_language",
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
    parsed = Extraction.model_validate_json(response.text or '{"facts": []}')

    haystack = _normalise(text)
    verified, dropped = [], 0
    for fact in parsed.facts:
        quote = _normalise(fact.evidence)
        checked = (_check(fact, _text_before(text, fact.evidence))
                   if len(quote) >= 20 and quote in haystack else None)
        if checked is None:
            dropped += 1
            continue
        verified.append(checked)

    return {
        "available": True,
        "form": meta["form"],
        "filing_date": meta["filing_date"],
        "url": meta["url"],
        "facts": verified,
        "dropped_unverified": dropped,
        "passage_chars": len(passages),
    }


# Bump when extraction changes, so results read under older rules are redone.
# v2: "percent" spelled out, floors ("10% or more"), single vs group, indirect.
# v3: table rows, and earlier years from the same quote for a trend.
EXTRACTION_VERSION = 3


def cache_key(cik: str) -> str:
    return f"conc_v{EXTRACTION_VERSION}_{cik}"


def for_company(cik: str, name: str) -> dict:
    """Concentration disclosures from this company's latest annual report.

    Cached forever against the filing, which never changes.
    """
    if not cik:
        return {"available": False, "reason": "no_cik"}
    return cached(cache_key(cik), lambda: _extract(cik, name), max_age_seconds=None)


# --- reading the facts -----------------------------------------------------

# A percentage of revenue is a concentration risk. A percentage of receivables is
# a working-capital detail, and a split across sales channels is a route to
# market, not a dependency - both crowded out the real finding when ranked purely
# by size.
_REVENUE_METRIC = re.compile(r"revenue|net sales|\bsales\b", re.IGNORECASE)
_NOT_A_DEPENDENCY = re.compile(r"receivabl|distribution channel|direct and indirect|"
                               r"\bchannel\b|segment\b", re.IGNORECASE)


def _is_revenue_dependency(fact: dict) -> bool:
    metric = fact.get("metric") or ""
    subject = fact.get("subject") or ""
    return bool(_REVENUE_METRIC.search(metric)
                and not _NOT_A_DEPENDENCY.search(metric)
                and not _NOT_A_DEPENDENCY.search(subject))


def _is_one_customer(fact: dict) -> bool:
    """A share of revenue from one customer: the only kind that can be a slice of
    a revenue pie. A group ("our ten largest customers") contains the single
    customers, so it would count the same revenue twice."""
    return (fact["kind"] == "customer_concentration" and fact.get("percent") is not None
            and _is_revenue_dependency(fact)
            and fact.get("scope", "single") == "single")


def _pct(fact: dict) -> str:
    return f"{fact['percent']:.0f}%{'+' if fact.get('at_least') else ''}"


def headline(result: dict) -> str | None:
    """The single most important concentration fact, in plain words.

    Ranked by what would worry an investor: a share of revenue from a
    counterparty first, a named one ahead of an unnamed one, then geography, then
    a stated absence of concentration - which is reported, not hidden.
    """
    if not result.get("available") or not result.get("facts"):
        return None

    with_pct = [f for f in result["facts"]
                if f.get("percent") and _is_revenue_dependency(f)
                and f["kind"] in ("customer_concentration", "supplier_concentration")]
    if with_pct:
        worst = max(with_pct, key=lambda f: (f.get("counterparty_name") is not None,
                                             f["percent"]))
        who = worst.get("counterparty_name") or worst.get("subject") or "one counterparty"
        metric = worst.get("metric") or "revenue"
        return f"{_pct(worst)} of {metric} comes from {who}."

    none_above = [f for f in result["facts"] if f["kind"] == "none_above_threshold"]
    if none_above:
        level = none_above[0].get("threshold")
        return (f"No single customer or supplier exceeds {level:.0f}% of revenue."
                if level else "No single customer or supplier is a material share.")

    geographic = [f for f in result["facts"]
                  if f["kind"] == "geographic_concentration" and f.get("percent")]
    if geographic:
        worst = max(geographic, key=lambda f: f["percent"])
        return (f"{_pct(worst)} of {worst.get('metric') or 'revenue'} "
                f"comes from {worst.get('subject') or 'one region'}.")

    single = [f for f in result["facts"] if f["kind"] == "single_source"]
    if single:
        return f"Depends on a single source for {single[0].get('subject') or 'key inputs'}."
    return None


def customer_share(result: dict) -> float | None:
    """Largest disclosed single-customer share of revenue, if any."""
    if not result.get("available"):
        return None
    shares = [f["percent"] for f in result["facts"] if _is_one_customer(f)]
    return max(shares) if shares else None


def named_counterparties(result: dict) -> list[dict]:
    """Concentration facts that actually name the other company.

    These are the ones that can be matched against a portfolio, which is where
    a disclosure stops being trivia: Qualcomm naming Apple as a 10%-plus
    customer matters a great deal to someone holding both.
    """
    if not result.get("available"):
        return []
    return [f for f in result["facts"] if f.get("counterparty_name")
            and f["kind"] in ("customer_concentration", "supplier_concentration")]


def single_source_facts(result: dict) -> list[dict]:
    if not result.get("available"):
        return []
    return [f for f in result["facts"] if f["kind"] == "single_source"]


def summarise(result: dict) -> str:
    if not result.get("available"):
        return {
            "no_annual_report": "This company files no annual report with the SEC.",
            "no_concentration_language": "Its annual report makes no concentration "
                                         "disclosures we could find.",
            "no_cik": "We could not find this company in SEC's records.",
        }.get(result.get("reason", ""), "Its filings could not be read.")
    count = len(result["facts"])
    return (f"Read its {result['form']} filed {result['filing_date']} and found "
            f"{count} concentration disclosure{'s' if count != 1 else ''}.")


# --- revenue mix: who pays the company, as shares of a whole -----------------

# Companies must name any customer worth 10% or more of revenue in their segment
# note (ASC 280 in the US, IFRS 8 for 20-F filers), so what is left over is made
# of customers each below that level. Used only as the fallback when the
# filing states no level of its own.
DISCLOSURE_THRESHOLD = 10.0

def _year(fact: dict) -> int | None:
    years = [int(y) for y in _YEAR.findall(fact.get("period") or "")]
    return max(years) if years else None


def _latest(facts: list[dict]) -> list[dict]:
    """Facts from the most recent period stated. Filings repeat prior years
    ("18% in fiscal 2023"), and mixing years in one pie would be wrong."""
    years = [y for y in map(_year, facts) if y is not None]
    if not years:
        return facts
    newest = max(years)
    return [f for f in facts if _year(f) in (None, newest)]


def _dedupe(facts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in facts:
        key = (_normalise(f.get("counterparty_name") or f.get("subject") or ""),
               f.get("percent"), f["kind"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _history(fact: dict) -> list[dict]:
    """This counterparty's share by year, oldest first, as its quote states it."""
    points = [*fact.get("earlier", []), {"period": fact.get("period") or "", "percent": fact["percent"]}]
    points = [p for p in points if _YEAR.search(p["period"] or "")]
    points.sort(key=lambda p: max(int(y) for y in _YEAR.findall(p["period"])))
    return points if len(points) > 1 else []


def _one_per_customer(facts: list[dict]) -> list[dict]:
    """Drop the same unnamed customer stated twice.

    TSMC's 20-F gives its two largest customers in a sentence ("our largest
    customer ... 19%") and again in a table ("Customer A 19%"). Unnamed shares
    with the same percentage and year from different passages are one customer.
    Within one passage they are distinct ("two customers, each 12%"), so each
    group keeps as many as its fullest passage states.
    """
    named = [f for f in facts if f.get("counterparty_name") or f.get("at_least")]
    groups: dict[tuple, list[dict]] = {}
    for f in facts:
        if f not in named:
            groups.setdefault((f["percent"], _year(f)), []).append(f)
    kept = list(named)
    for group in groups.values():
        by_quote: dict[str, list[dict]] = {}
        for f in group:
            by_quote.setdefault(f["evidence"], []).append(f)
        # The passage that says the most: the fullest history, then words over labels.
        best = max(by_quote.values(), key=lambda fs: (
            len(fs), max(len(f.get("earlier") or []) for f in fs),
            not all(re.fullmatch(r"(?i)customer\W*\w?\W*", f.get("subject") or "") for f in fs)))
        kept.extend(best)
    return kept


def _described(fact: dict) -> dict:
    return {"text": fact.get("subject") or fact.get("counterparty_name") or "",
            "percent": fact.get("percent"), "at_least": bool(fact.get("at_least")),
            "metric": fact.get("metric"), "period": fact.get("period"),
            "evidence": fact["evidence"]}


def revenue_mix(result: dict) -> dict:
    """Who pays the company, as slices of its revenue, from its own filing.

    Each slice is one direct customer with a stated share of revenue. A
    customer the filing leaves unnamed stays unnamed ("Customer A") and keeps
    the filing's own description ("one direct customer"); nothing here guesses
    who it is. The rest is "all other customers", which the 10% disclosure
    rule means are each below that level.

    Floors ("10% or more") are drawn at the floor and flagged, so the
    remainder is then an upper bound. When disclosed shares add up to more than
    100% they overlap in a way the filing does not explain, so no pie is drawn
    and the quotes are shown instead.
    """
    base = {"available": bool(result.get("available")),
            "summary": summarise(result),
            **{k: result.get(k) for k in ("form", "filing_date", "url")},
            "dropped_unverified": result.get("dropped_unverified", 0)}
    if not result.get("available"):
        return {**base, "status": "unavailable", "slices": [], "other": None,
                "named_without_share": [],
                "context": [], "suppliers": [], "geography": [], "period": None,
                "threshold": None}

    facts = result.get("facts", [])
    candidates = _dedupe(_latest([f for f in facts if _is_one_customer(f)]))
    # An indirect customer buys through the direct ones (NVIDIA's end customer
    # via its partners), so beside direct shares it would be counted twice. On
    # its own it is the real split: Cirrus Logic reports Apple, buying through
    # contract manufacturers, as 91% of sales and no direct customer shares.
    direct = [f for f in candidates if f.get("basis") != "indirect"]
    singles = _one_per_customer(direct or candidates)

    none_above = [f for f in facts if f["kind"] == "none_above_threshold"
                  and _REVENUE_METRIC.search(f.get("metric") or "revenue")
                  and not re.search(r"supplier|vendor|countr|purchas|receivabl",
                                    f"{f.get('subject')} {f.get('metric')}", re.I)]
    stated = [f["threshold"] for f in none_above if f.get("threshold")]
    threshold = stated[0] if stated else DISCLOSURE_THRESHOLD

    # Qualcomm gives exact shares for unnamed customers (x) 21%, (y) 20%,
    # (z) 13%, and separately names Apple, Samsung and Xiaomi as "10% or more".
    # They are the same customers, and the filing does not say which is which,
    # so the names are listed rather than drawn, and never matched to a share.
    exact = [f for f in singles if not f.get("at_least")]
    floors = [f for f in singles if f.get("at_least") and f["percent"] <= threshold]
    named_without_share = []
    if exact and floors:
        singles = [f for f in singles if f not in floors]
        named_without_share = [{"name": f.get("counterparty_name") or f.get("subject"),
                                "at_least": f["percent"], "evidence": f["evidence"]}
                               for f in floors]
    singles.sort(key=lambda f: (-f["percent"], f.get("counterparty_name") is None))

    slices, letter = [], iter("ABCDEFGHIJ")
    for f in singles:
        name = f.get("counterparty_name")
        slices.append({
            "label": name or f"Customer {next(letter)}",
            "named": bool(name),
            "described_as": f.get("subject"),
            "percent": f["percent"],
            "at_least": bool(f.get("at_least")),
            "metric": f.get("metric"),
            "period": f.get("period"),
            "history": _history(f),
            "evidence": f["evidence"],
        })

    total = round(sum(s["percent"] for s in slices), 2)
    status = "disclosed" if slices else ("none_above_threshold" if none_above
                                         else "not_disclosed")
    other = None
    if status == "none_above_threshold":
        other = {"percent": 100.0, "at_most": False,
                 "note": f"No customer is {threshold:.0f}% or more of revenue."}
    elif slices and total <= 100.5:
        other = {"percent": round(max(0.0, 100 - total), 2),
                 "at_most": any(s["at_least"] for s in slices),
                 "note": f"Every other customer is below {threshold:.0f}% of revenue each; "
                         "companies must disclose any customer at or above that level."}
    elif slices:
        status = "overlapping"

    periods = [f.get("period") for f in singles + none_above if f.get("period")]
    context = [_described(f) for f in _latest(facts)
               if f["kind"] == "customer_concentration" and f.get("percent") is not None
               and f not in singles and _is_revenue_dependency(f)
               and not any(n["evidence"] == f["evidence"] for n in named_without_share)]
    # Receivables are money owed, not dependence: Apple's "two vendors are 46% of
    # vendor non-trade receivables" says nothing about how much it relies on them.
    suppliers = [_described(f) for f in facts
                 if f["kind"] == "single_source"
                 or (f["kind"] == "supplier_concentration"
                     and not re.search(r"receivabl", f.get("metric") or "", re.I))]
    # A floor at the disclosure level is the filing's cut-off for listing a
    # country ("countries that accounted for 10% or more"), not its share.
    geography = [_described(f) for f in _latest(facts)
                 if f["kind"] == "geographic_concentration" and f.get("percent")
                 and not re.search(r"receivabl", f.get("metric") or "", re.I)
                 and not (f.get("at_least") and f["percent"] <= threshold)]
    return {**base, "status": status, "period": periods[0] if periods else None,
            "threshold": threshold, "slices": slices, "disclosed_total": total,
            "named_without_share": named_without_share,
            "other": other, "context": context, "suppliers": suppliers,
            "geography": geography}


def depended_on_by(name: str, aliases: tuple[str, ...] = (), exclude_cik: str = "") -> list[dict]:
    """Supported companies whose own filing names this one as a customer, and how
    much of their revenue it is.

    This is the direction filings actually quantify. Apple publishes no share
    for any supplier, but Cirrus Logic's 10-K says Apple is about 91% of its
    sales. Reads only extractions already cached, so it never triggers a
    Gemini call; scripts/build_revenue_mix.py fills the cache.
    """
    from ..cache import load
    from ..universe import COMPANIES
    from .relationships import _squash_name

    wanted = {_squash_name(n) for n in (name, name.split(",")[0], *aliases)}
    wanted = {w for w in wanted if len(w) > 2}
    out = []
    for ticker, company in COMPANIES.items():
        if company.cik == exclude_cik:
            continue
        result = load(cache_key(company.cik))
        if not result or not result.get("available"):
            continue
        for f in _latest([f for f in result["facts"] if _is_one_customer(f)]):
            named = _squash_name(f.get("counterparty_name") or "")
            if named and any(named == w or (len(w) > 3 and (w in named or named in w))
                             for w in wanted):
                out.append({"ticker": ticker, "name": company.name,
                            "percent": f["percent"], "at_least": bool(f.get("at_least")),
                            "metric": f.get("metric"), "period": f.get("period"),
                            "evidence": f["evidence"], "form": result["form"],
                            "url": result["url"]})
    return sorted(out, key=lambda d: -d["percent"])


FILED_SOURCES = ("10-K", "20-F", "40-F")


def named_in_filings(graph_id: str | None) -> list[dict]:
    """Customers the knowledge graph links to this company, from filings only.

    These are names without shares: "we purchase wafers from TSMC" in NVIDIA's
    10-K says NVIDIA buys from TSMC, not how much. They are never matched to an
    unnamed slice; the filing that gives the share does not say which is which.
    Hand-added edges are left out, since they rest on general knowledge rather
    than a filing.
    """
    if not graph_id:
        return []
    from .. import portfolio

    edges, companies = portfolio._graph()
    out: dict[str, dict] = {}
    for e in edges:
        if (e.rel != "SUPPLIES" or e.from_id != graph_id or e.to_id == graph_id
                or e.source not in FILED_SOURCES or e.to_id in out):
            continue
        company = companies.get(e.to_id, {})
        reporter = e.reported_by or e.from_id
        out[e.to_id] = {
            "id": e.to_id,
            "name": company.get("name") or e.to_name,
            "in_universe": company.get("in_universe") == "True",
            "detail": e.detail or None,
            "evidence": e.evidence,
            "reported_by": reporter,
            "reported_by_name": companies.get(reporter, {}).get("name") or reporter,
            "source": e.source,
            "filing_url": e.filing_url,
        }
    return sorted(out.values(), key=lambda c: (not c["in_universe"], c["name"]))


class UnknownCompany(Exception):
    """No SEC filer has this ticker."""


def for_ticker(ticker: str) -> dict:
    """The revenue mix for any SEC filer, by exact ticker.

    The 13 supported companies resolve from the company list; anything else
    from SEC's ticker directory, the same one Research searches. The first read
    of a company costs one Gemini call over its filing; after that it is cached.
    """
    from ..universe import COMPANIES
    from . import lookup

    ticker = ticker.strip().upper()
    from .subject import graph_id_for

    company = COMPANIES.get(ticker)
    if company:
        cik, name, aliases, graph_id = company.cik, company.name, company.aliases, ticker
    else:
        match = next((m for m in lookup.search(ticker, limit=1) if m.ticker == ticker), None)
        if match is None:
            raise UnknownCompany(ticker)
        cik, name, aliases = match.cik, match.name, ()
        graph_id = graph_id_for(ticker, name)

    mix = revenue_mix(for_company(cik, name))
    return {"ticker": ticker, "name": name, **mix,
            "depended_on_by": depended_on_by(name, aliases, exclude_cik=cik),
            "named_in_filings": named_in_filings(graph_id),
            "method": ("Read from the company's latest annual report. Every quote was "
                       "checked word for word against the filing, and every percentage "
                       "and name against its quote. Unnamed customers are left unnamed.")}


# --- across a whole portfolio ----------------------------------------------

def _holding_index(holdings: list[str]) -> dict[str, str]:
    """Squashed company name -> ticker, for matching a filing's wording."""
    from ..universe import COMPANIES
    from .relationships import _squash_name

    index: dict[str, str] = {}
    for ticker in holdings:
        company = COMPANIES.get(ticker)
        if not company:
            continue
        for candidate in (company.name, company.name.split(",")[0], *company.aliases):
            squashed = _squash_name(candidate)
            if len(squashed) > 2:
                index[squashed] = ticker
    return index


def _resolve_holding(name: str, index: dict[str, str]) -> str | None:
    from .relationships import _squash_name

    squashed = _squash_name(name)
    if squashed in index:
        return index[squashed]
    return next((ticker for key, ticker in index.items()
                 if len(squashed) > 3 and (squashed in key or key in squashed)), None)


def portfolio(holdings: list[str]) -> dict:
    """Concentration across every holding, plus the links between them.

    The cross-holding links are the point. A filing disclosure is trivia on its
    own; "Qualcomm says Apple is more than 10% of its revenue, and you hold both"
    is concentration the investor cannot see from a list of positions, stated by
    one of their own companies and quoted from its filing.
    """
    from ..universe import COMPANIES

    index = _holding_index(holdings)
    rows, unavailable, internal, geography = [], [], [], []

    for ticker in holdings:
        company = COMPANIES.get(ticker)
        if company is None:
            continue
        result = for_company(company.cik, company.name)
        if not result.get("available"):
            unavailable.append({"ticker": ticker, "name": company.name,
                                "reason": summarise(result)})
            continue

        share = customer_share(result)
        singles = single_source_facts(result)
        rows.append({
            "ticker": ticker,
            "name": company.name,
            "headline": headline(result),
            "largest_customer_share": share,
            "single_source_count": len(singles),
            "fact_count": len(result["facts"]),
            "dropped_unverified": result.get("dropped_unverified", 0),
            "form": result["form"],
            "filing_date": result["filing_date"],
            "url": result["url"],
            "facts": result["facts"],
        })

        for fact in named_counterparties(result):
            other = _resolve_holding(fact["counterparty_name"], index)
            if other and other != ticker:
                internal.append({
                    "from": ticker, "to": other,
                    "role": ("customer" if fact["kind"] == "customer_concentration"
                             else "supplier"),
                    "percent": fact.get("percent"),
                    "at_least": bool(fact.get("at_least")),
                    "metric": fact.get("metric"),
                    "quote": fact["evidence"],
                    "form": result["form"], "url": result["url"],
                })

        for fact in result["facts"]:
            if fact["kind"] == "geographic_concentration" and fact.get("percent"):
                geography.append({
                    "ticker": ticker, "region": fact.get("subject"),
                    "percent": fact["percent"], "metric": fact.get("metric"),
                    "quote": fact["evidence"], "url": result["url"],
                })

    with_share = [r for r in rows if r["largest_customer_share"]]
    stats = {
        "holdings_requested": len(holdings),
        "filings_read": len(rows),
        "disclosing_customer_concentration": len(with_share),
        "largest_disclosed_share": (max(r["largest_customer_share"] for r in with_share)
                                    if with_share else None),
        "holdings_with_single_source": sum(1 for r in rows if r["single_source_count"]),
        "internal_links": len(internal),
        "claims_dropped_unverified": sum(r["dropped_unverified"] for r in rows),
    }

    rows.sort(key=lambda r: (r["largest_customer_share"] is None,
                             -(r["largest_customer_share"] or 0)))
    internal.sort(key=lambda link: -(link["percent"] or 0))
    geography.sort(key=lambda g: -g["percent"])
    return {"holdings": rows, "internal_links": internal, "geography": geography,
            "unavailable": unavailable, "stats": stats,
            "method": ("Read from each holding's latest annual report. Every quote was "
                       "checked against the filing text; claims whose quote did not "
                       "appear were dropped.")}
