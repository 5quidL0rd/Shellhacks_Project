#!/usr/bin/env python3
"""Load Story Mode data into Snowflake.

    python -m scripts.load_snowflake                     # graph, stories, prices, news for every company
    python -m scripts.load_snowflake graph               # just the knowledge graph tables
    python -m scripts.load_snowflake stories             # just the stories
    python -m scripts.load_snowflake prices news NVDA    # some datasets, some companies

Stories come from the committed cache (data/cache/story_*.json), so build them
first with scripts.build_story_cache. The graph comes from data/exports/ (run
kg.load and kg.export_edges first). Prices and news use the same fetchers as
Story Mode (cached for a few hours). Safe to re-run: the graph is replaced
whole, stories are replaced per company, prices and news are upserted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import warehouse  # noqa: E402
from app.cache import load  # noqa: E402
from app.config import GRAPH_EDGES_CSV  # noqa: E402
from app.snowflake_db import get_connection  # noqa: E402
from app.universe import SYMBOLS  # noqa: E402

DATASETS = ("graph", "stories", "prices", "news")


def main(args: list[str]) -> int:
    datasets = [a.lower() for a in args if a.lower() in DATASETS] or list(DATASETS)
    symbols = [a.upper() for a in args if a.lower() not in DATASETS] or list(SYMBOLS)
    unknown = [s for s in symbols if s not in SYMBOLS]
    if unknown:
        print(f"Unknown symbols {unknown}; supported: {list(SYMBOLS)}")
        return 2

    failures = 0
    with get_connection() as conn:
        if "graph" in datasets:
            counts = warehouse.replace_graph(
                conn, GRAPH_EDGES_CSV, GRAPH_EDGES_CSV.with_name("graph_companies.csv"))
            print(f"graph: {counts['edges']} edges, {counts['companies']} companies (tables replaced)")
            if datasets == ["graph"]:
                symbols = []
        for symbol in symbols:
            print(f"\n=== {symbol} ===", flush=True)
            if "stories" in datasets:
                story = load(f"story_{symbol}")
                if story is None:
                    print("  stories: no cached story; run scripts.build_story_cache first")
                    failures += 1
                else:
                    counts = warehouse.replace_story(conn, story)
                    print(f"  stories: 1 story, {counts['events']} events, "
                          f"{counts['evidence']} evidence rows")
            for name, loader in (("prices", warehouse.upsert_prices),
                                 ("news", warehouse.upsert_news)):
                if name not in datasets:
                    continue
                try:
                    print(f"  {name}: {loader(conn, symbol)} rows upserted")
                except Exception as exc:
                    print(f"  {name}: FAILED {type(exc).__name__}: {exc}")
                    failures += 1

    print(f"\nDone{' with ' + str(failures) + ' failure(s)' if failures else ''}.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
