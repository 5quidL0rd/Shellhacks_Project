#!/usr/bin/env python3
"""Precompute every story before the demo.

    python -m scripts.build_story_cache            # all five companies
    python -m scripts.build_story_cache NVDA AMD   # just these

Run this once you have keys in .env. After it finishes, the API serves entirely
from data/cache/ and the demo cannot be broken by a rate limit on stage.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.story.build import build_story  # noqa: E402
from app.cache import save  # noqa: E402
from app.universe import SYMBOLS  # noqa: E402


def main(symbols: list[str]) -> int:
    failures = 0
    for symbol in symbols:
        print(f"\n=== {symbol} ===", flush=True)
        try:
            story = build_story(symbol)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        save(f"story_{symbol}", story.model_dump(mode="json"))
        print(f"  {len(story.beats)} beats, {len(story.evidence)} evidence rows")
        for beat in story.beats:
            print(f"  {beat.date}  {beat.pct_change:+6.2f}%  [{beat.confidence:6}] "
                  f"{beat.headline}  ({len(beat.citation_ids)} citations)")
        for warning in story.warnings:
            print(f"  WARN: {warning}")

    print(f"\nDone. {len(symbols) - failures}/{len(symbols)} built.")
    return 1 if failures else 0


if __name__ == "__main__":
    requested = [s.upper() for s in sys.argv[1:]] or list(SYMBOLS)
    raise SystemExit(main(requested))
