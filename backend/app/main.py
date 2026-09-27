"""FastAPI app for the whole backend.

Story Mode serves precomputed stories from disk, so it keeps working if
Snowflake is unreachable. The /graph and /health/snowflake routes read
Snowflake live. The feed and research endpoints in plans.md land here too.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
try:
    from snowflake.connector import DictCursor
    from snowflake.connector.errors import Error as SnowflakeError
except ImportError:
    DictCursor = None


    class SnowflakeError(Exception):
        pass

from . import portfolio, quotes
from .feed import rank as feed_rank
from .research import build as research
from .research import concentration as concentration_mod
from .connections import connections
from .snowflake_db import get_connection
from .story.build import get_story
from .story.schema import Story
from .universe import COMPANIES, SYMBOLS

app = FastAPI(title="Portfolio Story API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness only; never touches Snowflake, so it stays green on stage."""
    return {"status": "ok", "universe": list(SYMBOLS)}


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    """Run a parameterized read-only query and return JSON-friendly rows."""
    try:
        with get_connection() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(query, params)
                return [{k.lower(): v for k, v in row.items()} for row in cursor.fetchall()]
    except (RuntimeError, SnowflakeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/health/snowflake")
def health_snowflake() -> dict:
    """Confirms that the API can reach the configured Snowflake account."""
    rows = fetch_all("SELECT CURRENT_DATABASE() AS database, CURRENT_SCHEMA() AS schema")
    return {"status": "ok", **rows[0]}


@app.get("/graph/summary")
def graph_summary() -> dict:
    """Counts the Snowflake mirror of the Neo4j connection graph."""
    rows = fetch_all(
        """
        SELECT
            (SELECT COUNT(*) FROM GRAPH_EDGES) AS edges,
            (SELECT COUNT(*) FROM GRAPH_COMPANIES) AS companies
        """
    )
    return rows[0]


@app.get("/graph/{ticker}/connections")
def graph_connections(ticker: str) -> list[dict]:
    """Every company relationship touching one ticker, from Snowflake.

    `role` is what the connected company is to `ticker`: its supplier, its
    customer, or its competitor. SUPPLIES edges point supplier -> customer,
    so the role depends on which end `ticker` is on.
    """
    ticker = ticker.upper()
    return fetch_all(
        """
        SELECT
            CASE WHEN from_id = %s THEN to_id ELSE from_id END AS connected_id,
            CASE WHEN from_id = %s THEN to_name ELSE from_name END AS connected_name,
            CASE
                WHEN relationship = 'SUPPLIES' AND to_id = %s THEN 'supplier'
                WHEN relationship = 'SUPPLIES' THEN 'customer'
                WHEN relationship = 'COMPETES_WITH' THEN 'competitor'
                ELSE LOWER(relationship)
            END AS role,
            relationship,
            detail,
            source,
            confidence,
            evidence,
            filing_url
        FROM GRAPH_EDGES
        WHERE from_type = 'Company'
          AND to_type = 'Company'
          AND (from_id = %s OR to_id = %s)
        ORDER BY role, connected_name
        """,
        (ticker, ticker, ticker, ticker, ticker),
    )


def _holdings(raw: list[str]) -> tuple[list[str], list[str]]:
    supported, unsupported = portfolio.parse_holdings(raw)
    if not supported:
        raise HTTPException(
            status_code=400,
            detail=f"None of the holdings are supported. Unsupported: {unsupported}. "
                   f"Supported: {list(SYMBOLS)}",
        )
    return supported, unsupported


HOLDINGS = Query(..., description="Tickers, comma-separated or repeated: ?holdings=AAPL,NVDA")


@app.get("/portfolio/xray")
def portfolio_xray(holdings: list[str] = HOLDINGS, include_headquarters: bool = False) -> dict:
    """What the portfolio depends on (suppliers and countries), ranked by how
    many holdings share each dependency. The home screen."""
    supported, unsupported = _holdings(holdings)
    deps = portfolio.xray(supported, include_headquarters)
    return {
        "holdings": supported,
        "unsupported": unsupported,
        "shared_count": sum(d["holding_count"] > 1 for d in deps),
        "dependencies": deps,
    }


@app.get("/portfolio/map")
def portfolio_map(holdings: list[str] = HOLDINGS,
                  include_countries: bool = True,
                  include_competitors: bool = True) -> dict:
    """Nodes and links for the Connection Map: the holdings and everything one
    step away. Shaped for react-force-graph / Cytoscape.js."""
    supported, unsupported = _holdings(holdings)
    return {"holdings": supported, "unsupported": unsupported,
            **portfolio.portfolio_map(supported, include_countries, include_competitors)}


@app.get("/portfolio/impact")
def portfolio_impact(company: str = Query(..., description="Ticker or graph id, e.g. TSM or samsung-electronics"),
                     holdings: list[str] = HOLDINGS) -> dict:
    """Which holdings news about `company` touches, and how: supply chain in
    both directions, one extra step downstream, and competitors."""
    supported, unsupported = _holdings(holdings)
    try:
        result = portfolio.impact(company, supported)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from None
    return {"holdings": supported, "unsupported": unsupported, **result}


@app.get("/feed")
def get_feed(holdings: list[str] = HOLDINGS,
             tier: int | None = Query(default=None, ge=1, le=3,
                                      description="1 your holdings, 2 connected, 3 same sector"),
             limit: int = Query(default=40, ge=1, le=100)) -> dict:
    """What Changed: last week's news events that matter to this portfolio,
    ranked by how directly they touch it. Events are precomputed
    (scripts.build_feed); relevance comes from the knowledge graph."""
    supported, unsupported = _holdings(holdings)
    return {"holdings": supported, "unsupported": unsupported,
            **feed_rank.feed(supported, tier, limit)}


@app.get("/quotes")
def get_quotes(symbols: str = Query(default="", description="Comma-separated; empty = every supported company")) -> dict:
    """Last close, daily change, period returns, range, volume, and a 30-day
    sparkline per company. From saved prices, so never a live call."""
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()] or None
    return quotes.quotes(wanted)


