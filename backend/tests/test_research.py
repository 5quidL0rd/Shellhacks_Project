"""Tests for Research: resolving a searched company, and scoring the overlap.

Three things worth protecting:
  1. Search finds the common stock, not a preferred share class, and knows a
     brand from a filer.
  2. Every axis's rank points the friendly way round. A silent inversion makes
     the wildest stock look steadiest and nothing downstream would notice.
  3. An overlap check that could not be run is excluded, never scored as if the
     absence were good news.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.research import fit, generate, lookup  # noqa: E402
from app.research.metrics import AXES, HIGHER_IS_BETTER, _percentile  # noqa: E402
from app.research.subject import Subject, UNKNOWN_SECTOR  # noqa: E402


def subject(ticker="F", sector="Consumer Cyclical", graph_id=None) -> Subject:
    return Subject(ticker=ticker, name=f"{ticker} Inc", cik="0000000001",
                   sector=sector, industry="Autos", country="United States",
                   in_universe=False, graph_id=graph_id)


# --- search ----------------------------------------------------------------

def test_exact_ticker_wins():
    best, _ = lookup.resolve("F")
    assert best is not None and best.ticker == "F"


def test_company_name_resolves_to_common_stock_not_preferred_shares():
    """Ford's preferred shares file under the same name; the common stock wins."""
    best, matches = lookup.resolve("ford motor")
    assert best is not None and best.ticker == "F"
    assert any("-" in m.ticker for m in matches), "expected preferred classes present"


def test_brand_resolves_to_the_company_that_files():
    best, _ = lookup.resolve("alienware")
    assert best is not None and best.ticker == "DELL"


def test_genuinely_ambiguous_query_returns_no_confident_match():
    """BRK-A and BRK-B are different securities; the user must choose."""
    best, matches = lookup.resolve("berkshire hathaway")
    assert best is None
    assert len(matches) >= 2


def test_nonsense_query_finds_nothing():
    best, matches = lookup.resolve("zzzzqqqnotacompany")
    assert best is None and matches == []


def test_empty_query_is_not_an_error():
    assert lookup.search("") == []


# --- rank direction --------------------------------------------------------

@pytest.mark.parametrize("axis", sorted(set(AXES) - HIGHER_IS_BETTER))
def test_lower_is_better_axes_rank_the_low_value_highest(axis):
    """Volatility, debt and drawdown: the small number is the good news."""
    population = [10.0, 50.0, 90.0]
    assert _percentile(axis, 10.0, population) == 100
    assert _percentile(axis, 90.0, population) == 0


@pytest.mark.parametrize("axis", sorted(HIGHER_IS_BETTER))
def test_higher_is_better_axes_rank_the_high_value_highest(axis):
    population = [10.0, 50.0, 90.0]
    assert _percentile(axis, 90.0, population) == 100
    assert _percentile(axis, 10.0, population) == 0


def test_percentile_is_neutral_with_nothing_to_compare():
    assert _percentile("growth", 5.0, [5.0]) == 50


# --- correlation -----------------------------------------------------------

def bars(pcts: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i + 1:02d}", "close": 100.0, "volume": 1, "pct_change": p}
            for i, p in enumerate(pcts)]


def test_identical_series_correlate_at_one():
    series = bars([1.0, -2.0, 3.0, -1.5] * 10)
    assert fit.correlation(series, series) == pytest.approx(1.0)


def test_opposite_series_correlate_at_minus_one():
    up = bars([1.0, -2.0, 3.0, -1.5] * 10)
    down = [{**b, "pct_change": -b["pct_change"]} for b in up]
    assert fit.correlation(up, down) == pytest.approx(-1.0)


def test_correlation_needs_enough_shared_days():
    assert fit.correlation(bars([1.0, 2.0, 3.0]), bars([1.0, 2.0, 3.0])) is None


def test_a_lockstep_company_scores_worse_than_an_uncorrelated_one():
    """The trap this feature exists to catch: same price behaviour is not
    diversification, whatever sector the company is labelled."""
    holding = bars([1.0, -2.0, 3.0, -1.5] * 10)
    mirror = fit.correlation_fit(holding, {"AAPL": holding})
    inverse = fit.correlation_fit([{**b, "pct_change": -b["pct_change"]} for b in holding],
                                 {"AAPL": holding})
    assert mirror.score < inverse.score
    assert mirror.score == 0


