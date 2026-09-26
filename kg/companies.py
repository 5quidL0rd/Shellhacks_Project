"""The supported company universe and name resolution.

To add a company: add one entry to COMPANIES. Everything else reads from here.
"""

import re

COMPANIES = {
    "AAPL": {
        "name": "Apple Inc.",
        "cik": 320193,
        "form": "10-K",
        "sector": "Technology Hardware",
        "hq_country": "United States",
        "aliases": ["Apple", "Apple Inc"],
    },
    "NVDA": {
        "name": "NVIDIA Corporation",
        "cik": 1045810,
        "form": "10-K",
        "sector": "Semiconductors",
        "hq_country": "United States",
        "aliases": ["NVIDIA", "Nvidia", "NVIDIA Corp"],
    },
    "AMD": {
        "name": "Advanced Micro Devices, Inc.",
        "cik": 2488,
        "form": "10-K",
        "sector": "Semiconductors",
        "hq_country": "United States",
        "aliases": ["AMD", "Advanced Micro Devices"],
    },
    "TSM": {
        "name": "Taiwan Semiconductor Manufacturing Company Limited",
        "cik": 1046179,
        "form": "20-F",
        "sector": "Semiconductors",
        "hq_country": "Taiwan",
        "aliases": [
            "TSMC",
            "Taiwan Semiconductor Manufacturing Company",
            "Taiwan Semiconductor Manufacturing Co",
            "Taiwan Semiconductor",
        ],
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "cik": 789019,
        "form": "10-K",
        "sector": "Software",
        "hq_country": "United States",
        "aliases": ["Microsoft", "Microsoft Corp"],
    },
}

_SUFFIXES = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|llc|plc|holdings?|group)\b\.?",
    re.IGNORECASE,
)


def normalize(name: str) -> str:
    """Lowercase, drop legal suffixes and punctuation: 'Apple Inc.' -> 'apple'."""
    name = _SUFFIXES.sub(" ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return " ".join(name.split())


# Companies outside the universe that filings name in more than one way.
# slug -> (display name, [variants])
EXTERNAL = {
    "samsung-electronics": ("Samsung Electronics", ["Samsung", "Samsung Electronics Co"]),
    "alphabet": ("Alphabet (Google)", ["Google", "Google LLC", "Alphabet Inc"]),
    "openai": ("OpenAI", ["OpenAI OpCo", "OpenAI OpCo LLC"]),
    "nxp-semiconductors": ("NXP Semiconductors", ["NXP Semiconductors N.V."]),
    "hon-hai-precision-industry": ("Hon Hai (Foxconn)", ["Foxconn", "Hon Hai"]),
    "amazon": ("Amazon", ["Amazon.com", "Amazon Web Services", "AWS"]),
}

_ALIAS_INDEX = {}
for _ticker, _c in COMPANIES.items():
    for _n in [_ticker, _c["name"], *_c["aliases"]]:
        _ALIAS_INDEX[normalize(_n)] = _ticker
for _slug, (_display, _variants) in EXTERNAL.items():
    for _n in [_display, *_variants]:
        _ALIAS_INDEX[normalize(_n)] = _slug


def resolve(name: str) -> tuple[str, bool]:
    """Map a company name to a graph key.

    Returns (key, in_universe). Known companies resolve to their ticker;
    anything else gets a stable slug like 'samsung-electronics'.
    """
    norm = normalize(name)
    key = _ALIAS_INDEX.get(norm, norm.replace(" ", "-"))
    return key, key in COMPANIES


def display_name(key: str, fallback: str) -> str:
    if key in COMPANIES:
        return COMPANIES[key]["name"]
    if key in EXTERNAL:
        return EXTERNAL[key][0]
    return fallback
