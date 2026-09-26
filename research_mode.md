# Research a New Investment

Product.md feature 5. Search any public company, see how it would fit the portfolio you already hold.

Answers **"How would this fit your portfolio?"** — never "buy or don't buy." The ranking measures overlap with what you own, not expected return, and the prompt forbids buy/sell/cheap/expensive language outright. That is both the product principle (Product.md:71) and the more defensible claim: growth screeners are everywhere, but nothing else tells an investor *three of your holdings depend on the same foundry*.

## Endpoints

| Endpoint | Cost |
|---|---|
| `GET /research/search?q=ford` | Free. SEC's ticker directory, cached daily. |
| `GET /research/analyze?q=HPE&holdings=AAPL,NVDA,...` | First call per company: one filing download + two Gemini calls. Cached after. |

Search accepts tickers, names and brands (`alienware` → DELL, `bmw` → BAMXF, `supermicro` → SMCI). Genuinely ambiguous queries return **409** with the options rather than guessing — `berkshire hathaway` could be BRK-A or BRK-B. Nothing matching returns **404** with the closest names.

## The fit score

```
fit = 0.35 × correlation         Pearson on daily returns vs each holding
    + 0.30 × sector_crowding     how much of the portfolio is already that sector
    + 0.20 × dependency_overlap  shared suppliers and countries
    + 0.15 × direct_connection   does it supply / buy from / compete with a holding
```

Each check scores **0–100 where 100 means it adds something you don't already have**, and carries a word (`Little` / `Some` / `Notable` / `Heavy overlap`) plus a plain-English sentence, because a bare "54/100" told people nothing. Verdicts: **≥70 Good diversity**, **≥45 Some diversification**, **<45 Risky overlap**.

**A check that could not be run is excluded and the weights renormalised** — never scored as "no overlap." Absence of evidence is not evidence of absence, and treating it as clean would systematically flatter every unknown company. **If no check can be run at all, there is no score** (`fit_score: null`, verdict **Not enough data**) rather than a 0 that would read as heavy overlap.

**Researching a stock you already hold** compares it with the rest of the portfolio, not with itself (`already_held: true`); otherwise its own sector and a 1.0 self-correlation read as overlap.

`correlation` is the check that catches what the others miss: a company in an unrelated sector can still move in lockstep, and a different sector label does not cancel that out.

## Reading the searched company's filing on demand

The knowledge graph covers 13 companies; search accepts ~10,400. Without this, the two supply-chain checks reported "unknown" for almost everything anyone would actually research — the one question the product exists to answer.

So for any company outside our covered 13, [backend/app/research/relationships.py](backend/app/research/relationships.py) runs the `kg/` idea live:

1. Fetch its latest 10-K/20-F.
2. Cut ~600k chars to ~40k, keeping only sentences that name a company we care about or use supply-chain/geography language ([filing.py](backend/app/sources/filing.py)).
3. One Gemini call extracts suppliers, customers, competitors and countries, each with a quote.
4. **Every quote is checked against the filing text and dropped if it does not appear.** The model is reading a real document, so a fabricated quote is the failure mode, and it is cheap to check exactly.
5. Counterparties are matched to holdings on squashed names, so "Apple" and "Apple Inc." both reach AAPL.

Cached against the filing, which never changes.

**The graph only wins for our 13 hand-checked companies.** Companies in the graph as *outside* nodes were recorded from somebody else's filing, so the view is thin and one-sided: HPE sat there with a single competitor edge while its own 10-K names AMD and NVIDIA as suppliers. Outside nodes read their own filing; where both sources have something, the links are merged and the lower score wins.

### What it produces

HPE against `AAPL, NVDA, AMD, MSFT, QCOM, CRUS, AMZN`:

```
direct_connection    ····················   0   Heavy overlap
    Its own 10-K states that HPE buys from AMD; buys from NVDA;
    competes with AMZN; competes with MSFT; competes with NVDA.

dependency_overlap   ███████████·········  56   Some overlap
    Shares 8 of 18 named dependencies: China, India,
    NVIDIA (supplier), Singapore, South Korea.
```

