-- Knowledge graph tables for Snowflake.
-- Source files: graph_edges.csv and graph_companies.csv (made by `python -m kg.export_edges`).
-- Change the database/schema names below to match your setup.

USE DATABASE SHELLHACKS;
USE SCHEMA PUBLIC;

-- One row per relationship in the graph.
--   relationship: SUPPLIES (from = supplier, to = customer)
--                 COMPETES_WITH (stored once; check both columns when filtering)
--                 IN_SECTOR (to = sector), OPERATES_IN (to = country, kind says how)
--   from_id / to_id: ticker for companies, name for sectors and countries.
--   source: 10-K / 20-F (from a filing), manual (hand-added, see note), config (from companies.py)
CREATE OR REPLACE TABLE GRAPH_EDGES (
    from_id      VARCHAR,
    from_name    VARCHAR,
    from_type    VARCHAR,   -- Company
    relationship VARCHAR,
    to_id        VARCHAR,
    to_name      VARCHAR,
    to_type      VARCHAR,   -- Company, Sector, or Country
    kind         VARCHAR,   -- OPERATES_IN only: headquarters, manufacturing, major_market
    detail       VARCHAR,   -- e.g. 'wafer foundry'
    source       VARCHAR,
    reported_by  VARCHAR,   -- ticker whose filing stated it
    confidence   VARCHAR,   -- high, medium, low
    evidence     VARCHAR,   -- exact quote from the filing
    filing_url   VARCHAR,
    note         VARCHAR    -- why a manual edge exists
);

-- One row per company in the graph. in_universe = TRUE for our supported list;
-- FALSE for companies that only appear because a filing names them.
CREATE OR REPLACE TABLE GRAPH_COMPANIES (
    ticker       VARCHAR,   -- same tickers as the price/news tables (TSM, not 2330.TW)
    name         VARCHAR,
    in_universe  BOOLEAN,
    cik          NUMBER,
    sector       VARCHAR,
    hq_country   VARCHAR
);

CREATE OR REPLACE FILE FORMAT GRAPH_CSV
    TYPE = CSV
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('')
    ENCODING = 'UTF8';

-- ---------------------------------------------------------------------------
-- Loading the files. Pick ONE option.
--
-- Option A (no command line): in Snowsight, open each table under
--   Data > Databases > SHELLHACKS > PUBLIC > Tables, click "Load Data",
--   upload the matching CSV, and choose the GRAPH_CSV file format.
--
-- Option B (SnowSQL / Snowflake CLI), run from the project folder:
--   PUT file://data/exports/graph_edges.csv @%GRAPH_EDGES OVERWRITE = TRUE;
--   PUT file://data/exports/graph_companies.csv @%GRAPH_COMPANIES OVERWRITE = TRUE;
--   then run the two COPY statements below.
-- ---------------------------------------------------------------------------
COPY INTO GRAPH_EDGES FROM @%GRAPH_EDGES FILE_FORMAT = (FORMAT_NAME = GRAPH_CSV);
COPY INTO GRAPH_COMPANIES FROM @%GRAPH_COMPANIES FILE_FORMAT = (FORMAT_NAME = GRAPH_CSV);

-- Checks: expect 80 edges and 43 companies (5 with in_universe = TRUE).
SELECT relationship, COUNT(*) FROM GRAPH_EDGES GROUP BY relationship ORDER BY relationship;
SELECT in_universe, COUNT(*) FROM GRAPH_COMPANIES GROUP BY in_universe;

-- Example: suppliers shared by more than one holding (the demo's "hidden risk").
SELECT from_name AS supplier, ARRAY_AGG(to_id) AS holdings
FROM GRAPH_EDGES
WHERE relationship = 'SUPPLIES'
  AND to_id IN ('AAPL', 'NVDA', 'AMD', 'TSM', 'MSFT')
GROUP BY from_name
HAVING COUNT(*) > 1;

-- Example for the news feed: every company connected to a holding, and how.
-- Join this to the NEWS table on ticker to rank "connected company" news.
SELECT CASE WHEN from_id = 'NVDA' THEN to_id ELSE from_id END AS connected_ticker,
       relationship, detail
FROM GRAPH_EDGES
WHERE from_type = 'Company' AND to_type = 'Company'
  AND (from_id = 'NVDA' OR to_id = 'NVDA');
