# Shellhacks backend

One FastAPI service for the frontend. Story Mode serves precomputed stories from
`data/cache/`, so it keeps working without Snowflake. The `/graph` routes read
Snowflake live. Credentials live only in `.env` on the machine running the API.

## First-time setup

macOS / Linux, from the project root:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r backend/requirements.txt
cp .env.example .env    # then fill in the values
```

Windows (PowerShell), from the project root:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r backend/requirements.txt
Copy-Item .env.example .env
```

Settings are read from `backend/.env` first, then the project-root `.env`.
Keeping everything in the root `.env` is simplest. `backend/.env.example`
lists every backend setting.

Snowflake needs either:
- `keypair`: the path to the private key belonging to `SHELLHACKS_APP`, or
- `pat`: a Snowflake programmatic access token.

The private key or token never belongs in GitHub. The required role and grants
are in `snowflake/service_access_setup.sql`. The account identifier for an AWS
US East account is `<locator>.us-east-1`, with no `.aws` suffix.

## Run the API

From the `backend` folder:
```bash
../.venv/bin/uvicorn app.main:app --reload
```
Then open `http://127.0.0.1:8000/docs` for the interactive API page.

## Endpoints

| Endpoint | Reads | Returns |
|---|---|---|
| `GET /health` | nothing | Liveness; never touches Snowflake |
| `GET /health/snowflake` | Snowflake | Confirms the Snowflake connection |
| `GET /universe` | graph export | The supported companies with their graph connections |
| `GET /feed?holdings=AAPL,NVDA` | feed cache | What Changed: last week's news events (precomputed by `scripts.build_feed`, Gemini-summarised with verified citations) that touch the portfolio, ranked your holding → connected company → same sector; each lists the holdings it reaches (from the graph) and its sources. `tier=1..3` filters |
| `GET /quotes?symbols=AAPL,NVDA` | story cache | Last close, daily change, 1W/1M/3M/6M returns, 6-month range, volume vs 30-day average, 30-day sparkline; empty `symbols` = all companies |
| `GET /story/{symbol}` | story cache | Price series and cited explanations of big moves |
| `GET /story/{symbol}/citation/{id}` | story cache | One evidence row for the drill-down panel |
| `GET /graph/summary` | Snowflake | Row counts of the graph tables |
| `GET /graph/{ticker}/connections` | Snowflake | Companies linked to a ticker, with `role`: supplier, customer, or competitor |
| `GET /portfolio/xray?holdings=AAPL,NVDA` | graph export | Dependencies (suppliers, countries) ranked by how many holdings share them. Headquarters left out unless `include_headquarters=true` |
| `GET /portfolio/map?holdings=...` | graph export | `nodes` and `links` for the holdings and everything one step away; `include_countries`, `include_competitors` toggles |
| `GET /portfolio/impact?company=TSM&holdings=...` | graph export | Holdings touched by news about a company: `customer`, `supplier`, `indirect_customer` (one more supply-chain step), or `competitor`, each with the path and evidence |

Portfolio endpoints take `holdings` comma-separated or repeated. Tickers outside
the universe come back in `unsupported` instead of failing the request. They
read the graph export in `data/exports/`, not Neo4j, so they need no live
connection; restart the API after re-exporting the graph.

The feed and research endpoints will be added once their Snowflake tables are
populated. See `data_sources.md` for Story Mode's sources and citation rules,
and `snowflake/schema_contract.sql` for the table definitions.

## Refresh the data

Everything the app serves is precomputed. To bring it up to date (before a demo, or from a scheduled job):
```bash
../.venv/bin/python -m scripts.refresh                 # stories (prices, news) + What Changed events
../.venv/bin/python -m scripts.refresh --snowflake     # ...and load everything into Snowflake
../.venv/bin/python -m scripts.refresh --skip-stories  # just What Changed (about 3 minutes)
```
It prints how fresh the data was before and after. Commit `data/cache/story_*.json` and `data/cache/feed_events.json` afterwards.

## Load data into Snowflake

From the `backend` folder, after building the stories (`python -m scripts.build_story_cache`):
```bash
../.venv/bin/python -m scripts.load_snowflake                    # stories, prices, news for all five
../.venv/bin/python -m scripts.load_snowflake stories NVDA       # one dataset, one company
```
Safe to re-run. Stories are replaced per company in one transaction (`STORIES`,
`STORY_EVENTS`, `STORY_EVIDENCE`); prices and news are upserted into `PRICES`
and `NEWS`, so news builds up history beyond Finnhub's few-day free window.
`PRICE_HISTORY` is a view over `PRICES` and needs no loading.

To see every source behind one story event:
```sql
SELECT ev.KIND, ev.TITLE, ev.URL
FROM STORY_EVENTS e, LATERAL FLATTEN(input => e.CITATION_IDS) c
JOIN STORY_EVIDENCE ev ON ev.EVIDENCE_ID = c.value::VARCHAR
WHERE e.EVENT_ID = 'NVDA_2026-08-27';
```

## Tests

From the `backend` folder:
```bash
../.venv/bin/python -m pytest tests
```
