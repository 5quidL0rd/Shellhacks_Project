"""Peers come from the knowledge graph export, with the relationship attached."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.connections as conn  # noqa: E402
from app.story.evidence import peer_evidence  # noqa: E402

FIELDS = ["from_id", "relationship", "to_id", "detail", "source"]


def use_graph(monkeypatch, tmp_path, rows):
    path = tmp_path / "graph_edges.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(dict(zip(FIELDS, r)) for r in rows)
    monkeypatch.setattr(conn, "GRAPH_EDGES_CSV", path)
    conn._edges.cache_clear()


def test_supply_direction_is_seen_from_the_subject(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [("TSM", "SUPPLIES", "NVDA", "wafer foundry", "10-K")])
    assert [(c.symbol, c.label) for c in conn.connections("NVDA")] == [("TSM", "supplier")]
    assert [(c.symbol, c.label) for c in conn.connections("TSM")] == [("NVDA", "customer")]


def test_competes_with_works_in_both_directions(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [("AMD", "COMPETES_WITH", "NVDA", "GPUs", "10-K")])
    assert conn.peers("AMD") == ("NVDA",)
    assert conn.peers("NVDA") == ("AMD",)


def test_companies_outside_the_universe_are_skipped(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [
        ("samsung-electronics", "SUPPLIES", "NVDA", "memory", "10-K"),
        ("TSM", "SUPPLIES", "NVDA", "wafer foundry", "10-K"),
    ])
    assert conn.peers("NVDA") == ("TSM",)


def test_a_pair_with_two_relationships_is_one_peer(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [
        ("NVDA", "SUPPLIES", "MSFT", "GPUs", "manual"),
        ("MSFT", "COMPETES_WITH", "NVDA", "AI", "10-K"),
    ])
    (only,) = conn.connections("MSFT")
    assert only.symbol == "NVDA"
    assert only.label == "supplier and competitor"
    assert only.detail == "GPUs"  # the supply detail wins


def test_no_graph_links_falls_back_to_same_sector(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [])
    same_sector = {s for s, c in conn.COMPANIES.items()
                   if s != "NVDA" and c.sector == conn.COMPANIES["NVDA"].sector}
    assert {"AMD", "TSM"} <= same_sector
    assert set(conn.peers("NVDA")) == same_sector
    assert {c.label for c in conn.connections("NVDA")} == {"same_sector"}


def test_peer_evidence_names_the_relationship():
    move = {"date": "2026-06-05", "pct_change": -6.2,
            "peer_moves": {"TSM": -6.69},
            "peer_relations": {"TSM": {"relationship": "supplier",
                                       "detail": "wafer foundry", "source": "10-K"}}}
    (item,) = peer_evidence("NVDA", move)
    assert item.title == "TSM (supplier) moved -6.69% the same day"
    assert "TSM is NVDA's supplier (wafer foundry)" in item.detail
    assert item.numbers["relationship"] == "supplier"
