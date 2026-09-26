import { useState } from 'react'
import { api, type Dependency } from '../api'
import { EmptyPortfolio, EvidenceQuote, HoldingsSummary, ImpactPanel } from '../components'
import { useAsync } from '../hooks'

const HOW_LABEL: Record<string, string> = {
  supplier: 'supplier',
  manufacturing: 'manufacturing',
  major_market: 'major market',
  headquarters: 'headquarters',
}

/** Home screen: what the portfolio actually depends on. */
export function XRayPage({ holdings }: { holdings: string[] }) {
  const xray = useAsync(() => (holdings.length ? api.xray(holdings) : Promise.resolve(null)), holdings.join(','))
  const [open, setOpen] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const deps = xray.data?.dependencies ?? []
  const supported = xray.data?.holdings.length ?? 0
  const shared = deps.filter((d) => d.holding_count > 1)
  const shown = showAll ? deps : shared
  const openDep = deps.find((d) => d.id === open)

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Portfolio X-Ray</div>
        {xray.data ? (
          <div className="hero">
            <div className="big">
              Your {supported} holdings share <em>{shared.length} hidden {shared.length === 1 ? 'dependency' : 'dependencies'}</em>
            </div>
            {shared[0] && (
              <p className="secondary">
                The biggest: <strong>{shared[0].name}</strong>, which {shared[0].holding_count} of your {supported} holdings depend on.
              </p>
            )}
          </div>
        ) : <h1>What you actually depend on</h1>}
      </div>
      {holdings.length === 0 && <EmptyPortfolio />}
      {xray.data && <HoldingsSummary holdings={holdings} unsupported={xray.data.unsupported} />}
      {xray.error && <p className="error">{xray.error}</p>}
      {xray.data && (
        <>
          <div className="two-col">
            <section className="card" aria-label="Dependencies">
              <div className="card-label">What your portfolio depends on</div>
              <p className="small muted" style={{ marginTop: 0 }}>Suppliers and countries, from SEC filings. Click one to see the evidence.</p>
              <div className="dep-list">
                {shown.map((d) => (
                  <DependencyRow key={`${d.type}:${d.id}`} dep={d} total={supported}
                                 open={open === d.id} onToggle={() => setOpen(open === d.id ? null : d.id)} />
                ))}
              </div>
              <button className="ghost-btn small" onClick={() => setShowAll(!showAll)}>
                {showAll ? 'Show shared dependencies only' : `Show all ${deps.length} dependencies`}
              </button>
            </section>
            <aside className="card">
              {openDep?.type === 'company'
                ? <ImpactPanel company={openDep.id} holdings={holdings} />
                : <p className="secondary small">
                    Pick a supplier to see which of your holdings news about it would reach,
                    including through the supply chain.
                  </p>}
            </aside>
          </div>
        </>
      )}
      {xray.loading && !xray.data && <p className="muted">Loading…</p>}
    </>
  )
}

function DependencyRow({ dep, total, open, onToggle }: {
  dep: Dependency
  total: number
  open: boolean
  onToggle: () => void
}) {
  return (
    <>
      <button className={`dep-row ${open ? 'open' : ''}`} onClick={onToggle} aria-expanded={open}>
        <span>
          <span className="dep-name">{dep.name}</span>
          <div className="dep-type">
            {dep.type === 'country' ? 'Country' : dep.in_universe ? 'Supported company' : 'Outside company'}
            {dep.is_holding ? ' · you own it' : ''}
          </div>
        </span>
        <span className="bar-track" aria-hidden="true">
          <span className="bar-fill" style={{ display: 'block', width: `${(dep.holding_count / total) * 100}%` }} />
        </span>
        <span className="dep-count">{dep.holding_count} of {total}</span>
      </button>
      {open && (
        <div className="dep-detail">
          {dep.holdings.map((h) => (
            <div key={h.ticker}>
              <strong>{h.ticker}</strong>{' '}
              <span className="small muted">{h.how.map((x) => HOW_LABEL[x] ?? x).join(', ')}</span>
              {h.evidence.map((p, i) => <EvidenceQuote key={i} p={p} />)}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
