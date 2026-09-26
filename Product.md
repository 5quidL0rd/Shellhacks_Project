# Product Vision

> Context document for contributors and AI coding agents. Read this before building features. The build order and task checklist live in [plans.md](plans.md); current progress and next steps are in [README.md](README.md).

## One-Line Pitch

**Other apps show you what you own. We show you what you actually depend on.**

## The Problem

Experienced, self-directed investors hold 15–30 individual stocks and are drowning in information: news, filings, earnings, and price moves spread across many sources. Existing tools explain each stock in isolation, so investors miss risks that come from *connections* between companies. A single problem at one supplier can hit several holdings at once, even when the headline never mentions any of them.

## Target User

- Already invests and picks individual stocks
- Follows the market but lacks time to read everything
- Does **not** want the app to make decisions for them

## Positioning

| Alternative | What it does | How we differ |
|---|---|---|
| Robo-advisors (Betterment, Wealthfront) | Invest *for* you in index funds | We never trade or decide. We help users understand and decide themselves. |
| Brokerage AI (Robinhood Cortex, Public Alpha) | Explain news about the stocks you own, one at a time | We catch news about companies you *don't* own that still affect your holdings, by following connections. We also work with any portfolio, not one broker's accounts. |
| Professional terminals (Bloomberg SPLC, FactSet) | Map company supply chains | Expensive and not built around a personal portfolio. We build the map from free SEC filings and connect it to the user's holdings and today's news. |

## Core Idea: The Portfolio as a Web of Dependencies

A stock is a bet on everything that company depends on: its suppliers, customers, countries of operation, and business themes. We model these relationships as a **knowledge graph** in Neo4j. The graph powers every feature.

