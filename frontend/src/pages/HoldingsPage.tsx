import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Quote, type UniverseCompany } from '../api'
import { AsOf, Change, Sparkline } from '../components'
import { money } from '../format'
import { parseTickers, SAMPLE_PORTFOLIO, useAsync } from '../hooks'

/** Where the portfolio is built: paste, upload, or browse, then review. */
export function HoldingsPage({ holdings, setHoldings }: { holdings: string[]; setHoldings: (h: string[]) => void }) {
  const universe = useAsync(api.universe, 'universe')
  const quotes = useAsync(api.quotes, 'quotes')
  const companies = useMemo(() => universe.data ?? [], [universe.data])
  const bySymbol = useMemo(() => new Map(companies.map((c) => [c.symbol, c])), [companies])

  const addMany = (tickers: string[]) => setHoldings([...holdings, ...tickers.filter((t) => !holdings.includes(t))])
  const toggle = (ticker: string) =>
    setHoldings(holdings.includes(ticker) ? holdings.filter((h) => h !== ticker) : [...holdings, ticker])

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Holdings</div>
        <h1>Your portfolio</h1>
        <AsOf date={quotes.data?.as_of} />
        <p>
          Paste your tickers, upload a CSV from your brokerage, or pick companies from the list.
          Every screen reads from here.
        </p>
      </div>
      {universe.error && <p className="error">{universe.error}</p>}
      <div className="holdings-grid">
        <div className="stack">
          <PasteBox known={bySymbol} onAdd={addMany} />
          <HoldingsTable holdings={holdings} bySymbol={bySymbol} setHoldings={setHoldings}
                         quotes={quotes.data?.quotes ?? {}} />
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

function HoldingsTable({ holdings, bySymbol, setHoldings, quotes }: {
  holdings: string[]
  bySymbol: Map<string, UniverseCompany>
  setHoldings: (h: string[]) => void
  quotes: Record<string, Quote>
}) {
  const rows = [...holdings].sort()
  return (
    <section className="card">
      <div className="row-between" style={{ marginBottom: 10 }}>
        <div className="card-label" style={{ margin: 0 }}>Current holdings · {holdings.length}</div>
        <div className="row">
          <button className="ghost-btn" onClick={() => setHoldings(SAMPLE_PORTFOLIO)}>Use sample portfolio</button>
          <button className="ghost-btn" disabled={!holdings.length} onClick={() => setHoldings([])}>Clear all</button>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="small muted">Nothing yet. Paste tickers above or check companies on the right.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Ticker</th><th>Company</th><th className="num">Price</th><th className="num">Today</th>
              <th>30 days</th><th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => {
              const c = bySymbol.get(t)
              const q = quotes[t]
              return (
                <tr key={t}>
                  <td><Link to={`/stock/${t}`}><strong>{t}</strong></Link></td>
                  <td className="secondary">
                    {c?.name ?? <span className="muted">Not supported</span>}
                    {c && <div className="small muted">{c.sector}</div>}
                  </td>
                  <td className="num price">{q ? money(q.price) : '—'}</td>
                  <td className="num"><Change pct={q?.change_pct} /></td>
                  <td>{q && <Sparkline points={q.sparkline} />}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="ghost-btn" aria-label={`Remove ${t}`}
                            onClick={() => setHoldings(holdings.filter((h) => h !== t))}>Remove</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}

function CompanyBrowser({ companies, holdings, toggle, setHoldings }: {
  companies: UniverseCompany[]
  holdings: string[]
  toggle: (t: string) => void
  setHoldings: (h: string[]) => void
}) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
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
      <div className="card-label">Browse supported companies · {companies.length}</div>
      <input type="search" className="search" placeholder="Search ticker, company, or sector"
             value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search companies" />
      <div className="browser-list">
        {groups.length === 0 && <p className="small muted">No companies match “{query}”.</p>}
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
