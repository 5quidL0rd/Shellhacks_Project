#!/usr/bin/env python3
"""Read who pays each company out of its annual report, and print the mix.

    python -m scripts.build_revenue_mix                 # all supported companies
    python -m scripts.build_revenue_mix NVDA CRUS F     # these, any SEC filer
    python -m scripts.build_revenue_mix NVDA --refresh  # read the filing again

Supported companies must be read before `depended_on_by` can find them, so run
this with no arguments after changing the extraction. The results are
committed (data/cache/conc_v*_*.json), so the app shows them without a key.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import _path  # noqa: E402
from app.research import concentration as conc  # noqa: E402
from app.research import lookup  # noqa: E402
from app.universe import COMPANIES  # noqa: E402

BOLD, DIM, RESET, CYAN = "\033[1m", "\033[2m", "\033[0m", "\033[36m"


def filer(ticker: str) -> tuple[str, str] | None:
    """(cik, name) for a ticker, or None if no SEC filer has it."""
    if ticker in COMPANIES:
        return COMPANIES[ticker].cik, COMPANIES[ticker].name
    match = next((m for m in lookup.search(ticker, limit=1) if m.ticker == ticker), None)
    return (match.cik, match.name) if match else None


def show(mix: dict) -> None:
    print(f"\n{BOLD}{mix['ticker']}{RESET}  {mix['name']}  {DIM}{mix['summary']}{RESET}")
    print(f"  status: {mix['status']}   period: {mix.get('period')}")
    for s in mix["slices"]:
        pct = f"{s['percent']:.0f}%{'+' if s['at_least'] else ''}"
        print(f"  {CYAN}{pct:>5}{RESET}  {s['label']:<14} {DIM}{s.get('described_as') or ''}{RESET}")
    if mix.get("other"):
        o = mix["other"]
        print(f"  {'≤' if o['at_most'] else ' '}{o['percent']:>4.0f}%  all other customers")
    for c in mix.get("context", []):
        print(f"  {DIM}context: {c['text']} {c['percent']}%{RESET}")
    for d in mix.get("depended_on_by", []):
        print(f"  {DIM}depended on by {d['ticker']}: {d['percent']:.0f}%"
              f"{'+' if d['at_least'] else ''} of its revenue{RESET}")
    if mix.get("dropped_unverified"):
        print(f"  {DIM}{mix['dropped_unverified']} claim(s) dropped: quote or number not verified{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*", help="default: every supported company")
    parser.add_argument("--refresh", action="store_true", help="read the filings again")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers] or list(COMPANIES)
    if args.refresh:
        for ticker in tickers:
            found = filer(ticker)
            if found:
                _path(conc.cache_key(found[0])).unlink(missing_ok=True)

    # Read everything first, so each company's "depended on by" sees the others.
    for ticker in tickers:
        found = filer(ticker)
        if found:
            try:
                conc.for_company(*found)
            except Exception as exc:
                print(f"{ticker}: could not read ({exc})", file=sys.stderr)
    for ticker in tickers:
        try:
            show(conc.for_ticker(ticker))
        except Exception as exc:
            print(f"{ticker}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
