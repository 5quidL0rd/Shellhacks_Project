import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  type Analysis,
  type FitComponent,
  type FitComponentName,
  type PortfolioRadarAxis,
  type RadarAxis,
  type ResearchEvidence,
  type Verdict,
} from '../api'
import { RevenueMixPanel } from '../RevenueMix'
import { Cite, CiteGuide, EmptyPortfolio, HoldingsSummary } from '../components'
import { useAsync } from '../hooks'

const VERDICT_CLASS: Record<Verdict, string> = {
  'Good diversity': 'up',
  'Some diversification': 'flat',
  'Risky overlap': 'down',
  'Not enough data': 'flat',
}

const COMPONENT_LABEL: Record<FitComponentName, string> = {
  correlation: 'Price correlation',
  sector_crowding: 'Sector crowding',
  dependency_overlap: 'Shared dependencies',
  direct_connection: 'Direct links to holdings',
}

const KIND_LABEL: Record<ResearchEvidence['kind'], string> = {
  metric: 'Measured figure',
  diversification: 'Portfolio overlap',
  news: 'News article',
}

/** A company worth searching if you have not typed anything yet. Ford looks
 * like obvious diversification against a chip-heavy portfolio and mostly is,
 * but its financials are nothing like them — a useful thing to discover. */
const EXAMPLES = ['Ford', 'Waste Management', 'Coca Cola', 'BMW', 'Union Pacific']

/** Research: type any public company, see how it would fit what you own. */
export function ResearchPage({ holdings }: { holdings: string[] }) {
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<string | null>(null)

  if (holdings.length === 0) {
    return (
      <>
        <PageHead />
        <EmptyPortfolio />
      </>
    )
  }

  const pick = (ticker: string) => {
    setChosen(ticker)
    setQuery('')
  }

  return (
    <>
      <PageHead />
      <HoldingsSummary holdings={holdings} />
      <SearchBox query={query} setQuery={setQuery} onPick={pick} />
      {chosen
        ? <Result key={chosen} ticker={chosen} holdings={holdings} onPick={pick} />
        : <Intro onPick={setQuery} />}
    </>
  )
}

function PageHead() {
  return (
    <div className="page-head">
      <div className="eyebrow">Research</div>
      <h1>How would this fit your portfolio?</h1>
      <p>
        Search any public company. You will see how much it overlaps what you already own —
        by sector, by price behaviour, and by supply chain — and what that means for your
        concentration. This measures fit, not expected return.
      </p>
    </div>
  )
}

