"""The companies Story Mode covers.

Read from data/companies.json, the one list shared with the knowledge graph, so
a company is added in one place. Which companies are connected to which comes
from the knowledge graph; see connections.py.
"""
import json
from dataclasses import dataclass

from .config import BACKEND_DIR

COMPANIES_FILE = BACKEND_DIR.parent / "data" / "companies.json"


@dataclass(frozen=True)
class Company:
    symbol: str
    name: str
    cik: str  # zero-padded to 10 digits, the form data.sec.gov wants
    sector: str
    aliases: tuple[str, ...] = ()  # other names the company goes by, e.g. "Google"


COMPANIES: dict[str, Company] = {
    c["ticker"]: Company(c["ticker"], c["name"], f"{int(c['cik']):010d}", c["sector"],
                         tuple(c.get("aliases", ())))
    for c in json.loads(COMPANIES_FILE.read_text())["companies"]
}

SYMBOLS = tuple(COMPANIES)


def get(symbol: str) -> Company:
    try:
        return COMPANIES[symbol.upper()]
    except KeyError:
        raise KeyError(f"{symbol} is outside the supported universe {SYMBOLS}") from None
