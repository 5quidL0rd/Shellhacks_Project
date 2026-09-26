#!/usr/bin/env python3
"""Load Story Mode data into Snowflake.

    python -m scripts.load_snowflake                     # stories, prices, news for all five
    python -m scripts.load_snowflake stories             # just the stories
    python -m scripts.load_snowflake prices news NVDA    # some datasets, some companies

Stories come from the committed cache (data/cache/story_*.json), so build them
first with scripts.build_story_cache. Prices and news use the same fetchers as
Story Mode (cached for a few hours). Safe to re-run: stories are replaced per
company, prices and news are upserted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import warehouse  # noqa: E402
from app.cache import load  # noqa: E402
from app.snowflake_db import get_connection  # noqa: E402
from app.universe import SYMBOLS  # noqa: E402

DATASETS = ("stories", "prices", "news")


def main(args: list[str]) -> int:
    datasets = [a.lower() for a in args if a.lower() in DATASETS] or list(DATASETS)
    symbols = [a.upper() for a in args if a.lower() not in DATASETS] or list(SYMBOLS)
    unknown = [s for s in symbols if s not in SYMBOLS]
    if unknown:
        print(f"Unknown symbols {unknown}; supported: {list(SYMBOLS)}")
        return 2

    failures = 0
    with get_connection() as conn:
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
