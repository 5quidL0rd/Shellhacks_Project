#!/usr/bin/env python3
"""Analyse a searched company against a portfolio, in the terminal.

    python -m scripts.show_research ford --holdings AAPL,NVDA,AMD,MSFT
    python -m scripts.show_research "waste management" --holdings AAPL,NVDA
    python -m scripts.show_research bmw --holdings AAPL,NVDA --refresh
    python -m scripts.show_research --search "coca" --holdings AAPL
"""
import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.research import build  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, RED, YELLOW, CYAN = "\033[32m", "\033[31m", "\033[33m", "\033[36m"

VERDICT_COLOR = {"Good diversity": GREEN, "Some diversification": YELLOW,
                 "Risky overlap": RED}
CONFIDENCE_COLOR = {"high": GREEN, "medium": YELLOW, "low": DIM}


def wrap(text: str, indent: str = "      ") -> str:
    return textwrap.fill(text, width=96, initial_indent=indent, subsequent_indent=indent)


def bar(score, width: int = 20) -> str:
    """A score as a bar, always oriented so longer is more favourable."""
    if score is None:
        return f"{DIM}{'·' * width} not measured{RESET}"
    filled = round(score / 100 * width)
    color = GREEN if score >= 67 else YELLOW if score >= 34 else RED
    return f"{color}{'█' * filled}{DIM}{'·' * (width - filled)}{RESET} {score:>3}"


def render(r: dict) -> None:
    color = VERDICT_COLOR.get(r["verdict"], "")
    conf = CONFIDENCE_COLOR[r["confidence"]]

    print(f"\n{BOLD}{r['name']} ({r['ticker']}){RESET}  {DIM}{r['sector']}"
          f"{' · ' + r['industry'] if r['industry'] else ''}"
          f"{' · ' + r['country'] if r['country'] else ''}{RESET}")
    fit = "—" if r["fit_score"] is None else r["fit_score"]
    print(f"{BOLD}Fit {fit}/100{RESET}  {color}{r['verdict']}{RESET}  "
          f"{conf}[{r['confidence']} confidence]{RESET}")
    print(wrap(r["verdict_meaning"], indent="  "))
    print(f"{DIM}{wrap(r['confidence_reason'], indent='  ')}{RESET}")
    print(f"\n  {DIM}against: {', '.join(r['holdings'])}{RESET}")
    if r["already_held"]:
        print(f"  {YELLOW}You already hold this.{RESET}")

    print(f"\n{BOLD}OVERLAP WITH THE PORTFOLIO{RESET}")
    ordered = sorted(r["components"].items(),
                     key=lambda kv: (not kv[1]["measured"], kv[1]["score"] or 0))
    for name, comp in ordered:
        weight = (f"weight {comp['weight_applied']:.0%}" if comp["measured"]
                  else "excluded from the score")
        print(f"  {name:<20} {bar(comp['score'])}  {DIM}{weight}{RESET}")
        print(wrap(comp["detail"]))

    print(f"\n{BOLD}SHAPE{RESET}  {DIM}(rank against your holdings plus this company){RESET}")
    portfolio = {a["axis"]: a["score"] for a in r["portfolio_radar"]}
    for axis in r["radar"]:
        raw = f"{axis['value']}{axis['unit']}" if axis["available"] else "n/a"
        vendor = (f" {YELLOW}est.{RESET}" if axis["basis"] == "Yahoo Finance"
                  and axis["axis"] in ("growth", "profitability", "debt") else "")
        mine = portfolio.get(axis["axis"])
        print(f"  {axis['axis']:<14} {raw:>9}{vendor}  {bar(axis['score'])}"
              f"  {DIM}portfolio avg {mine}{RESET}")

    brief = r["brief"]
    if brief["summary"]:
        print(f"\n{BOLD}THE BRIEF{RESET}")
        print(wrap(brief["summary"], indent="  "))

    for heading, items, sign, tone in (("FOR", brief["pros"], "+", GREEN),
                                       ("AGAINST", brief["cons"], "-", RED)):
        print(f"\n{BOLD}{tone}{heading}{RESET}")
        if not items:
            print(f"  {DIM}Nothing the evidence supports.{RESET}")
        for item in items:
            print(wrap(item["point"], indent=f"  {tone}{sign}{RESET} ")
                  .replace(f"  {tone}{sign}{RESET} ", f"  {tone}{sign}{RESET} ", 1))
            for cid in item["citation_ids"]:
                ev = r["evidence"].get(cid)
                if not ev:
                    print(f"        {RED}MISSING {cid}{RESET}")
                    continue
                print(f"        {DIM}[{ev['kind']}] {ev['title'][:74]}{RESET}")
                if ev.get("url"):
                    print(f"          {CYAN}{ev['url']}{RESET}")

    print(f"\n{BOLD}WHERE IT WOULD CONNECT{RESET}")
    if not r["map_placement"]["in_graph"]:
        print(wrap(f"{r['name']} is not in the knowledge graph, so a supply-chain link to "
                   "your holdings is unknown rather than absent.", indent="  "))
    else:
        node = r["graph_id"] or r["ticker"]
        held = {n["id"] for n in r["map_placement"]["nodes"] if n["is_holding"]}
        direct = [l for l in r["map_placement"]["links"]
                  if (l["source"] == node and l["target"] in held)
                  or (l["target"] == node and l["source"] in held)]
        print(f"  {len(direct)} direct link(s) to holdings")
        for link in direct[:8]:
            outgoing = link["source"] == node
            other = link["target"] if outgoing else link["source"]
            print(f"    {node} {'->' if outgoing else '<-'} {other:<20} {DIM}{link['type']}{RESET}")

    if r["warnings"]:
        print(f"\n{BOLD}{YELLOW}CAVEATS{RESET}")
        for w in r["warnings"]:
            print(f"  - {w}")

    cited = {c for g in (brief["pros"], brief["cons"]) for i in g for c in i["citation_ids"]}
    dangling = [c for c in cited if c not in r["evidence"]]
    print(f"\n{BOLD}CITATION INTEGRITY{RESET}")
    print(f"  {len(r['evidence'])} evidence rows, {len(cited)} cited, {len(dangling)} dangling "
          f"({GREEN + 'PASS' + RESET if not dangling else RED + 'FAIL' + RESET})")
    print(f"\n{DIM}{wrap(r['disclaimer'], indent='  ')}{RESET}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="ticker, company name, or brand")
    parser.add_argument("--holdings", required=True, help="comma-separated tickers you own")
    parser.add_argument("--search", help="just list matches for this text")
    parser.add_argument("--refresh", action="store_true", help="re-run the Gemini brief")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    holdings = [h.strip().upper() for h in args.holdings.split(",") if h.strip()]

    if args.search:
        for match in build.search(args.search)["matches"]:
            covered = "  (covered in depth)" if match["in_universe"] else ""
            print(f"  {match['ticker']:<8} {match['name']}{covered}")
        return 0

    if not args.query:
        parser.error("give a company to analyse, or --search to look one up")

    try:
        result = build.analyse(args.query, holdings, refresh=args.refresh)
    except build.Ambiguous as exc:
        print(f"'{exc.query}' matched several companies. Pick one:")
        for option in exc.options:
            print(f"  {option['ticker']:<8} {option['name']}")
        return 1
    except build.NotFound as exc:
        print(f"No public company matched '{exc.query}'.")
        return 1

    if args.json:
        print(json.dumps(result, indent=2, default=str)[:8000])
    else:
        render(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
