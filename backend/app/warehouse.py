"""Load Story Mode data into Snowflake.

Tables are defined in snowflake/schema_contract.sql. Two write patterns:

- Stories are replaced per company: STORIES, STORY_EVENTS and STORY_EVIDENCE
  rows for a symbol are deleted and re-inserted in one transaction, so a
  rebuilt story never leaves stale beats or evidence behind.
- Prices and news are upserted (MERGE on their keys), so reloading is safe
  and news accumulates history beyond Finnhub's few-day free window.

Row builders are pure functions so they can be tested without Snowflake.
"""
from __future__ import annotations

import json
from typing import Iterable, Sequence

from .sources import news as news_source
from .sources import prices as price_source

CHUNK_ROWS = 200  # rows per statement; keeps each bound query a sensible size


# --- row builders -----------------------------------------------------------

def story_rows(story: dict) -> tuple[tuple, list[tuple], list[tuple]]:
    """(STORIES row, STORY_EVENTS rows, STORY_EVIDENCE rows) for one story."""
    symbol = story["symbol"]
    story_id = symbol
    story_row = (
        story_id, symbol, story.get("company_name"), story.get("generated_at") or None,
        story.get("arc") or "", json.dumps(story.get("arc_citation_ids", [])),
        json.dumps(story.get("warnings", [])),
    )
    events = [
        (
            f"{symbol}_{beat['date']}", story_id, symbol, beat["date"], "price_move",
            beat["pct_change"], beat["close"], beat["direction"], beat["headline"],
            beat["explanation"], beat["confidence"], json.dumps(beat.get("citation_ids", [])),
        )
        for beat in story.get("beats", [])
    ]
    evidence = [
        (
            item["id"], story_id, symbol, item["kind"], item.get("title"), item.get("detail"),
            item.get("source"), item.get("url"), item.get("occurred_on") or None,
            json.dumps(item.get("numbers", {})),
        )
        for item in story.get("evidence", {}).values()
    ]
    return story_row, events, evidence


def price_rows(symbol: str, bars: Iterable[dict]) -> list[tuple]:
    """PRICES rows, one per (ticker, date); a later bar for the same date wins."""
    by_date = {
        bar["date"]: (symbol, bar["date"], bar.get("open"), bar.get("high"), bar.get("low"),
                      bar["close"], bar.get("volume"), price_source.SOURCE_NAME)
        for bar in bars
    }
    return list(by_date.values())


def news_rows(symbol: str, items: Iterable[dict]) -> list[tuple]:
    """NEWS rows. The same Finnhub article can be listed under several
    tickers, so the id includes the ticker."""
    by_id = {}
    for item in items:
        if item.get("id") is None:
            continue
        news_id = f"finnhub-{item['id']}-{symbol}"
        by_id[news_id] = (
            news_id, symbol, item["published_at"], item["headline"] or "(no headline)",
            item.get("summary") or None, item.get("url"), item.get("publisher"),
            item.get("category") or None,
        )
    return list(by_id.values())


# --- SQL helpers ------------------------------------------------------------

def _chunks(rows: Sequence[tuple], size: int = CHUNK_ROWS):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _values_clause(rows: Sequence[tuple]) -> tuple[str, list]:
    """'VALUES (%s, %s), (%s, %s)' plus the flattened parameters."""
    width = len(rows[0])
    row_sql = "(" + ", ".join(["%s"] * width) + ")"
    params = [value for row in rows for value in row]
    return "VALUES " + ", ".join([row_sql] * len(rows)), params


def _insert(cur, table: str, columns: Sequence[str], exprs: Sequence[str], rows: Sequence[tuple]) -> None:
    """INSERT ... SELECT <exprs over $1..$n> FROM VALUES (...). The SELECT lets
    columns be converted on the way in (PARSE_JSON for ARRAY/VARIANT, dates)."""
    for chunk in _chunks(rows):
        values, params = _values_clause(chunk)
        cur.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"SELECT {', '.join(exprs)} FROM {values}",
            params,
        )


