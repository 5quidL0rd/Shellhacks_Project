"""Analyse one searched company against the investor's holdings.

The flow is: resolve what they typed, measure the company, measure the overlap
with what they own, then have Gemini write the trade-offs from that evidence and
nothing else.

There is no ranked shortlist of our own companies any more. The question this
feature answers is "I am thinking about buying X - how would it fit?", so it
analyses X and only X.
"""
from __future__ import annotations

from ..cache import load, save
from ..sources import news
from ..universe import COMPANIES
from . import concentration as conc
from . import fit as fit_module
from . import generate
from . import lookup
from . import relationships as rels
from . import subject as subject_mod
from .metrics import AXES, FAVOURABLE, Metric, raw_metrics, rank_within
from .subject import Subject

NEWS_ITEMS = 6


SearchUnavailable = lookup.SearchUnavailable


class NotFound(Exception):
    """Nothing matched the query; `suggestions` are the closest names."""

    def __init__(self, query: str, suggestions: list[dict]):
        super().__init__(f"No public company matched {query!r}")
        self.query = query
        self.suggestions = suggestions


class Ambiguous(Exception):
    """Several companies matched; the caller should ask which."""

    def __init__(self, query: str, options: list[dict]):
        super().__init__(f"{query!r} matched several companies")
        self.query = query
        self.options = options


def search(query: str, limit: int = 8) -> dict:
    """Matches for a typed query, for the search box's dropdown."""
    matches = lookup.search(query, limit)
    return {"query": query, "matches": [m.as_dict() for m in matches]}


