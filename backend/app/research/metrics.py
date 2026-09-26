"""The five radar axes for any company, each traceable to what it came from.

Growth, profitability and debt come from SEC XBRL filings where the company
files them, and fall back to Yahoo's ratios where it does not - BMW's SEC
presence is an ADR registration with no financials at all, and three blank axes
would make the whole shape useless. Every metric records which it used, because
an audited filing and a vendor's ratio are not the same evidence.

Stability and risk come from the daily price series, which exists for anything
with a ticker.

Scores are percentile ranks **within the investor's own holdings plus this
candidate**. That makes the comparison the one they actually asked for - "how
does this stack up against what I own" - rather than against an arbitrary
reference set.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..sources import edgar
from . import subject as subject_mod
from .subject import Subject

TRADING_DAYS_PER_YEAR = 252

# Higher raw value is the favourable end for these; for the rest, lower is.
# "stability" carries annualised volatility and "risk" a drawdown, so both
# belong in the lower-is-better group even though their names sound positive.
HIGHER_IS_BETTER = {"growth", "profitability"}
AXES = ("growth", "profitability", "stability", "debt", "risk")

# What the favourable end of each axis means, so a rank can be read correctly.
FAVOURABLE = {
    "growth": "faster revenue growth",
    "profitability": "a fatter profit margin",
    "stability": "a steadier price, i.e. lower volatility",
    "debt": "less debt relative to equity",
    "risk": "a shallower worst-case drawdown",
}


@dataclass
class Metric:
    axis: str
    value: float | None
    unit: str
    label: str
    explanation: str = ""
    percentile: int | None = None
    evidence: list[dict] = field(default_factory=list)
    as_of: str | None = None
    stale_days: int | None = None
    # "SEC EDGAR" or "Yahoo Finance"; an audited filing is stronger evidence
    # than a vendor ratio, and the UI says which one it is.
    basis: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None


def _filing_url(cik: str | None, point: dict) -> str | None:
    accession = (point.get("accession") or "").replace("-", "")
    if not accession or not cik:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/"


def _filing_evidence(cik: str | None, point: dict, what: str) -> dict:
    return {
        "what": what,
        "value": point["value"],
        "as_of": point.get("period_end") or point.get("as_of"),
        "form": point.get("form"),
        "xbrl_tag": point.get("xbrl_tag"),
        "taxonomy": point.get("taxonomy"),
        "derived": point.get("derived", False),
        "source": "SEC EDGAR",
        "url": _filing_url(cik, point),
    }


def _yahoo_evidence(subject: Subject, what: str, value: float) -> dict:
    return {
        "what": what,
        "value": value,
        "source": "Yahoo Finance",
        "url": f"https://finance.yahoo.com/quote/{subject.ticker}/key-statistics",
        "note": "Vendor-computed ratio, not read from a filing.",
    }


def _price_evidence(subject: Subject, bars: list[dict], value: float, what: str) -> dict:
    return {
        "what": what,
        "value": value,
        "as_of": bars[-1]["date"],
        "source": "Yahoo Finance (daily closes)",
        "url": f"https://finance.yahoo.com/quote/{subject.ticker}/history",
        "note": f"{len(bars)} sessions, {bars[0]['date']} to {bars[-1]['date']}",
    }


def growth(subject: Subject, bars: list[dict]) -> Metric:
    """Revenue growth year over year.

    Compared like with like: a quarterly filer against the same quarter a year
    earlier, an annual filer against the prior year.
    """
    series = edgar.duration_facts(subject.cik, "revenue") if subject.cik else []
    if len(series) >= 2:
        period = series[-1]["period"]
        lag = 4 if period == "quarter" else 1
        if len(series) > lag and series[-1 - lag]["value"]:
            latest, prior = series[-1], series[-1 - lag]
            pct = (latest["value"] - prior["value"]) / abs(prior["value"]) * 100
            unit = "quarter" if period == "quarter" else "year"
            return Metric(
                "growth", round(pct, 2), "%", "Revenue growth (YoY)",
                explanation=(
                    f"Revenue was {latest['value'] / 1e9:,.1f}B in the {unit} ending "
                    f"{latest['period_end']}, against {prior['value'] / 1e9:,.1f}B a "
                    f"year earlier ({prior['period_end']})."
                ),
                evidence=[_filing_evidence(subject.cik, p, f"Revenue, {unit} ending {p['period_end']}")
                          for p in (prior, latest)],
                as_of=latest["period_end"], stale_days=latest.get("stale_days"),
                basis="SEC EDGAR",
            )

    fallback = subject_mod.profile(subject.ticker).get("revenue_growth_pct")
    if fallback is not None:
        return Metric(
            "growth", fallback, "%", "Revenue growth (YoY)",
            explanation=f"Revenue grew {fallback:+.1f}% year over year, per Yahoo. "
                        "This company files no usable financials with the SEC.",
            evidence=[_yahoo_evidence(subject, "Revenue growth, year over year", fallback)],
            basis="Yahoo Finance",
        )
    return Metric("growth", None, "%", "Revenue growth (YoY)",
                  "No revenue history in EDGAR, and no vendor figure either.")


def profitability(subject: Subject, bars: list[dict]) -> Metric:
    """Net profit margin: net income as a percent of revenue."""
    revenue = edgar.duration_facts(subject.cik, "revenue") if subject.cik else []
    income = edgar.duration_facts(subject.cik, "net_income") if subject.cik else []
    if revenue and income:
        by_income = {p["period_end"]: p for p in income}
        shared = [p for p in revenue if p["period_end"] in by_income]
        if shared and shared[-1]["value"]:
            latest_rev = shared[-1]
            latest_inc = by_income[latest_rev["period_end"]]
            margin = latest_inc["value"] / latest_rev["value"] * 100
            return Metric(
                "profitability", round(margin, 2), "%", "Net profit margin",
                explanation=(
                    f"Kept {margin:.1f} cents of every revenue dollar as profit in the "
                    f"period ending {latest_rev['period_end']} "
                    f"({latest_inc['value'] / 1e9:,.1f}B on {latest_rev['value'] / 1e9:,.1f}B)."
                ),
                evidence=[_filing_evidence(subject.cik, latest_rev, "Revenue"),
                          _filing_evidence(subject.cik, latest_inc, "Net income")],
                as_of=latest_rev["period_end"], stale_days=latest_rev.get("stale_days"),
                basis="SEC EDGAR",
            )

    fallback = subject_mod.profile(subject.ticker).get("profit_margin_pct")
    if fallback is not None:
        return Metric(
            "profitability", fallback, "%", "Net profit margin",
            explanation=f"Net margin of {fallback:.1f}%, per Yahoo. This company files "
                        "no usable financials with the SEC.",
            evidence=[_yahoo_evidence(subject, "Net profit margin", fallback)],
            basis="Yahoo Finance",
        )
    return Metric("profitability", None, "%", "Net profit margin",
                  "No revenue or net income available.")


def debt(subject: Subject, bars: list[dict]) -> Metric:
    """Liabilities as a multiple of equity. Lower is less leveraged."""
    liabilities = edgar.instant_facts(subject.cik, "total_liabilities") if subject.cik else []
    equity = edgar.instant_facts(subject.cik, "equity") if subject.cik else []
    if liabilities and equity:
        by_equity = {p["as_of"]: p for p in equity}
        shared = [p for p in liabilities if p["as_of"] in by_equity]
        if shared and by_equity[shared[-1]["as_of"]]["value"] > 0:
            latest_liab = shared[-1]
            latest_eq = by_equity[latest_liab["as_of"]]
            ratio = latest_liab["value"] / latest_eq["value"]
            return Metric(
                "debt", round(ratio, 2), "x", "Debt-to-equity",
                explanation=(
                    f"Owes {ratio:.2f}x its equity as of {latest_liab['as_of']}: "
                    f"{latest_liab['value'] / 1e9:,.1f}B of liabilities against "
                    f"{latest_eq['value'] / 1e9:,.1f}B of equity."
                ),
                evidence=[_filing_evidence(subject.cik, latest_liab, "Total liabilities"),
                          _filing_evidence(subject.cik, latest_eq, "Shareholders' equity")],
                as_of=latest_liab["as_of"], stale_days=latest_liab.get("stale_days"),
                basis="SEC EDGAR",
            )

    fallback = subject_mod.profile(subject.ticker).get("debt_to_equity")
    if fallback is not None:
        return Metric(
            "debt", fallback, "x", "Debt-to-equity",
            explanation=f"Owes {fallback:.2f}x its equity, per Yahoo. This company files "
                        "no usable balance sheet with the SEC.",
            evidence=[_yahoo_evidence(subject, "Debt-to-equity", fallback)],
            basis="Yahoo Finance",
        )
    return Metric("debt", None, "x", "Debt-to-equity",
                  "No liabilities or equity available.")


def stability(subject: Subject, bars: list[dict]) -> Metric:
    """Annualised volatility of daily returns. Lower is steadier."""
    rets = [b["pct_change"] / 100 for b in bars[1:] if b.get("pct_change") is not None]
    if len(rets) < 20:
        return Metric("stability", None, "%", "Annualised volatility",
                      "Not enough price history.")
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    annual = math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100
    return Metric(
        "stability", round(annual, 2), "%", "Annualised volatility",
        explanation=(f"Daily moves over {len(rets)} sessions annualise to "
                     f"{annual:.0f}% volatility. Lower means a steadier price."),
        evidence=[_price_evidence(subject, bars, round(annual, 2),
                                  "Annualised volatility of daily returns")],
        as_of=bars[-1]["date"], stale_days=0, basis="Yahoo Finance",
    )


def risk(subject: Subject, bars: list[dict]) -> Metric:
    """Worst peak-to-trough fall over the window.

    Volatility says how much it wobbles; drawdown says how much it actually lost
    from a high, which is the number an investor feels.
    """
    if len(bars) < 20:
        return Metric("risk", None, "%", "Maximum drawdown", "Not enough price history.")

    peak, peak_date = bars[0]["close"], bars[0]["date"]
    worst, trough_date, worst_peak = 0.0, bars[0]["date"], bars[0]["date"]
    for bar in bars:
        if bar["close"] > peak:
            peak, peak_date = bar["close"], bar["date"]
        drop = (bar["close"] - peak) / peak * 100
        if drop < worst:
            worst, trough_date, worst_peak = drop, bar["date"], peak_date

    return Metric(
        "risk", round(abs(worst), 2), "%", "Maximum drawdown",
        explanation=(f"Fell {abs(worst):.1f}% from its {worst_peak} high to its "
                     f"{trough_date} low. Lower means shallower losses."),
        evidence=[_price_evidence(subject, bars, round(abs(worst), 2),
                                  f"Peak {worst_peak} to trough {trough_date}")],
        as_of=bars[-1]["date"], stale_days=0, basis="Yahoo Finance",
    )


_CALCULATORS = {"growth": growth, "profitability": profitability,
                "stability": stability, "debt": debt, "risk": risk}


def raw_metrics(subject: Subject, bars: list[dict] | None = None) -> dict[str, Metric]:
    bars = bars if bars is not None else subject_mod.bars(subject.ticker)
    return {axis: _CALCULATORS[axis](subject, bars) for axis in AXES}


def _percentile(axis: str, value: float, others: list[float]) -> int:
    """0-100, where 100 is always the most favourable end of the axis."""
    if len(others) < 2:
        return 50
    if axis in HIGHER_IS_BETTER:
        beaten = sum(1 for v in others if value > v)
    else:
        beaten = sum(1 for v in others if value < v)
    return round(beaten / (len(others) - 1) * 100)


def rank_within(
    metrics: dict[str, Metric],
    population: dict[str, dict[str, Metric]],
) -> dict[str, Metric]:
    """Fill in each metric's rank against a population of companies.

    `population` maps ticker to that company's metrics, and must include the
    subject itself so the ranks span the full comparison set.
    """
    for axis, metric in metrics.items():
        if not metric.available:
            continue
        values = [m[axis].value for m in population.values()
                  if m[axis].available and m[axis].value is not None]
        metric.percentile = _percentile(axis, metric.value, values)
    return metrics
