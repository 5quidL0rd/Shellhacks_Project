"""How a searched company would fit the portfolio the investor already holds.

Answers Product.md's question - "How would this fit your portfolio?" - and
deliberately not "will this go up". Every component measures overlap with what
they own:

  price correlation    does it rise and fall with their holdings
  sector crowding      how much of the portfolio is already that sector
  shared dependencies  the same suppliers and countries, from the graph
  direct connection    does it supply, buy from, or compete with a holding

Since the search box accepts anything, most companies will not be in our
knowledge graph. The two graph components then report "unknown" and are dropped
from the weighting rather than scored as if the absence were good news: not
finding a link is not the same as there being none. The weights left over are
renormalised so the score still spans 0-100 and stays comparable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..portfolio import _graph
from . import relationships as rels
from .subject import Subject, UNKNOWN_SECTOR

# Correlation and sector carry the most weight because they need no graph data,
# so they are the two that are always available.
WEIGHTS = {
    "correlation": 0.35,
    "sector_crowding": 0.30,
    "dependency_overlap": 0.20,
    "direct_connection": 0.15,
}

VERDICTS = (
    (70, "Good diversity", "Adds exposure the portfolio does not already carry."),
    (45, "Some diversification",
     "Adds a little that is new, but overlaps the portfolio in places."),
    (0, "Risky overlap",
     "Largely doubles down on sectors, dependencies, or price behaviour the "
     "portfolio already has."),
)


# What a 0-100 component score means in words. Every component is scored in the
# same direction - higher is less overlap - so one band table covers them all.
BANDS = (
    (80, "Little overlap"),
    (50, "Some overlap"),
    (25, "Notable overlap"),
    (0, "Heavy overlap"),
)

SCALE_EXPLAINER = (
    "Each check scores 0-100, where 100 means this company adds something your "
    "portfolio does not already have and 0 means it repeats what you own."
)


@dataclass
class Component:
    name: str
    score: int | None           # None = could not be measured, excluded from the score
    label: str                  # the numbers, e.g. "Average correlation +0.19"
    detail: str                 # the numbers spelled out
    # One sentence in plain words: what this means for the investor, no figures.
    # Added because the numeric detail alone left people asking "so is 54 good?"
    plain: str = ""
    evidence: list[dict] = field(default_factory=list)

    @property
    def measured(self) -> bool:
        return self.score is not None

    @property
    def band(self) -> str:
        if self.score is None:
            return "Unknown"
        for threshold, label in BANDS:
            if self.score >= threshold:
                return label
        return BANDS[-1][1]


def correlation(a_bars: list[dict], b_bars: list[dict]) -> float | None:
    """Pearson correlation of daily returns on the days both traded."""
    a = {x["date"]: x.get("pct_change") for x in a_bars}
    b = {x["date"]: x.get("pct_change") for x in b_bars}
    pairs = [(a[d], b[d]) for d in sorted(set(a) & set(b))
             if a[d] is not None and b[d] is not None]
    if len(pairs) < 30:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(i * i for i in dx) * sum(j * j for j in dy))
    return round(sum(i * j for i, j in zip(dx, dy)) / den, 3) if den else None


def correlation_fit(subject_bars: list[dict], holding_bars: dict[str, list[dict]]) -> Component:
    """How closely the candidate tracks the holdings.

    This is the component that catches the trap the other three miss: a company
    in an unrelated sector with no shared suppliers can still move in lockstep,
    because it sits downstream of the same demand. Carmakers and chipmakers are
    the standard example.
    """
    measured = [(t, c) for t, bars in holding_bars.items()
                if (c := correlation(subject_bars, bars)) is not None]
    if not measured:
        return Component("correlation", None, "No overlapping price history",
                         "Fewer than 30 trading days overlap with your holdings.",
                         plain="There is not enough shared price history to tell whether "
                               "this moves with your portfolio.")

    average = sum(c for _, c in measured) / len(measured)
    # Map [-1, 1] onto 0-100 so an uncorrelated or inversely correlated company
    # scores well. Divided by 1.5, not 2, because beyond about -0.5 the extra
    # diversification benefit is marginal and the scale should not reward it.
    score = round(max(0.0, min(1.0, (1 - average) / 1.5)) * 100)
    closest = max(measured, key=lambda p: p[1])

    if average > 0.6:
        plain = ("It rises and falls almost in step with what you own, so it would not "
                 "cushion a bad day for your portfolio.")
    elif average > 0.3:
        plain = ("It often moves the same way as your holdings, so it only partly "
                 "spreads your risk.")
    elif average > 0:
        plain = ("It mostly moves on its own. A bad day for your holdings would not "
                 "usually be a bad day for this.")
    else:
        plain = ("It tends to go up when your holdings go down, which softens your "
                 "worst days.")

    return Component(
        "correlation", score, f"Average correlation {average:+.2f}",
        (f"Over the last six months it moved with your holdings at {average:+.2f} on "
         f"average, where +1.00 is perfect lockstep and 0.00 is unrelated. Its closest "
         f"match is {closest[0]} at {closest[1]:+.2f}."),
        plain=plain,
        evidence=[{
            "what": "Pearson correlation of daily returns, per holding",
            "per_holding": dict(measured),
            "average": round(average, 3),
            "source": "Yahoo Finance (daily closes)",
        }],
    )


def sector_crowding(subject: Subject, holding_sectors: dict[str, str]) -> Component:
    """How much of the portfolio already sits in the candidate's sector."""
    if subject.sector == UNKNOWN_SECTOR:
        return Component("sector_crowding", None, "Sector unknown",
                         "No sector classification available for this company.",
                         plain="We could not establish what industry this company is in.")
    if not holding_sectors:
        return Component("sector_crowding", 100, "Nothing held yet",
                         "An empty portfolio cannot be concentrated.",
                         plain="You hold nothing yet, so there is nothing to crowd.")

    same = sorted(t for t, s in holding_sectors.items() if s == subject.sector)
    total = len(holding_sectors)
    share = len(same) / total
    score = round((1 - share) * 100)

    if same:
        detail = (f"{len(same)} of your {total} holdings are already in "
                  f"{subject.sector} ({share * 100:.0f}%): {', '.join(same)}. "
                  f"Adding this would make it {len(same) + 1} of {total + 1} "
                  f"({(len(same) + 1) / (total + 1) * 100:.0f}%).")
    else:
        detail = (f"None of your {total} holdings are in {subject.sector}.")

    if not same:
        plain = (f"{subject.sector} is a part of the economy you own nothing in, so this "
                 "would broaden where your money sits.")
    elif share >= 0.5:
        plain = (f"Most of your portfolio is already in {subject.sector}. Buying this "
                 "would be more of what you have.")
    elif share >= 0.25:
        plain = (f"You already have a fair amount in {subject.sector}, so this adds to "
                 "an area you are not short of.")
    else:
        plain = (f"You have only a little in {subject.sector}, so this would not crowd "
                 "your portfolio much.")

    return Component(
        "sector_crowding", score,
        f"{len(same)} of {total} holdings in {subject.sector}", detail,
        plain=plain,
        evidence=[{
            "what": "Sector of the candidate and each holding",
            "candidate_sector": subject.sector,
            "candidate_industry": subject.industry,
            "holding_sectors": holding_sectors,
            "source": "Yahoo Finance sector classification",
        }],
    )