def _metric_evidence(subject: Subject, metrics: dict[str, Metric]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for axis, metric in metrics.items():
        if not metric.available:
            continue
        notes = []
        if metric.percentile is not None:
            notes.append(
                f"Ranks {metric.percentile}/100 against this portfolio plus the "
                f"candidate, where 100 is the most favourable end of the axis "
                f"({FAVOURABLE[axis]})."
            )
        if (metric.stale_days or 0) > 400:
            notes.append(f"From a filing {metric.stale_days} days old; this company "
                         "reports annually.")
        if metric.basis == "Yahoo Finance" and axis in ("growth", "profitability", "debt"):
            notes.append("A vendor-computed ratio, not read from a filing.")

        row_id = f"rv_{subject.ticker}_metric_{axis}"
        out[row_id] = {
            "id": row_id, "kind": "metric",
            "title": f"{metric.label}: {metric.value}{metric.unit}",
            "detail": " ".join([metric.explanation, *notes]).strip(),
            "numbers": {
                "value": metric.value, "unit": metric.unit,
                "rank_out_of_100_higher_is_better": metric.percentile,
                "as_of": metric.as_of, "stale_days": metric.stale_days,
            },
            "source": metric.basis or "unknown",
            "url": next((e.get("url") for e in metric.evidence if e.get("url")), None),
            "supporting": metric.evidence,
        }
    return out


def _fit_evidence(subject: Subject, components: dict[str, fit_module.Component],
                  applied: dict[str, float]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, component in components.items():
        row_id = f"rv_{subject.ticker}_fit_{name}"
        out[row_id] = {
            "id": row_id, "kind": "diversification",
            "title": f"{name.replace('_', ' ').title()}: {component.label}",
            "detail": " ".join(filter(None, [component.plain, component.detail])),
            "numbers": {
                "score_0_100": component.score,
                "weight_applied": round(applied.get(name, 0.0), 3),
                "measured": component.measured,
            },
            "source": "Knowledge graph and saved price series",
            "url": None,
            "supporting": component.evidence,
        }
    return out


def _news_evidence(subject: Subject, warnings: list[str]) -> dict[str, dict]:
    """Recent coverage, so a point can cite something the investor can read."""
    try:
        items = news.company_news(subject.ticker, days=14)[:NEWS_ITEMS]
    except Exception as exc:
        warnings.append(f"Recent news unavailable ({exc}).")
        return {}

    out: dict[str, dict] = {}
    for index, item in enumerate(items):
        row_id = f"rv_{subject.ticker}_news_{index}"
        out[row_id] = {
            "id": row_id, "kind": "news", "title": item["headline"],
            "detail": f"Reported by {item['publisher']} on {item['date']}. "
                      + item.get("summary", "")[:400],
            "numbers": {}, "source": f"{item['publisher']} (via Finnhub)",
            "url": item["url"], "supporting": [],
        }
    return out


def _radar(metrics: dict[str, Metric]) -> list[dict]:
    return [{
        "axis": axis, "label": metrics[axis].label, "value": metrics[axis].value,
        "unit": metrics[axis].unit, "score": metrics[axis].percentile,
        "available": metrics[axis].available, "basis": metrics[axis].basis,
        "explanation": metrics[axis].explanation,
        "favourable": FAVOURABLE[axis],
    } for axis in AXES]


# Bump when the analysis changes, so results cached by an older version are
# recomputed instead of served. v2: no-data verdict, held stocks not compared
# with themselves. v3: concentration carries the revenue mix. v4: named
# customers and year-over-year shares.
ANALYSIS_VERSION = 4


def _cache_key(ticker: str, holdings: list[str]) -> str:
    return f"research_v{ANALYSIS_VERSION}_{ticker}_{'-'.join(sorted(holdings)) or 'none'}"


def analyse(query: str, holdings: list[str], refresh: bool = False) -> dict:
    """Resolve `query` and analyse it against `holdings`.

    Raises NotFound or Ambiguous so the caller can ask a better question rather
    than guessing at which company the investor meant.
    """
    match, alternatives = lookup.resolve(query)
    if match is None:
        options = [m.as_dict() for m in alternatives]
        raise (Ambiguous(query, options) if options else NotFound(query, options))

    held = [h for h in holdings if h in COMPANIES]
    # When the investor already owns it, compare it with the rest of the
    # portfolio: comparing a stock with itself (correlation 1.0, its own sector,
    # its own suppliers) reads as heavy overlap that is not there.
    others = [h for h in held if h != match.ticker]
    key = _cache_key(match.ticker, held)
    if not refresh:
        cached = load(key)
        if cached is not None:
            return cached

    warnings: list[str] = []
    subject = subject_mod.from_match(match)
    subject_bars = subject_mod.bars(subject.ticker)
    if not subject_bars:
        warnings.append(f"No price history available for {subject.ticker}; "
                        "correlation, volatility and drawdown cannot be measured.")

    holding_subjects = {t: subject_mod.for_holding(t) for t in others}
    holding_bars = {t: subject_mod.bars(t) for t in others}
    holding_bars = {t: b for t, b in holding_bars.items() if b}

    # Rank the candidate against the holdings plus itself: the comparison the
    # investor actually asked for, rather than an arbitrary reference set.
    metrics = raw_metrics(subject, subject_bars)
    population = {subject.ticker: metrics}
    for ticker, holding in holding_subjects.items():
        population[ticker] = raw_metrics(holding, holding_bars.get(ticker, []))
    # Rank every member against the same population, not just the candidate:
    # the holdings' ranks are what the radar's portfolio overlay is drawn from.
    for member in population.values():
        rank_within(member, population)

    # Read the company's own annual report for anything outside our covered 13.
    # That includes companies the graph already holds as outside nodes: those
    # were recorded from somebody else's filing, so the view is thin and
    # one-sided. HPE sits in the graph with one competitor edge, while its own
    # 10-K names AMD and NVIDIA as suppliers. One Gemini call, cached against
    # the filing, which never changes.
    extracted = None
    if not subject.in_universe:
        try:
            extracted = rels.for_company(subject.cik, subject.name, [subject.name, subject.ticker])
        except Exception as exc:
            warnings.append(f"Could not read {subject.ticker}'s annual report ({exc}).")

    # How much its dependencies matter, not just that they exist. Read from the
    # same filing, so this costs one extra Gemini call over ~1.5% of the text.
    concentration = None
    try:
        found = conc.for_company(subject.cik, subject.name)
        concentration = {"summary": conc.summarise(found),
                         "headline": conc.headline(found),
                         "largest_customer_share": conc.customer_share(found),
                         "revenue_mix": {
                             **conc.revenue_mix(found),
                             "depended_on_by": conc.depended_on_by(
                                 subject.name, exclude_cik=subject.cik or ""),
                             "named_in_filings": conc.named_in_filings(subject.graph_id),
                         },
                         **found}
    except Exception as exc:
        warnings.append(f"Concentration disclosures unavailable ({exc}).")

    components = {
        "correlation": fit_module.correlation_fit(subject_bars, holding_bars),
        "sector_crowding": fit_module.sector_crowding(
            subject, {t: s.sector for t, s in holding_subjects.items()}),
        "dependency_overlap": fit_module.dependency_overlap(subject, others, extracted),
        "direct_connection": fit_module.direct_connection(subject, others, extracted),
    }
    score, applied = fit_module.combine(components)
    verdict, meaning = fit_module.verdict_for(score)
    confidence, confidence_reason = fit_module.confidence_for(subject, components, metrics)

    evidence: dict[str, dict] = {}
    evidence.update(_metric_evidence(subject, metrics))
    evidence.update(_fit_evidence(subject, components, applied))
    evidence.update(_news_evidence(subject, warnings))

    summary = {"fit_score": score, "verdict": verdict, "verdict_meaning": meaning,
               "confidence": confidence}
    try:
        brief = generate.narrate(subject, others, evidence, summary)
    except Exception as exc:
        warnings.append(f"Gemini brief unavailable ({exc}); showing measured data only.")
        brief = {"summary": "", "summary_citation_ids": [], "pros": [], "cons": [],
                 "warnings": [], "generated_at": None}

    result = {
        **subject.as_dict(),
        "already_held": subject.ticker in held,
        "holdings": held,
        "fit_score": score,
        "verdict": verdict,
        "verdict_meaning": meaning,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "components": {
            name: {"score": c.score, "measured": c.measured,
                   "band": c.band, "plain": c.plain,
                   "weight_applied": round(applied.get(name, 0.0), 3),
                   "label": c.label, "detail": c.detail, "evidence": c.evidence}
            for name, c in components.items()
        },
        "score_scale": fit_module.SCALE_EXPLAINER,
        "radar": _radar(metrics),
        "portfolio_radar": _portfolio_radar(population, others),
        "brief": {k: brief[k] for k in
                  ("summary", "summary_citation_ids", "pros", "cons", "generated_at")},
        "evidence": evidence,
        "map_placement": _map_placement(subject, others),
        "filing_read": ({"summary": rels.summarise(extracted), **extracted}
                        if extracted else None),
        "concentration": concentration,
        "alternatives": [m.as_dict() for m in alternatives[1:4]],
        "warnings": warnings + brief["warnings"],
        "disclaimer": (
            "This describes how the company would fit the portfolio's existing "
            "exposures. It is not investment advice and makes no claim about "
            "future returns."
        ),
    }
    save(key, result)
    return result


def _portfolio_radar(population: dict[str, dict[str, Metric]], held: list[str]) -> list[dict]:
    """The holdings' average shape, for drawing the candidate over it.

    An unweighted mean: no share counts are stored, so a position-weighted
    average is not available.
    """
    out = []
    for axis in AXES:
        ranks = [population[t][axis].percentile for t in held
                 if t in population and population[t][axis].percentile is not None]
        out.append({"axis": axis, "label": population[held[0]][axis].label if held else axis,
                    "score": round(sum(ranks) / len(ranks)) if ranks else None,
                    "from_holdings": len(ranks)})
    return out


def _map_placement(subject: Subject, holdings: list[str]) -> dict:
    """Where the candidate would sit on the Connection Map.

    Only meaningful when the graph knows the company; otherwise the frontend
    says so rather than drawing a lone node and implying independence.
    """
    from ..portfolio import portfolio_map

    if not subject.in_graph:
        return {"in_graph": False, "nodes": [], "links": []}

    result = portfolio_map(holdings + [subject.graph_id])
    for node in result["nodes"]:
        node["is_candidate"] = node["id"] == subject.graph_id
    return {"in_graph": True, **result}