def _merge(cur, table: str, columns: Sequence[str], exprs: Sequence[str],
           keys: Sequence[str], rows: Sequence[tuple]) -> None:
    """Upsert rows on `keys`: update matches, insert the rest."""
    source_cols = ", ".join(f"{expr} AS {col}" for col, expr in zip(columns, exprs))
    on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    updates = ", ".join(f"t.{c} = s.{c}" for c in columns if c not in keys)
    inserts = ", ".join(f"s.{c}" for c in columns)
    for chunk in _chunks(rows):
        values, params = _values_clause(chunk)
        cur.execute(
            f"MERGE INTO {table} t USING (SELECT {source_cols} FROM {values}) s ON {on} "
            f"WHEN MATCHED THEN UPDATE SET {updates}, t.INGESTED_AT = CURRENT_TIMESTAMP() "
            f"WHEN NOT MATCHED THEN INSERT ({', '.join(columns)}) VALUES ({inserts})",
            params,
        )


# --- loaders ----------------------------------------------------------------

STORY_COLUMNS = ("STORY_ID", "SYMBOL", "COMPANY_NAME", "GENERATED_AT", "ARC",
                 "ARC_CITATION_IDS", "WARNINGS")
STORY_EXPRS = ("$1", "$2", "$3", "TRY_TO_TIMESTAMP_TZ($4)", "$5",
               "PARSE_JSON($6)::ARRAY", "PARSE_JSON($7)::ARRAY")

EVENT_COLUMNS = ("EVENT_ID", "STORY_ID", "SYMBOL", "EVENT_DATE", "EVENT_TYPE",
                 "PRICE_MOVE_PCT", "CLOSE_PRICE", "DIRECTION", "HEADLINE", "SUMMARY",
                 "CONFIDENCE", "CITATION_IDS")
EVENT_EXPRS = ("$1", "$2", "$3", "$4::DATE", "$5", "$6", "$7", "$8", "$9", "$10",
               "$11", "PARSE_JSON($12)::ARRAY")

EVIDENCE_COLUMNS = ("EVIDENCE_ID", "STORY_ID", "SYMBOL", "KIND", "TITLE", "DETAIL",
                    "SOURCE", "URL", "OCCURRED_ON", "NUMBERS")
EVIDENCE_EXPRS = ("$1", "$2", "$3", "$4", "$5", "$6", "$7", "$8",
                  "TRY_TO_DATE($9)", "PARSE_JSON($10)")

PRICE_COLUMNS = ("TICKER", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "SOURCE")
PRICE_EXPRS = ("$1", "$2::DATE", "$3", "$4", "$5", "$6", "$7", "$8")

NEWS_COLUMNS = ("NEWS_ID", "TICKER", "PUBLISHED_AT", "HEADLINE", "SUMMARY", "URL",
                "SOURCE", "CATEGORY")
NEWS_EXPRS = ("$1", "$2", "TO_TIMESTAMP_TZ($3)", "$4", "$5", "$6", "$7", "$8")


def replace_story(conn, story: dict) -> dict:
    """Replace one company's story rows in a single transaction."""
    story_row, events, evidence = story_rows(story)
    symbol = story["symbol"]
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        for table in ("STORY_EVIDENCE", "STORY_EVENTS", "STORIES"):
            cur.execute(f"DELETE FROM {table} WHERE SYMBOL = %s", (symbol,))
        _insert(cur, "STORIES", STORY_COLUMNS, STORY_EXPRS, [story_row])
        if events:
            _insert(cur, "STORY_EVENTS", EVENT_COLUMNS, EVENT_EXPRS, events)
        if evidence:
            _insert(cur, "STORY_EVIDENCE", EVIDENCE_COLUMNS, EVIDENCE_EXPRS, evidence)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.close()
    return {"events": len(events), "evidence": len(evidence)}


def upsert_prices(conn, symbol: str, days: int | None = None) -> int:
    bars = price_source.daily_bars(symbol, days) if days else price_source.daily_bars(symbol)
    rows = price_rows(symbol, bars)
    if rows:
        with conn.cursor() as cur:
            _merge(cur, "PRICES", PRICE_COLUMNS, PRICE_EXPRS, ("TICKER", "DATE"), rows)
    return len(rows)


def upsert_news(conn, symbol: str) -> int:
    rows = news_rows(symbol, news_source.company_news(symbol))
    if rows:
        with conn.cursor() as cur:
            _merge(cur, "NEWS", NEWS_COLUMNS, NEWS_EXPRS, ("NEWS_ID",), rows)
    return len(rows)
