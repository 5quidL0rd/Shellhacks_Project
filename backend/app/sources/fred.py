"""Sector-level context from FRED (St. Louis Fed).

This exists because of the IBISWorld entry on the team's source list: industry
and sector trend data. IBISWorld itself is an enterprise subscription with no
developer API, but the underlying question - "is this whole industry expanding
or contracting?" - is answerable from US federal statistics for free.

FRED's graph CSV endpoint needs no API key. The data is monthly and lags by a
month or two, so it belongs in the story's arc paragraph ("semiconductor
production is up 12% year over year") and never in a single-day beat.
"""
from __future__ import annotations

import csv
import io
from datetime import date

import requests

from ..cache import cached

SOURCE_NAME = "FRED (Federal Reserve Bank of St. Louis)"
_CSV_ENDPOINT = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class Series:
    def __init__(self, series_id: str, label: str, units: str):
        self.series_id = series_id
        self.label = label
        self.units = units

    @property
    def url(self) -> str:
        return f"https://fred.stlouisfed.org/series/{self.series_id}"


SEMICONDUCTOR_PRODUCTION = Series(
    "IPG3344S",
    "US semiconductor and electronic component production",
    "index, 2017=100",
)
SEMICONDUCTOR_PRICES = Series(
    "PCU334413334413",
    "US semiconductor producer price index",
    "index",
)
ELECTRONICS_EMPLOYMENT = Series(
    "CES3133400001",
    "US computer and electronic product manufacturing employment",
    "thousands of jobs",
)

# Which backdrop is relevant to which kind of company.
SECTOR_SERIES: dict[str, tuple[Series, ...]] = {
    "Semiconductors": (SEMICONDUCTOR_PRODUCTION, SEMICONDUCTOR_PRICES),
    # Equipment demand follows chip production, so the same backdrop applies.
    "Semiconductor Equipment": (SEMICONDUCTOR_PRODUCTION, SEMICONDUCTOR_PRICES),
    "Technology Hardware": (ELECTRONICS_EMPLOYMENT, SEMICONDUCTOR_PRODUCTION),
    "Software": (),  # no federal series maps cleanly; better none than a bad proxy
}


def _fetch(series_id: str) -> list[dict]:
    response = requests.get(
        _CSV_ENDPOINT,
        params={"id": series_id},
        headers={"User-Agent": "Mozilla/5.0 ShellhacksPortfolioStory"},
        timeout=30,
    )
    response.raise_for_status()
    if not response.text.lstrip().startswith("observation_date"):
        raise RuntimeError(f"FRED returned no CSV for {series_id}")

    rows: list[dict] = []
    for row in csv.DictReader(io.StringIO(response.text)):
        raw = row.get(series_id, "")
        if raw in ("", "."):  # FRED writes "." for a missing observation
            continue
        rows.append({"date": row["observation_date"], "value": float(raw)})
    return rows


def observations(series: Series, since_year: int | None = None) -> list[dict]:
    rows = cached(f"fred_{series.series_id}", lambda: _fetch(series.series_id),
                  max_age_seconds=7 * 24 * 3600)
    if since_year is not None:
        rows = [r for r in rows if int(r["date"][:4]) >= since_year]
    return rows


def latest_with_yoy(series: Series) -> dict | None:
    """Most recent observation and its change from twelve months earlier.

    Year over year rather than month over month: these series are seasonal, and
    "up 12% from a year ago" is the sentence an investor can use.
    """
    rows = observations(series, since_year=date.today().year - 3)
    if not rows:
        return None

    latest = rows[-1]
    yoy = None
    if len(rows) >= 13:
        year_ago = rows[-13]["value"]
        if year_ago:
            yoy = round((latest["value"] - year_ago) / abs(year_ago) * 100, 2)

    return {
        "series_id": series.series_id,
        "label": series.label,
        "units": series.units,
        "url": series.url,
        "as_of": latest["date"],
        "value": latest["value"],
        "yoy_pct_change": yoy,
    }


def sector_context(sector: str) -> list[dict]:
    """Latest reading per series relevant to this sector. Never raises: a
    missing backdrop should thin the arc, not fail the story."""
    out = []
    for series in SECTOR_SERIES.get(sector, ()):
        try:
            reading = latest_with_yoy(series)
        except Exception:
            continue
        if reading:
            out.append(reading)
    return out
