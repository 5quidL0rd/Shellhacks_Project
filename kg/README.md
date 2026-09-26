# Knowledge Graph (Connection Map data)

Builds the Neo4j graph behind the Connection Map from SEC filings.

```
SEC EDGAR --(kg.edgar)--> data/raw/ --(kg.extract, Gemini)--> data/extracted/*.json
                                                                   | hand-check
                                           Neo4j <--(kg.load)-- + data/manual_edges.json
```

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in the values
```

## Run
```bash
.venv/bin/python -m kg.edgar            # download latest 10-K / 20-F for every company (cached)
.venv/bin/python -m kg.extract          # Gemini -> data/extracted/{TICKER}.json (costs API calls)
.venv/bin/python -m kg.load --reset     # wipe and rebuild the graph
.venv/bin/python -m kg.export_edges     # graph -> data/exports/*.csv for Snowflake
```
Each step takes tickers (`python -m kg.extract NVDA`). `data/extracted/` is committed, so teammates can run `kg.load` without calling EDGAR or Gemini.

**Adding a company:** add it to `data/companies.json` (the one list shared with the backend), then run the three steps for its ticker and hand-check the JSON.

## Snowflake export
`kg.export_edges` writes the graph as two CSV tables in `data/exports/`: `GRAPH_EDGES` (one row per relationship) and `GRAPH_COMPANIES` (one row per company). The tables are defined in `snowflake/schema_contract.sql`; After every `kg.load`, re-run the export, then replace the Snowflake tables with one command from the `backend` folder: `../.venv/bin/python -m scripts.load_snowflake graph`. (`data/exports/snowflake_graph_tables.sql` does the same by hand in Snowsight and has example queries.)

## Schema (contract with the backend)

**Nodes**
| Label | Properties |
|---|---|
| `Company` | `ticker` (unique key), `name`, `cik`, `in_universe` |
| `Sector` | `name` |
| `Country` | `name` |

`in_universe: true` marks companies in our supported list. Other companies named in filings (Samsung, Foxconn, ...) have `in_universe: false`, and their `ticker` is a name slug such as `samsung-electronics`.

**Relationships**
| Type | Direction | Notes |
|---|---|---|
| `SUPPLIES` | supplier → customer | There is no `CUSTOMER_OF`: "A is a customer of B" is stored as `(B)-[:SUPPLIES]->(A)` |
| `COMPETES_WITH` | stored once | Always query without direction: `(a)-[:COMPETES_WITH]-(b)` |
| `IN_SECTOR` | Company → Sector | |
| `OPERATES_IN` | Company → Country | `kind`: `headquarters`, `manufacturing`, `major_market` |

**Every relationship has provenance:** `source` (`10-K`, `20-F`, `manual`, `config`), `filing_url`, `evidence` (an exact quote from the filing), `confidence`, `detail` (e.g. "wafer foundry"), `reported_by` (whose filing said it). Manual edges add a `note` explaining why they exist.

**Useful queries**
```cypher
// Everything connected to a portfolio
MATCH (h:Company) WHERE h.ticker IN $tickers
MATCH (h)-[r]-(x) RETURN h, r, x

// Shared suppliers = hidden concentration risk
MATCH (s:Company)-[:SUPPLIES]->(h:Company) WHERE h.ticker IN $tickers
WITH s, collect(h.ticker) AS holdings WHERE size(holdings) > 1
RETURN s.name, holdings
```

## Hand-check notes
Known facts the extraction should reproduce, all confirmed:
- [x] TSMC supplies NVDA and AMD (10-K)
- [x] NVDA and AMD compete (both 10-Ks)
- [x] Samsung supplies NVDA and AMD (10-K)
- [x] AMD supplies Microsoft for Xbox (AMD 10-K)

What the filings leave out (covered in `data/manual_edges.json`):
- Apple's 10-K names no suppliers ("outsourcing partners... in Asia"), and TSMC's 20-F names no customers ("our largest customer"). **TSMC → Apple is added by hand.**
- Nvidia's customers are unnamed ("one direct customer represented 22%"). **Nvidia → Microsoft is added by hand.**
- Microsoft's latest 10-K names no competitors. Apple's 10-K names Windows and Xbox as rival platforms, but by product name, so the extractor missed it. **Apple ↔ Microsoft is added by hand, citing Apple's quote.**

Unnamed mentions ("a single supplier in Asia") stay in the JSON for reference. The loader skips them, except when they give a country, which becomes an `OPERATES_IN` edge. For example, NVDA's "supply from our overseas partners, especially in Taiwan" becomes NVDA → Taiwan (manufacturing).

To fix a bad extraction, edit `data/extracted/{TICKER}.json`: delete the row, or set `is_named: false` and add a `review_note`. Re-running `kg.extract` overwrites these edits.
