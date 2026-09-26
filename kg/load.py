"""Load companies and extracted relationships into Neo4j.

Usage: python -m kg.load [--reset]

Reads data/extracted/*.json and data/manual_edges.json. Uses MERGE throughout,
so running it twice leaves the graph unchanged.
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from kg.companies import COMPANIES, display_name, resolve

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EXTRACTED_DIR = ROOT / "data" / "extracted"
MANUAL_PATH = ROOT / "data" / "manual_edges.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.cypher"

COUNTRY_ALIASES = {
    "u.s.": "United States", "us": "United States", "usa": "United States",
    "united states of america": "United States", "the united states": "United States",
    "korea": "South Korea", "republic of korea": "South Korea",
    "prc": "China", "mainland china": "China", "people's republic of china": "China",
}


def country_name(raw: str) -> str:
    return COUNTRY_ALIASES.get(raw.strip().lower(), raw.strip())


def edges_from_extraction(doc: dict) -> tuple[list[dict], dict]:
    """Turn one extracted filing into graph edges, plus counts of what was skipped."""
    me = doc["company"]
    base = {"source": doc["source"], "filing_url": doc["filing_url"], "reported_by": me}
    edges, skipped = [], {"unnamed": 0, "self": 0}

    for r in doc["relationships"]:
        props = {**base, "evidence": r["evidence"], "confidence": r["confidence"],
                 "detail": r.get("detail")}

        if r["type"] == "OPERATES_IN" or not r["is_named"]:
            # Unnamed suppliers/customers still reveal country exposure.
            kind = {"OPERATES_IN": r.get("operates_kind") or "major_market",
                    "SUPPLIER": "manufacturing", "CUSTOMER": "major_market"}.get(r["type"])
            if r.get("country") and kind:
                edges.append({"type": "OPERATES_IN", "a": me, "country": country_name(r["country"]),
                              "kind": kind, "props": props})
            elif r["type"] != "OPERATES_IN":
                skipped["unnamed"] += 1
            continue

        other, _ = resolve(r["counterparty_name"])
        if other == me:
            skipped["self"] += 1
            continue
        other_name = display_name(other, r["counterparty_name"])

        if r["type"] == "SUPPLIER":
            edges.append({"type": "SUPPLIES", "a": other, "a_name": other_name, "b": me, "props": props})
        elif r["type"] == "CUSTOMER":
            edges.append({"type": "SUPPLIES", "a": me, "b": other, "b_name": other_name, "props": props})
        elif r["type"] == "COMPETITOR":
            edges.append(competes(me, other, other_name, props))
    return edges, skipped


def competes(x: str, y: str, y_name: str, props: dict) -> dict:
    """COMPETES_WITH is stored once, from the alphabetically smaller key."""
    if x < y:
        return {"type": "COMPETES_WITH", "a": x, "b": y, "b_name": y_name, "props": props}
    return {"type": "COMPETES_WITH", "a": y, "a_name": y_name, "b": x, "props": props}


def edges_from_manual(doc: dict) -> list[dict]:
    edges = []
    for r in doc["relationships"]:
        props = {k: r.get(k) for k in ("source", "filing_url", "evidence", "confidence", "detail", "note")}
        a, _ = resolve(r["from"])
        b, _ = resolve(r["to"])
        if r["type"] == "COMPETES_WITH":
            edges.append(competes(a, b, display_name(b, r["to"]), props))
        else:
            edges.append({"type": r["type"], "a": a, "a_name": display_name(a, r["from"]),
                          "b": b, "b_name": display_name(b, r["to"]), "props": props})
    return edges


MERGE_COMPANY = """
MERGE (c:Company {ticker: $key})
ON CREATE SET c.name = $name, c.in_universe = false
"""

MERGE_EDGE = {
    "SUPPLIES": """
        UNWIND $rows AS row
        MATCH (a:Company {ticker: row.a}), (b:Company {ticker: row.b})
        MERGE (a)-[r:SUPPLIES]->(b) SET r += row.props""",
    "COMPETES_WITH": """
        UNWIND $rows AS row
        MATCH (a:Company {ticker: row.a}), (b:Company {ticker: row.b})
        MERGE (a)-[r:COMPETES_WITH]->(b) SET r += row.props""",
    "OPERATES_IN": """
        UNWIND $rows AS row
        MATCH (a:Company {ticker: row.a})
        MERGE (k:Country {name: row.country})
        MERGE (a)-[r:OPERATES_IN {kind: row.kind}]->(k) SET r += row.props""",
}


def load(reset: bool = False) -> None:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
    )
    db = os.environ.get("NEO4J_DATABASE") or None
    driver.verify_connectivity()

    edges, skipped = [], {"unnamed": 0, "self": 0}
    for path in sorted(EXTRACTED_DIR.glob("*.json")):
        e, s = edges_from_extraction(json.loads(path.read_text()))
        edges += e
        skipped = {k: skipped[k] + s[k] for k in skipped}
    if MANUAL_PATH.exists():
        edges += edges_from_manual(json.loads(MANUAL_PATH.read_text()))

    with driver.session(database=db) as session:
        if reset:
            session.run("MATCH (n) DETACH DELETE n")
            print("Reset: deleted all nodes")

        schema = "\n".join(l for l in SCHEMA_PATH.read_text().splitlines() if not l.strip().startswith("//"))
        for stmt in schema.split(";"):
            if stmt.strip():
                session.run(stmt)

        for ticker, c in COMPANIES.items():
            session.run(
                """
                MERGE (co:Company {ticker: $ticker})
                SET co.name = $name, co.cik = $cik, co.in_universe = true
                MERGE (s:Sector {name: $sector})
                MERGE (co)-[:IN_SECTOR]->(s)
                MERGE (k:Country {name: $country})
                MERGE (co)-[r:OPERATES_IN {kind: 'headquarters'}]->(k)
                SET r.source = coalesce(r.source, 'config')
                """,
                ticker=ticker, name=c["name"], cik=c["cik"], sector=c["sector"], country=c["hq_country"],
            )

        for e in edges:
            for side in ("a", "b"):
                if f"{side}_name" in e:
                    session.run(MERGE_COMPANY, key=e[side], name=e[f"{side}_name"])

        for rel_type, query in MERGE_EDGE.items():
            rows = [e for e in edges if e["type"] == rel_type]
            session.run(query, rows=rows)

        counts = session.run(
            """
            CALL () { MATCH (n) RETURN count(n) AS nodes }
            CALL () { MATCH ()-[r]->() RETURN count(r) AS rels }
            RETURN nodes, rels
            """
        ).single()
        by_type = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY t"
        ).data()
    driver.close()

    print(f"Loaded {len(edges)} edges from filings + manual file "
          f"(skipped {skipped['unnamed']} unnamed mentions without a country, {skipped['self']} self-references)")
    print(f"Graph now has {counts['nodes']} nodes and {counts['rels']} relationships: "
          + ", ".join(f"{r['t']} {r['n']}" for r in by_type))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete everything in the database first")
    args = parser.parse_args()
    load(args.reset)


if __name__ == "__main__":
    main()
