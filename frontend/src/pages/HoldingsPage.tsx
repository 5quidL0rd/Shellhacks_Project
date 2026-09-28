import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type LiveQuotes, type Quote, type UniverseCompany } from '../api'
import { Change } from '../components'
import { money } from '../format'
import { parseTickers, useAsync, type Position } from '../hooks'

/** Where the portfolio is built: paste, upload, or browse, then review. */
export function HoldingsPage({ holdings, setHoldings, positions, setPosition, demo,
  useSamplePortfolio, startCustomPortfolio, live, liveError }: {
  holdings: string[]
  setHoldings: (h: string[]) => void
  positions: Record<string, Position>
  setPosition: (symbol: string, field: keyof Position, value: number | null) => void
  demo: boolean
  useSamplePortfolio: () => void
  startCustomPortfolio: () => void
  live: LiveQuotes | null
  liveError: string | null
}) {
  const universe = useAsync(api.universe, 'universe')
  const quotes = useAsync(api.quotes, 'quotes')
  const companies = useMemo(() => universe.data ?? [], [universe.data])
  const bySymbol = useMemo(() => new Map(companies.map((c) => [c.symbol, c])), [companies])
  const valued = holdings.filter((symbol) => (positions[symbol]?.shares ?? 0) > 0 && live?.quotes[symbol])
  const marketValue = valued.reduce((sum, symbol) => sum + positions[symbol].shares! * live!.quotes[symbol].price, 0)
  const dailyValued = valued.filter((symbol) => (live!.quotes[symbol].previous_close ?? 0) > 0)
  const previousValue = dailyValued.reduce((sum, symbol) =>
    sum + positions[symbol].shares! * live!.quotes[symbol].previous_close!, 0)
  const dailyChange = dailyValued.reduce((sum, symbol) =>
    sum + positions[symbol].shares! *
      (live!.quotes[symbol].price - live!.quotes[symbol].previous_close!), 0)
  const costed = valued.filter((symbol) => (positions[symbol].averageCost ?? 0) > 0)
  const costBasis = costed.reduce((sum, symbol) => sum + positions[symbol].shares! * positions[symbol].averageCost!, 0)
  const gain = costed.reduce((sum, symbol) => sum + positions[symbol].shares! *
    (live!.quotes[symbol].price - positions[symbol].averageCost!), 0)

  const addMany = (tickers: string[]) => setHoldings([...holdings, ...tickers.filter((t) => !holdings.includes(t))])
  const toggle = (ticker: string) =>
    setHoldings(holdings.includes(ticker) ? holdings.filter((h) => h !== ticker) : [...holdings, ticker])

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Holdings</div>
        <h1>{demo ? 'Sample portfolio' : 'Your portfolio'}</h1>
        <div className="small muted">{demo ? 'Illustrative share counts, not your actual holdings. ' : ''}Live prices from Finnhub refresh every minute. Historical charts and filing analysis have separate as-of dates.</div>
        <p>
          Paste your tickers, upload a CSV from your brokerage, or pick companies from the list.
          Every screen reads from here.
        </p>
        {demo && <button type="button" className="ghost-btn" onClick={startCustomPortfolio}>
          Switch to my own portfolio
        </button>}
      </div>
      {universe.error && <p className="error">{universe.error}</p>}
      {holdings.length > 0 && <section className="card position-summary" aria-label="Portfolio value">
        <div><span className="card-label">{demo ? 'Illustrative market value' : 'Live market value'}</span><strong>{valued.length ? money(marketValue) : 'Add share counts'}</strong>
          <small>{valued.length} of {holdings.length} tickers valued with live quotes</small></div>
        <div><span className="card-label">Unrealized gain / loss</span><strong>{costed.length ? money(gain) : 'Add average cost'}</strong>
          <small>{costed.length} positions with cost basis{costBasis > 0 ? ` · ${((gain / costBasis) * 100).toFixed(2)}%` : ''}</small></div>
        <div><span className="card-label">Since previous close</span><strong>{dailyValued.length ? money(dailyChange) : 'Add share counts'}</strong>
          <small>{dailyValued.length} positions with live prior-close data{previousValue > 0 ? ` · ${((dailyChange / previousValue) * 100).toFixed(2)}%` : ''}</small></div>
        <div><span className="card-label">Quote status</span><strong>{liveError ? 'Unavailable' : live ? 'Connected' : 'Loading…'}</strong>
          <small>{liveError ?? 'Provider timestamps appear beside each price'}</small></div>
      </section>}
      <div className="holdings-grid">
        <div className="stack">
          <PasteBox known={bySymbol} onAdd={addMany} />
          <HoldingsTable holdings={holdings} bySymbol={bySymbol} setHoldings={setHoldings}
                         quotes={quotes.data?.quotes ?? {}} live={live} positions={positions}
                         setPosition={setPosition} useSamplePortfolio={useSamplePortfolio} />
        </div>
        <CompanyBrowser companies={companies} holdings={holdings} toggle={toggle}
                        setHoldings={setHoldings} />
      </div>
    </>
  )
}

