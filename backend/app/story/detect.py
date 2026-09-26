"""Pick which days deserve an explanation.

Not every wiggle is a story. A day earns a beat when it clears the absolute
threshold, and it is ranked above its peers when volume confirms it and when the
move is not simply the whole sector moving together.
"""
from __future__ import annotations

from ..config import MAX_STORY_BEATS, MOVE_THRESHOLD_PCT
from ..sources.prices import average_volume


def _idiosyncratic(pct: float, peer_pcts: list[float]) -> float:
    """How much of the move is this company rather than the sector.

    A 5% drop on a day the whole sector fell 4.5% is mostly beta and is a far
    weaker story than a 5% drop while peers were flat.
    """
    if not peer_pcts:
        return abs(pct)
    sector = sum(peer_pcts) / len(peer_pcts)
    return abs(pct - sector)


def significant_moves(
    bars: list[dict],
    peer_bars: dict[str, list[dict]] | None = None,
    threshold_pct: float = MOVE_THRESHOLD_PCT,
    limit: int = MAX_STORY_BEATS,
) -> list[dict]:
    """Return candidate move days, chronological, with the scoring context
    attached so the evidence layer and the prompt can both use it."""
    peer_bars = peer_bars or {}
    peer_lookup = {
        symbol: {bar["date"]: bar.get("pct_change", 0.0) for bar in series}
        for symbol, series in peer_bars.items()
    }
    avg_volume = average_volume(bars)

    candidates: list[dict] = []
    for bar in bars:
        pct = bar.get("pct_change")
        if pct is None or abs(pct) < threshold_pct:
            continue

        peers_that_day = {
            symbol: lookup[bar["date"]]
            for symbol, lookup in peer_lookup.items()
            if bar["date"] in lookup
        }
        idio = _idiosyncratic(pct, list(peers_that_day.values()))
        volume_ratio = bar["volume"] / avg_volume if avg_volume else 1.0

        candidates.append({
            "date": bar["date"],
            "pct_change": pct,
            "close": bar["close"],
            "prev_close": bar.get("prev_close", bar["open"]),
            "volume": bar["volume"],
            "volume_ratio": round(volume_ratio, 2),
            "peer_moves": {s: round(p, 2) for s, p in peers_that_day.items()},
            "idiosyncratic_pct": round(idio, 2),
            # Volume is a tiebreaker, not the main signal.
            "score": round(idio * min(volume_ratio, 3.0), 3),
        })

    top = sorted(candidates, key=lambda c: c["score"], reverse=True)[:limit]
    return sorted(top, key=lambda c: c["date"])
