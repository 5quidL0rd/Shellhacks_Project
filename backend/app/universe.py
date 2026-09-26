"""The five companies Story Mode covers for the demo.

Keeping CIKs and peers here means no lookup call at story-build time, and it
gives the Connection Map a starting set of edges to grow from.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Company:
    symbol: str
    name: str
    cik: str  # zero-padded to 10 digits, the form data.sec.gov wants
    sector: str
    peers: tuple[str, ...] = field(default_factory=tuple)


COMPANIES: dict[str, Company] = {
    "AAPL": Company(
        "AAPL", "Apple Inc.", "0000320193", "Consumer Electronics",
        peers=("MSFT", "NVDA"),
    ),
    "NVDA": Company(
        "NVDA", "NVIDIA Corporation", "0001045810", "Semiconductors",
        peers=("AMD", "TSM"),
    ),
    "AMD": Company(
        "AMD", "Advanced Micro Devices, Inc.", "0000002488", "Semiconductors",
        peers=("NVDA", "TSM"),
    ),
    "TSM": Company(
        "TSM", "Taiwan Semiconductor Manufacturing Company Limited",
        "0001046179", "Semiconductors", peers=("NVDA", "AMD"),
    ),
    "MSFT": Company(
        "MSFT", "Microsoft Corporation", "0000789019", "Software",
        peers=("AAPL", "NVDA"),
    ),
}

SYMBOLS = tuple(COMPANIES)


def get(symbol: str) -> Company:
    try:
        return COMPANIES[symbol.upper()]
    except KeyError:
        raise KeyError(f"{symbol} is outside the supported universe {SYMBOLS}") from None
