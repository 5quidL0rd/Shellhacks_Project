"""SEC EDGAR: official filings and XBRL fundamentals.

Free and unkeyed, but a descriptive User-Agent with a real contact email is
mandatory or data.sec.gov answers 403. Rate limit is 10 requests/second.

This is the strongest citation source in the stack, because the link lands on
the company's own filing rather than someone's write-up of it.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from ..cache import cached
from ..config import SEC_USER_AGENT
from ..universe import get as get_company

SOURCE_NAME = "SEC EDGAR"
_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}

# Filing types that actually move a price. An 8-K is how a company announces
# earnings; the 10-Q/10-K is the detail behind it.
MATERIAL_FORMS = {"8-K", "10-Q", "10-K", "20-F", "6-K"}


def _get(url: str) -> dict:
    response = requests.get(url, headers=_HEADERS, timeout=30)
    if response.status_code == 403:
        raise RuntimeError(
            "SEC EDGAR returned 403. Set SEC_USER_AGENT in backend/.env to "
            "'AppName your-real-email@example.com'."
        )
    response.raise_for_status()
    return response.json()


def filing_url(cik: str, accession: str, primary_document: str) -> str:
    """Public URL of a filing's primary document."""
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{primary_document}"
    )


def recent_filings(symbol: str, days: int = 400) -> list[dict]:
    """Material filings, newest first, each with a clickable SEC URL."""
    company = get_company(symbol)
    payload = cached(
        f"edgar_submissions_{company.cik}",
        lambda: _get(f"https://data.sec.gov/submissions/CIK{company.cik}.json"),
        max_age_seconds=12 * 3600,
    )

    recent = payload.get("filings", {}).get("recent", {})
    cutoff = date.today() - timedelta(days=days)
    filings: list[dict] = []
    for form, filed, accession, primary, doc_desc in zip(
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("primaryDocDescription", []),
    ):
        if form not in MATERIAL_FORMS:
            continue
        if date.fromisoformat(filed) < cutoff:
            continue
        filings.append({
            "form": form,
            "filed_date": filed,
            "description": doc_desc or form,
            "accession": accession,
            "url": filing_url(company.cik, accession, primary),
        })
    filings.sort(key=lambda f: f["filed_date"], reverse=True)
    return filings


def filings_near(filings: list[dict], target_date: str, window_days: int = 2) -> list[dict]:
    target = date.fromisoformat(target_date)
    lo = target - timedelta(days=window_days)
    return [f for f in filings if lo <= date.fromisoformat(f["filed_date"]) <= target]


# XBRL tags worth showing an investor, in the order we try them.
_CONCEPTS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"),
    "net_income": ("NetIncomeLoss",),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "rnd_expense": ("ResearchAndDevelopmentExpense",),
}


def _company_concept(cik: str, tag: str, taxonomy: str = "us-gaap") -> dict:
    return cached(
        f"edgar_concept_{cik}_{taxonomy}_{tag}" if taxonomy != "us-gaap"
        else f"edgar_concept_{cik}_{tag}",
        lambda: _get(
            "https://data.sec.gov/api/xbrl/companyconcept/"
            f"CIK{cik}/{taxonomy}/{tag}.json"
        ),
        max_age_seconds=24 * 3600,
    )


def quarterly_fundamentals(symbol: str, quarters: int = 8) -> dict[str, list[dict]]:
    """Recent quarterly figures per concept, oldest first.

    Each point keeps the accession number so the UI can link the number back to
    the filing it was reported in.
    """
    company = get_company(symbol)
    out: dict[str, list[dict]] = {}

    for label, tags in _CONCEPTS.items():
        for tag in tags:
            try:
                payload = _company_concept(company.cik, tag)
            except Exception:
                continue

            points = []
            for unit_rows in payload.get("units", {}).values():
                for row in unit_rows:
                    # fp Q1-Q4 with a ~quarter-long window is a quarterly figure
                    if row.get("form") not in {"10-Q", "10-K", "20-F"}:
                        continue
                    if not row.get("start") or not row.get("end"):
                        continue
                    span = (date.fromisoformat(row["end"])
                            - date.fromisoformat(row["start"])).days
                    if not 80 <= span <= 100:
                        continue
                    points.append({
                        "period_end": row["end"],
                        "fiscal_period": f"{row.get('fy', '')}{row.get('fp', '')}",
                        "value": row["val"],
                        "form": row["form"],
                        "accession": row.get("accn", ""),
                        "filed_date": row.get("filed", ""),
                        "xbrl_tag": tag,
                    })
            if points:
                seen: dict[str, dict] = {}
                for point in sorted(points, key=lambda p: p["period_end"]):
                    seen[point["period_end"]] = point  # last write wins: the restated value
                out[label] = list(seen.values())[-quarters:]
                break
    return out