4 of 4 checks measured, high confidence, fit 34 — **Risky overlap**. That is the demo: real hidden overlap, found live, in the company's own words.

| | fit | checks | named in its filing |
|---|---|---|---|
| Coca-Cola | 92 | 4/4 high | 11 (PepsiCo, Nestlé, KDP) |
| Waste Management | 84 | 4/4 high | 0 |
| Ford | 73 | 4/4 high | 1 |
| BMW | 73 | **2/4 low** | files no annual report |
| **HPE** | **34** | 4/4 high | **39** |
| TSMC | 23 | 4/4 | in the graph |

## The radar

Five axes, ranked as percentiles **against your holdings plus this company** — the comparison you asked for, not an arbitrary reference set. Ranks always point so 100 is the favourable end, and plotted values are ranks not raw figures, since a chart mixing percent-growth with a debt multiple would be meaningless.

| Axis | Measure | From |
|---|---|---|
| growth | Revenue YoY | SEC XBRL, else Yahoo |
| profitability | Net profit margin | SEC XBRL, else Yahoo |
| debt | Liabilities ÷ equity | SEC XBRL, else Yahoo |
| stability | Annualised volatility | Daily closes |
| risk | Maximum drawdown | Daily closes |

Vendor ratios are labelled `est.` in the UI and called out in the brief, and they drop confidence. BMW needs them: its SEC presence is an ADR registration whose `companyfacts` 404s.

## Citation contract

Same as Story Mode. Gemini sees evidence rows with ids, titles and numbers — **never URLs**. Every pro and con must cite ids; unknown ids are dropped; an item left with none is deleted rather than shown.

## EDGAR problems solved along the way

1. **`companyconcept` is unreliable.** For Ford it answers 200 with concept metadata and *zero* `units` for `Assets`, `StockholdersEquity` and its current revenue tag, while `companyfacts` has all three. Switched to `companyfacts`: one request per company instead of ten, and complete.
2. **Filers change tags.** NVIDIA's old quarters are under `RevenueFromContractWithCustomerExcludingAssessedTax` and current ones under `Revenues`; Ford went the other way. Taking the first tag with any data gave NVIDIA a revenue figure from **2020**. Every candidate is now evaluated and the freshest wins.
3. **Foreign filers use IFRS.** TSMC and ASML file 20-Fs, so they have no `us-gaap` facts at all. Each metric tries `(taxonomy, tag)` pairs. TSMC's figures come back annual and ~634 days stale, surfaced as `stale_days`.
4. **Not everyone tags total liabilities.** AMD and Intel report only current and non-current; Ford uses `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`. Reconstructed from assets − equity, or current + non-current, marked `derived`.

## Known limits

- **First search of a new company takes 20–60s** — a filing download plus two Gemini calls, and Yahoo profile lookups. Cached after, on that machine only (`backend/data/cache/` is not committed). Pre-warm before demoing. Research needs `GEMINI_API_KEY`, `SEC_USER_AGENT`, and `FINNHUB_API_KEY`.
- **If SEC's ticker directory cannot be downloaded**, search returns **503** with the reason instead of failing.
- **Cached analyses carry a version** (`ANALYSIS_VERSION` in `research/build.py`); bump it when the analysis changes so old results are recomputed.
- **`backend/data/cache/` is now ~144MB** (filing texts). Gitignored except `story_*.json`.
- **Not drawn on the Connection Map** unless the company is already a graph node. The extracted relationships are shown as quotes instead.
- **No position weighting.** The portfolio radar average and sector shares are unweighted; no share counts are stored.
- **Passage filtering can miss things.** It keeps ~6% of a filing. Ford's 10-K mentions "semiconductor" zero times, so no chip-supplier link exists to find — but a relationship stated only in language the filter does not match would be missed.

## Try it

```bash
cd backend
../.venv/bin/python -m scripts.show_research HPE --holdings AAPL,NVDA,AMD,MSFT,QCOM,CRUS,AMZN
../.venv/bin/python -m scripts.show_research --search "coca" --holdings AAPL
```
