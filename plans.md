# Build Plan

A product that helps experienced investors cut through information overload by showing what matters to *their* portfolio, revealing hidden connections between their holdings, and explaining why prices moved.

## App Structure

1. **Sign up and add portfolio**: users enter stock symbols and share counts (or upload a spreadsheet). A prebuilt sample portfolio is available for the demo.
2. **My Portfolio**
   - **What Changed feed**: a short, ranked list of the news and events that actually affect the user's holdings.
   - **Connection Map**: an interactive graph showing how holdings are linked through suppliers, customers, competitors, sectors, and countries, exposing hidden concentration risk.
   - **Story Mode**: opens when the user taps any stock. Shows its price chart with each major move labeled with its cause.
3. **Research a New Investment**
   - **Shape comparison**: the new company's profile (growth, stability, profitability, debt, risk) drawn as a radar shape and overlaid on the user's current holdings.
   - **Map placement**: shows where the new company would connect to the user's existing holdings.
   - Framed as "How would this fit your portfolio?", not "buy or don't buy."

## Demo Story

The user logs in with a sample portfolio and sees an alert about a chip supplier. They open the Connection Map and discover three of their stocks depend on that supplier. They tap one to see its story and understand a recent drop. Then they research a new company and see whether it adds something new or doubles down on risk they already carry.

---

## Step 1: Lock Scope and Demo Story (first hour)

- [ ] Write the final demo script
- [ ] Pick a fixed list of 30–50 supported companies (a naturally connected cluster such as big tech + semiconductors, plus a few from other sectors)
- [ ] Build the sample demo portfolio from that list

## Step 2: Choose Data Sources (time-box to 1–2 hours)

| Data needed | Used for | Candidate sources |
|---|---|---|
| Historical stock prices | Story Mode charts | yfinance (unofficial, cache everything), Finnhub, Financial Modeling Prep |
| Company fundamentals (revenue growth, margins, debt) | Shape comparison | yfinance, Financial Modeling Prep |
| Company news | What Changed feed, Story Mode labels | Finnhub company-news endpoint |
| Annual filings (10-K) | Connection Map relationships | SEC EDGAR (free, official) |

- [ ] Confirm current free-tier limits for each source
- [ ] Get API keys

## Step 3: Data Pipeline and Knowledge Graph (foundation)

- [ ] Fetch and store prices, fundamentals, and news for all supported companies
- [ ] Pull 10-Ks from SEC EDGAR
- [ ] Use an LLM to extract relationships (supplies, buys from, competes with, operates in)
- [ ] Load companies, sectors, countries, and relationships into Neo4j (AuraDB free tier)
- [ ] Spot-check extracted relationships for accuracy
- [ ] Precompute everything: the demo must not depend on live API calls

## Step 4: Backend and Frontend Skeleton (in parallel)

**Backend (FastAPI)**
- [ ] `POST /portfolio`: save a user's portfolio
- [ ] `GET /feed`: ranked What Changed items
- [ ] `GET /graph`: connection graph for a portfolio
- [ ] `GET /story/{symbol}`: price history with labeled events
- [ ] `GET /research/{symbol}`: shape data and map placement for a new company

**Frontend**
- [ ] App shell with navigation (My Portfolio / Research)
- [ ] Screens built with fake data first, then swapped to real endpoints

## Step 5: Features in Priority Order

Cut from the bottom if time runs short.

1. - [ ] **Portfolio entry**: form plus sample portfolio
2. - [ ] **Connection Map**: graph visualization (react-force-graph or Cytoscape.js)
3. - [ ] **Story Mode**: chart with markers on big moves (TradingView Lightweight Charts), each labeled by an LLM summary of that day's news
4. - [ ] **What Changed feed**: rank news by relevance (owned company > connected company > same sector)
5. - [ ] **Research a New Investment**: shape comparison and map placement
6. - [ ] **Natural-language questions**: GraphRAG over the knowledge graph (e.g., "What do I own that depends on TSMC?")

## Step 6: Polish and Rehearse (last few hours)

- [ ] Feature freeze
- [ ] Fix bugs and clean up visuals
- [ ] Run the demo script end to end several times
- [ ] Record a backup demo video

---

## Team Roles

| Role | Owns |
|---|---|
| Data | Steps 2–3: data sources, pipeline, LLM extraction, Neo4j |
| Backend | API endpoints, feed-ranking logic |
| Frontend | Screens, graph visualization, charts |

## Out of Scope

- What-if / scenario simulator
- Live brokerage account linking
- Buy/sell recommendations
- Coverage beyond the fixed company list