function Intro({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="placeholder">
      <strong>Search a company to begin</strong>
      <p className="small muted">
        Any of the ~10,400 companies that file with the SEC. Try a ticker, a company name, or
        even a brand.
      </p>
      <div className="example-chips">
        {EXAMPLES.map((e) => (
          <button key={e} type="button" className="ghost-btn small" onClick={() => onPick(e)}>
            {e}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Type-ahead over SEC's ticker directory. */
function SearchBox({ query, setQuery, onPick }: {
  query: string
  setQuery: (q: string) => void
  onPick: (ticker: string) => void
}) {
  const [debounced, setDebounced] = useState(query)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 200)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const loader = useCallback(
    () => (debounced.length >= 1 ? api.researchSearch(debounced) : Promise.resolve(null)),
    [debounced],
  )
  const results = useAsync(loader, debounced)
  const matches = results.data?.matches ?? []

  return (
    <div className="search-box" ref={box}>
      <label className="visually-hidden" htmlFor="company-search">Search a company</label>
      <input
        id="company-search"
        className="search-input"
        type="search"
        autoComplete="off"
        placeholder="Search any public company — ticker, name, or brand"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && matches.length > 0) {
            onPick(matches[0].ticker)
            setOpen(false)
          }
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && debounced.length >= 1 && (
        <ul className="search-results" role="listbox">
          {results.loading && <li className="search-note muted small">Searching…</li>}
          {!results.loading && matches.length === 0 && (
            <li className="search-note muted small">
              No SEC filer matches “{debounced}”. Brands often file under a parent company.
            </li>
          )}
          {matches.map((m) => (
            <li key={m.ticker}>
              <button type="button" className="search-hit" role="option" aria-selected="false"
                      onClick={() => { onPick(m.ticker); setOpen(false) }}>
                <span className="search-ticker">{m.ticker}</span>
                <span className="search-name">{m.name}</span>
                {m.in_universe && <span className="tag">covered in depth</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** One overlap check: what it means, then the score, then the figures.
 *
 * The plain sentence leads because the number alone did not land — "54/100"
 * and "weight 54%" both read as jargon until you say which direction is good
 * and what the weight is a share of. */
function Check({ name, comp }: { name: FitComponentName; comp: FitComponent }) {
  const [open, setOpen] = useState(false)
  const tone = comp.score == null ? 'flat'
    : comp.score >= 67 ? 'up' : comp.score >= 34 ? 'flat' : 'down'
  return (
    <div className="fit-component">
      <div className="check-head">
        <span className="check-name">{COMPONENT_LABEL[name]}</span>
        <span className={`band ${tone}`}>{comp.band}</span>
      </div>
      <p className="check-plain">{comp.plain || comp.detail}</p>
      <div className="check-meter">
        <ScoreBar score={comp.score} width={130} />
        <span className="small muted">
          {comp.measured
            ? `counts for ${Math.round(comp.weight_applied * 100)}% of the fit score`
            : 'not counted in the fit score'}
        </span>
      </div>
      <button type="button" className="link-btn small" onClick={() => setOpen(!open)}
              aria-expanded={open}>
        {open ? 'Hide the numbers' : 'Show the numbers'}
      </button>
      {open && (
        <p className="small secondary check-detail">
          <strong>{comp.label}.</strong> {comp.detail}
        </p>
      )}
    </div>
  )
}

function ScoreBar({ score, width = 140 }: { score: number | null; width?: number }) {
  if (score == null) return <span className="muted small">not measured</span>
  const tone = score >= 67 ? 'up' : score >= 34 ? 'flat' : 'down'
  return (
    <span className="score-bar" style={{ width }} title={`${score} out of 100`}>
      <span className="bar-track">
        <span className={`bar-fill ${tone}`} style={{ width: `${score}%` }} />
      </span>
      <span className="num small">{score}</span>
    </span>
  )
}

function Result({ ticker, holdings, onPick }: {
  ticker: string
  holdings: string[]
  onPick: (ticker: string) => void
}) {
  const [citation, setCitation] = useState<string | null>(null)
  const state = useAsync(() => api.researchAnalyze(ticker, holdings), `${ticker}|${holdings.join(',')}`)

  if (state.loading) {
    return <div className="card"><p className="muted">Analysing {ticker} against your holdings…</p></div>
  }
  if (state.error) {
    return <LookupProblem message={state.error} />
  }
  const r = state.data!

  return (
    <div className="two-col">
      <div className="stack">
        <div className="card">
          <div className="row-between">
            <div className="role">{r.sector}{r.industry ? ` · ${r.industry}` : ''}</div>
            {r.country && <span className="small muted">{r.country}</span>}
          </div>
          <h2 style={{ marginTop: 4, marginBottom: 6 }}>
            {r.name} <span className="muted">{r.ticker}</span>
          </h2>
          {r.already_held && (
            <p className="small" style={{ margin: '0 0 8px' }}>
              <strong>You already hold this.</strong> The comparison below is against your
              other holdings.
            </p>
          )}
          <div className="quote-line">
            <span className={`verdict big ${VERDICT_CLASS[r.verdict]}`}>{r.verdict}</span>
            <span className="small muted">fit {r.fit_score ?? '—'}/100</span>
            <span className="confidence" title={r.confidence_reason}>{r.confidence} confidence</span>
          </div>
          <p className="small secondary" style={{ marginBottom: 4 }}>{r.verdict_meaning}</p>
          <p className="small muted" style={{ margin: 0 }}>{r.confidence_reason}</p>
          {r.in_universe && (
            <Link className="link-btn small" to={`/stock/${r.ticker}`}>See its price story →</Link>
          )}
        </div>

        {r.concentration?.revenue_mix && (
          <div className="card">
            <RevenueMixPanel mix={r.concentration.revenue_mix} name={r.name} />
          </div>
        )}

        <div className="card">
          <div className="card-label">Overlap with your portfolio</div>
          <p className="small muted" style={{ marginTop: 0 }}>{r.score_scale}</p>
          {(Object.entries(r.components) as [FitComponentName, FitComponent][])
            .sort((a, b) => {
              if (a[1].measured !== b[1].measured) return a[1].measured ? -1 : 1
              return (a[1].score ?? 0) - (b[1].score ?? 0)
            })
            .map(([name, comp]) => (
              <Check key={name} name={name} comp={comp} />
            ))}
        </div>

        {r.brief.summary && (
          <div className="card">
            <div className="card-label">The brief</div>
            <p className="small secondary" style={{ marginTop: 0 }}>
              {r.brief.summary}
              {r.brief.summary_citation_ids.map((id, i) => (
                <Cite key={id} n={i + 1} id={id} active={citation === id} onClick={setCitation} evidence={r.evidence[id]} />
              ))}
            </p>
            <BriefList title="For" tone="up" items={r.brief.pros} citation={citation} evidence={r.evidence} onCite={setCitation} />
            <BriefList title="Against" tone="down" items={r.brief.cons} citation={citation} evidence={r.evidence} onCite={setCitation} />
          </div>
        )}

        <p className="small muted">{r.disclaimer}</p>
      </div>

      <aside className="stack" style={{ position: 'sticky', top: 16 }}>
        <div className="card">
          <div className="card-label">Shape vs your portfolio</div>
          <Radar candidate={r.radar} portfolio={r.portfolio_radar} />
          <dl className="numbers">
            {r.radar.map((a) => (
              <div key={a.axis} style={{ display: 'contents' }}>
                <dt title={a.explanation}>{a.label}</dt>
                <dd>
                  {a.available ? `${a.value}${a.unit}` : '—'}
                  {a.available && a.basis === 'Yahoo Finance'
                    && a.axis !== 'stability' && a.axis !== 'risk'
                    && <span className="tag" title="Vendor ratio, not read from a filing">est.</span>}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {citation && r.evidence[citation] ? (
          <div className="card">
            <EvidencePanel e={r.evidence[citation]} onClose={() => setCitation(null)} />
          </div>
        ) : r.brief.summary && (
          <div className="card">
            <CiteGuide kinds={[...r.brief.summary_citation_ids,
              ...[...r.brief.pros, ...r.brief.cons].flatMap((p) => p.citation_ids)]
              .map((id) => r.evidence[id]?.kind).filter(Boolean) as string[]} />
          </div>
        )}

        <div className="card">
          <div className="card-label">Where it would connect</div>
          <MapPlacement r={r} />
        </div>

        {r.filing_read && <FilingRead read={r.filing_read} ticker={r.ticker} />}

        {r.alternatives.length > 0 && (
          <div className="card">
            <div className="card-label">Did you mean</div>
            {r.alternatives.map((m) => (
              <button key={m.ticker} type="button" className="link-btn small"
                      style={{ display: 'block' }} onClick={() => onPick(m.ticker)}>
                {m.ticker} · {m.name}
              </button>
            ))}
          </div>
        )}

        {r.warnings.length > 0 && (
          <div className="card">
            <div className="card-label">Caveats</div>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
              {r.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        )}
      </aside>
    </div>
  )
}

/** Shown when the analysis itself fails. Picking a company from the search
 * dropdown resolves it to an exact ticker first, so this is the rare case:
 * a backend error, or a company with nothing to measure. */
function LookupProblem({ message }: { message: string }) {
  return (
    <div className="placeholder">
      <strong>Could not analyse that</strong>
      <p className="small muted">{message}</p>
      <p className="small muted">Try another company, or search by ticker.</p>
    </div>
  )
}

/** Candidate drawn over the portfolio's average shape.
 *
 * Both use the 0-100 rank rather than raw figures: a chart mixing percent
 * growth with a debt multiple would be meaningless. Ranks point so that
 * further out is better on every axis. */
function Radar({ candidate, portfolio, size = 250 }: {
  candidate: RadarAxis[]
  portfolio: PortfolioRadarAxis[]
  size?: number
}) {
  // Room for axis names. Asymmetric: "profitability" sits on the right and is
  // the longest label; the left only holds "risk" and "debt".
  const padLeft = 36
  const padRight = 88
  const cx = size / 2 + padLeft
  const cy = size / 2
  const r = size / 2 - 40
  const angle = (i: number) => (Math.PI * 2 * i) / candidate.length - Math.PI / 2
  const point = (i: number, value: number) => {
    const d = (value / 100) * r
    return [cx + Math.cos(angle(i)) * d, cy + Math.sin(angle(i)) * d]
  }
  const polygon = (scores: (number | null)[]) =>
    scores.map((s, i) => point(i, s ?? 0).map((n) => n.toFixed(1)).join(',')).join(' ')

  const byAxis = new Map(portfolio.map((p) => [p.axis, p.score]))

  return (
    <figure className="radar">
      <svg width={size + padLeft + padRight} height={size}
           viewBox={`0 0 ${size + padLeft + padRight} ${size}`}
           style={{ maxWidth: '100%', height: 'auto' }} role="img"
           aria-label="Candidate shape compared with the portfolio average">
        {[25, 50, 75, 100].map((ring) => (
          <polygon key={ring} className="radar-ring" points={polygon(candidate.map(() => ring))} />
        ))}
        {candidate.map((_, i) => {
          const [x, y] = point(i, 100)
          return <line key={i} className="radar-spoke" x1={cx} y1={cy} x2={x} y2={y} />
        })}
        <polygon className="radar-portfolio"
                 points={polygon(candidate.map((a) => byAxis.get(a.axis) ?? null))} />
        <polygon className="radar-candidate" points={polygon(candidate.map((a) => a.score))} />
        {candidate.map((a, i) => {
          const [x, y] = point(i, 124)
          return (
            <text key={a.axis} className="radar-label" x={x} y={y}
                  textAnchor={x > cx + 4 ? 'start' : x < cx - 4 ? 'end' : 'middle'}
                  dominantBaseline="middle">
              {a.axis}
            </text>
          )
        })}
      </svg>
      <figcaption className="small muted">
        <span className="legend-key candidate" /> this company
        <span className="legend-key portfolio" /> your holdings’ average
        <br />
        Rank against your holdings plus this company; further out is better on every axis.
      </figcaption>
    </figure>
  )
}

function BriefList({ title, tone, items, citation, evidence, onCite }: {
  title: string
  tone: 'up' | 'down'
  items: { point: string; citation_ids: string[] }[]
  citation: string | null
  evidence: Analysis['evidence']
  onCite: (id: string | null) => void
}) {
  return (
    <div className="brief-block">
      <div className={`role ${tone}`}>{title}</div>
      {items.length === 0
        ? <p className="small muted">Nothing the evidence supports.</p>
        : (
          <ul className="brief-list">
            {items.map((item, i) => (
              <li key={i} className="small">
                {item.point}
                {item.citation_ids.map((id, n) => (
                  <Cite key={id} n={n + 1} id={id} active={citation === id} onClick={onCite} evidence={evidence[id]} />
                ))}
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}

function EvidencePanel({ e, onClose }: { e: ResearchEvidence; onClose: () => void }) {
  const numbers = Object.entries(e.numbers).filter(([, v]) => v != null)
  return (
    <div>
      <div className="role">{KIND_LABEL[e.kind] ?? e.kind}</div>
      <h2 style={{ marginTop: 4, fontSize: '1rem' }}>{e.title}</h2>
      {e.detail && <p className="small secondary">{e.detail}</p>}
      {numbers.length > 0 && (
        <dl className="numbers">
          {numbers.map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{typeof v === 'number' ? v.toLocaleString() : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="small">
        {e.url ? <a href={e.url} target="_blank" rel="noreferrer">Open source · {e.source}</a> : e.source}
      </p>
      <div className="row-between">
        <button className="ghost-btn small" onClick={onClose}>Close</button>
        <span className="small muted">Click the highlighted citation again for the guide</span>
      </div>
    </div>
  )
}

/** What the company's own annual report said, for anything outside our 13.
 *
 * This replaces what used to be a dead end. The knowledge graph covers 13
 * companies, so for almost anything searched the supply-chain checks reported
 * "unknown" — which is the one thing this product is supposed to answer. Now the
 * filing is read on demand and every relationship carries the quote it came
 * from. */
function FilingRead({ read, ticker }: {
  read: NonNullable<Analysis['filing_read']>
  ticker: string
}) {
  const [open, setOpen] = useState(false)
  const named = (read.relationships ?? []).filter((x) => x.counterparty_name)
  const countries = [...new Set((read.relationships ?? [])
    .filter((x) => x.country).map((x) => x.country as string))]

  return (
    <div className="card">
      <div className="card-label">What we read in its annual report</div>
      <p className="small secondary" style={{ marginTop: 0 }}>
        {read.summary}
        {read.url && (
          <> <a href={read.url} target="_blank" rel="noreferrer">Open the filing →</a></>
        )}
      </p>
      {!read.available ? null : (
        <>
          <div className="filing-stats small muted">
            <span>{named.length} named companies</span>
            <span>{countries.length} countries</span>
            {!!read.dropped_unverified && (
              <span title="Every quote is checked against the filing; these did not appear">
                {read.dropped_unverified} unverifiable claims dropped
              </span>
            )}
          </div>
          <button type="button" className="link-btn small" onClick={() => setOpen(!open)}
                  aria-expanded={open}>
            {open ? 'Hide what it says' : 'Show what it says'}
          </button>
          {open && (
            <div className="filing-rels">
              {named.map((x, i) => (
                <div key={i} className="filing-rel">
                  <div className="small">
                    <strong>{ROLE_WORD[x.type]} {x.counterparty_name}</strong>
                    {x.detail ? <span className="muted"> · {x.detail}</span> : null}
                  </div>
                  <q className="small secondary">{x.evidence}</q>
                </div>
              ))}
              {countries.length > 0 && (
                <p className="small muted">Operates in: {countries.join(', ')}</p>
              )}
            </div>
          )}
        </>
      )}
      <p className="small muted" style={{ marginBottom: 0 }}>
        Read from {ticker}&rsquo;s own filing when you searched it. Each quote above was
        checked against the document.
      </p>
    </div>
  )
}

const ROLE_WORD: Record<string, string> = {
  SUPPLIER: 'Buys from',
  CUSTOMER: 'Sells to',
  COMPETITOR: 'Competes with',
  OPERATES_IN: 'Operates in',
}

interface DirectLink {
  verb: string
  holding: string
  source: 'filing' | 'graph'
}

/** The links behind the "Direct links to holdings" check, from both of its
 * sources: the company's own annual report and the knowledge graph. Reading the
 * check's evidence keeps this list and the check's count in agreement. */
function directLinks(r: Analysis): DirectLink[] {
  const graphVerb: Record<string, string> = {
    supplies: 'supplies', buys_from: 'buys from', competes_with: 'competes with',
  }
  const filingVerb: Record<string, string> = {
    SUPPLIER: 'buys from', CUSTOMER: 'sells to', COMPETITOR: 'competes with',
  }
  const out = new Map<string, DirectLink>()
  for (const item of r.components.direct_connection?.evidence ?? []) {
    const links = (item as { links?: Record<string, string>[] }).links ?? []
    const fromFiling = typeof (item as { filing_url?: string }).filing_url === 'string'
    for (const link of links) {
      const verb = fromFiling ? filingVerb[link.type] : graphVerb[link.role]
      if (!verb || !link.holding) continue
      const key = `${verb}|${link.holding}`
      if (!out.has(key)) out.set(key, { verb, holding: link.holding, source: fromFiling ? 'filing' : 'graph' })
    }
  }
  return [...out.values()].sort((a, b) => a.holding.localeCompare(b.holding) || a.verb.localeCompare(b.verb))
}

function MapPlacement({ r }: { r: Analysis }) {
  const links = directLinks(r)
  const holdings = new Set(links.map((l) => l.holding))
  return (
    <>
      {links.length === 0 ? (
        <p className="small secondary" style={{ marginTop: 0 }}>
          {r.components.direct_connection?.measured
            ? 'Nothing we read connects it directly to anything you hold.'
            : 'We could not check whether it connects to anything you hold.'}
        </p>
      ) : (
        <>
          <p className="small secondary" style={{ marginTop: 0 }}>
            Directly linked to {holdings.size} of your holdings:
          </p>
          <div className="dep-list">
            {links.map((l) => (
              <div key={`${l.verb}|${l.holding}`} className="dep-row">
                <span className="dep-name">{r.ticker} {l.verb} {l.holding}</span>
                <span className="small muted">{l.source === 'filing' ? 'its annual report' : 'knowledge graph'}</span>
              </div>
            ))}
          </div>
        </>
      )}
      {r.map_placement.in_graph
        ? <Link className="link-btn small" to="/map">Open the Connection Map →</Link>
        : (
          <p className="small muted">
            {r.name} is not on the Connection Map yet, so it cannot be drawn there.
          </p>
        )}
    </>
  )
}
