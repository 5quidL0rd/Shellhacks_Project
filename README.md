# Shellhacks Portfolio Intelligence

An app that helps experienced investors see what matters to *their* portfolio: which news affects their holdings, how their holdings are connected through suppliers, customers, and competitors, and why each stock's price moved. The product vision (pitch, features, and the principles every feature follows) is in [Product.md](Product.md); the build steps are in [plans.md](plans.md).

Detailed story and relationship coverage currently spans **13 companies** (listed in [data/companies.json](data/companies.json)). Search also finds SEC-listed companies outside that set, including Tesla (TSLA); those can be tracked with Finnhub quotes, but do not yet have the cited story or graph coverage. A 40-company list is drafted in [company_universe_draft.md](company_universe_draft.md).

*Last updated: September 28, 2026*

---

## Quick start (run it locally)

**No API keys needed for saved views.** The graph export, precomputed stories, and saved prices run from a fresh clone. Current Finnhub quotes and the Cortex assistant need server-side credentials; without them the UI labels saved-price fallbacks or shows a service error.

**You need:** Python 3.10+ and Node 20.19+ (or 22.12+).

**1. Clone and install** (once):
```bash
git clone https://github.com/5quidL0rd/Shellhacks_Project.git
cd Shellhacks_Project
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r backend/requirements.txt
cd frontend && npm install && cd ..
```

**2. Start the API** (terminal 1):
```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload
```

**3. Start the app** (terminal 2):
```bash
cd frontend
npm run dev
```

**4. Open http://localhost:5173.** It starts with a clearly labeled demo portfolio and illustrative share counts. Its displayed value is calculated from Finnhub quotes, not a claim about the visitor's real assets. On **Holdings**, select **Switch to my own portfolio** before entering real positions. Demo and personal share counts are stored separately in this browser.

On Windows, use `.venv\Scripts\pip` and `..\.venv\Scripts\uvicorn` instead of the `.venv/bin/...` paths.

**What needs keys:** selected-stock live quotes require `FINNHUB_API_KEY`; the floating Cortex assistant requires the Snowflake settings and key-pair/PAT authentication in `backend/.env.example`. Research uses `GEMINI_API_KEY`, `SEC_USER_AGENT`, and `FINNHUB_API_KEY`. Set these as server-side environment variables in Vercel. Never put credentials in `VITE_*` variables or commit a `.env` file.

## Where we are

| Area (plans.md) | Status | Notes |
|---|---|---|
| **Knowledge graph** for the Connection Map | Done for 13 companies | Built from SEC filings, loaded in Neo4j AuraDB and mirrored in Snowflake |
| **Story Mode** (why each price move happened) | Done for all 13 companies | 153 explained moves, 113 at high confidence; every citation verified; served by the API |
| **Snowflake** (sponsor track) | Connected and loaded | Graph, stories, prices, and news are in Snowflake |
| **Backend API** (FastAPI) | Working for the current demo | Story, graph, X-Ray, map, feed, research, live quotes, and Cortex chat endpoints work; positions are saved in the browser, not to a user account |
| **Frontend** (React) | Scaffolded and working | Holdings, X-Ray, What Changed, Connection Map, Story Mode, and Research screens on the real API. See [frontend/README.md](frontend/README.md) |
| **What Changed feed** | Working | Last week's news per company, grouped into cited events by Gemini (precomputed), ranked for your portfolio by the knowledge graph |
| **Research a New Investment** | Working | Search any SEC filer; fit score, radar vs your holdings, cited brief. See [research_mode.md](research_mode.md) |
| **Company list of 30–50** (Step 1) | Not started | `companylist.md` is a list of data providers, not companies |

### The demo story already works
The graph shows **TSMC supplying Apple, Nvidia, and AMD**, which is the "three of your stocks depend on one supplier" moment in the demo script. Story Mode then explains each stock's moves in terms of those connections, for example *"TSM dropped 6.98%… shared with customer AMD (-6.89%)."*

---

## How it fits together

```
SEC EDGAR 10-K/20-F ──> Gemini extraction ──> hand-check ──> Neo4j AuraDB (the graph)
                                                                   │ export
                                                                   v
                                                      data/exports/graph_edges.csv
                                                                   │
Yahoo prices ─┐                                                    │ connections
Finnhub news ─┼──> Story Mode (detect moves, gather evidence, ─────┘
SEC filings  ─┤     Gemini writes cited explanations)
FRED sector  ─┘                    │
                                   v
                       backend/data/cache/story_*.json (precomputed)
                                   │                  │
                                   v                  v
                         FastAPI backend       Snowflake (SHELLHACKS_DB.STORY_MODE)
                         (serves the app)      graph, stories, prices, news
```