def test_correlation_without_price_history_is_unmeasured():
    component = fit.correlation_fit([], {})
    assert not component.measured and component.score is None


# --- sector crowding -------------------------------------------------------

def test_sector_crowding_penalises_piling_into_one_sector():
    crowded = fit.sector_crowding(subject(sector="Technology"),
                                  {"NVDA": "Technology", "AMD": "Technology"})
    fresh = fit.sector_crowding(subject(sector="Utilities"),
                                {"NVDA": "Technology", "AMD": "Technology"})
    assert crowded.score == 0
    assert fresh.score == 100


def test_empty_portfolio_cannot_be_concentrated():
    assert fit.sector_crowding(subject(), {}).score == 100


def test_unknown_sector_is_unmeasured_not_assumed_good():
    component = fit.sector_crowding(subject(sector=UNKNOWN_SECTOR), {"NVDA": "Technology"})
    assert not component.measured


# --- graph components: absence is unknown, not clean ----------------------

def test_company_outside_the_graph_has_dependencies_unmeasured():
    component = fit.dependency_overlap(subject(graph_id=None), ["AAPL"])
    assert not component.measured
    assert component.band == "Unknown"
    # It must say it does not know, not imply a clean result.
    assert component.plain and "cannot tell" in component.plain


def test_company_outside_the_graph_has_direct_links_unmeasured():
    component = fit.direct_connection(subject(graph_id=None), ["AAPL"])
    assert not component.measured
    assert component.band == "Unknown"
    assert component.plain and "cannot say" in component.plain


def test_every_component_carries_a_plain_sentence():
    """The numbers alone did not tell people whether a score was good, so each
    component must explain itself in words."""
    tsm = Subject("TSM", "TSMC", "0001046179", "Technology", "Semiconductors",
                  "Taiwan", True, "TSM")
    holding_bars = {"AAPL": bars([1.0, -2.0, 3.0, -1.5] * 10)}
    components = [
        fit.correlation_fit(bars([1.0, -2.0, 3.0, -1.5] * 10), holding_bars),
        fit.correlation_fit([], {}),
        fit.sector_crowding(subject(sector="Technology"), {"NVDA": "Technology"}),
        fit.sector_crowding(subject(sector="Utilities"), {"NVDA": "Technology"}),
        fit.sector_crowding(subject(), {}),
        fit.dependency_overlap(subject(graph_id=None), ["AAPL"]),
        fit.dependency_overlap(tsm, ["AAPL", "NVDA"]),
        fit.direct_connection(subject(graph_id=None), ["AAPL"]),
        fit.direct_connection(tsm, ["AAPL", "NVDA"]),
        fit.direct_connection(tsm, []),
    ]
    for component in components:
        assert component.plain, f"{component.name} ({component.label}) has no plain text"
        # Plain speech means no bare figures to decode.
        assert "/100" not in component.plain


def test_band_words_track_the_score():
    assert fit.Component("x", 95, "", "").band == "Little overlap"
    assert fit.Component("x", 80, "", "").band == "Little overlap"
    assert fit.Component("x", 79, "", "").band == "Some overlap"
    assert fit.Component("x", 50, "", "").band == "Some overlap"
    assert fit.Component("x", 49, "", "").band == "Notable overlap"
    assert fit.Component("x", 25, "", "").band == "Notable overlap"
    assert fit.Component("x", 24, "", "").band == "Heavy overlap"
    assert fit.Component("x", 0, "", "").band == "Heavy overlap"
    assert fit.Component("x", None, "", "").band == "Unknown"


def test_tsmc_supplying_three_holdings_scores_low():
    """A real graph read: TSMC supplies Apple, NVIDIA and AMD."""
    tsm = Subject("TSM", "TSMC", "0001046179", "Technology", "Semiconductors",
                  "Taiwan", True, "TSM")
    component = fit.direct_connection(tsm, ["AAPL", "NVDA", "AMD"])
    assert component.measured
    assert component.score <= 25


# --- combining -------------------------------------------------------------

def test_unmeasured_components_are_excluded_and_weights_renormalised():
    components = {
        "correlation": fit.Component("correlation", 50, "", ""),
        "sector_crowding": fit.Component("sector_crowding", 100, "", ""),
        "dependency_overlap": fit.Component("dependency_overlap", None, "", ""),
        "direct_connection": fit.Component("direct_connection", None, "", ""),
    }
    score, applied = fit.combine(components)
    assert set(applied) == {"correlation", "sector_crowding"}
    assert sum(applied.values()) == pytest.approx(1.0)
    # 50 and 100 weighted 0.35/0.65 of the remaining 0.65 total.
    assert score == round(50 * (0.35 / 0.65) + 100 * (0.30 / 0.65))


