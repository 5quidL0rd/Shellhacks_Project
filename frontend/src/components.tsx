import { Link } from 'react-router-dom'
import { api, type Provenance } from './api'
import { EVIDENCE_DESCRIPTION, EVIDENCE_ICON, EVIDENCE_LABEL } from './evidence'
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

/** ▲ +1.23% / ▼ −0.45%: arrow, sign, and color together, never color alone. */
export function Change({ pct, suffix = '' }: { pct: number | null | undefined; suffix?: string }) {
  if (pct == null) return <span className="muted">—</span>
  const flat = Math.abs(pct) < 0.005
  const dir = flat ? 'flat' : pct > 0 ? 'up' : 'down'
  const arrow = flat ? '•' : pct > 0 ? '▲' : '▼'
  const sign = pct > 0 ? '+' : pct < 0 ? '−' : ''
  return <span className={`change ${dir}`}>{arrow} {sign}{Math.abs(pct).toFixed(2)}%{suffix}</span>
}

/** Tiny single-series price line (no axes, no legend; the row names it). */
export function Sparkline({ points, width = 88, height = 26 }: {
  points: { date: string; close: number }[]
  width?: number
  height?: number
}) {
  if (points.length < 2) return null
  const closes = points.map((p) => p.close)
  const lo = Math.min(...closes)
  const hi = Math.max(...closes)
  const x = (i: number) => (i / (points.length - 1)) * (width - 4) + 2
  const y = (c: number) => (hi === lo ? height / 2 : height - 3 - ((c - lo) / (hi - lo)) * (height - 6))
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join(' ')
  const first = points[0]
  const last = points[points.length - 1]
  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label={`${points.length}-day price, ${first.close.toFixed(2)} to ${last.close.toFixed(2)}`}>
      <title>{`${first.date}: $${first.close.toFixed(2)} → ${last.date}: $${last.close.toFixed(2)}`}</title>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(points.length - 1)} cy={y(last.close)} r="2.2" fill="currentColor" />
    </svg>
  )
}

/** "Prices as of Sep 25 close": quotes are saved data, not live. */
export function AsOf({ date }: { date: string | null | undefined }) {
  if (!date) return null
  const label = new Date(`${date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return <span className="as-of" title="Prices come from saved data, not a live feed">Prices as of {label} close</span>
}


function EvidenceIcon({ kind }: { kind: string }) {
  const d = EVIDENCE_ICON[kind]
  if (!d) return null
  return (
    <svg className="cite-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

/** A numbered citation: an icon for the kind of evidence, the number, and a
 * hover title saying what it is. A click opens the evidence panel; clicking
 * the highlighted one again closes it and brings back the "How to read the
 * citations" guide (passes null). */
export function Cite({ n, id, active, onClick, evidence }: {
  n: number
  id: string
  active: boolean
  onClick: (id: string | null) => void
  evidence?: { kind: string; title: string; occurred_on?: string }
}) {
  const label = evidence ? EVIDENCE_LABEL[evidence.kind] ?? evidence.kind : 'Source'
  const when = evidence?.occurred_on
    ? ` · ${new Date(`${evidence.occurred_on}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
    : ''
  return (
    <button className={`cite ${active ? 'active' : ''}`}
            aria-label={`Citation ${n}: ${label}${evidence ? `, ${evidence.title}` : ''}`}
            title={`${label}${when}${evidence ? ` · ${evidence.title}` : ''}`}
            onClick={(e) => { e.stopPropagation(); onClick(active ? null : id) }}>
      {evidence && <EvidenceIcon kind={evidence.kind} />}{n}
    </button>
  )
}

/** How to read the citations on this page: what the numbers are, then each
 * icon that appears here with its name and a one-line description. */
export function CiteGuide({ kinds }: { kinds: string[] }) {
  const shown = [...new Set(kinds)].filter((k) => EVIDENCE_ICON[k])
  if (!shown.length) return null
  return (
    <section className="cite-guide" aria-label="How to read the citations">
      <div className="card-label">How to read the citations</div>
      <p className="small secondary">
        Each explanation was written only from the sources we gathered first. The small numbered
        buttons after a paragraph are those sources: the icon says what kind it is, and clicking one
        opens it with its figures and a link to the original. Click the highlighted one again to come
        back to this guide.
      </p>
      <dl className="cite-guide-list">
        {shown.map((k) => (
          <div key={k} className="cite-guide-item">
            <dt><span className="cite cite-sample"><EvidenceIcon kind={k} />1</span> {EVIDENCE_LABEL[k]}</dt>
            <dd>{EVIDENCE_DESCRIPTION[k]}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
