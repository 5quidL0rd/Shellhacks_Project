"""Export the knowledge graph as CSV tables for Snowflake.

Usage: python -m kg.export_edges

Reads the live graph from Neo4j (run kg.load first) and writes:
  data/exports/graph_edges.csv       one row per relationship  -> GRAPH_EDGES
  data/exports/graph_companies.csv   one row per company       -> GRAPH_COMPANIES
Load them with data/exports/snowflake_graph_tables.sql.
"""

import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EXPORT_DIR = ROOT / "data" / "exports"

# Company nodes are keyed by ticker; Sector and Country nodes by name.
EDGES_QUERY = """
MATCH (a)-[r]->(b)
RETURN coalesce(a.ticker, a.name) AS from_id, a.name AS from_name, labels(a)[0] AS from_type,
       type(r) AS relationship,
       coalesce(b.ticker, b.name) AS to_id, b.name AS to_name, labels(b)[0] AS to_type,
       r.kind AS kind, r.detail AS detail, r.source AS source, r.reported_by AS reported_by,
       r.confidence AS confidence, r.evidence AS evidence, r.filing_url AS filing_url, r.note AS note
ORDER BY relationship, from_id, to_id, kind
"""

# One row per company. A filing can add a second "headquarters" link, so the
# headquarters from data/companies.json (source 'config') is preferred.
COMPANIES_QUERY = """
MATCH (c:Company)
OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
OPTIONAL MATCH (c)-[h:OPERATES_IN {kind: 'headquarters'}]->(k:Country)
WITH c, s, k ORDER BY CASE h.source WHEN 'config' THEN 0 ELSE 1 END
WITH c, collect(DISTINCT s.name)[0] AS sector, collect(k.name)[0] AS hq_country
RETURN c.ticker AS ticker, c.name AS name, c.in_universe AS in_universe, c.cik AS cik,
       sector, hq_country
ORDER BY in_universe DESC, ticker
"""


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path.relative_to(ROOT)}")


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
    )
    with driver.session(database=os.environ.get("NEO4J_DATABASE") or None) as session:
        edges = session.run(EDGES_QUERY).data()
        companies = session.run(COMPANIES_QUERY).data()
    driver.close()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(EXPORT_DIR / "graph_edges.csv", edges)
    write_csv(EXPORT_DIR / "graph_companies.csv", companies)


if __name__ == "__main__":
    main()