def _dependencies(node_id: str) -> set[tuple[str, str]]:
    """What a company relies on: its suppliers, and where it operates.

    Headquarters are excluded, as in the X-Ray: "both are headquartered in the
    United States" is not a shared dependency worth warning anyone about.
    """
    edges, _ = _graph()
    deps: set[tuple[str, str]] = set()
    for e in edges:
        if e.rel == "SUPPLIES" and e.to_id == node_id and e.from_id != node_id:
            deps.add(("supplier", e.from_id))
        elif e.rel == "OPERATES_IN" and e.from_id == node_id and e.kind != "headquarters":
            deps.add(("country", e.to_id))
    return deps


def _portfolio_dependency_names(holdings: list[str]) -> set[tuple[str, str]]:
    """The portfolio's dependencies as (kind, name), for comparing with names
    read out of a filing rather than graph node ids."""
    _, companies = _graph()
    out: set[tuple[str, str]] = set()
    for holding in holdings:
        for kind, node_id in _dependencies(holding):
            name = companies.get(node_id, {}).get("name") or node_id
            out.add((kind, name))
    return out


def _same_thing(a: str, b: str) -> bool:
    """Whether two names refer to the same company or country."""
    x, y = rels._squash_name(a), rels._squash_name(b)
    return bool(x) and bool(y) and (x == y or (len(x) > 3 and len(y) > 3
                                               and (x in y or y in x)))


