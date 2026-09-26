"""Turn evidence into prose with Gemini, then verify every citation.

Two rules make this safe to show an investor:

1. Gemini sees only the evidence rows we fetched, and is told to cite their ids.
2. Anything it returns is checked against those ids afterwards. A beat citing an
   id we never supplied is a hallucinated source, so the explanation is replaced
   with the plain price fact and flagged, rather than quietly shown.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache

from google import genai
from google.genai import types

from ..config import GEMINI_API_KEY, GEMINI_MODEL
from .schema import Evidence, StoryBeat

_SYSTEM = """You explain stock price moves to experienced investors.

You will receive a company, a list of significant price moves, and an EVIDENCE
list. Each evidence row has an "id".

Hard rules:
- Explain a move ONLY using the evidence rows supplied for that move. Never use
  outside knowledge, and never guess at a cause.
- Every beat must list the evidence ids it relied on in citation_ids. An
  explanation with no citation_ids is invalid.
- If the evidence does not explain the move, say so plainly (for example: "No
  company-specific news accompanied this drop; its supplier TSM fell a similar
  amount the same day") and cite the price and peer evidence you do have.
- peer_move evidence covers companies connected to this one: its suppliers,
  customers, and competitors. Name the relationship when you mention one ("its
  supplier TSM", "competitor AMD"). When connected companies moved the same
  way, say the move was shared with them rather than company-specific. When
  they were flat or moved the other way, say it was company-specific. Do not
  claim one company's move caused another's; only say they moved together.
- Evidence of kind "sector" and "fundamental" is monthly or quarterly. Use it
  only in the arc, never as the cause of a single day's move.
- Never give buy, sell, or hold advice. Never predict future prices. Describe
  what happened and why.
- headline: under 60 characters, concrete, no hype. It becomes a chart label.
- explanation: 2-3 sentences, plain language, name the actual numbers.
- confidence: "high" when a filing or an unambiguous news item explains the
  move, "medium" when the news is suggestive, "low" when nothing explains it.

Also write "arc": one paragraph on the whole period - the shape of the story
across all the moves, what drove it, and what an investor should understand
about their position. Draw on the "fundamental" and "sector" evidence here:
whether the industry was expanding while this stock fell is exactly the context
a single day's headline cannot give. Cite evidence ids in arc_citation_ids.
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "headline": {"type": "string"},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["date", "headline", "explanation", "confidence",
                             "citation_ids"],
            },
        },
        "arc": {"type": "string"},
        "arc_citation_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["beats", "arc", "arc_citation_ids"],
}


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    """Cached: a Client created per call gets garbage-collected mid-request,
    which surfaces as "Cannot send a request, as the client has been closed"."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set; add it to backend/.env")
    return genai.Client(api_key=GEMINI_API_KEY)


def _evidence_for_prompt(evidence: Evidence) -> dict:
    """Only the fields the model needs. The URL is deliberately withheld: the
    frontend resolves links from the id, so the model cannot invent one."""
    return {
        "id": evidence.id,
        "kind": evidence.kind.value,
        "date": evidence.occurred_on,
        "title": evidence.title,
        "detail": evidence.detail,
        "numbers": evidence.numbers,
    }


def build_prompt(
    symbol: str,
    company_name: str,
    moves: list[dict],
    evidence_by_move: dict[str, dict[str, Evidence]],
    portfolio_context: dict | None = None,
) -> str:
    payload = {
        "company": {"symbol": symbol, "name": company_name},
        "moves": [
            {
                "date": move["date"],
                "pct_change": move["pct_change"],
                "close": move["close"],
                "volume_vs_30d_avg": move["volume_ratio"],
                "connected_moves_same_day": {
                    peer: {"pct_change": pct,
                           "relationship": move.get("peer_relations", {})
                                               .get(peer, {}).get("relationship", "peer")}
                    for peer, pct in move["peer_moves"].items()
                },
                "move_excluding_sector_pct": move["idiosyncratic_pct"],
                "evidence": [
                    _evidence_for_prompt(item)
                    for item in evidence_by_move.get(move["date"], {}).values()
                ],
            }
            for move in moves
        ],
    }
    if portfolio_context:
        payload["investor_position"] = portfolio_context
    return json.dumps(payload, indent=2, default=str)


def verify_citations(
    beats: list[StoryBeat],
    known_ids: set[str],
) -> tuple[list[StoryBeat], list[str]]:
    """Drop unknown citation ids; neutralise any beat left with none."""
    warnings: list[str] = []
    verified: list[StoryBeat] = []

    for beat in beats:
        good = [cid for cid in beat.citation_ids if cid in known_ids]
        invented = set(beat.citation_ids) - set(good)
        if invented:
            warnings.append(
                f"{beat.date}: dropped uncitable reference(s) {sorted(invented)}"
            )
        if not good:
            warnings.append(
                f"{beat.date}: explanation had no valid citation and was replaced "
                "with the price fact only"
            )
            direction = "rose" if beat.pct_change > 0 else "fell"
            beat = beat.model_copy(update={
                "headline": f"{direction.title()} {abs(beat.pct_change):.1f}%, cause unverified",
                "explanation": (
                    f"The price {direction} {abs(beat.pct_change):.2f}% to "
                    f"${beat.close:.2f}. No source we could cite explains this move."
                ),
                "confidence": "low",
                "citation_ids": [],
            })
        else:
            beat = beat.model_copy(update={"citation_ids": good})
        verified.append(beat)

    return verified, warnings


def narrate(
    symbol: str,
    company_name: str,
    moves: list[dict],
    evidence_by_move: dict[str, dict[str, Evidence]],
    extra_evidence: dict[str, Evidence] | None = None,
    portfolio_context: dict | None = None,
) -> dict:
    """Call Gemini and return verified beats, the arc, and warnings."""
    all_evidence: dict[str, Evidence] = {}
    for bundle in evidence_by_move.values():
        all_evidence.update(bundle)
    if extra_evidence:
        all_evidence.update(extra_evidence)

    prompt = build_prompt(symbol, company_name, moves, evidence_by_move,
                          portfolio_context)

    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.3,  # explanation, not creative writing
        ),
    )

    parsed = json.loads(response.text)
    move_lookup = {move["date"]: move for move in moves}

    raw_beats: list[StoryBeat] = []
    for item in parsed.get("beats", []):
        move = move_lookup.get(item["date"])
        if move is None:
            continue  # a date we never asked about
        raw_beats.append(StoryBeat(
            date=item["date"],
            pct_change=move["pct_change"],
            close=move["close"],
            direction="up" if move["pct_change"] > 0 else "down",
            headline=item["headline"],
            explanation=item["explanation"],
            confidence=item["confidence"],
            citation_ids=item.get("citation_ids", []),
        ))

    beats, warnings = verify_citations(raw_beats, set(all_evidence))

    missing = sorted(set(move_lookup) - {beat.date for beat in beats})
    if missing:
        warnings.append(f"Gemini skipped move dates: {missing}")

    arc_citations = [cid for cid in parsed.get("arc_citation_ids", [])
                     if cid in all_evidence]

    return {
        "beats": beats,
        "arc": parsed.get("arc", ""),
        "arc_citation_ids": arc_citations,
        "evidence": all_evidence,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
