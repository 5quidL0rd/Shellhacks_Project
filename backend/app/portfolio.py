"""Portfolio views over the knowledge graph: X-Ray, Connection Map, and impact.

Everything here is a deterministic walk over the graph; no AI is involved, so
every result can be explained by the exact edges behind it (Product.md: "the
graph handles logic"). The graph comes from the export in data/exports/
(python -m kg.export_edges), so the API needs no live Neo4j or Snowflake call.

Edges keep their provenance all the way to the response: the quote from the
filing, the filing link, the source (10-K, 20-F, manual, config), and a note
for hand-added edges.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from .config import GRAPH_COMPANIES_CSV, GRAPH_EDGES_CSV
from .universe import COMPANIES

@dataclass(frozen=True)
class Edge:
    from_id: str
    from_name: str
    rel: str
    to_id: str
    to_name: str
    to_type: str
    kind: str
    detail: str
    source: str
    confidence: str
    evidence: str
    filing_url: str
    note: str
    reported_by: str = ""  # whose filing stated it, when not the from-company's

    def provenance(self) -> dict:
        """Why this edge exists, for the frontend's 'show me the source' view."""
        return {
            "relationship": self.rel,
            "kind": self.kind or None,
            "detail": self.detail or None,
            "evidence": self.evidence or None,
            "source": self.source or None,
            "filing_url": self.filing_url or None,
            "confidence": self.confidence or None,
            "note": self.note or None,
        }


@lru_cache(maxsize=1)
def _graph() -> tuple[tuple[Edge, ...], dict[str, dict]]:
    with GRAPH_EDGES_CSV.open(encoding="utf-8") as f:
        edges = tuple(
            Edge(r["from_id"], r["from_name"], r["relationship"], r["to_id"], r["to_name"],
                 r["to_type"], r["kind"], r["detail"], r["source"], r["confidence"],
                 r["evidence"], r["filing_url"], r["note"], r.get("reported_by") or "")
            for r in csv.DictReader(f)
        )
    with GRAPH_COMPANIES_CSV.open(encoding="utf-8") as f:
        companies = {r["ticker"]: r for r in csv.DictReader(f)}
    return edges, companies


def reload() -> None:
    """Forget the loaded graph, e.g. after re-exporting it."""
    _graph.cache_clear()


def parse_holdings(raw: list[str]) -> tuple[list[str], list[str]]:
    """(supported, unsupported) tickers, upper-cased, de-duplicated, in order.

    Unsupported tickers are reported rather than rejected: a real portfolio
    can hold stocks outside the universe, and the rest should still work.
    """
    seen, supported, unsupported = set(), [], []
    for item in raw:
        for ticker in item.split(","):
            ticker = ticker.strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            (supported if ticker in COMPANIES else unsupported).append(ticker)
    return supported, unsupported


def _company_node(node_id: str, holdings: set[str]) -> dict:
    _, companies = _graph()
    c = companies.get(node_id, {})
    return {
        "id": node_id,
        "name": c.get("name") or node_id,
        "type": "company",
        "in_universe": c.get("in_universe") == "True",
        "is_holding": node_id in holdings,
        "sector": c.get("sector") or None,
    }


def _name(node_id: str) -> str:
    return _graph()[1].get(node_id, {}).get("name") or node_id


# --- Portfolio X-Ray --------------------------------------------------------

def _country_node(name: str) -> dict:
    return {"id": name, "name": name, "type": "country", "in_universe": False,
            "is_holding": False, "sector": None}


def xray(holdings: list[str], include_headquarters: bool = False) -> list[dict]:
    """What the portfolio depends on, ranked by how many holdings share it.

    Dependencies are suppliers of a holding (incoming SUPPLIES) and countries a
    holding manufactures in or sells heavily into (OPERATES_IN). Headquarters
    are left out by default: "7 of your holdings are headquartered in the
    United States" crowds out the dependencies that matter. Each dependency
    lists which holdings rely on it, how, and the evidence.
    """
    held = set(holdings)
    deps: dict[tuple[str, str], dict] = {}
    for e in _graph()[0]:
        if e.rel == "SUPPLIES" and e.to_id in held and e.from_id != e.to_id:
            key, holding, how = ("company", e.from_id), e.to_id, "supplier"
        elif e.rel == "OPERATES_IN" and e.from_id in held and (
                include_headquarters or e.kind != "headquarters"):
            key, holding, how = ("country", e.to_id), e.from_id, e.kind or "operates_in"
        else:
            continue
        dep = deps.setdefault(key, {"holdings": {}})
        entry = dep["holdings"].setdefault(holding, {"ticker": holding, "how": [], "evidence": []})
        if how not in entry["how"]:
            entry["how"].append(how)
        entry["evidence"].append(e.provenance())

    out = []
    for (dep_type, dep_id), dep in deps.items():
        node = _company_node(dep_id, held) if dep_type == "company" else _country_node(dep_id)
        out.append({
            **node,
            "holding_count": len(dep["holdings"]),
            "holdings": sorted(dep["holdings"].values(), key=lambda h: h["ticker"]),
        })
    return sorted(out, key=lambda d: (-d["holding_count"], d["type"] != "company", d["name"]))


# --- Connection Map ---------------------------------------------------------

