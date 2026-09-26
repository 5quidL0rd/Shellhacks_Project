"""Tests for the rule the feature rests on: nothing reaches the investor's
screen unless it points at evidence we actually fetched."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.story.detect import significant_moves  # noqa: E402
from app.story.generate import verify_citations  # noqa: E402
from app.story.schema import StoryBeat  # noqa: E402


def beat(**overrides) -> StoryBeat:
    base = dict(date="2026-08-27", pct_change=8.74, close=224.41, direction="up",
                headline="Jumped on earnings", explanation="Revenue beat.",
                confidence="high", citation_ids=["ev_real"])
    return StoryBeat(**{**base, **overrides})


def test_known_citation_survives():
    verified, warnings = verify_citations([beat()], {"ev_real"})
    assert verified[0].citation_ids == ["ev_real"]
    assert verified[0].explanation == "Revenue beat."
    assert warnings == []


def test_invented_citation_is_dropped_but_beat_survives_on_the_real_one():
    verified, warnings = verify_citations(
        [beat(citation_ids=["ev_real", "ev_hallucinated"])], {"ev_real"}
    )
    assert verified[0].citation_ids == ["ev_real"]
    assert any("ev_hallucinated" in w for w in warnings)


def test_beat_with_only_invented_citations_is_neutralised():
    verified, warnings = verify_citations([beat(citation_ids=["ev_fake"])], {"ev_real"})
    only = verified[0]
    assert only.citation_ids == []
    assert only.confidence == "low"
    assert "cause unverified" in only.headline
    # The claim is gone; the arithmetic fact remains.
    assert "Revenue beat" not in only.explanation
    assert "8.74%" in only.explanation
    assert len(warnings) == 2  # one for the drop, one for the replacement


def test_beat_with_no_citations_at_all_is_neutralised():
    verified, _ = verify_citations([beat(citation_ids=[])], {"ev_real"})
    assert verified[0].confidence == "low"


def test_down_move_neutralises_with_correct_direction():
    verified, _ = verify_citations(
        [beat(pct_change=-6.2, direction="down", citation_ids=["nope"])], {"ev_real"}
    )
    assert "Fell" in verified[0].headline
    assert "fell 6.20%" in verified[0].explanation


# --- move detection ---

def bars(*specs) -> list[dict]:
    """specs: (date, close, volume). pct_change is derived as in prices.py."""
    out = []
    for i, (day, close, volume) in enumerate(specs):
        row = {"date": day, "open": close, "high": close, "low": close,
               "close": close, "volume": volume}
        if i:
            prior = out[-1]["close"]
            row["pct_change"] = round((close - prior) / prior * 100, 3)
            row["prev_close"] = prior
        else:
            row["pct_change"] = 0.0
            row["prev_close"] = close
        out.append(row)
    return out


def test_quiet_days_produce_no_beats():
    series = bars(("2026-01-02", 100.0, 1000), ("2026-01-03", 100.5, 1000),
                  ("2026-01-04", 100.2, 1000))
    assert significant_moves(series) == []


def test_big_move_is_detected():
    series = bars(("2026-01-02", 100.0, 1000), ("2026-01-03", 110.0, 3000))
    moves = significant_moves(series)
    assert len(moves) == 1
    assert moves[0]["date"] == "2026-01-03"
    assert moves[0]["pct_change"] == 10.0


def test_sector_wide_move_scores_below_a_company_specific_one():
    """The core ranking claim: a move peers shared is a weaker story."""
    subject = bars(("2026-01-02", 100.0, 1000), ("2026-01-03", 105.0, 1000),
                   ("2026-01-06", 110.25, 1000))
    # On 01-03 the peer rose the same 5%; on 01-06 the peer was flat.
    peer = bars(("2026-01-02", 50.0, 500), ("2026-01-03", 52.5, 500),
                ("2026-01-06", 52.5, 500))
    moves = {m["date"]: m for m in significant_moves(subject, {"PEER": peer})}
    assert moves["2026-01-03"]["score"] < moves["2026-01-06"]["score"]
    assert moves["2026-01-03"]["idiosyncratic_pct"] == 0.0


def test_beat_limit_is_respected_and_output_is_chronological():
    specs = [("2026-01-01", 100.0, 1000)]
    price = 100.0
    for day in range(2, 20):
        price *= 1.05 if day % 2 else 0.95
        specs.append((f"2026-01-{day:02d}", round(price, 4), 1000))
    moves = significant_moves(bars(*specs), limit=5)
    assert len(moves) == 5
    assert [m["date"] for m in moves] == sorted(m["date"] for m in moves)
