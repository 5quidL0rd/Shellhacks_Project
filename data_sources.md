# Story Mode: Data Sources & Citation Contract

Scope: the five demo companies — Apple (AAPL), NVIDIA (NVDA), AMD (AMD), TSMC (TSM), Microsoft (MSFT).

Reconciled against `companylist.md` (see §6).

---

## 1. Sources in use

All limits below were checked on 2026-09-26 and verified by actually calling each one (`python -m scripts.check_sources`).

| Source | Feeds | Key? | Free limit | Verified |
|---|---|---|---|---|
| **Yahoo Finance** via `yfinance` | Daily OHLCV for the chart and move detection | No | Unofficial, unpublished | 180 days × 5 symbols, works |
| **SEC EDGAR** submissions | 8-K / 10-Q / 10-K filings near a move date | No | 10 req/sec | 19 material NVDA filings |
| **SEC EDGAR** XBRL `companyconcept` | Revenue, net income, gross profit, operating income, R&D | No | 10 req/sec | All 5 concepts for NVDA |
| **Finnhub** `company-news` | Company news; ~250 newest articles per request | Yes | 60 req/min | 248 NVDA articles |
| **FRED** (St. Louis Fed) | Sector backdrop for the arc paragraph | No | Unmetered | Semis production +12.35% YoY |
| **Gemini** `gemini-3.8-flash` | The narration itself | Yes | — | Live call OK |

### The known limitation: no historical news

**Correction (2026-09-26): Finnhub's free tier does honor the date range; it caps each request at about 250 articles and returns the newest ones in that range.** Requesting 180 days of NVDA news returned 248 articles, all from the previous three days, because 250 NVDA articles only span about three days. A request for a past week (NVDA, 2026-06-01 to 06-07) returns about 250 articles from the end of that week. Less-covered companies fit the whole window in one request: Cirrus Logic's 180-day request returned 128 articles going back to March.

**Fixed (2026-09-26):** `news_for_move()` now also requests news for each move's own dates (the move day and the day before), about 12 extra requests per company, paced under 60 per minute. Past windows are cached for good. Articles are ranked so those naming the company in the headline come first, since a two-day window for a heavily covered stock holds ~250 articles, many of them market roundups. Across the 13 stories, low-confidence explanations fell from 108 to 7 and news citations rose from 22 to 336. The notes below describe how moves without news are still handled.

