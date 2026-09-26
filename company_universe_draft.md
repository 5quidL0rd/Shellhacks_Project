# Company Universe: Draft for Team Review

**Status: draft, not adopted.** Nothing here is in `data/companies.json` yet. Once the team agrees, these companies get added there and run through the pipeline.

Proposed: **40 companies**, the current 5 plus 35 new ones. Every company below was checked against SEC EDGAR on 2026-09-26: the CIK is real, and a recent annual report (10-K or 20-F) is on file, so the knowledge graph pipeline can read it.

## Pilot results (2026-09-26)

The first 8 new companies (INTC, MU, AVGO, QCOM, ASML, CRUS, AMZN, GOOGL) have been added to `data/companies.json` and run through the knowledge graph pipeline. The universe is now 13 companies.

- **Links between supported companies went from 8 to 35.** The graph has 93 nodes and 195 relationships.
- **TSMC supplies 7 of the 13**: AAPL, NVDA, AMD, INTC, AVGO, QCOM, CRUS. **ASML supplies TSMC and Intel**, a two-step dependency.
- **New shared suppliers surfaced from the filings**: Siliconware (4 supported companies), ASE, Amkor, GlobalFoundries, Samsung (3 each).
- **Intel names TSMC as its "primary competitor"** while also buying from it, which fills TSMC's missing competitor link.
- **Cirrus Logic: Apple is 91% of sales**, per its 10-K.
- **Amazon and Alphabet name no suppliers or competitors** in their own filings; their links come from other companies naming them (2 and 3 links).
- **Two filings had no standard section headings** (Intel's topic-organized 10-K and ASML's 20-F, which is its full annual report). The fetcher now falls back to keeping only sentences that mention a known company or a supply-chain term. On NVDA's filing this keeps 26 of the 27 quotes the normal extraction used.
- **Hand-check fixes**: one row removed (Cirrus Logic's "limited sales to Russia" would have become a major-market link), and company-name matching now handles names like "Taiwan Semiconductor Manufacturing Company (TSMC)" and variants such as "Global Foundries" / "GLOBALFOUNDRIES".

Snowflake's graph tables have been refreshed to match (194 edges, 74 companies, 13 supported). A second hand-check fix came from that step: Intel's filing says its Mobileye subsidiary is headquartered in Israel, which had been recorded as Intel's headquarters; that row is removed, and the export now always gives one row per company.

Story Mode stories are built for all 13 companies (153 moves, 752 citations, none broken). The original 5 were rebuilt so their peers come from the 13-company graph.

One quality note for the full rollout: Alphabet and Amazon are linked in the graph only as chip competitors (NVIDIA and Intel name them for designing their own chips), so their Story Mode peers are chip companies and explanations read like "Alphabet drops 4.99% as Intel rallies." Adding more cloud and internet companies (META, ORCL), or always including same-sector companies as peers, would give them better comparisons.

## How the list was chosen

The product's pitch is "we show you what you actually depend on," so the list is built around **one connected cluster: the AI and chip supply chain**, from chip-making equipment through foundries, chip designers, and hardware makers to cloud companies. Companies in a cluster name each other in their filings, which makes the Connection Map dense and makes shared dependencies visible.

It also includes:
- **Apple suppliers that depend heavily on Apple** (Cirrus Logic, Skyworks, Qorvo, Corning). These show hidden concentration in the other direction: owning Apple and Cirrus Logic is a doubled bet on iPhone demand.
- **AI power companies** (Constellation, Vistra), linked through data-center electricity demand.
- **Two unconnected companies** (Johnson & Johnson, JPMorgan). The Research feature's "fill the gaps" view needs companies that *don't* share the portfolio's dependencies, and the X-Ray needs a contrast.

## The list

### Already in the graph (5)
| Ticker | Company | Form | Sector |
|---|---|---|---|
| AAPL | Apple | 10-K | Technology Hardware |
| NVDA | NVIDIA | 10-K | Semiconductors |
| AMD | Advanced Micro Devices | 10-K | Semiconductors |
| TSM | Taiwan Semiconductor Manufacturing (TSMC) | 20-F | Semiconductors |
| MSFT | Microsoft | 10-K | Software |

### Chip manufacturing: foundries and memory (4)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| INTC | Intel | 50863 | 10-K | United States | Chip maker and foundry; competes with TSMC, NVIDIA, AMD |
| GFS | GlobalFoundries | 1709048 | 20-F | United States | Foundry; AMD already names it as a supplier |
| UMC | United Microelectronics | 1033767 | 20-F | Taiwan | Foundry; AMD already names it as a supplier |
| MU | Micron Technology | 723125 | 10-K | United States | Memory; NVIDIA already names it as a supplier |

### Chip designers (7)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| AVGO | Broadcom | 1730168 | 10-K | United States | Custom AI chips; NVIDIA and AMD name it as a competitor |
| QCOM | Qualcomm | 804328 | 10-K | United States | Phone chips; relies on foundries; supplies phone makers |
| MRVL | Marvell Technology | 1835632 | 10-K | United States | Data-center chips; NVIDIA and AMD name it as a competitor |
| ARM | Arm Holdings | 1973239 | 20-F | United Kingdom | Licenses chip designs to Apple, NVIDIA, Qualcomm, and others |
| SWKS | Skyworks Solutions | 4127 | 10-K | United States | Phone radio chips; Apple is a large customer |
| QRVO | Qorvo | 1604778 | 10-K | United States | Phone radio chips; Apple is a large customer |
| CRUS | Cirrus Logic | 772406 | 10-K | United States | Audio chips; Apple is its dominant customer |

### Chip-making equipment and design software (6)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| ASML | ASML Holding | 937966 | 20-F | Netherlands | Sole maker of the most advanced chip-printing machines; TSMC, Intel, and Samsung depend on it |
| AMAT | Applied Materials | 6951 | 10-K | United States | Equipment for every foundry |
| LRCX | Lam Research | 707549 | 10-K | United States | Equipment for every foundry |
| KLAC | KLA | 319201 | 10-K | United States | Inspection equipment for every foundry |
| SNPS | Synopsys | 883241 | 10-K | United States | Chip design software used by every chip designer |
| CDNS | Cadence Design Systems | 813672 | 10-K | United States | Chip design software used by every chip designer |

### Packaging and assembly (3)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| AMKR | Amkor Technology | 1047127 | 10-K | United States | Chip packaging for designers without their own factories |
| ASX | ASE Technology | 1122411 | 20-F | Taiwan | Largest chip packager; parent of Siliconware, which AMD names |
| JBL | Jabil | 898293 | 10-K | United States | Contract manufacturer for Apple and data-center hardware |

### Hardware and networking (6)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| DELL | Dell Technologies | 1571996 | 10-K | United States | AI servers built on NVIDIA and AMD chips |
| HPE | Hewlett Packard Enterprise | 1645590 | 10-K | United States | AI servers; NVIDIA names it as a competitor |
| SMCI | Super Micro Computer | 1375365 | 10-K | United States | AI servers built on NVIDIA chips |
| ANET | Arista Networks | 1596532 | 10-K | United States | Data-center networking; NVIDIA names it as a competitor |
| CSCO | Cisco Systems | 858877 | 10-K | United States | Networking; NVIDIA names it as a competitor |
| GLW | Corning | 24741 | 10-K | United States | Phone glass for Apple; fiber for data centers |

### Cloud and internet: the big chip buyers (4)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| GOOGL | Alphabet (Google) | 1652044 | 10-K | United States | Buys AI chips; builds its own; NVIDIA names it as a competitor |
| AMZN | Amazon | 1018724 | 10-K | United States | Buys AI chips; builds its own; NVIDIA names it as a competitor |
| META | Meta Platforms | 1326801 | 10-K | United States | One of the largest AI chip buyers |
| ORCL | Oracle | 1341439 | 10-K | United States | Cloud; large AI data-center buildout |

### Other sectors (5)
| Ticker | Company | CIK | Form | HQ | Why |
|---|---|---|---|---|---|
| TSLA | Tesla | 1318605 | 10-K | United States | Designs its own chips; NVIDIA names it as a competitor |
| CEG | Constellation Energy | 1868275 | 10-K | United States | Power for AI data centers |
| VST | Vistra | 1692819 | 10-K | United States | Power for AI data centers |
| JNJ | Johnson & Johnson | 200406 | 10-K | United States | Unconnected contrast for the X-Ray and "fill the gaps" |
| JPM | JPMorgan Chase | 19617 | 10-K | United States | Unconnected contrast for the X-Ray and "fill the gaps" |

**"Why" notes marked "already names"** come from the extractions we have. The rest are expected links that have to be confirmed from the new filings; any the filings don't state will not appear in the graph unless added by hand.

## Companies that stay outside the universe

These matter to the supply chain but **file no annual reports with the SEC**, so the pipeline can't read them. They stay in the graph as outside companies (`in_universe: false`) whenever a supported company names them, as they are today:
- **Samsung Electronics** (not SEC-listed)
- **SK Hynix** (has an SEC record but no 10-K or 20-F)
- **Hon Hai / Foxconn** (not SEC-listed)

## Suggested demo portfolio

Twelve holdings that make the demo story work: several stocks that look different but share TSMC and Taiwan underneath.

| | Holdings |
|---|---|
| Depend on TSMC | AAPL, NVDA, AMD, QCOM *(QCOM to confirm from its filing)* |
| Depend on Apple | CRUS |
| Cloud | MSFT, AMZN, GOOGL |
| Other | TSLA, CEG, JPM, JNJ |

The X-Ray would then show TSMC, Taiwan, and AI chip demand shared across most of the portfolio, while JPM and JNJ share almost nothing.

## Things to decide

1. **Size.** 40 fits the plan's 30–50. If time is short, run a pilot first: 8–10 of the new companies (for example INTC, MU, AVGO, QCOM, ASML, CRUS, AMZN, GOOGL) to confirm the pipeline handles them and the links appear.
2. **Six new 20-F filers** (GFS, UMC, ARM, ASML, ASX, plus TSMC already). The section finder was tuned on TSMC's 20-F, so these need an extra check that the right sections were found.
3. **Sector names.** Proposed fixed set: Semiconductors, Semiconductor Equipment, Technology Hardware, Software, Internet & Cloud, Automotive, Utilities, Healthcare, Financials. Story Mode's industry backdrop (FRED) currently covers only Semiconductors and Technology Hardware; Semiconductor Equipment should map to the same series as Semiconductors.
4. **Story Mode scope.** Stories for all 40 means about 40 Gemini calls plus price and news downloads. Stories for the demo portfolio only (12) may be enough.

## Cost and time estimate

- **Knowledge graph:** 35 filing downloads (free) and roughly 100–140 Gemini calls (about 3–4 text chunks per filing), plus hand-checking the results, the slowest part.
- **Story Mode:** one Gemini call per company, plus prices and news.
- **Snowflake:** a reload of the graph, stories, prices, and news; the loaders already handle any number of companies.
