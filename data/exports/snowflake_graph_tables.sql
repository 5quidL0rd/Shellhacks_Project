-- Reload the knowledge graph tables in Snowflake from the CSV exports, by hand.
-- The usual way is one command from backend/: python -m scripts.load_snowflake graph
-- Source files: graph_edges.csv and graph_companies.csv (made by `python -m kg.export_edges`).
--
-- The tables themselves are defined in snowflake/schema_contract.sql; this file
-- only replaces their rows. Run it after re-running kg.load and kg.export_edges.

USE DATABASE SHELLHACKS_DB;
USE SCHEMA STORY_MODE;

-- Column meanings:
--   relationship: SUPPLIES (from = supplier, to = customer)
--                 COMPETES_WITH (stored once; check both columns when filtering)
--                 IN_SECTOR (to = sector), OPERATES_IN (to = country, kind says how)
--   from_id / to_id: ticker for companies, name for sectors and countries.
--   source: 10-K / 20-F (from a filing), manual (hand-added, see note), config (from companies.py)

CREATE FILE FORMAT IF NOT EXISTS GRAPH_CSV
    TYPE = CSV
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('')
    ENCODING = 'UTF8';

CREATE STAGE IF NOT EXISTS GRAPH_STAGE FILE_FORMAT = (FORMAT_NAME = GRAPH_CSV);

-- ---------------------------------------------------------------------------
-- Upload the two CSVs to the stage. Pick ONE option.
--
-- Option A (no command line): in Snowsight, open
--   Data > Databases > SHELLHACKS_DB > STORY_MODE > Stages > GRAPH_STAGE,
--   click "+ Files", and upload graph_edges.csv and graph_companies.csv.
--
-- Option B (SnowSQL / Snowflake CLI), run from the project folder:
--   PUT file://data/exports/graph_edges.csv @GRAPH_STAGE OVERWRITE = TRUE AUTO_COMPRESS = FALSE;
--   PUT file://data/exports/graph_companies.csv @GRAPH_STAGE OVERWRITE = TRUE AUTO_COMPRESS = FALSE;
-- ---------------------------------------------------------------------------

-- Replace the rows. DELETE first so a reload never duplicates them.
BEGIN;
DELETE FROM GRAPH_EDGES;
COPY INTO GRAPH_EDGES FROM @GRAPH_STAGE FILES = ('graph_edges.csv') FORCE = TRUE;
DELETE FROM GRAPH_COMPANIES;
COPY INTO GRAPH_COMPANIES FROM @GRAPH_STAGE FILES = ('graph_companies.csv') FORCE = TRUE;
COMMIT;

-- Checks: row counts should match the CSVs (one row per line, minus the header);
-- in_universe = TRUE should match the number of companies in data/companies.json.
SELECT relationship, COUNT(*) FROM GRAPH_EDGES GROUP BY relationship ORDER BY relationship;
SELECT in_universe, COUNT(*) FROM GRAPH_COMPANIES GROUP BY in_universe;

-- Example: suppliers shared by more than one holding (the demo's "hidden risk").
SELECT from_name AS supplier, ARRAY_AGG(to_id) AS holdings
FROM GRAPH_EDGES
WHERE relationship = 'SUPPLIES'
  AND to_id IN ('AAPL', 'NVDA', 'AMD', 'TSM', 'MSFT')
GROUP BY from_name
HAVING COUNT(*) > 1;
