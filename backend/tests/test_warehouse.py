"""Row builders for the Snowflake loaders: every citation survives the trip."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.warehouse import (  # noqa: E402
    EVENT_COLUMNS, EVIDENCE_COLUMNS, STORY_COLUMNS, _values_clause, news_rows,
    price_rows, story_rows,
)

STORY = {
    "symbol": "NVDA",
    "company_name": "NVIDIA Corporation",
    "generated_at": "2026-09-26T09:16:03+00:00",
    "arc": "A volatile half year.",
    "arc_citation_ids": ["ev_NVDA_20260827_price"],
    "warnings": [],
    "beats": [{
        "date": "2026-08-27", "pct_change": 8.738, "close": 227.98, "direction": "up",
        "headline": "NVDA surges 8.7% after filings", "explanation": "It rose.",
        "confidence": "high",
        "citation_ids": ["ev_NVDA_20260827_price", "ev_NVDA_20260827_peer_TSM"],
    }],
    "evidence": {
        "ev_NVDA_20260827_price": {
            "id": "ev_NVDA_20260827_price", "kind": "price", "title": "NVDA rose 8.74%",
            "detail": "", "source": "Yahoo", "url": "https://finance.yahoo.com/quote/NVDA/history",
            "occurred_on": "2026-08-27", "numbers": {"pct_change": 8.738},
        },
        "ev_NVDA_20260827_peer_TSM": {
            "id": "ev_NVDA_20260827_peer_TSM", "kind": "peer_move", "title": "TSM (supplier)",
            "detail": "", "source": "Yahoo", "url": None, "occurred_on": "2026-08-27",
            "numbers": {"relationship": "supplier"},
        },
    },
}


def test_story_rows_match_their_columns():
    story, events, evidence = story_rows(STORY)
    assert len(story) == len(STORY_COLUMNS)
    assert all(len(row) == len(EVENT_COLUMNS) for row in events)
    assert all(len(row) == len(EVIDENCE_COLUMNS) for row in evidence)


def test_every_citation_is_kept():
    _, events, evidence = story_rows(STORY)
    (event,) = events
    cited = json.loads(event[EVENT_COLUMNS.index("CITATION_IDS")])
    assert cited == STORY["beats"][0]["citation_ids"]
    assert {row[0] for row in evidence} == set(cited)


def test_event_ids_are_stable_so_reloads_replace_rows():
    _, first, _ = story_rows(STORY)
    _, second, _ = story_rows(STORY)
    assert first[0][0] == second[0][0] == "NVDA_2026-08-27"


def test_confidence_stays_as_words():
    _, events, _ = story_rows(STORY)
    assert events[0][EVENT_COLUMNS.index("CONFIDENCE")] == "high"


def test_price_rows_keep_one_row_per_date():
    bars = [{"date": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"date": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.6, "volume": 11}]
    (row,) = price_rows("NVDA", bars)
    assert row[:2] == ("NVDA", "2026-01-02")
    assert row[5] == 1.6


def test_news_ids_include_the_ticker():
    item = {"id": 42, "published_at": "2026-09-21T14:00:00+00:00", "headline": "AMD hits $1T",
            "summary": "", "url": "https://x", "publisher": "Yahoo", "category": "company"}
    assert news_rows("AMD", [item])[0][0] == "finnhub-42-AMD"
    assert news_rows("NVDA", [item])[0][0] == "finnhub-42-NVDA"


def test_news_without_an_id_is_skipped():
    assert news_rows("AMD", [{"id": None, "headline": "x", "published_at": "2026-01-01"}]) == []


def test_values_clause_binds_every_value():
    sql, params = _values_clause([(1, "a"), (2, "b")])
    assert sql == "VALUES (%s, %s), (%s, %s)"
    assert params == [1, "a", 2, "b"]


def test_graph_csv_rows_turn_empty_cells_into_nulls(tmp_path):
    from app.warehouse import GRAPH_COMPANY_COLUMNS, csv_rows
    path = tmp_path / "graph_companies.csv"
    path.write_text("ticker,name,in_universe,cik,sector,hq_country\n"
                    "AAPL,Apple Inc.,True,320193,Technology Hardware,United States\n"
                    "samsung-electronics,Samsung Electronics,False,,,\n", encoding="utf-8")
    rows = csv_rows(path, GRAPH_COMPANY_COLUMNS)
    assert rows[0] == ("AAPL", "Apple Inc.", "True", "320193", "Technology Hardware", "United States")
    assert rows[1] == ("samsung-electronics", "Samsung Electronics", "False", None, None, None)


def test_graph_csv_rows_reject_a_missing_column(tmp_path):
    import pytest
    from app.warehouse import GRAPH_COMPANY_COLUMNS, csv_rows
    path = tmp_path / "graph_companies.csv"
    path.write_text("ticker,name\nAAPL,Apple\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        csv_rows(path, GRAPH_COMPANY_COLUMNS)