Two principles run through everything:
- **Every claim cites its source.** Graph edges carry a quote from the filing; story explanations may only cite evidence that was fetched first, and uncited claims are replaced with "cause unverified."
- **Saved analysis remains available when live services fail.** Stories, feed, and graph data are committed snapshots; current quotes and Cortex answers depend on Finnhub and Snowflake respectively. The UI distinguishes those states.

---

## What's in the repo

| Path | What it is | Owner |
|---|---|---|
| `kg/` | Knowledge graph pipeline: fetch filings, extract relationships with Gemini, load Neo4j, export CSVs. See [kg/README.md](kg/README.md) | Knowledge graph |
| `data/extracted/` | Relationships Gemini found in each filing, hand-checked | Knowledge graph |
| `data/manual_edges.json` | Three hand-added connections the filings leave out, each with a reason | Knowledge graph |
| `data/exports/` | The graph as CSVs for Snowflake, plus the SQL to reload them | Knowledge graph |
| `backend/` | FastAPI app: Story Mode, graph endpoints, Snowflake connection and loaders. See [backend/README.md](backend/README.md) | Story Mode / Backend |
| `frontend/` | React app: X-Ray home, Connection Map, Story Mode. See [frontend/README.md](frontend/README.md) | Frontend |
| `backend/data/cache/story_*.json` | The 13 precomputed stories the demo serves | Story Mode |
| `snowflake/` | Table definitions (`schema_contract.sql`), app login setup, and migrations | Snowflake |
| `data_sources.md` | Story Mode's data sources, their free-tier limits, and the citation rules | Story Mode |
| `plans.md` | The product plan and build steps | Team |

---

## Full setup (for rebuilding data)

