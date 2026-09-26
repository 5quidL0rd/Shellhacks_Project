"""Which supported companies are connected to which, from the knowledge graph.

Story Mode compares a move against the companies connected to it: a stock that
fell the same day its supplier fell tells a different story from one that fell
alone. The connections come from data/exports/graph_edges.csv, written by
`python -m kg.export_edges`, so building a story needs no live Neo4j call.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from .config import GRAPH_EDGES_CSV
from .universe import COMPANIES, get as get_company

# Order in which relationships are listed when a pair has more than one.
_RELATION_ORDER = ("supplier", "customer", "competitor", "same_sector")


@dataclass(frozen=True)
class Connection:
    symbol: str
    # How `symbol` relates to the subject company, e.g. "supplier" means
    # `symbol` supplies the subject. A pair can have several.
    relations: tuple[str, ...]
    detail: str = ""   # e.g. "wafer foundry"
    source: str = ""   # e.g. "10-K", "manual"

    @property
    def label(self) -> str:
        """'supplier', or 'supplier and competitor'."""
        return " and ".join(self.relations)


@lru_cache(maxsize=1)
def _edges() -> tuple[dict, ...]:
    if not GRAPH_EDGES_CSV.exists():
        return ()
    with GRAPH_EDGES_CSV.open(encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


def connections(symbol: str) -> list[Connection]:
    """Supported companies linked to `symbol` in the graph.

    Only companies in the universe are returned, since those are the ones we
    have prices for. If the graph links a company to nothing, it falls back to
    companies in the same sector so move detection still has a baseline.
    """
    subject = get_company(symbol).symbol
    found: dict[str, dict] = {}

    for edge in _edges():
        a, b, rel = edge["from_id"], edge["to_id"], edge["relationship"]
        if subject not in (a, b) or a == b:
            continue
        other = b if a == subject else a
        if other not in COMPANIES:
            continue

        if rel == "SUPPLIES":
            relation = "supplier" if b == subject else "customer"
        elif rel == "COMPETES_WITH":
            relation = "competitor"
        else:
            continue

        entry = found.setdefault(other, {"relations": set(), "detail": "", "source": ""})
        entry["relations"].add(relation)
        # Prefer describing the supply relationship; it is the more specific one.
        if not entry["detail"] or relation in ("supplier", "customer"):
            entry["detail"] = edge.get("detail") or entry["detail"]
            entry["source"] = edge.get("source") or entry["source"]

    if not found:
        sector = COMPANIES[subject].sector
        found = {
            s: {"relations": {"same_sector"}, "detail": sector, "source": "universe"}
            for s, c in COMPANIES.items() if s != subject and c.sector == sector
        }

    return [
        Connection(
            symbol=s,
            relations=tuple(r for r in _RELATION_ORDER if r in e["relations"]),
            detail=e["detail"],
            source=e["source"],
        )
        for s, e in sorted(found.items())
    ]


def peers(symbol: str) -> tuple[str, ...]:
    return tuple(c.symbol for c in connections(symbol))