# Balance-sheet tags are "instant" facts: a snapshot on one date, so they carry
# an `end` but no `start`. That is why quarterly_fundamentals, which filters on
# a ~90-day span, cannot see them.
_INSTANT_CONCEPTS = {
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "equity": ("StockholdersEquity",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
}


def balance_sheet(symbol: str, points: int = 8) -> dict[str, list[dict]]:
    """Recent balance-sheet snapshots per concept, oldest first.

    Same provenance contract as quarterly_fundamentals: every figure keeps the
    accession number, so the UI can link the number to the filing that reported
    it and the number stays citable.
    """
    company = get_company(symbol)
    out: dict[str, list[dict]] = {}

    for label, tags in _INSTANT_CONCEPTS.items():
        for tag in tags:
            try:
                payload = _company_concept(company.cik, tag)
            except Exception:
                continue

            found: dict[str, dict] = {}
            for unit_rows in payload.get("units", {}).values():
                for row in unit_rows:
                    if row.get("form") not in {"10-Q", "10-K", "20-F"}:
                        continue
                    # An instant fact has no start date; a duration fact does.
                    if row.get("start") or not row.get("end"):
                        continue
                    found[row["end"]] = {
                        "as_of": row["end"],
                        "value": row["val"],
                        "form": row["form"],
                        "accession": row.get("accn", ""),
                        "filed_date": row.get("filed", ""),
                        "xbrl_tag": tag,
                    }
            if found:
                # Sorted by date, last write wins so restatements replace originals.
                out[label] = [found[k] for k in sorted(found)][-points:]
                break
    return out


# --- Taxonomy-agnostic facts, for the Research radar ------------------------
#
# These read `companyfacts`, which returns every tag a company has ever filed in
# one request. The per-tag `companyconcept` endpoint looked tidier but is not
# reliable: for Ford it answers 200 with the concept's metadata and no `units`
# at all for Assets, StockholdersEquity and its current revenue tag, while
# companyfacts has all three through 2026-03-31. One request per company is also
# far cheaper than one per tag.
#
# Two things vary by filer and are handled by trying candidates in order:
#   - Taxonomy. Foreign private issuers file 20-Fs under IFRS, so TSMC and ASML
#     have no us-gaap facts at all.
#   - Tag choice. Ford reports equity as
#     StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest,
#     and changed revenue tags in 2022.

DURATION_METRICS: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("ifrs-full", "Revenue"),
        ("ifrs-full", "RevenueFromContractsWithCustomers"),
    ),
    "net_income": (
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
        ("ifrs-full", "ProfitLoss"),
    ),
    "gross_profit": (("us-gaap", "GrossProfit"), ("ifrs-full", "GrossProfit")),
    "operating_income": (
        ("us-gaap", "OperatingIncomeLoss"),
        ("ifrs-full", "ProfitLossFromOperatingActivities"),
    ),
}

INSTANT_METRICS: dict[str, tuple[tuple[str, str], ...]] = {
    "total_assets": (("us-gaap", "Assets"), ("ifrs-full", "Assets")),
    "total_liabilities": (("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities")),
    "equity": (
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ("ifrs-full", "Equity"),
    ),
    "current_assets": (("us-gaap", "AssetsCurrent"), ("ifrs-full", "CurrentAssets")),
    "current_liabilities": (
        ("us-gaap", "LiabilitiesCurrent"), ("ifrs-full", "CurrentLiabilities")),
    # Used only to reconstruct a total when the filer never tags one.
    "noncurrent_liabilities": (("us-gaap", "LiabilitiesNoncurrent"),
                               ("ifrs-full", "NoncurrentLiabilities")),
}

_ACCEPTED_FORMS = {"10-Q", "10-K", "20-F", "40-F"}
_QUARTER_DAYS = (80, 100)
_YEAR_DAYS = (350, 380)


def company_facts(cik: str) -> dict:
    """Every XBRL fact a company has filed. One request, cached for a day."""
    return cached(
        f"edgar_companyfacts_{cik}",
        lambda: _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"),
        max_age_seconds=24 * 3600,
    )


def _facts_for(cik: str, taxonomy: str, tag: str) -> list[dict]:
    """Raw rows for one tag, or [] when the company never filed it."""
    try:
        payload = company_facts(cik)
    except Exception:
        return []
    tag_facts = payload.get("facts", {}).get(taxonomy, {}).get(tag)
    if not tag_facts:
        return []
    rows: list[dict] = []
    for unit_rows in tag_facts.get("units", {}).values():
        rows.extend(unit_rows)
    return rows


def _stale_days(as_of: str) -> int:
    return (date.today() - date.fromisoformat(as_of)).days


def _best_series(candidates: list[list[dict]], date_key: str) -> list[dict]:
    """Pick the series with the most recent data, breaking ties on length.

    Filers change tags: NVIDIA's older quarters sit under
    RevenueFromContractWithCustomerExcludingAssessedTax while current ones sit
    under Revenues, and Ford went the other way. Taking the first tag that had
    any data gave NVIDIA a revenue figure from 2020, so every candidate is
    evaluated and the freshest wins.
    """
    usable = [c for c in candidates if len(c) >= 2]
    if not usable:
        return []
    return max(usable, key=lambda series: (series[-1][date_key], len(series)))


