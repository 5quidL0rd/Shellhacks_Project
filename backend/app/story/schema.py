"""The contract between the data layer, Gemini, and the frontend.

The rule the whole feature rests on: a sentence the investor reads must point
at an Evidence row, and that row must carry both the numbers and a URL. If a
claim cannot be traced that way, it does not ship to the screen.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    NEWS = "news"           # a published article, links to the publisher
    FILING = "filing"       # an SEC filing, links to sec.gov
    PRICE = "price"         # the move itself: OHLCV and percent change
    FUNDAMENTAL = "fundamental"  # an XBRL figure, links to the filing it came from
    PEER_MOVE = "peer_move"      # a related holding moved the same day
    SECTOR = "sector"            # industry-wide backdrop, links to FRED


class Evidence(BaseModel):
    """One citable fact. `id` is what Gemini is allowed to reference."""
    id: str
    kind: EvidenceKind
    title: str
    detail: str = ""
    source: str = Field(description="Human-readable provider, e.g. 'SEC EDGAR'")
    url: str | None = Field(default=None, description="Where the investor lands on click")
    occurred_on: str = Field(description="ISO date this fact is attached to")
    # Concrete figures for the drill-down panel, e.g. {"pct_change": -7.2}
    numbers: dict[str, float | int | str] = Field(default_factory=dict)


class StoryBeat(BaseModel):
    """One labelled point on the price chart."""
    date: str
    pct_change: float
    close: float
    direction: Literal["up", "down"]
    headline: str = Field(description="Under ~60 chars; the chart marker label")
    explanation: str = Field(description="2-3 sentences on why the price moved")
    confidence: Literal["high", "medium", "low"]
    citation_ids: list[str] = Field(default_factory=list)


class Story(BaseModel):
    symbol: str
    company_name: str
    generated_at: str
    # Full price series for the chart; beats are the markers laid over it.
    bars: list[dict]
    beats: list[StoryBeat]
    evidence: dict[str, Evidence]
    arc: str = Field(default="", description="Paragraph framing the whole period")
    arc_citation_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