def dependency_overlap(subject: Subject, holdings: list[str],
                       extracted: dict | None = None) -> Component:
    """Share of the candidate's dependencies the portfolio already relies on.

    Two sources. The knowledge graph is used for the companies we cover, whose
    filings were read in full and hand-checked. Everything else reads its own
    annual report on demand - including companies that appear in the graph only
    because somebody else's filing named them, since that gives a thin and
    one-sided view. HPE sits in the graph with a single competitor edge and no
    suppliers, while its own 10-K names AMD and NVIDIA as suppliers outright.
    """
    if not subject.in_universe:
        from_filing = _dependency_overlap_from_filing(subject, holdings, extracted)
        if from_filing.measured or not subject.in_graph:
            return from_filing

    candidate_deps = _dependencies(subject.graph_id)
    if not candidate_deps:
        return Component(
            "dependency_overlap", None, "No dependencies recorded",
            f"{subject.name} is in the graph, but the filings we read name no "
            "suppliers or operating countries for it.",
            plain="Its filings do not name any suppliers or countries, so there is "
                  "nothing to compare against your holdings.",
        )

    portfolio_deps: set[tuple[str, str]] = set()
    for holding in holdings:
        portfolio_deps |= _dependencies(holding)

    shared = candidate_deps & portfolio_deps
    score = round((1 - len(shared) / len(candidate_deps)) * 100)

    _, companies = _graph()

    def name(node_id: str) -> str:
        return companies.get(node_id, {}).get("name") or node_id

    shared_labels = sorted(f"{name(n)} ({kind})" for kind, n in shared)
    new_labels = sorted(f"{name(n)} ({kind})" for kind, n in (candidate_deps - shared))

    detail = (f"Shares {len(shared)} of {len(candidate_deps)} dependencies with your "
              f"portfolio: {', '.join(shared_labels[:5])}."
              if shared else
              f"None of its {len(candidate_deps)} dependencies are behind your holdings.")
    if new_labels:
        detail += f" New exposure: {', '.join(new_labels[:5])}."

    overlap = len(shared) / len(candidate_deps)
    if not shared:
        plain = ("It relies on a different set of suppliers and countries than your "
                 "holdings do, so one disruption is less likely to hit everything at once.")
    elif overlap >= 0.6:
        plain = ("It leans on mostly the same suppliers and countries your holdings "
                 "already depend on. A problem there would hit this and your portfolio "
                 "together.")
    else:
        plain = ("Some of what it depends on already sits behind your holdings, so "
                 "trouble at those suppliers would hit both.")

    return Component(
        "dependency_overlap", score,
        f"{len(shared)} of {len(candidate_deps)} dependencies already held", detail,
        plain=plain,
        evidence=[{"what": "Shared dependencies from the knowledge graph",
                   "shared": shared_labels, "new": new_labels,
                   "source": "SEC filings via the knowledge graph"}],
    )


def _dependency_overlap_from_filing(subject: Subject, holdings: list[str],
                                    extracted: dict | None) -> Component:
    """Dependency overlap for a company outside the graph, from its own filing."""
    if not extracted or not extracted.get("available"):
        reason = rels.summarise(extracted or {})
        return Component(
            "dependency_overlap", None, "Could not read its filings", reason,
            plain=f"{reason} Without that we cannot tell whether it leans on the same "
                  "suppliers or countries your holdings do — unknown, not clear.",
        )

    candidate_deps = rels.dependencies(extracted["relationships"])
    if not candidate_deps:
        return Component(
            "dependency_overlap", None, "No dependencies named in its filing",
            f"Its {extracted['form']} filed {extracted['filing_date']} names no "
            "suppliers or operating countries we could identify.",
            plain="Its annual report does not name the suppliers or countries it relies "
                  "on, so there is nothing to compare against your holdings.",
        )

    portfolio_deps = _portfolio_dependency_names(holdings)
    shared = {dep for dep in candidate_deps
              if any(kind == dep[0] and _same_thing(name, dep[1])
                     for kind, name in portfolio_deps)}
    score = round((1 - len(shared) / len(candidate_deps)) * 100)

    shared_labels = sorted(f"{name} ({kind})" for kind, name in shared)
    new_labels = sorted(f"{name} ({kind})" for kind, name in (candidate_deps - shared))
    detail = (f"Read its {extracted['form']} filed {extracted['filing_date']}. "
              + (f"Shares {len(shared)} of {len(candidate_deps)} named dependencies with "
                 f"your portfolio: {', '.join(shared_labels[:5])}."
                 if shared else
                 f"None of the {len(candidate_deps)} dependencies it names are behind "
                 "your holdings."))
    if new_labels:
        detail += f" New exposure: {', '.join(new_labels[:5])}."

    overlap = len(shared) / len(candidate_deps)
    if not shared:
        plain = ("Its annual report names a different set of suppliers and countries than "
                 "your holdings rely on, so one disruption is less likely to hit "
                 "everything at once.")
    elif overlap >= 0.6:
        plain = ("It leans on mostly the same suppliers and countries your holdings "
                 "already depend on. A problem there would hit this and your portfolio "
                 "together.")
    else:
        plain = ("Some of what it depends on already sits behind your holdings, so "
                 "trouble at those suppliers would hit both.")

    return Component(
        "dependency_overlap", score,
        f"{len(shared)} of {len(candidate_deps)} named dependencies already held",
        detail, plain=plain,
        evidence=[{"what": f"Relationships read from its {extracted['form']}",
                   "shared": shared_labels, "new": new_labels,
                   "filing_url": extracted["url"], "source": "SEC annual report"}],
    )


