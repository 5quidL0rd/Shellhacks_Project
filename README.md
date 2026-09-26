# Shellhacks Portfolio Intelligence

An app that helps experienced investors see what matters to *their* portfolio: which news affects their holdings, how their holdings are connected through suppliers, customers, and competitors, and why each stock's price moved. The product vision (pitch, features, and the principles every feature follows) is in [Product.md](Product.md); the build steps are in [plans.md](plans.md).

Current scope: **13 companies** (listed in [data/companies.json](data/companies.json)): the original five, Apple, Nvidia, AMD, TSMC, and Microsoft, plus a pilot of eight: Intel, Micron, Broadcom, Qualcomm, ASML, Cirrus Logic, Amazon, and Alphabet. A 40-company list is drafted in [company_universe_draft.md](company_universe_draft.md).

*Last updated: September 26, 2026*

---

## Where we are

| Area (plans.md) | Status | Notes |
|---|---|---|
| **Knowledge graph** for the Connection Map | Done for 13 companies | Built from SEC filings, loaded in Neo4j AuraDB and mirrored in Snowflake |
| **Story Mode** (why each price move happened) | Done for all 13 companies | 153 explained moves, 752 citations, none broken; served by the API |
| **Snowflake** (sponsor track) | Connected and loaded | Graph, stories, prices, and news are in Snowflake |
| **Backend API** (FastAPI) | Partly done | Story, universe, and graph endpoints work; feed and research are not started |
| **Frontend** | Not started | |
| **What Changed feed** | Not started | The data it needs (news and graph) is in place |
| **Research a New Investment** | Not started | Needs financial ratios (`FUNDAMENTALS` is empty) |
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
- **The demo never depends on a live call.** Everything is precomputed and saved to files, so a slow or rate-limited service cannot break the presentation.

---

## What's in the repo

| Path | What it is | Owner |
|---|---|---|
| `kg/` | Knowledge graph pipeline: fetch filings, extract relationships with Gemini, load Neo4j, export CSVs. See [kg/README.md](kg/README.md) | Knowledge graph |
| `data/extracted/` | Relationships Gemini found in each filing, hand-checked | Knowledge graph |
| `data/manual_edges.json` | Three hand-added connections the filings leave out, each with a reason | Knowledge graph |
| `data/exports/` | The graph as CSVs for Snowflake, plus the SQL to reload them | Knowledge graph |
| `backend/` | FastAPI app: Story Mode, graph endpoints, Snowflake connection and loaders. See [backend/README.md](backend/README.md) | Story Mode / Backend |
| `backend/data/cache/story_*.json` | The five precomputed stories the demo serves | Story Mode |
| `snowflake/` | Table definitions (`schema_contract.sql`), app login setup, and migrations | Snowflake |
| `data_sources.md` | Story Mode's data sources, their free-tier limits, and the citation rules | Story Mode |
| `plans.md` | The product plan and build steps | Team |

---

## Getting started

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
../.venv/bin/python -m scripts.build_story_cache       # rebuild the five stories (uses Gemini)
../.venv/bin/python -m scripts.load_snowflake          # load stories, prices, and news into Snowflake
../.venv/bin/python -m pytest tests                    # run the tests
```

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
- All 294 citations across the five stories point to real evidence.

### Snowflake
- A dedicated app login (`SHELLHACKS_APP`) with key-pair authentication and limited permissions.
- Tables: `GRAPH_EDGES` (194), `GRAPH_COMPANIES` (74), `STORIES` (5), `STORY_EVENTS` (57), `STORY_EVIDENCE` (282), `PRICES` (655), `NEWS` (1,236). `PRICE_HISTORY` is a view over `PRICES` that adds the daily change and direction.
- Loaders are safe to re-run: stories are replaced per company, and prices and news are updated in place. News builds up history each time it runs.

---

## Next steps

### High priority (affects the demo)
1. **Lock the company list (Step 1).** Pick the 30–50 companies and build the sample demo portfolio. Everything else scales from this list.
2. **Improve Story Mode explanations.** 108 of 153 moves are low confidence because they have no news behind them. Finnhub's free tier caps each request at ~250 articles, and Story Mode makes one 180-day request, which for heavily covered companies only reaches back a few days. Requesting news for each move's own dates fixes this (tested: a past week of NVDA news returns ~250 articles from that week). The change is in `news_for_move()` in `backend/app/story/build.py`, then rebuild all stories. This is the biggest risk to the demo's "understand a recent drop" moment.
3. **Start the frontend.** App shell, portfolio entry, Connection Map (react-force-graph or Cytoscape.js), and Story Mode chart (TradingView Lightweight Charts), built against fake data first and then the real endpoints.
4. **Build the What Changed feed.** Rank news by relevance: owned company, then connected company, then same sector. The `NEWS` and `GRAPH_EDGES` tables already hold what the ranking needs.

### Medium priority
5. **Scale the knowledge graph to the full list.** For each company: add it to `data/companies.json`, run the three `kg` commands, hand-check the JSON, re-export, and reload Snowflake.
6. **Fill `FUNDAMENTALS`** with revenue growth, profit margin, debt-to-equity, volatility, and market cap for the radar shape in Research a New Investment.
7. **Tighten one prompt rule.** Gemini sometimes calls a move "shared across the sector" when connected companies moved far less (AMD +9.95% vs peers around +2%). Only call it shared when the moves are similar in size.
8. **Decide on the Snowflake Cortex test.** Cortex could write Story Mode labels inside Snowflake, the strongest angle for the sponsor prize. The Snowflake owner is waiting for an explicit go-ahead since it uses credits.

### Decisions the team still owes
- **The two general-knowledge graph edges** (TSMC supplies Apple; Nvidia supplies Microsoft): keep them, clearly marked as manual, or show only what filings state.
- **Whether the Connection Map shows outside companies** (Samsung, Foxconn, ...) or only our holdings. Recommendation: keep them in the graph and filter on `in_universe` in the query, since outside suppliers are what reveal hidden shared risk.
- **The empty `GRAPH_EDGES_LEGACY_20260926` table** in Snowflake: delete it if the backup is no longer needed.

### Later (plans.md Steps 5–6)
- Natural-language questions over the graph (GraphRAG), e.g. "What do I own that depends on TSMC?"
- Feature freeze, polish, rehearse the demo end to end, and record a backup video.
