#!/usr/bin/env python3
"""Refresh everything the app serves, in one step. Run before a demo, or on a
schedule later (a cron job or CI workflow would run exactly this command).

    python -m scripts.refresh                  # stories + feed for every company
    python -m scripts.refresh --snowflake      # ...then load it all into Snowflake
    python -m scripts.refresh --skip-stories   # just the feed (about 3 minutes)

Steps, in order:
  1. Story Mode   6 months of prices (Yahoo) and news (Finnhub), explained by
                  Gemini. Quotes and sparklines come from these prices, so this
                  also moves "Prices as of ... close" forward. About 5 minutes.
  2. What Changed last week's news grouped into cited events by Gemini.
  3. Snowflake    (only with --snowflake) graph, stories, prices, and news.

Needs GEMINI_API_KEY, FINNHUB_API_KEY, and SEC_USER_AGENT in .env (and the
Snowflake settings for step 3). The results are saved files under
backend/data/cache/; commit them so everyone, and the demo, gets the fresh data.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import load  # noqa: E402
from app.universe import SYMBOLS  # noqa: E402
from scripts import build_feed, build_story_cache, load_snowflake  # noqa: E402


def _freshness() -> str:
    story = load(f"story_{SYMBOLS[0]}")
    feed = load("feed_events") or {}
    prices = story["bars"][-1]["date"] if story else "none"
    return f"prices through {prices}, news through {feed.get('as_of', 'none')}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbols", nargs="*", help="only these companies (default: all)")
    parser.add_argument("--skip-stories", action="store_true", help="skip Story Mode (and quotes)")
    parser.add_argument("--skip-feed", action="store_true", help="skip What Changed")
    parser.add_argument("--snowflake", action="store_true", help="also load everything into Snowflake")
    args = parser.parse_args(argv)
    symbols = [s.upper() for s in args.symbols] or list(SYMBOLS)

    print(f"Before: {_freshness()}")
    steps = []
    if not args.skip_stories:
        steps.append(("Story Mode", lambda: build_story_cache.main(symbols)))
    if not args.skip_feed:
        steps.append(("What Changed", lambda: build_feed.main(symbols)))
    if args.snowflake:
        steps.append(("Snowflake", lambda: load_snowflake.main(symbols)))

    results = []
    for name, run in steps:
        print(f"\n########## {name} ##########", flush=True)
        started = time.time()
        try:
            code = run()
        except Exception as exc:  # keep going: one failed step should not block the rest
            print(f"{name} FAILED: {type(exc).__name__}: {exc}")
            code = 1
        results.append((name, code, time.time() - started))

    print("\n########## Summary ##########")
    for name, code, seconds in results:
        print(f"  {name:<13} {'ok' if code == 0 else 'had failures'}  ({seconds:.0f}s)")
    print(f"After:  {_freshness()}")
    print("Commit backend/data/cache/story_*.json and feed_events.json to share the fresh data.")
    return 0 if all(code == 0 for _, code, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
