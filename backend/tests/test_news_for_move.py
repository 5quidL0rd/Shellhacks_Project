"""Per-move news: fetched for the move's own dates, ranked by relevance."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources import news  # noqa: E402
from app.story import build  # noqa: E402
from app.universe import Company  # noqa: E402

AVGO = Company("AVGO", "Broadcom Inc.", "0001730168", "Semiconductors", ("Broadcom",))


def article(headline, day="2026-06-04", url=None, summary="", hour="14"):
    return {"headline": headline, "summary": summary, "publisher": "Wire",
            "url": url or f"https://x/{headline}", "id": hash(headline),
            "published_at": f"{day}T{hour}:00:00+00:00", "date": day, "category": "company"}


def test_articles_naming_the_company_come_first():
    roundup = article("Stocks close lower as chip names slide", hour="20")
    in_summary = article("Chipmakers fall", summary="Broadcom led declines.", hour="19")
    in_headline = article("Broadcom plunges after guidance", hour="15")
    ranked = build.rank_news(AVGO, [roundup, in_summary, in_headline])
    assert [a["headline"] for a in ranked] == [
        "Broadcom plunges after guidance", "Chipmakers fall", "Stocks close lower as chip names slide"]


def test_ticker_in_headline_counts_as_a_mention():
    assert build.rank_news(AVGO, [article("Markets wrap"), article("AVGO falls 12%")])[0]["headline"] == "AVGO falls 12%"


def test_move_news_merges_recent_and_per_date_without_duplicates(monkeypatch):
    shared = article("Broadcom plunges after guidance")
    older = article("Broadcom outlook disappoints", day="2026-06-03")
    calls = []

    def fake_between(symbol, start, end):
        calls.append((symbol, start, end))
        return [shared, older]

    monkeypatch.setattr(news, "news_between", fake_between)
    got = build.news_for_move(AVGO, "2026-06-04", recent_news=[shared])
    assert calls == [("AVGO", "2026-06-03", "2026-06-04")]
    assert sorted(a["headline"] for a in got) == sorted([shared["headline"], older["headline"]])
    assert all(a["via"] == news.SOURCE_NAME for a in got)


def test_a_failed_per_date_request_falls_back_to_recent_news(monkeypatch):
    def boom(*_):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(news, "news_between", boom)
    recent = article("Broadcom plunges after guidance")
    got = build.news_for_move(AVGO, "2026-06-04", recent_news=[recent])
    assert [a["headline"] for a in got] == [recent["headline"]]


def test_news_outside_the_two_day_window_is_ignored(monkeypatch):
    monkeypatch.setattr(news, "news_between", lambda *_: [])
    stale = article("Broadcom news from last week", day="2026-05-28")
    assert build.news_for_move(AVGO, "2026-06-04", recent_news=[stale]) == []