def direct_connection(subject: Subject, holdings: list[str],
                      extracted: dict | None = None) -> Component:
    """Whether the candidate is already wired to a holding in the graph.

    A supplier of something owned is not new exposure; it is the same risk one
    step upstream. That is the hidden concentration the Connection Map exists to
    reveal, priced into a number.
    """
    if not subject.in_universe:
        from_filing = _direct_connection_from_filing(subject, holdings, extracted)
        from_graph = (_direct_connection_from_graph(subject, holdings)
                      if subject.in_graph else None)
        return _merge_direct(subject, from_filing, from_graph)

    return _direct_connection_from_graph(subject, holdings)


def _direct_connection_from_graph(subject: Subject, holdings: list[str]) -> Component:
    edges, _ = _graph()
    node = subject.graph_id
    held = set(holdings) - {node}
    links: list[dict] = []
    for e in edges:
        if e.from_id == e.to_id:
            continue
        if e.rel == "SUPPLIES" and e.from_id == node and e.to_id in held:
            links.append({"role": "supplies", "holding": e.to_id, "evidence": e.provenance()})
        elif e.rel == "SUPPLIES" and e.to_id == node and e.from_id in held:
            links.append({"role": "buys_from", "holding": e.from_id, "evidence": e.provenance()})
        elif e.rel == "COMPETES_WITH" and node in (e.from_id, e.to_id):
            other = e.to_id if e.from_id == node else e.from_id
            if other in held:
                links.append({"role": "competes_with", "holding": other,
                              "evidence": e.provenance()})

    if not links:
        return Component("direct_connection", 100, "No direct link to any holding",
                         "The filings we have read do not connect it to anything you "
                         "hold as a supplier, customer, or competitor.",
                         plain="It is not a supplier, customer, or rival of anything you "
                               "own, so its fortunes are not tied to your holdings.")

    linked = {link["holding"] for link in links}
    score = max(0, 100 - 25 * len(linked))
    phrasing = {"supplies": "supplies", "buys_from": "buys from",
                "competes_with": "competes with"}
    described = sorted({f"{phrasing[link['role']]} {link['holding']}" for link in links})
    holding_word = "holding" if len(linked) == 1 else "holdings"
    return Component(
        "direct_connection", score, f"Directly linked to {len(linked)} holding(s)",
        f"{subject.ticker} {'; '.join(described)}.",
        plain=(f"It does business directly with {len(linked)} of your {holding_word} "
               f"({', '.join(sorted(linked))}). Buying it would be betting on the same "
               "chain you already own, one link along."),
        evidence=[{"what": "Graph edges to holdings", "links": links,
                   "source": "SEC filings via the knowledge graph"}],
    )


def _merge_direct(subject: Subject, from_filing: Component,
                  from_graph: Component | None) -> Component:
    """Combine what the company says about itself with what the graph recorded.

    Both are real evidence, and neither is complete: a filing is the company's
    own account, while a graph edge came from somebody else naming it. The lower
    score wins, because a link found by either source is a link that exists.
    """
    candidates = [c for c in (from_filing, from_graph) if c and c.measured]
    if not candidates:
        return from_filing
    if len(candidates) == 1:
        return candidates[0]

    worst = min(candidates, key=lambda c: c.score or 0)
    other = next(c for c in candidates if c is not worst)
    if other.score == worst.score:
        return worst
    return Component(
        worst.name, worst.score, worst.label,
        f"{worst.detail} The other source adds: {other.detail}",
        plain=worst.plain,
        evidence=worst.evidence + other.evidence,
    )