def portfolio_map(holdings: list[str], include_countries: bool = True,
                  include_competitors: bool = True) -> dict:
    """Nodes and links for the holdings and everything one step away.

    Shaped for force-graph libraries (react-force-graph, Cytoscape.js):
    `nodes` with ids, `links` with `source` / `target` ids. Each node carries
    `connected_holdings`, so the frontend can size or highlight the shared
    dependencies that make hidden concentration visible.
    """
    held = set(holdings)
    rels = {"SUPPLIES"} | ({"COMPETES_WITH"} if include_competitors else set()) \
        | ({"OPERATES_IN"} if include_countries else set())
    nodes: dict[str, dict] = {h: _company_node(h, held) for h in holdings}
    links: dict[tuple, dict] = {}
    touches: dict[str, set[str]] = {h: {h} for h in holdings}

    for e in _graph()[0]:
        if e.rel not in rels or not ({e.from_id, e.to_id} & held) or e.from_id == e.to_id:
            continue
        for node_id, node_type in ((e.from_id, "company"), (e.to_id, e.to_type.lower())):
            if node_id not in nodes:
                nodes[node_id] = (_company_node(node_id, held) if node_type == "company"
                                  else _country_node(node_id))
        for end, other in ((e.from_id, e.to_id), (e.to_id, e.from_id)):
            if other in held:
                touches.setdefault(end, set()).add(other)
        key = (e.from_id, e.to_id, e.rel, e.kind)
        if key not in links:
            # Provenance is nested: its own "source" (10-K, manual, ...) must not
            # overwrite the link's "source" node id.
            links[key] = {"source": e.from_id, "target": e.to_id, "type": e.rel.lower(),
                          "kind": e.kind or None, "provenance": e.provenance()}

    for node_id, node in nodes.items():
        node["connected_holdings"] = sorted(touches.get(node_id, set()) - {node_id})
    return {
        "nodes": sorted(nodes.values(), key=lambda n: (not n.get("is_holding"), n["type"], n["id"])),
        "links": list(links.values()),
    }


# --- Impact (connected-company alerts) --------------------------------------

def resolve_node(node_id: str) -> str:
    """Graph id for a ticker or outside-company slug, case-insensitive."""
    companies = _graph()[1]
    if node_id in companies:
        return node_id
    by_lower = {k.lower(): k for k in companies}
    if node_id.lower() in by_lower:
        return by_lower[node_id.lower()]
    raise KeyError(f"'{node_id}' is not in the knowledge graph")


def impact(company_id: str, holdings: list[str]) -> dict:
    """Which holdings news about `company_id` touches, and how.

    Direct links: the company supplies a holding, buys from a holding, or
    competes with it. Indirect links follow the supply chain one more step
    downstream: the company supplies someone who supplies a holding (ASML ->
    TSMC -> Apple), since a supplier's problem flows to its customers.
    Competitors are listed as affected, never as winners or losers; judging
    the direction would be a trading call.
    """
    edges, _ = _graph()
    company_id = resolve_node(company_id)
    held = set(holdings)
    affected: dict[str, list[dict]] = {}

    def add(ticker: str, role: str, path: list[str], explanation: str, evidence: list[dict]) -> None:
        affected.setdefault(ticker, []).append(
            {"role": role, "path": path, "explanation": explanation, "evidence": evidence})

    customers_of_company = []
    for e in edges:
        if e.rel == "SUPPLIES" and e.from_id == company_id:
            customers_of_company.append(e)
            if e.to_id in held:
                add(e.to_id, "customer", [company_id, e.to_id],
                    f"{_name(company_id)} supplies {_name(e.to_id)}", [e.provenance()])
        elif e.rel == "SUPPLIES" and e.to_id == company_id and e.from_id in held:
            add(e.from_id, "supplier", [e.from_id, company_id],
                f"{_name(e.from_id)} supplies {_name(company_id)}", [e.provenance()])
        elif e.rel == "COMPETES_WITH" and company_id in (e.from_id, e.to_id):
            other = e.to_id if e.from_id == company_id else e.from_id
            if other in held:
                add(other, "competitor", [company_id, other],
                    f"{_name(other)} competes with {_name(company_id)}", [e.provenance()])

    directly_supplied = {e.to_id for e in customers_of_company}
    for first in customers_of_company:
        middle = first.to_id
        for e in edges:
            if (e.rel == "SUPPLIES" and e.from_id == middle and e.to_id in held
                    and e.to_id != company_id and e.to_id not in directly_supplied):
                add(e.to_id, "indirect_customer", [company_id, middle, e.to_id],
                    f"{_name(company_id)} supplies {_name(middle)}, which supplies {_name(e.to_id)}",
                    [first.provenance(), e.provenance()])

    order = {"customer": 0, "supplier": 1, "indirect_customer": 2, "competitor": 3}
    results = [
        {"ticker": t, "name": _name(t),
         "connections": sorted(conns, key=lambda c: (order[c["role"]], c["path"]))}
        for t, conns in affected.items()
    ]
    results.sort(key=lambda r: (min(order[c["role"]] for c in r["connections"]), r["ticker"]))
    return {
        "company": _company_node(company_id, held),
        "affected": results,
        "unaffected": sorted(held - set(affected) - {company_id}),
    }
