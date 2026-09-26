"""Use Gemini to extract company relationships from a filing.

Usage: python -m kg.extract [TICKER ...]

Reads data/raw/{ticker}.sections.txt (run kg.edgar first) and writes
data/extracted/{ticker}.json for hand-checking before kg.load.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from kg.companies import COMPANIES, normalize

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "extracted"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
CHUNK_CHARS = 60_000  # smaller chunks -> the model misses fewer mentions


class Relationship(BaseModel):
    type: Literal["SUPPLIER", "CUSTOMER", "COMPETITOR", "OPERATES_IN"] = Field(
        description="How the counterparty relates to the filing company."
    )
    counterparty_name: Optional[str] = Field(
        description="Company name exactly as written in the text. Null if the text does not name it."
    )
    country: Optional[str] = Field(
        description="Country, in plain English (e.g. 'Taiwan', 'China'). Required for OPERATES_IN."
    )
    operates_kind: Optional[Literal["headquarters", "manufacturing", "major_market"]] = Field(
        description="Only for OPERATES_IN."
    )
    detail: Optional[str] = Field(
        description="What is supplied, bought, or competed on, in a few words (e.g. 'wafer foundry')."
    )
    evidence: str = Field(description="Exact quote from the text, 40 words or fewer.")
    confidence: Literal["high", "medium", "low"]
    is_named: bool = Field(description="True only if the text names the counterparty company.")


class Extraction(BaseModel):
    relationships: list[Relationship]


PROMPT = """You are building a knowledge graph of company relationships from SEC filings.

Below is part of the annual report of {name} ("the filing company"). List every relationship it states between the filing company and another company or a country.

Types, always from the filing company's point of view:
- SUPPLIER: the counterparty sells to or makes things for the filing company (foundries, memory vendors, contract manufacturers, component suppliers, cloud/licensing providers).
- CUSTOMER: the counterparty buys from the filing company (customers, distributors, partners that resell its products).
- COMPETITOR: the text names the counterparty as a competitor.
- OPERATES_IN: the filing company has headquarters, manufacturing, or a major market in a country. Set counterparty_name to null.

Rules:
- Only extract what the text states. Do not use outside knowledge.
- evidence must be copied word for word from the text.
- If a supplier or customer is described but not named ("a single supplier in Asia", "our largest customer"), still include it with counterparty_name=null and is_named=false. Never guess the name.
- Use the company's name as written (e.g. "Taiwan Semiconductor Manufacturing Company Limited"), not a ticker.
- One entry per counterparty per type. If a company is both a supplier and a competitor, emit two entries.
- Skip the filing company's own subsidiaries.
- confidence: high = explicit, direct statement; medium = clear but indirect; low = implied.

TEXT:
{text}
"""


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries into pieces of about `size` characters."""
    out, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) > size and cur:
            out.append(cur)
            cur = ""
        cur += para + "\n"
    return out + [cur] if cur.strip() else out


def call_gemini(client: genai.Client, prompt: str, retries: int = 5) -> list[dict]:
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Extraction,
                    temperature=0,
                ),
            )
            return [r.model_dump() for r in Extraction.model_validate_json(resp.text or "").relationships]
        except errors.APIError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"    Gemini {e.code}, retrying in {wait}s")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")


def _squash(s: str) -> str:
    return re.sub(r"\W+", "", s.lower())


def dedupe(rels: list[dict]) -> list[dict]:
    """Keep one row per (type, counterparty/country, kind), preferring higher confidence."""
    rank = {"high": 0, "medium": 1, "low": 2}
    best = {}
    for r in sorted(rels, key=lambda r: rank[r["confidence"]]):
        who = normalize(r["counterparty_name"]) if r["counterparty_name"] else None
        if r["type"] == "OPERATES_IN":
            key = (r["type"], (r["country"] or "").lower(), r["operates_kind"])
        elif who:
            key = (r["type"], who)
        else:  # unnamed mentions are all kept for review
            key = (r["type"], None, r["evidence"])
        best.setdefault(key, r)
    return list(best.values())


def extract(ticker: str, client: genai.Client) -> dict:
    meta = json.loads((RAW_DIR / f"{ticker}.meta.json").read_text())
    text = (RAW_DIR / f"{ticker}.sections.txt").read_text()
    name = COMPANIES[ticker]["name"]

    pieces = chunks(text)
    rels = []
    for i, piece in enumerate(pieces, 1):
        print(f"  {ticker}: chunk {i}/{len(pieces)}")
        rels += call_gemini(client, PROMPT.format(name=name, text=piece))

    haystack = _squash(text)
    rels = dedupe(rels)
    for r in rels:
        r["evidence_verified"] = _squash(r["evidence"]) in haystack

    result = {
        "company": ticker,
        "source": meta["form"],
        "filing_url": meta["url"],
        "filing_date": meta["filing_date"],
        "model": MODEL,
        "relationships": sorted(rels, key=lambda r: (r["type"], r["counterparty_name"] or "~")),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{ticker}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def summarize(result: dict) -> None:
    rels = result["relationships"]
    named = [r for r in rels if r["is_named"]]
    unverified = [r for r in rels if not r["evidence_verified"]]
    print(f"{result['company']}: {len(rels)} relationships ({len(named)} named, "
          f"{len(rels) - len(named)} unnamed, {len(unverified)} with unverified quotes)")
    for r in rels:
        who = r["counterparty_name"] or r["country"] or "(unnamed)"
        flag = "" if r["evidence_verified"] else "  [quote not found]"
        print(f"  {r['type']:<12} {who:<45} {r['confidence']:<6}{flag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*", default=list(COMPANIES))
    args = parser.parse_args()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for t in args.tickers:
        summarize(extract(t.upper(), client))


if __name__ == "__main__":
    main()