Only needed to add companies, rebuild stories, or load Snowflake. To just run the app, see [Quick start](#quick-start-run-it-locally).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r backend/requirements.txt
cp .env.example .env        # then fill in the values
```

### Settings (`.env`)
All code reads the project-root `.env`, which git ignores. [.env.example](.env.example) lists the knowledge graph settings, and [backend/.env.example](backend/.env.example) lists the backend's, including Snowflake. Put all of them in the one root `.env`.

| Setting | Where to get it |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | The AuraDB credentials file downloaded when the instance was created |
| `SEC_USER_AGENT` | Your name and a real email; no signup needed |
| `FINNHUB_API_KEY` | finnhub.io (free) |
| `SNOWFLAKE_*` | From the Snowflake owner. The account is `RAC74299.us-east-1` (no `.aws`) |
| `SNOWFLAKE_PRIVATE_KEY_FILE` | Path to the app's private key. Get the key privately from whoever holds it; it lives in `backend/keys/`, which git ignores |

Never commit `.env`, the private key, or any token.

### Common commands
```bash
# Knowledge graph (from the project root)
.venv/bin/python -m kg.load --reset          # rebuild the Neo4j graph from the committed JSON
.venv/bin/python -m kg.export_edges          # refresh the CSVs for Snowflake

# Backend (from backend/)
../.venv/bin/uvicorn app.main:app --reload             # run the API; docs at http://127.0.0.1:8000/docs
../.venv/bin/python -m scripts.refresh                 # refresh stories + What Changed in one step (add --snowflake to also load Snowflake)
../.venv/bin/python -m scripts.build_story_cache       # rebuild the stories (uses Gemini and Finnhub)
../.venv/bin/python -m scripts.build_feed              # rebuild What Changed events (uses Gemini and Finnhub)
../.venv/bin/python -m scripts.load_snowflake          # load graph, stories, prices, and news into Snowflake
../.venv/bin/python -m scripts.build_revenue_mix       # read who pays each company from its filing (uses Gemini)
../.venv/bin/python -m pytest tests                    # run the tests

# Frontend (from frontend/, with the API running)
npm install && npm run dev                             # the app at http://localhost:5173
```

### Keeping the data fresh
Selected-stock and portfolio quotes request Finnhub and refresh every minute; the server keeps each quote for 30 seconds. Enter shares and average cost on Holdings to see live market value, change since the previous close, and unrealized gain/loss; this information stays in the current browser. Historical charts, feed events, filings, and dependency data are saved snapshots. Before a demo that needs fresh historical analysis, run `../.venv/bin/python -m scripts.refresh` from `backend/` (about 8 minutes; needs `GEMINI_API_KEY`, `FINNHUB_API_KEY`, `SEC_USER_AGENT`), then commit the updated `backend/data/cache/story_*.json` and `feed_events.json`.

### API endpoints
| Endpoint | Returns |
|---|---|
| `GET /health` | Liveness, without touching Snowflake |
| `GET /health/snowflake` | Confirms the Snowflake connection |
| `GET /universe` | The supported companies and their graph connections |
| `GET /story/{symbol}` | Price series and cited explanations of each big move |
| `GET /story/{symbol}/citation/{id}` | One evidence row for the drill-down panel |
| `GET /graph/summary` | Graph table row counts in Snowflake |
| `GET /graph/{ticker}/connections` | A company's connections, each with its role (supplier, customer, competitor) |
| `GET /portfolio/xray?holdings=AAPL,NVDA` | What the portfolio depends on (suppliers, countries), ranked by how many holdings share each; the home screen |
| `GET /portfolio/map?holdings=...` | Nodes and links for the Connection Map, shaped for react-force-graph / Cytoscape.js |
| `GET /portfolio/impact?company=TSM&holdings=...` | Which holdings news about a company touches, and how (supply chain, one step further downstream, competitors) |
| `GET /feed?holdings=...` | What Changed: last week's events that touch the portfolio, ranked your holding → connected → same sector, with the holdings each reaches and its sources |
| `GET /quotes` | Last-close price, daily change, period returns, and a 30-day sparkline per company |
| `GET /market/{symbol}` | Selected-stock quote from Finnhub with provider and market timestamp |
| `GET /market?symbols=AAPL,NVDA` | Live quotes for up to 15 supported holdings |
| `POST /chat` | Snowflake Cortex answer grounded in current quotes, dated stories and news, portfolio dependencies, and any entered positions |
| `GET /company/{ticker}/revenue-mix` | Who pays a company: each disclosed customer's share of revenue (unnamed ones stay unnamed) and the rest, from its annual report; plus the supported companies whose filings say they depend on it. Any SEC filer; the 13 are precomputed |

---

## What's done, in detail

### Knowledge graph
- Pulls each company's latest annual report from SEC EDGAR (TSMC files a 20-F, not a 10-K) and keeps the Business and Risk Factors sections.
- Gemini extracts suppliers, customers, competitors, and countries, each with an exact quote. Every quote was confirmed to appear word for word in the filing.
- Graph: 13 supported companies plus 61 outside companies named in the filings, 5 sectors, 14 countries, 194 relationships, 35 of them directly between supported companies. "Customer of" is stored as `SUPPLIES` in the other direction.
- TSMC supplies 7 of the 13 supported companies, and ASML supplies TSMC and Intel.
- Filings often leave key names out (Apple's 10-K names no suppliers; TSMC's 20-F names no customers), so three edges are hand-added in `data/manual_edges.json`, each marked `source: manual` with a reason.

### Story Mode
- Finds each stock's biggest daily moves over 180 days, ranked by how differently it moved from its connected companies.
- Gathers evidence (price, connected-company moves, SEC filings, news, quarterly results, industry data) and has Gemini explain each move citing only that evidence.
- Peers come from the knowledge graph, so explanations name the relationship ("its supplier TSM").
- The saved stories link their explanations to dated evidence; open a citation in the app to inspect its source.

### Snowflake
- A dedicated app login (`SHELLHACKS_APP`) with key-pair authentication and limited permissions.
- Tables: `GRAPH_EDGES` (194), `GRAPH_COMPANIES` (74), `STORIES` (13), `STORY_EVENTS` (153), `STORY_EVIDENCE` (2,215), `PRICES` (1,703), `NEWS` (3,091 and growing). `PRICE_HISTORY` is a view over `PRICES` that adds the daily change and direction.
- Loaders are safe to re-run: stories are replaced per company, and prices and news are updated in place. News builds up history each time it runs.

---

## Current limits and next work

- The supported portfolio and Story Mode universe is 13 companies. Research search reaches more SEC filers, but graph and precomputed stories do not yet cover all of them.
- Finnhub quotes refresh in the browser every minute; this is not an exchange-streaming feed. Historical charts, news events, filing disclosures, and graph relationships have their own saved as-of dates and need an explicit rebuild to refresh.
- Share counts and average costs are optional and stay in this browser's local storage. There is no brokerage connection, account sync, order execution, or personalized investment advice.
- The public Cortex endpoint uses Snowflake credits. Before sustained public traffic, add abuse protection and cost monitoring; after a demo, disable or restrict the endpoint if it is not needed.
- Rehearse the deployed app's quote, story, holdings, and assistant flows, and verify both frontend and API health after each deployment.
