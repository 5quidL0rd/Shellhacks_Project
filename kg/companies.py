"""The supported company universe and name resolution.

The companies themselves live in data/companies.json, the one list shared with
the backend. To add a company, add it there.
"""

import json
import re
from pathlib import Path

_COMPANIES_FILE = Path(__file__).resolve().parent.parent / "data" / "companies.json"

COMPANIES = {
    c["ticker"]: {k: v for k, v in c.items() if k != "ticker"}
    for c in json.loads(_COMPANIES_FILE.read_text())["companies"]
}

_SUFFIXES = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|llc|plc|holdings?|group|gmbh|pte|ag)\b\.?",
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
    "openai": ("OpenAI", ["OpenAI OpCo", "OpenAI OpCo LLC"]),
    "nxp-semiconductors": ("NXP Semiconductors", ["NXP Semiconductors N.V."]),
    "hon-hai-precision-industry": ("Hon Hai (Foxconn)", ["Foxconn", "Hon Hai", "Foxconn Technology Group"]),
    "globalfoundries": ("GlobalFoundries", ["Global Foundries", "GLOBALFOUNDRIES Inc"]),
    "stats-chippac": ("STATS ChipPAC", ["STATSChipPAC", "STATS ChipPAC Pte. Ltd."]),
    "advanced-semiconductor-engineering": ("ASE (Advanced Semiconductor Engineering)",
                                           ["Advanced Semiconductor Engineering", "ASE Technology", "ASE"]),
    "huawei": ("Huawei", ["Huawei Technologies", "Huawei Technologies Co. Ltd."]),
    "skyworks": ("Skyworks Solutions", ["Skyworks", "Skyworks Solutions Inc."]),
    "carl-zeiss": ("Carl Zeiss", ["Zeiss", "Carl Zeiss SMT", "Carl Zeiss SMT GmbH"]),
    "kla": ("KLA", ["KLA Corporation", "KLA-Tencor", "KLA-Tencor Corporation"]),
    "meta": ("Meta Platforms", ["Meta", "Meta Platforms, Inc.", "Facebook"]),
}

_ALIAS_INDEX = {}
for _slug, (_display, _variants) in EXTERNAL.items():
    for _n in [_display, *_variants]:
        _ALIAS_INDEX[normalize(_n)] = _slug
# Supported companies go last so they win if a name is in both lists.
for _ticker, _c in COMPANIES.items():
    for _n in [_ticker, _c["name"], *_c["aliases"]]:
        _ALIAS_INDEX[normalize(_n)] = _ticker


def resolve(name: str) -> tuple[str, bool]:
    """Map a company name to a graph key.

    Returns (key, in_universe). Known companies resolve to their ticker;
    anything else gets a stable slug like 'samsung-electronics'.
    """
    norm = normalize(name)
    if norm not in _ALIAS_INDEX:
        # "Taiwan Semiconductor Manufacturing Company (TSMC)": try the name
        # without the parenthetical, then the abbreviation inside it.
        bare = re.sub(r"\s*\([^)]*\)", "", name)
        inner = re.findall(r"\(([^)]*)\)", name)
        for candidate in [bare, *inner]:
            if normalize(candidate) in _ALIAS_INDEX:
                norm = normalize(candidate)
                break
        else:
            norm = normalize(bare)
    key = _ALIAS_INDEX.get(norm, norm.replace(" ", "-"))
    return key, key in COMPANIES


def display_name(key: str, fallback: str) -> str:
    if key in COMPANIES:
        return COMPANIES[key]["name"]
    if key in EXTERNAL:
        return EXTERNAL[key][0]
    return fallback