function PasteBox({ known, onAdd }: { known: Map<string, UniverseCompany>; onAdd: (t: string[]) => void }) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<{ found: string[]; unknown: string[] } | null>(null)
  const file = useRef<HTMLInputElement>(null)

  const add = (input: string) => {
    const parsed = parseTickers(input, new Set(known.keys()))
    onAdd(parsed.found)
    setResult(parsed)
    setText('')
  }

  return (
    <section className="card">
      <div className="card-label">Add in bulk</div>
      <textarea
        className="paste"
        rows={4}
        value={text}
        placeholder={'Paste tickers: AAPL, NVDA, MSFT\nor a column copied from a spreadsheet'}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && text.trim()) add(text)
        }}
      />
      <div className="row-between">
        <div className="row">
          <button className="primary-btn" disabled={!text.trim()} onClick={() => add(text)}>Add tickers</button>
          <button className="ghost-btn" onClick={() => file.current?.click()}>Upload CSV</button>
          <input ref={file} type="file" accept=".csv,.txt,text/csv,text/plain" hidden
                 onChange={async (e) => {
                   const f = e.target.files?.[0]
                   if (f) add(await f.text())
                   e.target.value = ''
                 }} />
        </div>
        <span className="small muted">⌘/Ctrl + Enter to add</span>
      </div>
      {result && (
        <p className="small" role="status" style={{ marginBottom: 0 }}>
          {result.found.length > 0
            ? <>Added <strong>{result.found.length}</strong>: {result.found.join(', ')}. </>
            : 'No supported tickers found. '}
          {result.unknown.length > 0 && (
            <span className="muted">Skipped (not in the supported list): {result.unknown.join(', ')}</span>
          )}
        </p>
      )}
    </section>
  )
}

