-- Migration 001: PRICE_HISTORY becomes a view over PRICES, and Story Mode gets
-- tables that keep every citation.
--
-- Run once in Snowsight with the role that owns SHELLHACKS_DB.STORY_MODE (the
-- app role SHELLHACKS_APP_ROLE cannot create tables). Run the statements in
-- order and stop at the first error.
--
-- Why:
--   * PRICES and PRICE_HISTORY stored the same closing prices twice. Two copies
--     drift apart; one table plus a view that calculates the daily change
--     cannot. The PRICE_HISTORY name and columns are kept, plus DIRECTION.
--   * STORY_EVENTS had one SOURCE_URL and a numeric confidence, but each story
--     beat cites several evidence rows and uses high/medium/low. Saving a story
--     there would drop all but one citation. Stories now use three tables:
--     STORIES (one per company), STORY_EVENTS (one per labeled move), and
--     STORY_EVIDENCE (one per citable fact, with its link).

USE DATABASE SHELLHACKS_DB;
USE SCHEMA STORY_MODE;

-- 1. Safety check. Both tables below are replaced, so this stops the migration
--    if either already holds data. If it raises an error, stop and ask first.
EXECUTE IMMEDIATE $$
DECLARE
  not_empty EXCEPTION (-20001, 'PRICE_HISTORY or STORY_EVENTS has rows. Stop: replacing them would delete data.');
BEGIN
  LET price_rows INTEGER := (SELECT COUNT(*) FROM SHELLHACKS_DB.STORY_MODE.PRICE_HISTORY);
  LET event_rows INTEGER := (SELECT COUNT(*) FROM SHELLHACKS_DB.STORY_MODE.STORY_EVENTS);
  IF (price_rows + event_rows > 0) THEN
    RAISE not_empty;
  END IF;
  RETURN 'Both tables are empty; safe to continue.';
END;
$$;

-- 2. PRICE_HISTORY: replace the table with a view calculated from PRICES.
DROP TABLE IF EXISTS PRICE_HISTORY;

CREATE OR REPLACE VIEW PRICE_HISTORY AS
SELECT
    TICKER AS SYMBOL,
    DATE   AS TRADE_DATE,
    CLOSE  AS CLOSE_PRICE,
    ROUND((CLOSE / LAG(CLOSE) OVER (PARTITION BY TICKER ORDER BY DATE) - 1) * 100, 4)
           AS DAILY_RETURN_PCT,
    CASE
        WHEN CLOSE > LAG(CLOSE) OVER (PARTITION BY TICKER ORDER BY DATE) THEN 'up'
        WHEN CLOSE < LAG(CLOSE) OVER (PARTITION BY TICKER ORDER BY DATE) THEN 'down'
        WHEN LAG(CLOSE) OVER (PARTITION BY TICKER ORDER BY DATE) IS NULL THEN NULL
        ELSE 'flat'
    END    AS DIRECTION,
    SOURCE AS DATA_SOURCE,
    INGESTED_AT
FROM PRICES;

-- 3. Story tables.
CREATE TABLE IF NOT EXISTS STORIES (
    STORY_ID          VARCHAR NOT NULL,      -- the symbol, e.g. 'NVDA'
    SYMBOL            VARCHAR(16) NOT NULL,
    COMPANY_NAME      VARCHAR,
    GENERATED_AT      TIMESTAMP_TZ,
    ARC               VARCHAR,               -- paragraph summarizing the whole period
    ARC_CITATION_IDS  ARRAY,                 -- evidence ids the arc cites
    WARNINGS          ARRAY,
    INGESTED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (STORY_ID)
);

-- Replaces the old STORY_EVENTS (empty, checked in step 1). COPY GRANTS keeps
-- the app role's existing privileges on it.
CREATE OR REPLACE TABLE STORY_EVENTS COPY GRANTS (
    EVENT_ID        VARCHAR NOT NULL,        -- e.g. 'NVDA_2026-08-27'
    STORY_ID        VARCHAR NOT NULL,
    SYMBOL          VARCHAR(16) NOT NULL,
    EVENT_DATE      DATE NOT NULL,
    EVENT_TYPE      VARCHAR(50) NOT NULL DEFAULT 'price_move',
    PRICE_MOVE_PCT  NUMBER(10,4),
    CLOSE_PRICE     NUMBER(18,4),
    DIRECTION       VARCHAR(4),              -- 'up' or 'down'
    HEADLINE        VARCHAR NOT NULL,        -- chart label, under ~60 characters
    SUMMARY         VARCHAR NOT NULL,        -- the 2-3 sentence explanation
    CONFIDENCE      VARCHAR(6),              -- 'high', 'medium', 'low'
    CITATION_IDS    ARRAY,                   -- every evidence id this event cites
    INGESTED_AT     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (EVENT_ID)
);

CREATE TABLE IF NOT EXISTS STORY_EVIDENCE (
    EVIDENCE_ID  VARCHAR NOT NULL,           -- e.g. 'ev_NVDA_20260827_price'
    STORY_ID     VARCHAR NOT NULL,
    SYMBOL       VARCHAR(16) NOT NULL,
    KIND         VARCHAR(20),                -- price, peer_move, filing, news, fundamental, sector
    TITLE        VARCHAR,
    DETAIL       VARCHAR,
    SOURCE       VARCHAR,                    -- e.g. 'SEC EDGAR'
    URL          VARCHAR,                    -- where the investor lands on click
    OCCURRED_ON  DATE,
    NUMBERS      VARIANT,                    -- figures, e.g. {"pct_change": 8.74}
    INGESTED_AT  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (EVIDENCE_ID)
);

-- 4. Grants. Future-table grants cover new tables but not views, so the view
--    needs its own. The table grants repeat the future grants to be explicit.
GRANT SELECT ON VIEW PRICE_HISTORY TO ROLE SHELLHACKS_APP_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE STORIES        TO ROLE SHELLHACKS_APP_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE STORY_EVENTS   TO ROLE SHELLHACKS_APP_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE STORY_EVIDENCE TO ROLE SHELLHACKS_APP_ROLE;

-- 5. Checks. Expect PRICE_HISTORY listed as a VIEW, and the three story tables.
SHOW VIEWS LIKE 'PRICE_HISTORY';
SHOW TABLES LIKE 'STOR%';
