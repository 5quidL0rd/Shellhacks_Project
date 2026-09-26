"""FastAPI endpoints used by the Shellhacks frontend."""

from fastapi import FastAPI, HTTPException
from snowflake.connector import DictCursor

from backend.snowflake_db import get_connection


app = FastAPI(title="Shellhacks API", version="0.1.0")


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    """Run a parameterized read-only query and return JSON-friendly rows."""
    try:
        with get_connection() as connection:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/health")
def health():
    """Confirms that the API can reach the configured Snowflake account."""
    rows = fetch_all("SELECT CURRENT_DATABASE() AS database, CURRENT_SCHEMA() AS schema")
    return {"status": "ok", **rows[0]}


@app.get("/graph/summary")
def graph_summary():
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
def graph_connections(ticker: str):
    """Return every company relationship touching one stock ticker.

    This is useful for feed ranking. The interactive visual map should query
    Neo4j directly through its own backend route once that route is added.
    """
    ticker = ticker.upper()
    return fetch_all(
        """
        SELECT
            CASE WHEN from_id = %s THEN to_id ELSE from_id END AS connected_id,
            CASE WHEN from_id = %s THEN to_name ELSE from_name END AS connected_name,
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
        ORDER BY relationship, connected_name
        """,
        (ticker, ticker, ticker, ticker),
    )
