"""Assemble the evidence bundle a move gets explained from.

Gemini never searches and never recalls. It only sees rows built here, and it
may only cite their ids. That is what makes the citation on screen trustworthy:
the evidence was fetched before the sentence existed, not justified after it.
"""
from __future__ import annotations

from ..sources import edgar, fred, news, prices
from ..story.schema import Evidence, EvidenceKind

# How many articles to show per move. Enough to find the cause, few enough that
# the model is not picking a headline at random.
NEWS_PER_MOVE = 8


def _news_id(symbol: str, move_date: str, index: int) -> str:
    return f"ev_{symbol}_{move_date.replace('-', '')}_news{index}"


def price_evidence(symbol: str, move: dict) -> Evidence:
    direction = "rose" if move["pct_change"] > 0 else "fell"
    return Evidence(
        id=f"ev_{symbol}_{move['date'].replace('-', '')}_price",
        kind=EvidenceKind.PRICE,
        title=f"{symbol} {direction} {abs(move['pct_change']):.2f}% on {move['date']}",
        detail=(
            f"Closed at ${move['close']:.2f} from ${move['prev_close']:.2f}. "
            f"Volume was {move['volume_ratio']:.1f}x the 30-day average."
        ),
        source=prices.SOURCE_NAME,
        url=f"https://finance.yahoo.com/quote/{symbol}/history",
        occurred_on=move["date"],
        numbers={
            "pct_change": move["pct_change"],
            "close": move["close"],
            "prev_close": move["prev_close"],
            "volume": move["volume"],
            "volume_vs_30d_avg": move["volume_ratio"],
            "move_excluding_sector_pct": move["idiosyncratic_pct"],
        },
    )


def peer_evidence(symbol: str, move: dict) -> list[Evidence]:
    """Moves of connected companies (from the knowledge graph) tell the investor
    whether this was the company alone, or something that also hit its supplier,
    customer, or competitor - the link the Connection Map is about."""
    out = []
    relations = move.get("peer_relations", {})
    for peer, peer_pct in move["peer_moves"].items():
        link = relations.get(peer, {})
        relationship = link.get("relationship", "peer")
        detail = (
            f"{symbol} moved {move['pct_change']:+.2f}% while {peer} moved "
            f"{peer_pct:+.2f}%. {peer} is {symbol}'s {relationship}"
            + (f" ({link['detail']})" if link.get("detail") else "")
            + (f", per the knowledge graph (source: {link['source']})." if link.get("source") else ".")
        )
        out.append(Evidence(
            id=f"ev_{symbol}_{move['date'].replace('-', '')}_peer_{peer}",
            kind=EvidenceKind.PEER_MOVE,
            title=f"{peer} ({relationship}) moved {peer_pct:+.2f}% the same day",
            detail=detail,
            source=prices.SOURCE_NAME,
            url=f"https://finance.yahoo.com/quote/{peer}/history",
            occurred_on=move["date"],
            numbers={"peer_pct_change": peer_pct, "subject_pct_change": move["pct_change"],
                     "relationship": relationship},
        ))
    return out


def news_evidence(symbol: str, move: dict, items: list[dict]) -> list[Evidence]:
    """`items` is the date-filtered news for this move; see build.news_for_move."""
    out = []
    for index, item in enumerate(items[:NEWS_PER_MOVE]):
        out.append(Evidence(
            id=_news_id(symbol, move["date"], index),
            kind=EvidenceKind.NEWS,
            title=item["headline"],
            # Name the outlet: the model should weigh a wire report above a
            # blog's take on the same event.
            detail=(f"Reported by {item['publisher']}. "
                    + item.get("summary", "")[:600]).strip(),
            source=f"{item['publisher']} (via {item.get('via', news.SOURCE_NAME)})",
            url=item["url"],
            occurred_on=item["date"],
            numbers={},
        ))
    return out


def filing_evidence(symbol: str, move: dict, all_filings: list[dict]) -> list[Evidence]:
    nearby = edgar.filings_near(all_filings, move["date"], window_days=2)
    out = []
    for filing in nearby:
        out.append(Evidence(
            id=f"ev_{symbol}_{move['date'].replace('-', '')}_filing_{filing['accession'].replace('-', '')}",
            kind=EvidenceKind.FILING,
            title=f"{filing['form']} filed {filing['filed_date']}",
            detail=filing["description"],
            source=edgar.SOURCE_NAME,
            url=filing["url"],
            occurred_on=filing["filed_date"],
            numbers={},
        ))
    return out


def fundamental_evidence(symbol: str, fundamentals: dict[str, list[dict]]) -> list[Evidence]:
    """Latest quarter per concept, with its year-over-year change.

    These back the arc paragraph rather than a single day: "revenue grew 62%
    year over year" is why a stock is up over six months.
    """
    out = []
    for label, points in fundamentals.items():
        if not points:
            continue
        latest = points[-1]
        yoy = None
        if len(points) >= 5:
            year_ago = points[-5]["value"]
            if year_ago:
                yoy = round((latest["value"] - year_ago) / abs(year_ago) * 100, 2)

        numbers: dict[str, float | int | str] = {
            "value": latest["value"],
            "period_end": latest["period_end"],
            "xbrl_tag": latest["xbrl_tag"],
        }
        if yoy is not None:
            numbers["yoy_pct_change"] = yoy

        # Link to the filing index the figure was reported in, so the
        # investor lands on the primary document rather than a summary.
        url = None
        if latest.get("accession"):
            url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(_cik(symbol))}/{latest['accession'].replace('-', '')}/"
            )

        out.append(Evidence(
            id=f"ev_{symbol}_fund_{label}",
            kind=EvidenceKind.FUNDAMENTAL,
            title=f"{label.replace('_', ' ').title()}: {latest['value']:,.0f} ({latest['period_end']})",
            detail=(
                f"Reported on form {latest['form']}"
                + (f", {yoy:+.1f}% year over year." if yoy is not None else ".")
            ),
            source=edgar.SOURCE_NAME,
            url=url,
            occurred_on=latest.get("filed_date") or latest["period_end"],
            numbers=numbers,
        ))
    return out


def sector_evidence(symbol: str, sector: str) -> list[Evidence]:
    """Industry backdrop for the arc paragraph.

    Monthly and lagged, so it can say whether the whole industry was expanding
    while this stock fell - but it must never be offered as the cause of a
    single day's move.
    """
    out = []
    for reading in fred.sector_context(sector):
        yoy = reading["yoy_pct_change"]
        out.append(Evidence(
            id=f"ev_{symbol}_sector_{reading['series_id']}",
            kind=EvidenceKind.SECTOR,
            title=(
                f"{reading['label']}: {reading['value']:,.1f} {reading['units']}"
                + (f", {yoy:+.1f}% year over year" if yoy is not None else "")
            ),
            detail=f"Monthly series, latest reading {reading['as_of']}.",
            source=fred.SOURCE_NAME,
            url=reading["url"],
            occurred_on=reading["as_of"],
            numbers={
                "value": reading["value"],
                "units": reading["units"],
                "as_of": reading["as_of"],
                **({"yoy_pct_change": yoy} if yoy is not None else {}),
            },
        ))
    return out


def _cik(symbol: str) -> str:
    from ..universe import get
    return get(symbol).cik


def bundle_for_move(
    symbol: str,
    move: dict,
    news_items: list[dict],
    all_filings: list[dict],
) -> dict[str, Evidence]:
    items = [price_evidence(symbol, move)]
    items += peer_evidence(symbol, move)
    items += filing_evidence(symbol, move, all_filings)
    items += news_evidence(symbol, move, news_items)
    return {item.id: item for item in items}
