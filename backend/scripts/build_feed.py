#!/usr/bin/env python3
"""Precompute the What Changed feed's events before the demo.

    python -m scripts.build_feed            # every supported company
    python -m scripts.build_feed NVDA TSM   # just these

Fetches the last week of Finnhub news per company and has Gemini group it into
a few cited events (one call per company). Saves data/cache/feed_events.json,
which is committed, so the API serves the feed without live calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.feed import events  # noqa: E402
from app.universe import SYMBOLS  # noqa: E402


def main(args: list[str]) -> int:
    symbols = [a.upper() for a in args] or list(SYMBOLS)
    unknown = [s for s in symbols if s not in SYMBOLS]
    if unknown:
        print(f"Unknown symbols {unknown}; supported: {list(SYMBOLS)}")
        return 2
    saved = events.build(symbols)
    total = sum(len(c["events"]) for c in saved["companies"].values())
    print(f"\nDone: {total} events across {len(saved['companies'])} companies, "
          f"news through {saved['as_of']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
