"""The What Changed feed for one portfolio: saved events, ranked by relevance.

Why an event matters is decided by the knowledge graph, not AI, so every
"touches" line can be traced to a filing (Product.md: "the graph handles
logic"). Tiers, most relevant first:

  1  about a company you own
  2  about a company connected to one you own (supplier, customer, competitor,
     or one supply-chain step further), with the path
  3  about a company in the same sector as one you own

Within a tier: importance, then most recent. Events about companies with no
link to the portfolio are left out; that is the point of a short feed.
"""
from __future__ import annotations

from .. import portfolio, quotes
from ..universe import COMPANIES
from . import events as events_mod

TIER_LABELS = {1: "Your holding", 2: "Connected company", 3: "Same sector"}
IMPORTANCE_RANK = {"high": 0, "medium": 1, "low": 2}
# Order the "touches" list: direct supply-chain links first, competitors last.
ROLE_ORDER = {"holding": 0, "customer": 1, "supplier": 2, "indirect_customer": 3,
              "competitor": 4, "same_sector": 5}


def _touches(symbol: str, holdings: list[str]) -> tuple[int | None, list[dict]]:
    """(tier, holdings the event reaches and how). Tier None = not relevant."""
    touches: list[dict] = []
    if symbol in holdings:
        touches.append({"ticker": symbol, "role": "holding",
                        "explanation": f"You own {symbol}."})

    others = [h for h in holdings if h != symbol]
    try:
        impact = portfolio.impact(symbol, others) if others else {"affected": []}
    except KeyError:  # not in the graph
        impact = {"affected": []}
    for affected in impact["affected"]:
        best = min(affected["connections"], key=lambda c: ROLE_ORDER.get(c["role"], 9))
        touches.append({"ticker": affected["ticker"], "role": best["role"],
                        "explanation": best["explanation"] + ".",
                        "evidence": best["evidence"]})

    if touches:
        return (1 if symbol in holdings else 2), sorted(
            touches, key=lambda t: (ROLE_ORDER.get(t["role"], 9), t["ticker"]))

    sector = COMPANIES[symbol].sector if symbol in COMPANIES else None
    same = sorted(h for h in others if h in COMPANIES and COMPANIES[h].sector == sector)
    if sector and same:
        return 3, [{"ticker": h, "role": "same_sector",
                    "explanation": f"{h} is also in {sector}."} for h in same]
    return None, []


def feed(holdings: list[str], tier_filter: int | None = None, limit: int = 40) -> dict:
    saved = events_mod.load_events()
    q = quotes.quotes()["quotes"]

    items = []
    for symbol, company_events in saved.get("companies", {}).items():
        tier, touches = _touches(symbol, holdings)
        if tier is None or (tier_filter and tier != tier_filter):
            continue
        company = COMPANIES.get(symbol)
        for event in company_events.get("events", []):
            items.append({
                **event,
                "company_name": company.name if company else symbol,
                "tier": tier,
                "tier_label": TIER_LABELS[tier],
                "touches": touches,
                "change_pct": q.get(symbol, {}).get("change_pct"),
            })

    items.sort(key=lambda i: (i["tier"], IMPORTANCE_RANK.get(i["importance"], 3),
                              _neg_date(i["last_seen"]), i["symbol"]))
    counts = {t: sum(1 for i in items if i["tier"] == t) for t in TIER_LABELS}
    return {
        "as_of": saved.get("as_of"),
        "generated_at": saved.get("generated_at"),
        "window_days": events_mod.WINDOW_DAYS,
        "counts": {TIER_LABELS[t]: n for t, n in counts.items()},
        "items": items[:limit],
    }


def _neg_date(iso: str) -> int:
    """Sort key that puts later dates first."""
    return -int(iso.replace("-", ""))