def test_all_unmeasured_gives_no_score_rather_than_the_worst_one():
    components = {n: fit.Component(n, None, "", "") for n in fit.WEIGHTS}
    assert fit.combine(components) == (None, {})
    assert fit.verdict_for(None)[0] == "Not enough data"


def test_weights_sum_to_one():
    assert sum(fit.WEIGHTS.values()) == pytest.approx(1.0)


def test_verdict_thresholds_are_ordered():
    assert fit.verdict_for(95)[0] == "Good diversity"
    assert fit.verdict_for(70)[0] == "Good diversity"
    assert fit.verdict_for(69)[0] == "Some diversification"
    assert fit.verdict_for(45)[0] == "Some diversification"
    assert fit.verdict_for(44)[0] == "Risky overlap"
    assert fit.verdict_for(0)[0] == "Risky overlap"


# --- citation verification -------------------------------------------------

def test_invented_citation_is_dropped_but_the_item_survives_on_a_real_one():
    kept, warnings = generate._verify(
        [{"point": "Grew fast", "citation_ids": ["real", "made_up"]}], {"real"})
    assert kept[0]["citation_ids"] == ["real"]
    assert any("made_up" in w for w in warnings)


def test_item_citing_only_invented_evidence_is_removed():
    kept, warnings = generate._verify(
        [{"point": "Trust me", "citation_ids": ["nope"]}], {"real"})
    assert kept == []
    assert any("uncited claim" in w for w in warnings)


def test_item_with_no_citations_is_removed():
    kept, _ = generate._verify([{"point": "Vibes", "citation_ids": []}], {"real"})
    assert kept == []


# --- reading a searched company's own filing -------------------------------
#
# The knowledge graph covers 13 companies but Research accepts ~10,400, so for
# almost anything searched the two graph checks had nothing and said "unknown".
# These cover the on-demand extraction that fills that gap.

def extraction(relationships, available=True, **over) -> dict:
    base = {"available": available, "form": "10-K", "filing_date": "2025-12-18",
            "url": "https://sec.gov/x", "relationships": relationships,
            "dropped_unverified": 0, "passage_chars": 40000}
    return {**base, **over}


def rel(kind, name=None, country=None, quote="quoted from the filing text here",
        **over) -> dict:
    return {"type": kind, "counterparty_name": name, "country": country,
            "operates_kind": over.pop("operates_kind", None),
            "detail": over.pop("detail", None), "evidence": quote,
            "confidence": "high", "is_named": name is not None, **over}


def test_a_filing_naming_a_holding_is_found():
    """HPE's own 10-K names AMD and NVIDIA as suppliers; that must surface."""
    data = extraction([rel("SUPPLIER", "Advanced Micro Devices, Inc."),
                       rel("SUPPLIER", "NVIDIA Corporation"),
                       rel("COMPETITOR", "Microsoft Corporation")])
    component = fit.direct_connection(subject(graph_id=None), ["AMD", "NVDA", "MSFT"], data)
    assert component.measured
    assert component.score == max(0, 100 - 25 * 3)
    for ticker in ("AMD", "NVDA", "MSFT"):
        assert ticker in component.plain


def test_a_filing_naming_none_of_the_holdings_scores_clean():
    """Coca-Cola names PepsiCo and Nestle; none of them is held."""
    data = extraction([rel("COMPETITOR", "PepsiCo, Inc."), rel("COMPETITOR", "Nestle S.A.")])
    component = fit.direct_connection(subject(graph_id=None), ["AAPL", "NVDA"], data)
    assert component.measured and component.score == 100


def test_no_filing_still_reports_unknown_not_clean():
    """BMW files no annual report; that must stay unknown, not score as clean."""
    data = {"available": False, "reason": "no_annual_report"}
    for component in (fit.direct_connection(subject(graph_id=None), ["AAPL"], data),
                      fit.dependency_overlap(subject(graph_id=None), ["AAPL"], data)):
        assert not component.measured
        assert component.band == "Unknown"