**Key design principle:** AI handles messy language (reading filings and news, writing explanations). The graph handles logic (finding what's affected). Risk detection is a deterministic graph query, not an AI guess, so every alert is explainable by showing the exact path on the map.

## Features

### 1. Portfolio X-Ray (home screen)

Instead of a list of tickers, show the user what their portfolio depends on, ranked by how many holdings share each dependency.

Example output:
- TSMC: 5 holdings
- China manufacturing: 4 holdings
- US consumer spending: 6 holdings
- AI chip demand: 3 holdings

This reveals hidden concentration: a portfolio of 15 different stocks may rely heavily on a few shared dependencies.

### 2. What Changed Feed

A short, ranked list of news and events that affect the user's portfolio. Relevance ranking:
1. News about a company the user owns
2. News about a company connected to a holding (supplier, customer, competitor)
3. News about a shared sector or country

Each item states *why* it matters and which holdings it touches.

### 3. Connection Map

Interactive graph of the user's holdings and their connections. When news hits a node, highlight it and every holding reachable from it. Clicking an alert highlights the path that triggered it.

### 4. Story Mode

Opens when the user taps any stock. Shows a price chart with markers on major moves, each labeled with a short, cited explanation of the cause.

Each explanation is written by an LLM from evidence gathered first: the price move itself, how connected companies (suppliers, customers, competitors from the graph) moved the same day, SEC filings near the date, news, quarterly results, and industry data. The LLM may cite only that evidence. When nothing explains a move, it says "cause unverified" instead of guessing. News is requested for each move's own dates, because Finnhub's free tier returns only about 250 articles per request.

### 5. Research a New Investment

Framed as **"How would this fit your portfolio?"**, never "buy / don't buy."

- **Explore the map:** companies to research are the nodes adjacent to what the user already owns (suppliers, customers, competitors of their holdings).
- **Fill the gaps:** for any company the user picks, show whether it shares their biggest dependencies or adds new ones. The app shows the effect on dependencies; it does not propose companies to buy.
- **Shape comparison:** radar chart of the candidate (growth, stability, profitability, debt, risk) overlaid on current holdings.
- **Map placement:** show where the candidate would connect to existing holdings.

### 6. Connected-Company Alerts

News about one company reaches more than its suppliers and customers. When news hits a company, the alert shows every holding it touches and how:
- **Supply chain:** follow `SUPPLIES` edges in both directions. News about a supplier reaches its customers; news about a customer reaches its suppliers.
- **Competitors:** follow `COMPETES_WITH` edges and list them as "also affected: competitor AMD."

The alert states the connection and the evidence behind it. It does not say whether a company will gain or lose, since that would be a trading call; the user draws the conclusion.

Data note: a company's competitors only appear if some filing names them. TSMC's 20-F names none, so TSMC currently has no competitor edges. Covering this needs hand-added edges or a wider company list whose filings name TSMC's rivals.

### 7. Natural-Language Questions (stretch)

GraphRAG over the knowledge graph, e.g., "What do I own that depends on TSMC?" or "What in my portfolio is exposed to China?"

## How Risk Propagation Works

1. **Build the map (AI, offline):** an LLM reads each company's annual report from SEC EDGAR (10-K, or 20-F for foreign filers like TSMC) and extracts relationships as structured JSON (e.g., "TSMC `SUPPLIES` NVDA"), stored with the supporting quote and filing source. Extractions are hand-checked before loading.
2. **Understand the news (AI):** for each article, an LLM identifies the company it concerns and classifies it as positive or negative, with an event type (e.g., supply disruption, lawsuit, earnings miss).
3. **Find affected holdings (graph query, no AI):** traverse from the news company to the user's holdings.
4. **Explain it (AI):** an LLM writes a plain-English alert from the query result.

## Knowledge Graph Schema

Built and loaded for the first five companies, except `Theme`, which is planned. The full contract is in [kg/README.md](kg/README.md).

**Nodes**
- `Company {ticker, name, cik, in_universe}`. `in_universe` is true for supported companies and false for outside companies that filings name (Samsung, Foxconn, ...); those use a name slug such as `samsung-electronics` as their `ticker`.
- `Sector {name}`
- `Country {name}`
- `Theme {name}` *(planned)*: business exposures such as "AI chip demand" or "US consumer spending", extracted from 10-K business and risk sections. Themes must come from a fixed, agreed list; otherwise the LLM produces near-duplicates ("AI demand", "demand for AI") that split the counts the Portfolio X-Ray depends on.

**Relationships**
- `(:Company)-[:SUPPLIES]->(:Company)`: supplier → customer. There is no separate `CUSTOMER_OF`: "A is a customer of B" is stored as `(B)-[:SUPPLIES]->(A)`, so the graph cannot contradict itself.
- `(:Company)-[:COMPETES_WITH]->(:Company)`: stored once; always query without direction.
- `(:Company)-[:IN_SECTOR]->(:Sector)`
- `(:Company)-[:OPERATES_IN {kind}]->(:Country)`: `kind` is `headquarters`, `manufacturing`, or `major_market`.
- `(:Company)-[:EXPOSED_TO]->(:Theme)` *(planned)*

**Relationship properties** (required for explainability): `evidence` (exact quote from the filing), `source` (`10-K`, `20-F`, `manual`, or `config`), `filing_url`, `confidence`, `detail` (e.g. "wafer foundry"), and `reported_by` (whose filing stated it). Hand-added edges have `source: manual` and a `note` explaining why.

The graph is also mirrored to Snowflake as `GRAPH_EDGES` and `GRAPH_COMPANIES`.

### Example Queries

Holdings affected by news about a company, through the supply chain in either direction:

```cypher
MATCH (src:Company {ticker: $news_ticker})-[r:SUPPLIES]-(held:Company)
WHERE held.ticker IN $holdings
RETURN held.ticker, held.name,
       CASE WHEN startNode(r) = src THEN 'customer of ' + src.ticker
            ELSE 'supplier to ' + src.ticker END AS connection,
       r.evidence
```

Portfolio X-Ray (shared dependencies ranked):

```cypher
CALL () {
  MATCH (held:Company)-[:OPERATES_IN|EXPOSED_TO]->(dep)
  WHERE held.ticker IN $holdings
  RETURN held, dep
  UNION
  MATCH (dep:Company)-[:SUPPLIES]->(held:Company)
  WHERE held.ticker IN $holdings
  RETURN held, dep
}
RETURN dep.name AS dependency, count(DISTINCT held) AS holdings
ORDER BY holdings DESC
```

> Dependencies = suppliers (incoming `SUPPLIES`) plus countries and themes (outgoing `OPERATES_IN` / `EXPOSED_TO`). Until themes exist, Neo4j warns that `EXPOSED_TO` is unknown and the query uses suppliers and countries only. On the first five companies it returns United States (5 holdings), China (4), Taiwan (3), and TSMC (3).

Competitors also affected by news about a company (connected-company alerts):

```cypher
MATCH (src:Company {ticker: $news_ticker})-[:COMPETES_WITH]-(rival:Company)
RETURN rival.ticker, rival.name
```

## Data Sources

| Data | Used for | Source |
|---|---|---|
| Annual reports (10-K / 20-F) | Knowledge graph relationships | SEC EDGAR (free) |
| Filings near a price move (8-K, 10-Q) | Story Mode evidence | SEC EDGAR |
| Historical prices | Story Mode, move detection | Yahoo Finance via yfinance |
| Quarterly results (revenue, profit, R&D) | Story Mode context; shape comparison | SEC EDGAR XBRL |
| Company news | Feed, Story Mode, alerts | Finnhub company news (free tier: ~250 newest articles per request) |
| Industry trends | Story Mode context | FRED (St. Louis Fed) |
| Relationship extraction, explanations | Knowledge graph, Story Mode | Google Gemini |

Ratios for the shape comparison (debt-to-equity, volatility, market cap) are not collected yet. Details, free-tier limits, and citation rules are in [data_sources.md](data_sources.md).

## Constraints and Principles

- **Fixed company universe:** support a curated list of 30–50 connected companies (big tech + semiconductors, plus a few other sectors). Do not attempt full-market coverage.
- **Precompute everything:** the demo must not depend on live API calls. Cache all fetched data.
- **Explainability:** every alert and dependency must trace back to a graph path and a filing quote.
- **No financial advice:** never output buy/sell/hold recommendations. Frame everything as understanding and fit.
- **Verify extraction:** LLM-extracted relationships must be spot-checked. A wrong edge makes every downstream alert wrong.

## Out of Scope

- What-if / scenario simulator
- Live brokerage account linking
- Trade execution or buy/sell recommendations
- Coverage beyond the fixed company list

## Tech Stack

- **Graph:** Neo4j (AuraDB free tier)
- **Data warehouse:** Snowflake (hackathon sponsor): stores the graph mirror, stories with their citations, prices, and news. Snowflake Cortex (its built-in AI functions) is not available to the project, so all AI work runs on Gemini.
- **LLM:** Google Gemini for extraction and explanations
- **Backend:** Python, FastAPI; GraphRAG (LangGraph optional)
- **Frontend:** React; react-force-graph or Cytoscape.js for the map; TradingView Lightweight Charts for Story Mode