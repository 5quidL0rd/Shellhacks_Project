"""What Changed feed: event citations, article filtering, tiers, and ranking."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.feed import events, rank  # noqa: E402


def article(headline, day="2026-09-24", url=None, summary=""):
    return {"headline": headline, "summary": summary, "publisher": "Wire",
            "url": url or f"https://x/{headline}", "date": day,
            "published_at": f"{day}T14:00:00+00:00"}


# --- events ------------------------------------------------------------------

def test_events_keep_only_real_citations():
    articles = {"a0": article("TSMC raises prices"), "a1": article("TSMC expands")}
    raw = [
        {"headline": "Prices up", "citation_ids": ["a0", "a9"]},
        {"headline": "Invented", "citation_ids": ["a7"]},
        {"headline": "Uncited", "citation_ids": []},
    ]
    kept, warnings = events.verify_events(raw, articles)
    assert [e["headline"] for e in kept] == ["Prices up"]
    assert kept[0]["citation_ids"] == ["a0"]
    # a9 dropped; a7 dropped and its event removed; the uncited event removed
    assert len(warnings) == 4


def test_recent_articles_are_in_window_about_the_company_and_deduplicated():
    items = [
        article("Taiwan Semiconductor raises wafer prices", "2026-09-25"),
        article("Taiwan Semiconductor raises wafer prices", "2026-09-25"),  # same URL
        article("Stocks close higher on Friday", "2026-09-25"),             # roundup
        article("TSMC opens Arizona fab", "2026-09-10"),                    # too old
        article("Chip index rallies", "2026-09-24", summary="TSMC led gains."),
    ]
    got = events.recent_articles("TSM", items, date(2026, 9, 26))
    assert [a["headline"] for a in got] == [
        "Taiwan Semiconductor raises wafer prices", "Chip index rallies"]


# --- tiers -------------------------------------------------------------------

def fake_impact(affected):
    def impact(company, holdings):
        return {"affected": [a for a in affected if a["ticker"] in holdings]}
    return impact


def test_tier_1_for_your_holding_also_lists_connected_holdings(monkeypatch):
    monkeypatch.setattr(rank.portfolio, "impact", fake_impact([
        {"ticker": "AAPL", "connections": [
            {"role": "customer", "explanation": "TSMC supplies Apple", "evidence": []}]},
    ]))
    tier, touches = rank._touches("TSM", ["TSM", "AAPL"])
    assert tier == 1
    assert [(t["ticker"], t["role"]) for t in touches] == [("TSM", "holding"), ("AAPL", "customer")]


def test_tier_2_for_a_connected_company(monkeypatch):
    monkeypatch.setattr(rank.portfolio, "impact", fake_impact([
        {"ticker": "NVDA", "connections": [
            {"role": "competitor", "explanation": "NVIDIA competes with Intel", "evidence": []},
            {"role": "customer", "explanation": "Intel supplies NVIDIA", "evidence": []}]},
    ]))
    tier, touches = rank._touches("INTC", ["NVDA"])
    assert tier == 2
    assert touches[0]["role"] == "customer"  # the supply link outranks competition


def test_tier_3_for_same_sector_and_none_when_unrelated(monkeypatch):
    monkeypatch.setattr(rank.portfolio, "impact", fake_impact([]))
    tier, touches = rank._touches("MU", ["AMD"])  # both Semiconductors, no graph link
    assert tier == 3 and touches[0]["ticker"] == "AMD"
    assert rank._touches("MU", ["MSFT"]) == (None, [])  # Software, unconnected


# --- ranking -----------------------------------------------------------------

def test_feed_ranks_by_tier_then_importance_then_recency(monkeypatch):
    def event(symbol, importance, day):
        return {"id": f"{symbol}_{day}_{importance}", "symbol": symbol, "headline": "h",
                "summary": "s", "event_type": "other", "tone": "neutral",
                "importance": importance, "first_seen": day, "last_seen": day, "sources": []}

    monkeypatch.setattr(rank.events_mod, "load_events", lambda: {
        "as_of": "2026-09-26", "companies": {
            "AAPL": {"events": [event("AAPL", "low", "2026-09-25")]},
            "TSM": {"events": [event("TSM", "high", "2026-09-24"),
                               event("TSM", "high", "2026-09-26")]},
            "MSFT": {"events": [event("MSFT", "high", "2026-09-26")]},
        }})
    monkeypatch.setattr(rank.quotes, "quotes", lambda: {"quotes": {}})
    tiers = {"AAPL": (1, []), "TSM": (2, []), "MSFT": (None, [])}
    monkeypatch.setattr(rank, "_touches", lambda s, h: tiers[s])

    result = rank.feed(["AAPL"])
    assert [i["id"] for i in result["items"]] == [
        "AAPL_2026-09-25_low",    # your holding first, even at low importance
        "TSM_2026-09-26_high",    # then connected, newest first
        "TSM_2026-09-24_high",
    ]                             # MSFT is unrelated and left out
    assert result["counts"] == {"Your holding": 1, "Connected company": 2, "Same sector": 0}
    assert [i["id"] for i in rank.feed(["AAPL"], tier_filter=2)["items"]][0] == "TSM_2026-09-26_high"