def duration_facts(cik: str, metric: str, limit: int = 12) -> list[dict]:
    """Period figures (revenue, income) for one metric, oldest first.

    Quarterly where the filer reports quarters, else annual, never a mix -
    comparing a quarter against a year would misstate growth entirely.
    """
    if not cik:
        return []
    candidates: list[list[dict]] = []

    for taxonomy, tag in DURATION_METRICS.get(metric, ()):
        by_period: dict[str, dict[str, dict]] = {"quarter": {}, "year": {}}
        for row in _facts_for(cik, taxonomy, tag):
            if row.get("form") not in _ACCEPTED_FORMS:
                continue
            if not row.get("start") or not row.get("end"):
                continue
            span = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
            if _QUARTER_DAYS[0] <= span <= _QUARTER_DAYS[1]:
                kind = "quarter"
            elif _YEAR_DAYS[0] <= span <= _YEAR_DAYS[1]:
                kind = "year"
            else:
                continue
            by_period[kind][row["end"]] = {
                "period_end": row["end"], "period": kind, "value": row["val"],
                "form": row["form"], "accession": row.get("accn", ""),
                "filed_date": row.get("filed", ""), "xbrl_tag": tag,
                "taxonomy": taxonomy,
            }
        for kind in ("quarter", "year"):
            if by_period[kind]:
                candidates.append([by_period[kind][k] for k in sorted(by_period[kind])][-limit:])

    series = _best_series(candidates, "period_end")
    if series:
        # Prefer quarterly when it is no staler than the best annual series:
        # four quarters give a real year-over-year comparison.
        quarterly = [c for c in candidates if c and c[0]["period"] == "quarter"]
        best_q = _best_series(quarterly, "period_end")
        if best_q and best_q[-1]["period_end"] >= series[-1]["period_end"]:
            series = best_q
    for point in series:
        point["stale_days"] = _stale_days(point["period_end"])
    return series


def instant_facts(cik: str, metric: str, limit: int = 8) -> list[dict]:
    """Balance-sheet snapshots for one metric, oldest first.

    `total_liabilities` is reconstructed when the filer never tags a total:
    plenty report only current and non-current, or leave it to the accounting
    identity. Reconstructed figures are marked `derived`.
    """
    if not cik:
        return []
    candidates: list[list[dict]] = []

    for taxonomy, tag in INSTANT_METRICS.get(metric, ()):
        found: dict[str, dict] = {}
        for row in _facts_for(cik, taxonomy, tag):
            if row.get("form") not in _ACCEPTED_FORMS:
                continue
            # An instant fact has no start date; a duration fact does.
            if row.get("start") or not row.get("end"):
                continue
            found[row["end"]] = {
                "as_of": row["end"], "value": row["val"], "form": row["form"],
                "accession": row.get("accn", ""), "filed_date": row.get("filed", ""),
                "xbrl_tag": tag, "taxonomy": taxonomy,
            }
        if found:
            candidates.append([found[k] for k in sorted(found)][-limit:])

    series = _best_series(candidates, "as_of")
    if not series and metric == "total_liabilities":
        series = _derived_liabilities(cik, limit)
    for point in series:
        point["stale_days"] = _stale_days(point["as_of"])
    return series


def _combine(a: list[dict], b: list[dict], op, tag: str, limit: int) -> list[dict]:
    """Element-wise combine two instant series on their shared dates."""
    left = {p["as_of"]: p for p in a}
    right = {p["as_of"]: p for p in b}
    return [{
        "as_of": day,
        "value": op(left[day]["value"], right[day]["value"]),
        "form": left[day]["form"],
        "accession": left[day]["accession"],
        "filed_date": left[day]["filed_date"],
        "xbrl_tag": tag,
        "taxonomy": left[day]["taxonomy"],
        "derived": True,
    } for day in sorted(set(left) & set(right))][-limit:]


def _derived_liabilities(cik: str, limit: int) -> list[dict]:
    """Total liabilities, for filers that never tag one.

    Assets minus equity first, since both are common; otherwise current plus
    non-current liabilities.
    """
    assets = instant_facts(cik, "total_assets", limit)
    equity = instant_facts(cik, "equity", limit)
    if assets and equity:
        derived = _combine(assets, equity, lambda x, y: x - y,
                           "Assets - StockholdersEquity", limit)
        if derived:
            return derived

    current = instant_facts(cik, "current_liabilities", limit)
    noncurrent = instant_facts(cik, "noncurrent_liabilities", limit)
    if current and noncurrent:
        return _combine(current, noncurrent, lambda x, y: x + y,
                        "LiabilitiesCurrent + LiabilitiesNoncurrent", limit)
    return []
