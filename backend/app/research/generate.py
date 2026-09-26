"""Candid pros and cons for a candidate, written by Gemini from fixed evidence.

Same contract as Story Mode: the model sees only evidence rows assembled here,
may cite only their ids, and anything citing an id we did not supply is dropped.
It never sees a URL, so it cannot invent a link.

The prompt forbids buy/sell language. That is a product rule from Product.md,
not decoration: the honest output is "this overlaps three of your dependencies",
never "this is a good buy". Cons are required - a candidate with nothing against
it usually means the evidence was thin, and the model is told to say so.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache

from google import genai
from google.genai import types

from ..config import GEMINI_API_KEY, GEMINI_MODEL

_SYSTEM = """You brief experienced investors on how a company would fit the
portfolio they already hold.

You receive the candidate company, the investor's current holdings, a set of
measured metrics, a diversification analysis, and recent news. Each evidence row
has an "id".

Hard rules:
- Use ONLY the evidence rows supplied. Never use outside knowledge about the
  company, and never state a figure that is not in the evidence.
- Every pro and every con must list the evidence ids it rests on. An item with
  no citation is invalid.
- NEVER advise buying, selling, or holding. Never predict a price or say a stock
  is cheap, expensive, undervalued, or a good or bad investment. You describe
  fit and trade-offs; the investor decides.
- Frame everything against THIS portfolio. "Its only named supplier is already
  behind two of your holdings" is useful; "it has a strong balance sheet" is
  generic filler.
- Correlation is the subtle one. A company in an unrelated sector that still
  moves with the portfolio is NOT the diversification it appears to be, and
  saying so plainly is the most valuable thing you can do. Conversely, a high
  correlation is not cancelled out by a different sector label.
- Where an overlap check could not be run (evidence says measured: false), treat
  it as unknown, not as a clean result. Say what is unknown and why, as a con.
- Where a figure is a vendor ratio rather than a filing, say so in the item.
- Be candid. Give 2-4 pros and 2-4 cons. If the evidence is thin, say so as a
  con and cite what is missing. Do not invent a con for balance, and never pad
  with vague statements.
- Where a figure comes from a filing over a year old, say so in the item.
- summary: 2-3 sentences on how it would fit, naming the single biggest reason
  for and against. Lead with whichever measured overlap is most decisive.

Write plainly, for someone who already understands markets. No hype, no hedging
filler, no "it is important to note".
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "summary_citation_ids": {"type": "array", "items": {"type": "string"}},
        "pros": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["point", "citation_ids"],
            },
        },
        "cons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["point", "citation_ids"],
            },
        },
    },
    "required": ["summary", "summary_citation_ids", "pros", "cons"],
}


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    """Cached: a Client created per call is garbage-collected mid-request."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set; add it to backend/.env")
    return genai.Client(api_key=GEMINI_API_KEY)


def _verify(items: list[dict], known_ids: set[str]) -> tuple[list[dict], list[str]]:
    """Drop invented citations; drop any item left with none."""
    kept, warnings = [], []
    for item in items:
        good = [c for c in item.get("citation_ids", []) if c in known_ids]
        invented = set(item.get("citation_ids", [])) - set(good)
        if invented:
            warnings.append(f"dropped uncitable reference(s) {sorted(invented)} "
                            f"from: {item['point'][:60]}")
        if not good:
            warnings.append(f"removed an uncited claim: {item['point'][:80]}")
            continue
        kept.append({"point": item["point"], "citation_ids": good})
    return kept, warnings


def narrate(
    subject,
    holdings: list[str],
    evidence: dict[str, dict],
    fit_summary: dict,
) -> dict:
    """Ask Gemini for a cited pros/cons brief, then verify every citation."""
    payload = {
        "candidate": {
            "symbol": subject.ticker, "name": subject.name,
            "sector": subject.sector, "industry": subject.industry,
            "country": subject.country,
            "in_our_knowledge_graph": subject.in_graph,
        },
        "current_holdings": holdings,
        "diversification": {
            "fit_score_0_100": fit_summary["fit_score"],
            "verdict": fit_summary["verdict"],
            "what_the_score_means": fit_summary["verdict_meaning"],
            "confidence": fit_summary["confidence"],
        },
        # The model gets ids, titles and numbers - never the urls.
        "evidence": [
            {"id": e["id"], "kind": e["kind"], "title": e["title"],
             "detail": e.get("detail", ""), "numbers": e.get("numbers", {}),
             "source": e.get("source", "")}
            for e in evidence.values()
        ],
    }

    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=json.dumps(payload, indent=2, default=str),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.3,
        ),
    )

    parsed = json.loads(response.text)
    known = set(evidence)

    pros, pro_warnings = _verify(parsed.get("pros", []), known)
    cons, con_warnings = _verify(parsed.get("cons", []), known)
    summary_citations = [c for c in parsed.get("summary_citation_ids", []) if c in known]

    warnings = pro_warnings + con_warnings
    if not summary_citations:
        warnings.append("summary had no valid citation")
    if not cons:
        warnings.append("no cons survived verification; treat the brief as one-sided")

    return {
        "summary": parsed.get("summary", ""),
        "summary_citation_ids": summary_citations,
        "pros": pros,
        "cons": cons,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
