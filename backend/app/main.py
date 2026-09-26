"""FastAPI app for the whole backend.

Story Mode serves precomputed stories from disk, so it keeps working if
Snowflake is unreachable. The /graph and /health/snowflake routes read
Snowflake live. The feed and research endpoints in plans.md land here too.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from snowflake.connector import DictCursor
from snowflake.connector.errors import Error as SnowflakeError

from .connections import connections
from .snowflake_db import get_connection
from .story.build import get_story
from .story.schema import Story
from .universe import COMPANIES, SYMBOLS

app = FastAPI(title="Portfolio Story API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
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
