"""Download each company's latest annual report (10-K, or 20-F for foreign filers).

Usage: python -m kg.edgar [TICKER ...] [--force]

Writes to data/raw/:
  {ticker}.txt            full filing as plain text
  {ticker}.sections.txt   only the sections the extractor reads
  {ticker}.meta.json      form, filing date, URL
"""

import argparse
import json
import os
import re
import time
import warnings
from pathlib import Path

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from dotenv import load_dotenv

from kg.companies import COMPANIES, EXTERNAL

load_dotenv()
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # 10-Ks are XHTML

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
FLAGS = re.IGNORECASE | re.MULTILINE
SEP = r"\s*[.:\-–—|]?\s*"  # punctuation between "Item 1A" and its title


def _title(words: str) -> str:
    """Pattern for a heading title that tolerates line breaks inside words.

    Styled headings sometimes come out as 'ITEM 1. B\\nUSINESS'.
    """
    return r"\s+".join(r"\s*".join(map(re.escape, w)) for w in words.split())


def _item(num: str, title: str) -> str:
    """10-K heading at the start of a line: 'Item 1A. Risk Factors'."""
    return rf"^\s*item\s*{num}{SEP}{_title(title)}"


def _line(num: str, title: str) -> str:
    """20-F heading: the title alone on its line; 'Item N.' is optional."""
    return rf"^(?:item\s*{num}{SEP})?{_title(title)}\s*$"


# (label, start heading, end heading). Headings also appear in the table of
# contents, so extract_sections keeps the longest start->end span.
SECTIONS = {
    "10-K": [
        ("Item 1. Business", _item("1", "business"), _item("1a", "risk factors")),
        ("Item 1A. Risk Factors", _item("1a", "risk factors"),
         "|".join([_item("1b", "unresolved"), _item("1c", "cybersecurity"), _item("2", "properties")])),
    ],
    "20-F": [
        ("Item 3. Key Information (incl. 3.D Risk Factors)", _line("3", "key information"),
         _line("4", "information on the company")),
        ("Item 4. Information on the Company", _line("4", "information on the company"),
         "|".join([_line("4a", "unresolved staff comments"),
                   _line("5", "operating and financial reviews and prospects")])),
    ],
}


def _get(url: str) -> requests.Response:
    agent = os.environ.get("SEC_USER_AGENT")
    if not agent:
        raise SystemExit("SEC_USER_AGENT is not set in .env")
    time.sleep(0.2)  # SEC allows 10 requests/second
    resp = requests.get(url, headers={"User-Agent": agent}, timeout=60)
    resp.raise_for_status()
    return resp


def find_latest_filing(ticker: str) -> dict:
    c = COMPANIES[ticker]
    data = _get(f"https://data.sec.gov/submissions/CIK{c['cik']:010d}.json").json()
    recent = data["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == c["form"]:
            accession = recent["accessionNumber"][i]
            doc = recent["primaryDocument"][i]
            return {
                "ticker": ticker,
                "form": form,
                "filing_date": recent["filingDate"][i],
                "report_date": recent["reportDate"][i],
                "accession": accession,
                "url": f"https://www.sec.gov/Archives/edgar/data/{c['cik']}/"
                       f"{accession.replace('-', '')}/{doc}",
            }
    raise LookupError(f"No {c['form']} found in recent filings for {ticker}")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text("\n").replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# Terms that mark a sentence as describing a relationship.
RELATIONSHIP_TERMS = (
    r"\b(suppliers?|supplied by|sole[- ]source[ds]?|single[- ]source[ds]?|vendors?|foundr(y|ies)|"
    r"contract manufactur\w*|subcontract\w*|outsourc\w*|competitors?|compete[sd]?|competing|"
    r"(largest|significant|major|key|top \w+) customers?|customers? (accounted|represented)|"
    r"\d+% of (our )?(total |net )?(revenue|sales))\b"
)
PASSAGES_LABEL = "Relevant passages (section headings not found)"


def relevant_passages(text: str, ticker: str) -> str:
    """Fallback for filings without standard item headings, such as topic-organized
    10-Ks (Intel) or 20-Fs that are a full annual report (ASML).

    Keeps sentences that name another known company or use a supply-chain term,
    each with the sentence before it for context. The filing company's own names
    are excluded, or every sentence about itself would match. On NVDA's filing
    this keeps 26 of the 27 quotes the section-based extraction used.
    """
    names = {n for t, c in COMPANIES.items() if t != ticker
             for n in [c["name"].split(",")[0], *c["aliases"]] if len(n) > 3}
    names |= {n for display, variants in EXTERNAL.values() for n in [display, *variants]}
    pattern = re.compile(
        RELATIONSHIP_TERMS + r"|\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    sentences = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s*\n\s*", " ", para).strip()
        if len(para) >= 40:  # skip table cells, page numbers, running headers
            sentences += re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", para)
    keep = set()
    for i, sentence in enumerate(sentences):
        if pattern.search(sentence):
            keep.update({i - 1, i})
    return "\n".join(sentences[i] for i in sorted(keep) if i >= 0)


def extract_sections(text: str, form: str) -> tuple[str, list[str]]:
    """Return (trimmed text, labels of sections found), or ("", []) if none."""
    parts, found = [], []
    for label, start_re, end_re in SECTIONS[form]:
        best = ""
        for start in re.finditer(start_re, text, FLAGS):
            end = re.compile(end_re, FLAGS).search(text, start.end())
            if not end:  # a cross-reference late in the filing, not the heading
                continue
            span = text[start.start(): end.start()]
            if len(span) > len(best):
                best = span
        if len(best) > 2000:  # anything shorter is a table-of-contents hit
            parts.append(f"===== {label} =====\n{best}")
            found.append(label)
    if not parts:
        return "", []
    return "\n\n".join(parts), found


def fetch(ticker: str, force: bool = False) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = RAW_DIR / f"{ticker}.meta.json"
    if meta_path.exists() and not force:
        print(f"{ticker}: cached ({meta_path.name})")
        return json.loads(meta_path.read_text())

    meta = find_latest_filing(ticker)
    text = html_to_text(_get(meta["url"]).text)
    sections, found = extract_sections(text, meta["form"])
    if not found:
        sections = f"===== {PASSAGES_LABEL} =====\n" + relevant_passages(text, ticker)
        found = [PASSAGES_LABEL]
    meta["sections_found"] = found
    meta["chars_full"], meta["chars_sections"] = len(text), len(sections)

    (RAW_DIR / f"{ticker}.txt").write_text(text)
    (RAW_DIR / f"{ticker}.sections.txt").write_text(sections)
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"{ticker}: {meta['form']} filed {meta['filing_date']}, "
          f"{len(text):,} chars -> {len(sections):,} chars in {found}")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*", default=list(COMPANIES))
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()
    for t in args.tickers:
        fetch(t.upper(), args.force)


if __name__ == "__main__":
    main()
