import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Provenance, type UniverseCompany } from './api'
import { SAMPLE_PORTFOLIO, useAsync } from './hooks'

/** Holdings as chips (click to open Story Mode), plus add / remove / reset. */
export function PortfolioBar({ holdings, setHoldings, unsupported = [] }: {
  holdings: string[]
  setHoldings: (h: string[]) => void
  unsupported?: string[]
}) {
  const universe = useAsync(api.universe, 'universe')
  const [adding, setAdding] = useState('')
  const available = (universe.data ?? []).filter((c) => !holdings.includes(c.symbol))

  return (
    <div className="portfolio-bar" aria-label="Your holdings">
      <span className="small muted">Holdings</span>
      {holdings.map((t) => (
        <span key={t} className={`chip ${unsupported.includes(t) ? 'unsupported' : ''}`}
              title={unsupported.includes(t) ? 'Not in the supported company list' : undefined}>
          {unsupported.includes(t) ? t : <Link to={`/stock/${t}`}>{t}</Link>}
          <button aria-label={`Remove ${t}`} onClick={() => setHoldings(holdings.filter((h) => h !== t))}>×</button>
        </span>
      ))}
      <select aria-label="Add a holding" value={adding}
              onChange={(e) => {
                if (e.target.value) setHoldings([...holdings, e.target.value])
                setAdding('')
              }}>
        <option value="">+ Add</option>
        {available.map((c: UniverseCompany) => (
          <option key={c.symbol} value={c.symbol}>{c.symbol} · {c.name}</option>
        ))}
      </select>
      <button className="ghost-btn small" onClick={() => setHoldings(SAMPLE_PORTFOLIO)}>Use sample portfolio</button>
    </div>
  )
}

const SOURCE_LABEL: Record<string, string> = {
  '10-K': '10-K filing',
  '20-F': '20-F filing',
  manual: 'Added by hand',
  config: 'Company list',
}

/** One graph edge's evidence: the filing quote and where it came from. */
export function EvidenceQuote({ p }: { p: Provenance }) {
  const source = p.source ? SOURCE_LABEL[p.source] ?? p.source : 'Unknown source'
  return (
    <div className="evidence">
      {p.evidence ? <q>{p.evidence}</q> : <span className="muted">{p.note ?? 'No quote recorded.'}</span>}
      <div className="small muted">
        {p.detail ? `${p.detail} · ` : ''}
        {p.filing_url ? <a href={p.filing_url} target="_blank" rel="noreferrer">{source}</a> : source}
        {p.evidence && p.note ? ` · ${p.note}` : ''}
      </div>
    </div>
  )
}

const ROLE_LABEL: Record<string, string> = {
  customer: 'Buys from it',
  supplier: 'Supplies it',
  indirect_customer: 'Through the supply chain',
  competitor: 'Competitor, also affected',
}

/** "If news hits this company, which of my holdings does it touch?" */
export function ImpactPanel({ company, holdings }: { company: string; holdings: string[] }) {
  const impact = useAsync(() => api.impact(company, holdings), `${company}|${holdings.join(',')}`)
  if (impact.loading) return <p className="muted small">Tracing connections…</p>
  if (impact.error) return <p className="error small">{impact.error}</p>
  const r = impact.data!
  return (
    <div>
      <h2>If news hits {r.company.name}</h2>
      {r.affected.length === 0
        ? <p className="secondary small">None of your holdings are connected to it in the graph.</p>
        : <p className="secondary small">{r.affected.length} of your {r.holdings.length} holdings are connected:</p>}
      {r.affected.map((a) => (
        <div key={a.ticker} className="impact-item">
          <Link to={`/stock/${a.ticker}`}><strong>{a.ticker}</strong></Link>{' '}
          <span className="secondary small">{a.name}</span>
          {a.connections.map((c, i) => (
            <div key={i} style={{ marginTop: 6 }}>
              <div className="role">{ROLE_LABEL[c.role] ?? c.role}</div>
              <div className="small">{c.explanation}</div>
              {c.evidence.map((p, j) => <EvidenceQuote key={j} p={p} />)}
            </div>
          ))}
        </div>
      ))}
      {r.unaffected.length > 0 && (
        <p className="muted small">Not connected: {r.unaffected.join(', ')}</p>
      )}
    </div>
  )
}