There is no historical news source in the stack. That was a deliberate scope decision: GDELT was built, tested and working (it correctly found the CNBC earnings story behind NVDA's +8.74% day) but was removed as too much operational hassle for this project — its 1-request-per-5-seconds limit and frequent 429s made a full rebuild take upwards of half an hour.

**When no news explains a move**, it is explained from:

- **SEC filings** — an 8-K or 10-Q within 2 days of the move. This covers earnings days, which are the largest and most interesting moves anyway, at `high` confidence.
- **Connected-company moves** — whether its suppliers, customers, and competitors (from the knowledge graph, `backend/app/connections.py`) moved the same day, which distinguishes "this company had a bad day" from "its whole supply chain had a bad day."
- **Price and volume** — the move's size relative to the 30-day average.

Mid-period moves with no filing nearby come back as *"cause unverified"* at `low` confidence. That's the honest outcome and the system reports it plainly rather than inventing a reason.

**If explanation quality needs to improve, this is the one thing to change.** `news_for_move()` in [backend/app/story/build.py](backend/app/story/build.py) is the seam — a historical news provider drops in there without touching anything else. Options, cheapest first: bring GDELT back (free, keyless, slow), Alpha Vantage `NEWS_SENTIMENT` (free key, 25 req/day), or a paid Finnhub tier.

### Considered and rejected

| Source | Why not |
|---|---|
| GDELT Document API | Built and verified working, then **removed as out of scope.** Keyless and genuinely historical, but 1 req / 5 sec with frequent 429s. |
| Alpha Vantage `NEWS_SENTIMENT` | Supports `time_from`, so it *would* solve the history problem — but the free tier is 25 requests/day total, and 60 move-dates across 5 companies exceeds a day's budget in one rebuild. |
| Financial Modeling Prep | 250 calls/day, 500MB/month. Fine, but EDGAR already gives us fundamentals from the primary source with a better citation link. Wired into `.env` as optional; unused. |
| Kaggle datasets | Snapshots, not live feeds. "Continuously updated" Kaggle stock datasets are typically someone's cron job that stops silently, and they carry no per-row source URL — so nothing to cite. Unsuitable for this feature specifically. |
| NewsAPI.org free tier | Explicitly forbids production use and caps history at 1 month. |
| Web scraping IR pages | Too brittle for a hackathon timeline. |

---

## 2. The citation contract

This is the part that matters for the investor-trust story, and it's the reason the architecture looks the way it does.

**The model never retrieves anything.** Gemini receives only evidence rows we fetched first, and may only reference their `id`s. Then every id it returns is checked against the set we supplied.

```
prices ─┐
news   ─┼─► detect moves ─► build evidence rows (each: id, numbers, source URL)
filings─┤                              │
XBRL   ─┘                              ▼
                              Gemini (sees ids, NOT urls)
                                       │
                                       ▼
                          verify_citations: unknown id ─► dropped
                                       │
                                       ▼
                     beat with 0 valid citations ─► explanation replaced
                        with the bare price fact, confidence = low
```

Two consequences worth stating plainly:

- **Gemini is never given the URLs.** It gets ids only, and the frontend resolves ids back to URLs. So a fabricated link is structurally impossible, not just unlikely.
- **A move with no explaining evidence says so.** The prompt explicitly permits "No company-specific news accompanied this drop; peers fell a similar amount, so this looks sector-wide." That's a more valuable sentence to an investor than an invented cause, and it's why `confidence` is on every beat.

### Evidence kinds

| Kind | Click-through lands on | Numbers carried |
|---|---|---|
| `sector` | The FRED series page | value, units, as-of date, YoY % |
| `price` | Yahoo price history | % change, close, prev close, volume, volume vs 30-day avg, move excluding sector |
| `filing` | The filing's primary document on sec.gov | — |
| `fundamental` | The EDGAR filing index the figure was reported in | value, period end, XBRL tag, YoY % |
| `news` | The publisher's article | — |
| `peer_move` | That peer's price history | peer % change vs subject % change |

`sector` and `fundamental` evidence is monthly or quarterly, so the prompt forbids using either as the cause of a single day's move. They exist for the arc, where "semiconductor production is up 12.4% year over year while this stock fell 15%" is context no single headline can give.

`peer_move` is doing something specific: it separates "this company had a bad day" from "the whole sector had a bad day." That distinction is the honest answer to "how is my investment doing and why," and it's the same insight the Connection Map sells.

### API

| Endpoint | Returns |
|---|---|
| `GET /story/{symbol}` | Full bar series, beats with `citation_ids`, and an `evidence` map |
| `GET /story/{symbol}/citation/{id}` | One evidence row: numbers + outbound URL, for the drill-down panel |
| `GET /universe` | The 5 companies with sectors and their knowledge-graph connections (supplier, customer, competitor) |
| `GET /health` | Liveness |

The frontend renders `citation_ids` as clickable markers on each sentence; clicking one opens the panel with that row's numbers and a link out to the source.

---

## 3. Move detection

Not every wiggle earns a label. A day becomes a beat when `|% change| >= 3.0` (tunable via `MOVE_THRESHOLD_PCT`), then candidates are ranked by:

```
score = |move - sector average move| × min(volume / 30-day average, 3.0)
```

Subtracting the peer average is deliberate: a 5% drop on a day the sector fell 4.5% is beta, not news, and ranking it highly would waste a chart label and a Gemini call. Volume is a tiebreaker, capped so one freak session can't dominate. Top 12 by score, then re-sorted chronologically.

---

## 4. Running it

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env     # then fill in GEMINI_API_KEY and FINNHUB_API_KEY
.venv/bin/python -m scripts.check_sources        # verify every source + key
.venv/bin/python -m scripts.build_story_cache    # precompute all 5 stories
.venv/bin/uvicorn app.main:app --reload
```

`SEC_USER_AGENT` must contain a real contact email or data.sec.gov returns **403**, not a helpful error.

Per plans.md the demo must not depend on live calls: once the cache is built the API serves from `data/cache/`, and `check_sources` is the thing to run before going on stage. Deleting `data/cache/` is the only way to force a refetch.

To read a story in the terminal with every citation resolved:

```bash
.venv/bin/python -m scripts.show_story NVDA            # from the cache
.venv/bin/python -m scripts.show_story NVDA --days 21  # short window, built now
.venv/bin/python -m scripts.show_story NVDA --json     # the API payload
```

It ends with a citation-integrity count: total citations, how many point at evidence that does not exist (must be 0), and how many beats had no source.

---

## 5. Open items

- [ ] **Historical news is the biggest quality lever.** `news_for_move()` is the seam; see §1.
- [ ] Spot-check beat accuracy against what actually happened — the citation plumbing is verified and tested, the editorial judgment is not
- [ ] `portfolio_context` is plumbed through `narrate()` but nothing populates it yet; wiring it in lets the arc say "this is 18% of your portfolio" (needs the portfolio owner's endpoint)


---

## 6. Reconciling `companylist.md`

The saved list names ten sources: Bloomberg, Capital IQ, Factiva, Datastream (LSEG), Thomson Reuters, CRSP, IBISWorld, Mergent Online, S&P NetAdvantage, and Global Financial Data.

**None of the ten are callable from code here.** Every one is an institutional subscription — Bloomberg Terminal runs roughly $25k per seat per year, Capital IQ and IBISWorld are enterprise contracts, CRSP is an academic license. Several have no developer API at all; they're web portals or Excel add-ins. And the ones a university library commonly provides (Factiva, Capital IQ, IBISWorld, NetAdvantage) license *reading* access to the individual, under terms that forbid redistributing the data through an application.

The list is still useful, because it names the right *categories*. Each one maps onto something free and programmatic:

| From the list | What it provides | Free equivalent now in use |
|---|---|---|
| Bloomberg, Thomson Reuters | Wire-service news | **Finnhub**, ~250 newest articles per request; historical news needs per-date requests — see §1. |
| Factiva (Dow Jones) | News archive | **Nothing.** This is the acknowledged gap. |
| Capital IQ, Mergent, S&P NetAdvantage | Company fundamentals and filings | **SEC EDGAR** XBRL — the primary source these three resell, and a better citation link |
| CRSP, Global Financial Data, Datastream | Historical prices and returns | **yfinance** — far shorter history, but 180 days is all Story Mode charts |
| **IBISWorld** | Industry and sector trends | **FRED** — *this was a real gap.* Added because of this entry. |

IBISWorld is the entry that changed the design. I had no sector-level data at all, and "how is the whole industry doing" is a distinct question from "how is this company doing" — it's the difference between a stock falling *with* its industry and falling *against* it. FRED's keyless CSV endpoint gives US semiconductor production, semiconductor producer prices, and electronics manufacturing employment, monthly, each with a citable series page. Latest readings are through August 2026.

### Worth knowing about the list's provenance

It came from a `eliteresearch.com` listicle titled "Top 10 Data Sources for Corporate Market Analysis and Forecasting." That's written for human analysts at institutions with procurement budgets — people who will *read* Bloomberg, not query it. It's a reasonable answer to "where do professionals get market data" and the wrong answer to "what can a hackathon app call at 2am." Worth keeping the distinction in mind if more sources get added: the filter is **does it have a free, keyed-or-keyless HTTP API, and may we redistribute what it returns.**

### Two places these sources are still useful

1. **Spot-checking.** If you have library access to Factiva or Capital IQ, it is the fastest way to confirm a beat's explanation is actually right — the open item in §5 that I can't verify from here.
2. **The pitch.** "We use SEC EDGAR primary filings and federal industrial statistics" is a stronger credibility line to judges than naming a terminal you don't have access to.
