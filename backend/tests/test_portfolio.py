"""Portfolio X-Ray, Connection Map, and impact over a small made-up graph."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.portfolio as pf  # noqa: E402

EDGE_FIELDS = ["from_id", "from_name", "from_type", "relationship", "to_id", "to_name", "to_type",
               "kind", "detail", "source", "reported_by", "confidence", "evidence", "filing_url", "note"]
COMPANY_FIELDS = ["ticker", "name", "in_universe", "cik", "sector", "hq_country"]


def edge(a, rel, b, kind="", to_type="Company", evidence="quote"):
    return {"from_id": a, "from_name": a, "from_type": "Company", "relationship": rel, "to_id": b,
            "to_name": b, "to_type": to_type, "kind": kind, "detail": "", "source": "10-K",
            "reported_by": "", "confidence": "high", "evidence": evidence,
            "filing_url": "https://sec.gov/x", "note": ""}


EDGES = [
    edge("ASML", "SUPPLIES", "TSM", evidence="ASML ships EUV tools to TSMC"),
    edge("TSM", "SUPPLIES", "AAPL"),
    edge("TSM", "SUPPLIES", "NVDA", evidence="We utilize foundries, such as TSMC"),
    edge("samsung-electronics", "SUPPLIES", "NVDA"),
    edge("AMD", "COMPETES_WITH", "NVDA"),
    edge("AAPL", "OPERATES_IN", "Taiwan", "manufacturing", "Country"),
    edge("NVDA", "OPERATES_IN", "Taiwan", "manufacturing", "Country"),
    edge("AAPL", "OPERATES_IN", "United States", "headquarters", "Country"),
    edge("NVDA", "OPERATES_IN", "United States", "headquarters", "Country"),
]
COMPANIES = [
    {"ticker": t, "name": f"{t} Inc.", "in_universe": "True", "cik": "1", "sector": "Semiconductors",
     "hq_country": "United States"} for t in ("AAPL", "NVDA", "AMD", "TSM", "ASML")
] + [{"ticker": "samsung-electronics", "name": "Samsung Electronics", "in_universe": "False",
      "cik": "", "sector": "", "hq_country": ""}]


@pytest.fixture(autouse=True)
def small_graph(monkeypatch, tmp_path):
    for name, fields, rows, attr in (("edges.csv", EDGE_FIELDS, EDGES, "GRAPH_EDGES_CSV"),
                                     ("companies.csv", COMPANY_FIELDS, COMPANIES, "GRAPH_COMPANIES_CSV")):
        path = tmp_path / name
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        monkeypatch.setattr(pf, attr, path)
    pf.reload()
    yield
    pf.reload()


def test_holdings_accept_commas_repeats_and_any_case():
    assert pf.parse_holdings(["aapl,NVDA", "nvda", " AMD ", "XYZ"]) == (["AAPL", "NVDA", "AMD"], ["XYZ"])


def test_xray_ranks_shared_dependencies_first_with_evidence():
    deps = pf.xray(["AAPL", "NVDA"])
    top = deps[0]
    assert (top["id"], top["type"], top["holding_count"]) == ("TSM", "company", 2)
    assert [h["ticker"] for h in top["holdings"]] == ["AAPL", "NVDA"]
    assert top["holdings"][1]["evidence"][0]["evidence"] == "We utilize foundries, such as TSMC"
    taiwan = next(d for d in deps if d["id"] == "Taiwan")
    assert taiwan["holding_count"] == 2 and taiwan["holdings"][0]["how"] == ["manufacturing"]


def test_xray_leaves_out_headquarters_unless_asked():
    assert "United States" not in {d["id"] for d in pf.xray(["AAPL", "NVDA"])}
    us = next(d for d in pf.xray(["AAPL", "NVDA"], include_headquarters=True) if d["id"] == "United States")
    assert us["holding_count"] == 2


def test_map_links_holdings_to_their_neighbours_and_marks_shared_nodes():
    m = pf.portfolio_map(["AAPL", "NVDA"])
    nodes = {n["id"]: n for n in m["nodes"]}
    assert nodes["AAPL"]["is_holding"] and not nodes["TSM"]["is_holding"]
    assert nodes["TSM"]["connected_holdings"] == ["AAPL", "NVDA"]
    assert nodes["Taiwan"]["type"] == "country"
    assert "ASML" not in nodes  # two steps away, not on the one-step map
    assert {"source": "TSM", "target": "NVDA", "type": "supplies"}.items() <= next(
        l for l in m["links"] if (l["source"], l["target"]) == ("TSM", "NVDA")).items()


def test_map_can_hide_countries_and_competitors():
    ids = {n["id"] for n in pf.portfolio_map(["NVDA"], include_countries=False,
                                             include_competitors=False)["nodes"]}
    assert ids == {"NVDA", "TSM", "samsung-electronics"}


def test_impact_of_a_supplier_reaches_its_customers():
    r = pf.impact("TSM", ["AAPL", "NVDA", "AMD"])
    assert [(a["ticker"], a["connections"][0]["role"]) for a in r["affected"]] == [
        ("AAPL", "customer"), ("NVDA", "customer")]
    assert r["unaffected"] == ["AMD"]


def test_impact_follows_the_supply_chain_one_more_step():
    r = pf.impact("ASML", ["AAPL", "NVDA"])
    conn = r["affected"][0]["connections"][0]
    assert conn["role"] == "indirect_customer"
    assert conn["path"] == ["ASML", "TSM", "AAPL"]
    assert [e["evidence"] for e in conn["evidence"]] == ["ASML ships EUV tools to TSMC", "quote"]


def test_impact_lists_competitors_and_accepts_outside_companies():
    assert pf.impact("amd", ["NVDA"])["affected"][0]["connections"][0]["role"] == "competitor"
    assert pf.impact("samsung-electronics", ["NVDA"])["affected"][0]["ticker"] == "NVDA"


def test_impact_of_a_holding_supplying_the_company():
    r = pf.impact("TSM", ["ASML"])
    assert r["affected"][0]["connections"][0]["role"] == "supplier"


def test_unknown_company_is_an_error():
    with pytest.raises(KeyError):
        pf.impact("nope", ["NVDA"])


def test_map_link_endpoints_are_node_ids_not_filing_sources():
    m = pf.portfolio_map(["AAPL", "NVDA"])
    ids = {n["id"] for n in m["nodes"]}
    assert all(l["source"] in ids and l["target"] in ids for l in m["links"])
    assert m["links"][0]["provenance"]["source"] == "10-K"