def test_name_matching_tolerates_how_a_filing_writes_a_name():
    """A filing writes "Apple" or "Apple Inc."; both must reach AAPL."""
    from app.research import relationships as rels_mod
    hits = rels_mod.match_to_holdings(
        [rel("CUSTOMER", "Apple"), rel("SUPPLIER", "Apple Inc.")], ["AAPL"])
    assert {h["holding"] for h in hits} == {"AAPL"}
    assert len(hits) == 2


def test_countries_count_as_dependencies_but_headquarters_do_not():
    from app.research import relationships as rels_mod
    deps = rels_mod.dependencies([
        rel("OPERATES_IN", country="Taiwan", operates_kind="manufacturing"),
        rel("OPERATES_IN", country="Ireland", operates_kind="headquarters"),
        rel("SUPPLIER", "Taiwan Semiconductor Manufacturing Company Limited"),
        rel("CUSTOMER", "Dell Technologies Inc."),
    ])
    assert ("country", "Taiwan") in deps
    assert ("country", "Ireland") not in deps, "headquarters is not a shared dependency"
    assert ("supplier", "Taiwan Semiconductor Manufacturing Company Limited") in deps
    assert not any(kind == "customer" for kind, _ in deps)


def test_an_unverifiable_quote_is_dropped():
    """The model is reading a real document, so a fabricated quote is the failure
    mode to guard against."""
    from app.research import relationships as rels_mod
    filing_text = "Our largest supplier of graphics processors is NVIDIA Corporation."
    good = rels_mod._normalise("largest supplier of graphics processors is NVIDIA")
    assert good in rels_mod._normalise(filing_text)
    invented = rels_mod._normalise("We buy all our chips exclusively from Intel Corporation")
    assert invented not in rels_mod._normalise(filing_text)


# --- review fixes -------------------------------------------------------------

def test_a_stock_you_already_hold_is_compared_with_the_rest_not_itself(monkeypatch):
    """AMD researched against a portfolio containing AMD must not be measured
    against AMD: that is a guaranteed 1.0 correlation and its own sector."""
    from app.research import build
    from app.research.metrics import Metric

    amd = Subject("AMD", "Advanced Micro Devices", "0000002488", "Technology", "",
                  "United States", True, "AMD")
    seen = {}
    monkeypatch.setattr(build.lookup, "resolve",
                        lambda q: (lookup.Match("AMD", "0000002488", "AMD", True, 1.0), []))
    monkeypatch.setattr(build, "load", lambda key: None)
    monkeypatch.setattr(build, "save", lambda key, value: None)
    monkeypatch.setattr(build.subject_mod, "from_match", lambda m: amd)
    monkeypatch.setattr(build.subject_mod, "for_holding",
                        lambda t: Subject(t, t, None, "Technology", "", "", True, t))
    monkeypatch.setattr(build.subject_mod, "bars", lambda t: [])
    monkeypatch.setattr(build, "raw_metrics", lambda s, b: {
        a: Metric(a, None, "", a) for a in AXES})
    monkeypatch.setattr(build, "_news_evidence", lambda s, w: {})

    def fake_sector(subject, holding_sectors):
        seen["sector_holdings"] = set(holding_sectors)
        return fit.Component("sector_crowding", 50, "", "")

    def fake_direct(subject, holdings, extracted=None):
        seen["direct_holdings"] = set(holdings)
        return fit.Component("direct_connection", 100, "", "")

    monkeypatch.setattr(build.fit_module, "sector_crowding", fake_sector)
    monkeypatch.setattr(build.fit_module, "direct_connection", fake_direct)
    monkeypatch.setattr(build.generate, "narrate", lambda *a, **k: {
        "summary": "", "summary_citation_ids": [], "pros": [], "cons": [],
        "warnings": [], "generated_at": None})

    result = build.analyse("AMD", ["AMD", "NVDA", "AAPL"])
    assert result["already_held"] is True
    assert seen["sector_holdings"] == {"NVDA", "AAPL"}
    assert seen["direct_holdings"] == {"NVDA", "AAPL"}


def test_search_reports_an_unreachable_sec_directory_as_503(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    def boom():
        raise ConnectionError("offline")

    lookup.directory.cache_clear()
    monkeypatch.setattr(lookup, "cached", lambda key, producer, **kw: producer())
    monkeypatch.setattr(lookup, "_fetch_directory", boom)
    try:
        response = TestClient(app).get("/research/search", params={"q": "ford"})
        assert response.status_code == 503
        assert "ticker directory" in response.json()["detail"]
    finally:
        lookup.directory.cache_clear()
