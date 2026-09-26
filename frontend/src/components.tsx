import { Link } from 'react-router-dom'
import { api, type Provenance } from './api'
import { useAsync } from './hooks'

/** "7 holdings · Edit" line for page headers; holdings live on /holdings. */
export function HoldingsSummary({ holdings, unsupported = [] }: { holdings: string[]; unsupported?: string[] }) {
  return (
    <div className="holdings-summary">
      <span>{holdings.length} {holdings.length === 1 ? 'holding' : 'holdings'}</span>
      {unsupported.length > 0 && (
        <span className="muted" title="Not in the supported company list, so not analyzed">
          · {unsupported.length} not supported ({unsupported.join(', ')})
        </span>
      )}
      <Link to="/holdings">Edit holdings →</Link>
    </div>
  )
}

/** Shown instead of an analysis when there is nothing to analyze. */
export function EmptyPortfolio() {
  return (
    <div className="placeholder">
      <strong>No holdings yet</strong>
      <p className="small muted">Add the stocks you own to see what they depend on.</p>
      <Link className="primary-btn" to="/holdings">Add holdings</Link>
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