def _direct_connection_from_filing(subject: Subject, holdings: list[str],
                                   extracted: dict | None) -> Component:
    """Direct links for a company outside the graph, read from its own filing.

    This is the check that turns "unknown" into an answer for the ~10,400 filers
    the graph does not cover: if a company's own annual report names a holding as
    its supplier, customer or competitor, that is as good a source as the graph.
    """
    if not extracted or not extracted.get("available"):
        reason = rels.summarise(extracted or {})
        return Component(
            "direct_connection", None, "Could not read its filings", reason,
            plain=f"{reason} So we cannot say whether it buys from, sells to, or "
                  "competes with anything you own.",
        )

    hits = rels.match_to_holdings(extracted["relationships"], holdings)
    if not hits:
        return Component(
            "direct_connection", 100, "Its filing names none of your holdings",
            f"Its {extracted['form']} filed {extracted['filing_date']} names "
            f"{len(extracted['relationships'])} relationships, none of them with a "
            "company you hold.",
            plain="We read its annual report and it does not name any company you own as "
                  "a supplier, customer or competitor.",
            evidence=[{"what": f"Relationships read from its {extracted['form']}",
                       "count": len(extracted["relationships"]),
                       "filing_url": extracted["url"], "source": "SEC annual report"}],
        )

    linked = {hit["holding"] for hit in hits}
    score = max(0, 100 - 25 * len(linked))
    role_words = {"SUPPLIER": "buys from", "CUSTOMER": "sells to",
                  "COMPETITOR": "competes with"}
    described = sorted({f"{role_words.get(h['type'], h['type'].lower())} {h['holding']}"
                        for h in hits})
    holding_word = "holding" if len(linked) == 1 else "holdings"
    return Component(
        "direct_connection", score,
        f"Its filing names {len(linked)} of your holdings",
        f"Its own {extracted['form']} states that {subject.ticker} "
        f"{'; '.join(described)}.",
        plain=(f"Its own annual report says it does business directly with "
               f"{len(linked)} of your {holding_word} ({', '.join(sorted(linked))}). "
               "That is exposure you already carry, one step along the chain."),
        evidence=[{"what": "Relationships naming your holdings, quoted from the filing",
                   "links": [{"holding": h["holding"], "type": h["type"],
                              "detail": h.get("detail"), "quote": h["evidence"],
                              "confidence": h["confidence"]} for h in hits],
                   "filing_url": extracted["url"], "source": "SEC annual report"}],
    )


NO_VERDICT = ("Not enough data",
              "None of the overlap checks could be run for this company, so there is "
              "no fit score. Unknown is not the same as no overlap.")


def verdict_for(score: int | None) -> tuple[str, str]:
    if score is None:
        return NO_VERDICT
    for threshold, label, meaning in VERDICTS:
        if score >= threshold:
            return label, meaning
    return VERDICTS[-1][1], VERDICTS[-1][2]


def combine(components: dict[str, Component]) -> tuple[int | None, dict[str, float]]:
    """Weighted score over the components that could be measured.

    Weights are renormalised across whatever was available, so a company missing
    from the graph is still scored 0-100 on the two components that do apply,
    rather than being dragged toward the middle by placeholder values.
    """
    usable = {name: c for name, c in components.items() if c.measured}
    if not usable:
        # Nothing measured is not the worst possible overlap; it is no answer.
        return None, {}
    total_weight = sum(WEIGHTS[name] for name in usable)
    applied = {name: WEIGHTS[name] / total_weight for name in usable}
    score = round(sum(usable[name].score * weight for name, weight in applied.items()))
    return score, applied


def confidence_for(subject: Subject, components: dict[str, Component],
                   metrics: dict) -> tuple[str, str]:
    """How much to trust this result, driven by the data behind it.

    A thin-data candidate can still score well, and the investor deserves to
    know the score rests on less.
    """
    reasons = []
    unmeasured = [n for n, c in components.items() if not c.measured]
    if unmeasured:
        reasons.append(f"{len(unmeasured)} of {len(components)} overlap checks could "
                       f"not be run ({', '.join(n.replace('_', ' ') for n in unmeasured)})")

    vendor = [a for a, m in metrics.items() if m.available and m.basis == "Yahoo Finance"
              and a in ("growth", "profitability", "debt")]
    if vendor:
        reasons.append(f"{', '.join(vendor)} come from vendor ratios, not SEC filings")

    missing = [a for a, m in metrics.items() if not m.available]
    if missing:
        reasons.append(f"no data for {', '.join(missing)}")

    stale = [a for a, m in metrics.items()
             if m.available and (m.stale_days or 0) > 400]
    if stale:
        reasons.append(f"{', '.join(stale)} come from filings over a year old")

    if not reasons:
        return "high", "Sector, price history, graph connections and recent filings all available."
    if len(reasons) == 1:
        return "medium", f"Based on partial data: {reasons[0]}."
    return "low", "Based on limited data: " + "; ".join(reasons) + "."
