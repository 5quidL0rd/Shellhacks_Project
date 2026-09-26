"""The five companies Story Mode covers for the demo.

Keeping CIKs here means no lookup call at story-build time. Which companies
are connected to which comes from the knowledge graph; see connections.py.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    symbol: str
    name: str
    cik: str  # zero-padded to 10 digits, the form data.sec.gov wants
    sector: str


COMPANIES: dict[str, Company] = {
    "AAPL": Company(
        "AAPL", "Apple Inc.", "0000320193", "Consumer Electronics",
    ),
    "NVDA": Company(
        "NVDA", "NVIDIA Corporation", "0001045810", "Semiconductors",
    ),
    "AMD": Company(
        "AMD", "Advanced Micro Devices, Inc.", "0000002488", "Semiconductors",
    ),
    "TSM": Company(
        "TSM", "Taiwan Semiconductor Manufacturing Company Limited",
        "0001046179", "Semiconductors",
    ),
    "MSFT": Company(
        "MSFT", "Microsoft Corporation", "0000789019", "Software",
    ),
}

SYMBOLS = tuple(COMPANIES)


def get(symbol: str) -> Company:
    try:
        return COMPANIES[symbol.upper()]
    except KeyError:
        raise KeyError(f"{symbol} is outside the supported universe {SYMBOLS}") from None
