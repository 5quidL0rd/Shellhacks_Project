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


def _company_concept(cik: str, tag: str) -> dict:
    return cached(
        f"edgar_concept_{cik}_{tag}",
        lambda: _get(
            "https://data.sec.gov/api/xbrl/companyconcept/"
            f"CIK{cik}/us-gaap/{tag}.json"
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