@app.get("/universe")
def universe() -> list[dict]:
    return [
        {
            "symbol": c.symbol, "name": c.name, "sector": c.sector,
            "peers": [link.symbol for link in connections(c.symbol)],
            "connections": [
                {"symbol": link.symbol, "relationship": link.label,
                 "detail": link.detail, "source": link.source}
                for link in connections(c.symbol)
            ],
        }
        for c in COMPANIES.values()
    ]


@app.get("/portfolio/concentration")
def portfolio_concentration(holdings: list[str] = HOLDINGS) -> dict:
    """How concentrated each holding's revenue and supply base is, and where the
    portfolio's own companies depend on each other.

    Read from each holding's latest annual report, with every quote checked
    against the filing. The graph says a dependency exists; this says how much
    it matters.
    """
    supported, unsupported = _holdings(holdings)
    result = concentration_mod.portfolio(supported)
    result["unsupported"] = unsupported
    return result


@app.get("/company/{ticker}/revenue-mix")
def company_revenue_mix(ticker: str) -> dict:
    """Who pays the company: each disclosed customer's share of revenue, plus
    the rest, from its latest annual report. Works for any SEC filer.

    Unnamed customers stay unnamed ("Customer A", "one direct customer"). Also
    lists supported companies whose filings say they depend on this one, which
    is the direction filings quantify: Apple names no supplier shares, but
    Cirrus Logic says Apple is about 91% of its sales.
    """
    try:
        return concentration_mod.for_ticker(ticker)
    except concentration_mod.UnknownCompany:
        raise HTTPException(status_code=404,
                            detail=f"No SEC filer has the ticker '{ticker.upper()}'.") from None
    except research.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception as exc:  # SEC or Gemini unreachable on a first read
        raise HTTPException(status_code=502,
                            detail=f"Could not read {ticker.upper()}'s filing ({exc}).") from None


@app.get("/research/search")
def research_search(q: str = Query(..., min_length=1, description="Ticker, company name, or brand"),
                    limit: int = Query(default=8, ge=1, le=25)) -> dict:
    """Companies matching what the user typed, for the search box.

    Matched against SEC's public ticker directory, so any of the ~10,400 filers
    can be researched, not only the companies we precompute.
    """
    try:
        return research.search(q, limit)
    except research.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/research/analyze")
def research_analyze(q: str = Query(..., min_length=1, description="Ticker or company name"),
                     holdings: list[str] = HOLDINGS,
                     refresh: bool = Query(default=False)) -> dict:
    """How the searched company would fit the portfolio.

    Returns the radar shape, the overlap breakdown, a cited pros-and-cons brief,
    and its placement on the Connection Map when the graph knows it.
    """
    supported, unsupported = _holdings(holdings)
    try:
        result = research.analyse(q, supported, refresh=refresh)
    except research.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except research.Ambiguous as exc:
        raise HTTPException(status_code=409, detail={
            "message": f"'{exc.query}' matched several companies; pick one.",
            "options": exc.options,
        }) from None
    except research.NotFound as exc:
        raise HTTPException(status_code=404, detail={
            "message": f"No public company matched '{exc.query}'.",
            "options": exc.suggestions,
        }) from None
    result["unsupported"] = unsupported
    return result


@app.get("/story/{symbol}", response_model=Story)
def story(symbol: str, refresh: bool = Query(default=False)) -> Story:
    """Price series plus labelled, cited explanations of each major move."""
    try:
        return get_story(symbol, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/story/{symbol}/citation/{citation_id}")
def citation(symbol: str, citation_id: str) -> dict:
    """Backs the drill-down panel: the numbers and the outbound source link."""
    story_obj = get_story(symbol)
    item = story_obj.evidence.get(citation_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No evidence {citation_id}")
    return item.model_dump(mode="json")
