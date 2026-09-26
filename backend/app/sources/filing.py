"""Fetch a company's latest annual report and cut it down to the parts that
could describe a relationship with another company.

The knowledge graph does this offline for the 13 companies we cover (see kg/),
reading whole Item 1 and Item 1A sections. Research needs the same answer for
whatever the investor just typed, live, so this takes a narrower path: a 10-K
runs to 600,000-odd characters, and asking a model to read all of it for one
question would be slow and wasteful.

Instead it keeps sentences that either name a company we care about or use
supply-chain language, which reduces a filing by roughly 95% while keeping the
passages a relationship could hide in. Sentences naming a holding are kept in
preference to generic ones when the budget runs out.
"""
from __future__ import annotations

import re
import warnings

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..cache import cached
from ..config import SEC_USER_AGENT

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # 10-Ks are XHTML

ANNUAL_FORMS = ("10-K", "20-F", "40-F")
# How much text to hand the model. Enough for the passages that matter, small
# enough for one call.
BUDGET_CHARS = 45_000

# Where the company operates. Kept separately because country exposure is half
# the dependency story - "three of your holdings manufacture in Taiwan" is the
# kind of shared risk the portfolio X-Ray exists to surface - and none of the
# supply-chain words below would catch a sentence about geography.
GEOGRAPHY_TERMS = re.compile(
    r"\b(headquarter\w*|manufactur\w+ (?:facilit\w+|operations?|plants?|sites?)|"
    r"(?:our |principal |largest |key )(?:operations?|markets?|facilities) in|"
    r"operations? (?:in|across)|plants? (?:in|located)|"
    r"net (?:sales|revenues?) (?:in|from)|geographic\w*)\b",
    re.IGNORECASE,
)

# Language that marks a sentence as describing a supplier, customer or rival.
RELATIONSHIP_TERMS = re.compile(
    r"\b(suppliers?|supplied by|sole[- ]source[ds]?|single[- ]source[ds]?|vendors?|"
    r"foundr(y|ies)|contract manufactur\w*|subcontract\w*|outsourc\w*|competitors?|"
    r"compete[sd]?|competing|(largest|significant|major|key|principal) customers?|"
    r"customers? (accounted|represented)|depend\w* on|reli(es|ance) on|"
    r"\d+% of (our )?(total |net )?(revenue|sales))\b",
    re.IGNORECASE,
)


def _get(url: str) -> requests.Response:
    response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=60)
    if response.status_code == 403:
        raise RuntimeError("SEC returned 403; set a real contact email in SEC_USER_AGENT.")
    response.raise_for_status()
    return response


def latest_annual_report(cik: str) -> dict | None:
    """Metadata for the most recent 10-K, 20-F or 40-F, or None if there is none.

    Plenty of tickers have no annual report at all - BMW's SEC presence is an
    ADR registration whose only filings are F-6 forms.
    """
    payload = cached(
        f"edgar_submissions_{cik}",
        lambda: _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json(),
        max_age_seconds=12 * 3600,
    )
    recent = payload.get("filings", {}).get("recent", {})
    for index, form in enumerate(recent.get("form", [])):
        if form not in ANNUAL_FORMS:
            continue
        accession = recent["accessionNumber"][index]
        document = recent["primaryDocument"][index]
        return {
            "form": form,
            "filing_date": recent["filingDate"][index],
            "report_date": recent.get("reportDate", [""] * (index + 1))[index],
            "accession": accession,
            "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession.replace('-', '')}/{document}"),
        }
    return None


def _to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text("\n").replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def full_text(cik: str, url: str, accession: str) -> str:
    """The filing as plain text. Cached forever: a filed report never changes."""
    return cached(f"filing_text_{cik}_{accession.replace('-', '')}",
                  lambda: _to_text(_get(url).text), max_age_seconds=None)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s*\n\s*", " ", para).strip()
        if len(para) < 40:  # table cells, page numbers, running headers
            continue
        out += re.split(r'(?<=[.!?])\s+(?=[A-Z"“(])', para)
    return out


def relevant_passages(
    text: str,
    company_names: list[str],
    self_names: list[str],
    budget: int = BUDGET_CHARS,
) -> str:
    """Sentences that could describe a relationship, most useful first.

    `company_names` are the companies we want to detect - the investor's
    holdings and their known suppliers. `self_names` are the filing company's
    own names, excluded because otherwise every sentence about itself matches.

    Each kept sentence brings the one before it, since a filing often names a
    company in one sentence and says what it does in the next.
    """
    wanted = [n for n in company_names if len(n) > 3]
    named = (re.compile(r"\b(" + "|".join(sorted(map(re.escape, wanted), key=len,
                                                 reverse=True)) + r")\b", re.IGNORECASE)
             if wanted else None)
    mine = (re.compile(r"\b(" + "|".join(map(re.escape, [n for n in self_names if len(n) > 3]))
                       + r")\b", re.IGNORECASE) if self_names else None)

    sentences = _sentences(text)
    # Tier 1 names a company we care about; tier 2 only uses supply-chain words.
    tiers: dict[int, set[int]] = {1: set(), 2: set()}
    for index, sentence in enumerate(sentences):
        if mine and mine.search(sentence) and not (named and named.search(sentence)):
            continue
        if named and named.search(sentence):
            tiers[1].update({index - 1, index})
        elif RELATIONSHIP_TERMS.search(sentence) or GEOGRAPHY_TERMS.search(sentence):
            tiers[2].update({index - 1, index})

    kept: list[str] = []
    used = 0
    for tier in (1, 2):
        for index in sorted(i for i in tiers[tier] if i >= 0):
            sentence = sentences[index]
            if used + len(sentence) > budget:
                return "\n".join(kept)
            kept.append(sentence)
            used += len(sentence)
    return "\n".join(kept)
