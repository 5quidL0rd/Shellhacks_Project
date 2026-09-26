#!/usr/bin/env python3
"""Print a story in the terminal with every citation resolved.

This is the fastest way to see what Story Mode produces, and to sanity-check
that each explanation really is backed by a source you can open.

    python -m scripts.show_story NVDA              # from the cache
    python -m scripts.show_story NVDA --days 30    # build a short window now
    python -m scripts.show_story NVDA --refresh    # rebuild the full window
    python -m scripts.show_story NVDA --json       # raw payload the API returns
"""
import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import load, save  # noqa: E402
from app.story.build import build_story  # noqa: E402
from app.story.schema import Story  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, RED, YELLOW = "\033[32m", "\033[31m", "\033[33m"

CONFIDENCE_COLOR = {"high": GREEN, "medium": YELLOW, "low": DIM}


def wrap(text: str, indent: str = "     ") -> str:
    return textwrap.fill(text, width=96, initial_indent=indent,
                         subsequent_indent=indent)


def render(story: Story) -> None:
    print(f"\n{BOLD}{story.company_name} ({story.symbol}){RESET}")
    print(f"{DIM}{len(story.bars)} trading days | {len(story.beats)} labelled moves "
          f"| {len(story.evidence)} evidence rows | generated {story.generated_at}{RESET}")

    if story.arc:
        print(f"\n{BOLD}THE ARC{RESET}")
        print(wrap(story.arc, indent="  "))
        if story.arc_citation_ids:
            print(f"\n  {DIM}Sources for the arc:{RESET}")
            for cid in story.arc_citation_ids:
                item = story.evidence.get(cid)
                if item:
                    print(f"    - {item.title}")
                    print(f"      {DIM}{item.source} -> {item.url}{RESET}")

    print(f"\n{BOLD}LABELLED MOVES{RESET}")
    for beat in story.beats:
        color = GREEN if beat.direction == "up" else RED
        conf = CONFIDENCE_COLOR[beat.confidence]
        print(f"\n  {BOLD}{beat.date}{RESET}  {color}{beat.pct_change:+.2f}%{RESET}  "
              f"close ${beat.close:,.2f}  {conf}[{beat.confidence}]{RESET}")
        print(f"  {BOLD}{beat.headline}{RESET}")
        print(wrap(beat.explanation))

        if not beat.citation_ids:
            print(f"     {YELLOW}! no verifiable source for this move{RESET}")
            continue

        print(f"     {DIM}Cited:{RESET}")
        for n, cid in enumerate(beat.citation_ids, 1):
            item = story.evidence.get(cid)
            if item is None:
                print(f"       [{n}] {RED}MISSING EVIDENCE {cid}{RESET}")
                continue
            print(f"       [{n}] ({item.kind.value}) {item.title}")
            if item.numbers:
                figures = "  ".join(f"{k}={v}" for k, v in item.numbers.items())
                print(f"           {DIM}{figures}{RESET}")
            if item.url:
                print(f"           {DIM}{item.source} -> {item.url}{RESET}")

    if story.warnings:
        print(f"\n{BOLD}{YELLOW}WARNINGS{RESET}")
        for warning in story.warnings:
            print(f"  - {warning}")

    # The integrity check, restated as a number you can look at.
    total = sum(len(b.citation_ids) for b in story.beats)
    dangling = sum(1 for b in story.beats for c in b.citation_ids
                   if c not in story.evidence)
    uncited = sum(1 for b in story.beats if not b.citation_ids)
    print(f"\n{BOLD}CITATION INTEGRITY{RESET}")
    print(f"  {total} citations across {len(story.beats)} beats")
    print(f"  {dangling} pointing at evidence that does not exist "
          f"({'PASS' if dangling == 0 else 'FAIL'})")
    print(f"  {uncited} beats with no source (shown as 'cause unverified')\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--days", type=int, default=None,
                        help="build a fresh story over this many days instead of "
                             "reading the cache (cached separately)")
    parser.add_argument("--refresh", action="store_true",
                        help="rebuild the full-window story and overwrite the cache")
    parser.add_argument("--json", action="store_true", help="dump raw JSON instead")
    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.days:
        key = f"story_{symbol}_{args.days}d"
        cached = load(key)
        if cached:
            story = Story.model_validate(cached)
        else:
            story = build_story(symbol, days=args.days)
            save(key, story.model_dump(mode="json"))
    elif args.refresh:
        story = build_story(symbol)
        save(f"story_{symbol}", story.model_dump(mode="json"))
    else:
        cached = load(f"story_{symbol}")
        if cached is None:
            print(f"No cached story for {symbol}. Run:\n"
                  f"  python -m scripts.build_story_cache {symbol}\n"
                  f"or for something quick:\n"
                  f"  python -m scripts.show_story {symbol} --days 30")
            return 1
        story = Story.model_validate(cached)

    if args.json:
        print(json.dumps(story.model_dump(mode="json"), indent=2)[:8000])
    else:
        render(story)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