function HoldingsTable({ holdings, bySymbol, setHoldings, quotes, live, positions,
  setPosition, useSamplePortfolio }: {
  holdings: string[]
  bySymbol: Map<string, UniverseCompany>
  setHoldings: (h: string[]) => void
  quotes: Record<string, Quote>
  live: LiveQuotes | null
  positions: Record<string, Position>
  setPosition: (symbol: string, field: keyof Position, value: number | null) => void
  useSamplePortfolio: () => void
}) {
  const rows = [...holdings].sort()
  return (
    <section className="card">
      <div className="row-between" style={{ marginBottom: 10 }}>
        <div className="card-label" style={{ margin: 0 }}>Current holdings · {holdings.length}</div>
        <div className="row">
          <button className="ghost-btn" onClick={useSamplePortfolio}>Use sample portfolio</button>
          <button className="ghost-btn" disabled={!holdings.length} onClick={() => setHoldings([])}>Clear all</button>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="small muted">Nothing yet. Paste tickers above or check companies on the right.</p>
      ) : (
        <div className="table-scroll"><table className="table position-table">
          <thead>
            <tr>
              <th>Ticker</th><th>Company</th><th>Shares</th><th>Avg cost</th><th className="num">Price</th>
              <th className="num">Value</th><th className="num">Gain / loss</th><th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => {
              const c = bySymbol.get(t)
              const q = quotes[t]
              const current = live?.quotes[t]
              const position = positions[t] ?? { shares: null, averageCost: null }
              const value = current && position.shares ? current.price * position.shares : null
              const gain = value !== null && position.averageCost
                ? value - position.shares! * position.averageCost : null
              return (
                <tr key={t}>
                  <td><Link to={`/stock/${t}`}><strong>{t}</strong></Link></td>
                  <td className="secondary">
                    {c?.name ?? <span className="muted">Live quote tracking</span>}
                    <div className="small muted">{c?.sector ?? 'Detailed story not yet available'}</div>
                  </td>
                  <td><input className="position-input" type="number" min="0" step="any" inputMode="decimal"
                             aria-label={`${t} shares`} placeholder="—" value={position.shares ?? ''}
                             onChange={(e) => setPosition(t, 'shares', validNumber(e.target.value))} /></td>
                  <td><input className="position-input" type="number" min="0" step="any" inputMode="decimal"
                             aria-label={`${t} average cost`} placeholder="—" value={position.averageCost ?? ''}
                             onChange={(e) => setPosition(t, 'averageCost', validNumber(e.target.value))} /></td>
                  <td className="num price">{current ? money(current.price) : q ? money(q.price) : '—'}
                    <div className="as-of">{current ? `Live · ${new Date(current.market_timestamp ?? current.fetched_at).toLocaleTimeString()}` : 'Saved close'}</div>
                    <Change pct={current?.change_pct ?? q?.change_pct} /></td>
                  <td className="num">{value === null ? '—' : money(value)}</td>
                  <td className="num">{gain === null ? '—' : money(gain)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="ghost-btn" aria-label={`Remove ${t}`}
                            onClick={() => setHoldings(holdings.filter((h) => h !== t))}>Remove</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}
    </section>
  )
}

function validNumber(raw: string): number | null {
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) && value >= 0 ? value : null
}

function CompanyBrowser({ companies, holdings, toggle, setHoldings }: {
  companies: UniverseCompany[]
  holdings: string[]
  toggle: (t: string) => void
  setHoldings: (h: string[]) => void
}) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const [lookup, setLookup] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => setLookup(query.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [query])
  const external = useAsync(
    () => lookup.length >= 2 ? api.researchSearch(lookup, 6) : Promise.resolve(null), lookup,
  )
  const extraMatches = external.data?.matches.filter((match) => !match.in_universe) ?? []
  const groups = useMemo(() => {
    const matches = companies.filter((c) =>
      !q || c.symbol.toLowerCase().includes(q) || c.name.toLowerCase().includes(q) || c.sector.toLowerCase().includes(q))
    const bySector = new Map<string, UniverseCompany[]>()
    for (const c of matches) bySector.set(c.sector, [...(bySector.get(c.sector) ?? []), c])
    return [...bySector.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [companies, q])

  const setSector = (members: UniverseCompany[], on: boolean) => {
    const tickers = members.map((c) => c.symbol)
    setHoldings(on ? [...holdings, ...tickers.filter((t) => !holdings.includes(t))]
      : holdings.filter((h) => !tickers.includes(h)))
  }

  return (
    <section className="card browser">
      <div className="card-label">Search and track stocks</div>
      <p className="small muted">{companies.length} stocks have detailed stories and graph coverage. Search SEC-listed stocks such as Tesla for live price tracking.</p>
      <input type="search" className="search" placeholder="Search Tesla, TSLA, or another company"
             value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search companies" />
      {lookup.length >= 2 && <div className="external-matches" aria-label="Additional stock matches">
        {external.loading && <p className="small muted">Searching the SEC company list…</p>}
        {external.error && <p className="small error">Broader company search is temporarily unavailable: {external.error}</p>}
        {extraMatches.map((match) => <button key={match.ticker} type="button" className="external-match"
          onClick={() => toggle(match.ticker)} aria-pressed={holdings.includes(match.ticker)}>
          <span><strong>{match.ticker}</strong> {match.name}<small>Live quote tracking · detailed story not yet available</small></span>
          <span>{holdings.includes(match.ticker) ? 'Remove' : 'Track'}</span>
        </button>)}
      </div>}
      <div className="browser-list">
        {groups.length === 0 && extraMatches.length === 0 && !external.loading &&
          <p className="small muted">No companies match “{query}”.</p>}
        {groups.map(([sector, members]) => {
          const held = members.filter((c) => holdings.includes(c.symbol)).length
          return (
            <div key={sector} className="sector-group">
              <label className="sector-head">
                <input type="checkbox" checked={held === members.length}
                       ref={(el) => { if (el) el.indeterminate = held > 0 && held < members.length }}
                       onChange={(e) => setSector(members, e.target.checked)} />
                <span>{sector}</span>
                <span className="muted small">{held}/{members.length}</span>
              </label>
              {members.map((c) => (
                <label key={c.symbol} className="company-option">
                  <input type="checkbox" checked={holdings.includes(c.symbol)} onChange={() => toggle(c.symbol)} />
                  <strong>{c.symbol}</strong>
                  <span className="secondary">{c.name}</span>
                </label>
              ))}
            </div>
          )
        })}
      </div>
    </section>
  )
}
