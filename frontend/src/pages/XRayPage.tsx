import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type Dependency, type Quote, type RevenueMix } from '../api'
import { AsOf, Change, EmptyPortfolio, EvidenceQuote, HoldingsSummary, ImpactPanel } from '../components'
import { useAsync } from '../hooks'
import { RevenueMixPanel } from '../RevenueMix'

const HOW_LABEL: Record<string, string> = {
  supplier: 'supplier',
  manufacturing: 'manufacturing',
  major_market: 'major market',
  headquarters: 'headquarters',
}

type View = 'depends' | 'customers'

/** Home screen: what the portfolio actually depends on, from both sides -
 * what its companies rely on (suppliers, countries) and who they rely on for
 * revenue (their big customers). Findings first, then one list at a time with
 * a detail panel for whatever is picked. */
export function XRayPage({ holdings }: { holdings: string[] }) {
  const xray = useAsync(() => (holdings.length ? api.xray(holdings) : Promise.resolve(null)), holdings.join(','))
  const quotes = useAsync(api.quotes, 'quotes')
  const mixes = useAsync(
    () => Promise.all(holdings.map((h) => api.revenueMix(h).catch(() => null))),
    `mix:${holdings.join(',')}`,
  )
  // The view lives in the URL so a link can open the customer side directly.
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'customers' ? 'customers' : 'depends'
  const setView = (v: View) => setParams(v === 'customers' ? { view: v } : {}, { replace: true })
  const [openDep, setOpenDep] = useState<string | null>(null)
  const [pickedHolding, setPickedHolding] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const deps = xray.data?.dependencies ?? []
  const supported = xray.data?.holdings ?? []
  const shared = deps.filter((d) => d.holding_count > 1)
  const topSupplier = shared.find((d) => d.type === 'company')
  const topCountry = shared.find((d) => d.type === 'country')

  const rows = supported.map((t) => ({ ticker: t, mix: mixes.data?.[holdings.indexOf(t)] ?? null }))
  rows.sort((a, b) => rank(b.mix) - rank(a.mix))
  const reliant = rows.filter((r) => r.mix?.slices.length)
  const mostReliant = reliant[0]
  const selectedHolding = pickedHolding ?? mostReliant?.ticker ?? supported[0]
  const selectedMix = rows.find((r) => r.ticker === selectedHolding)?.mix

  const goDep = (id: string) => { setView('depends'); setOpenDep(id) }
  const goHolding = (t: string) => { setView('customers'); setPickedHolding(t) }

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Portfolio X-Ray</div>
        {xray.data ? (
          <div className="hero">
            <div className="big">
              Your {supported.length} holdings share <em>{shared.length} hidden {shared.length === 1 ? 'dependency' : 'dependencies'}</em>
            </div>
            {mixes.data && (
              <p className="secondary">
                {reliant.length
                  ? <>{reliant.length} of them get 10% or more of their revenue from a single customer.</>
                  : <>None of them reports a single customer worth 10% or more of revenue.</>}
              </p>
            )}
            <AsOf date={quotes.data?.as_of} />
          </div>
        ) : <h1>What you actually depend on</h1>}
      </div>
      {holdings.length === 0 && <EmptyPortfolio />}
      {xray.data && <HoldingsSummary holdings={holdings} unsupported={xray.data.unsupported} />}
      {xray.error && <p className="error">{xray.error}</p>}

      {xray.data && (
        <>
          <section className="glance" aria-label="At a glance">
            {topSupplier && (
              <Tile label="Most shared supplier" value={shortName(topSupplier.name)}
                    detail={`${topSupplier.holding_count} of your ${supported.length} holdings rely on it`}
                    onClick={() => goDep(topSupplier.id)} />
            )}
            {topCountry && (
              <Tile label="Most shared country" value={topCountry.name}
                    detail={`${topCountry.holding_count} of your ${supported.length} holdings make or sell there`}
                    onClick={() => goDep(topCountry.id)} />
            )}
            {mostReliant?.mix ? (
              <Tile label="Most reliant on one customer" value={`${mostReliant.ticker} · ${topShare(mostReliant.mix)}`}
                    detail={`of its revenue comes from ${mostReliant.mix.slices[0].named ? mostReliant.mix.slices[0].label : 'one unnamed customer'}`}
                    onClick={() => goHolding(mostReliant.ticker)} />
            ) : mixes.loading ? (
              <Tile label="Most reliant on one customer" value="…" detail="Reading annual reports" />
            ) : null}
            {mixes.data && (
              <Tile label="Holdings with a 10%+ customer" value={`${reliant.length} of ${supported.length}`}
                    detail="from their own filings" onClick={() => setView('customers')} />
            )}
          </section>

          <div className="view-tabs" role="tablist" aria-label="X-Ray view">
            <button role="tab" aria-selected={view === 'depends'} className={view === 'depends' ? 'active' : ''}
                    onClick={() => setView('depends')}>
              What they depend on <span className="tab-count">{shared.length} shared</span>
            </button>
            <button role="tab" aria-selected={view === 'customers'} className={view === 'customers' ? 'active' : ''}
                    onClick={() => setView('customers')}>
              Who pays them <span className="tab-count">{mixes.data ? `${reliant.length} with a big customer` : '…'}</span>
            </button>
          </div>

          <div className="two-col xray-layout">
            {view === 'depends' ? (
              <section className="card xray-deps" aria-label="Dependencies">
                <p className="small muted" style={{ marginTop: 0 }}>
                  Suppliers and countries your holdings rely on, from SEC filings, most shared first. Click one to see
                  the evidence.
                </p>
                <div className="dep-list">
                  {(showAll ? deps : shared).map((d) => (
                    <DependencyRow key={`${d.type}:${d.id}`} dep={d} total={supported.length} quote={quotes.data?.quotes[d.id]}
                                   open={openDep === d.id} onToggle={() => setOpenDep(openDep === d.id ? null : d.id)} />
                  ))}
                </div>
                <button className="ghost-btn small" onClick={() => setShowAll(!showAll)}>
                  {showAll ? 'Show shared dependencies only' : `Show all ${deps.length} dependencies`}
                </button>
              </section>
            ) : (
              <section className="card xray-deps" aria-label="Who pays your holdings">
                <p className="small muted" style={{ marginTop: 0 }}>
                  Each holding's revenue by customer, from its own annual report, most concentrated first. Teal is
                  a disclosed customer; gray is everyone else. Click one for the breakdown and quotes.
                </p>
                {mixes.loading && <p className="muted small">Reading annual reports…</p>}
                <div className="dep-list">
                  {mixes.data && rows.map((r) => (
                    <CustomerRow key={r.ticker} ticker={r.ticker} mix={r.mix} selected={r.ticker === selectedHolding}
                                 onSelect={() => setPickedHolding(r.ticker)} />
                  ))}
                </div>
              </section>
            )}

            <aside className="card detail-panel">
              {view === 'depends'
                ? (() => {
                    const dep = deps.find((d) => d.id === openDep)
                    if (dep?.type === 'company') return <ImpactPanel company={dep.id} holdings={holdings} />
                    return (
                      <p className="secondary small">
                        {dep ? `${dep.name} is a country, so there is no company news to trace. ` : ''}
                        Pick a supplier to see which of your holdings news about it would reach, including through
                        the supply chain.
                      </p>
                    )
                  })()
                : selectedMix
                  ? <RevenueMixPanel mix={selectedMix} />
                  : <p className="secondary small">{mixes.loading ? 'Reading annual reports…' : `Could not read ${selectedHolding}'s filing.`}</p>}
            </aside>
          </div>
        </>
      )}
      {xray.loading && !xray.data && <p className="muted">Loading…</p>}
    </>
  )
}

function Tile({ label, value, detail, onClick }: { label: string; value: string; detail: string; onClick?: () => void }) {
  const body = (
    <>
      <span className="glance-label">{label}</span>
      <span className="glance-value">{value}</span>
      <span className="glance-detail">{detail}</span>
    </>
  )
  return onClick
    ? <button type="button" className="glance-tile" onClick={onClick}>{body}</button>
    : <div className="glance-tile">{body}</div>
}

/** "Taiwan Semiconductor Manufacturing Company Limited" is too long for a tile. */
function shortName(name: string) {
  return name.length > 28 ? name.replace(/\b(Company|Corporation|Limited|Ltd\.?|Inc\.?|Holdings?)\b/g, '').replace(/\s+/g, ' ').trim() : name
}

/** Sort key: the largest disclosed customer; "no big customer" above "unknown". */
function rank(m: RevenueMix | null) {
  if (!m) return -2
  if (m.slices.length) return Math.max(...m.slices.map((s) => s.percent))
  return m.status === 'none_above_threshold' ? 0 : -1
}

function topShare(m: RevenueMix) {
  const top = m.slices[0]
  return `${top.percent.toFixed(0)}%${top.at_least ? '+' : ''}`
}

function CustomerRow({ ticker, mix, selected, onSelect }: {
  ticker: string
  mix: RevenueMix | null
  selected: boolean
  onSelect: () => void
}) {
  const summary = !mix ? 'Filing could not be read'
    : mix.slices.length
      ? `${topShare(mix)} from ${mix.slices[0].named ? mix.slices[0].label : 'one customer'}${mix.slices.length > 1 ? ` · ${mix.slices.length} disclosed` : ''}`
      : mix.status === 'none_above_threshold' ? `No customer is ${mix.threshold ?? 10}%+`
      : mix.context.length ? 'Shares given only for groups'
      : 'No customer shares disclosed'
  return (
    <button className={`dep-row customer-row ${selected ? 'open' : ''}`} onClick={onSelect} aria-pressed={selected}>
      <span>
        <span className="dep-name">{ticker}</span>
        <div className="dep-type">{mix?.name ?? ''}</div>
      </span>
      <MixBar mix={mix} />
      <span className="dep-count">{summary}</span>
    </button>
  )
}

/** One holding's revenue as a thin 100% bar: disclosed customers in teal,
 * everyone else gray. Empty track when nothing is disclosed. */
function MixBar({ mix }: { mix: RevenueMix | null }) {
  const slices = mix?.slices ?? []
  const label = slices.length
    ? `${slices.map((s) => `${s.label} ${s.percent}%`).join(', ')}, others ${mix?.other?.percent ?? '?'}%`
    : mix?.status === 'none_above_threshold' ? 'No single customer is 10% or more of revenue' : 'Not disclosed'
  return (
    <span className="mix-bar" role="img" aria-label={label} title={label}>
      {slices.map((s, i) => (
        <span key={i} className="mix-bar-seg" style={{ width: `${s.percent}%` }} />
      ))}
      {mix?.other && mix.other.percent > 0 && (
        <span className="mix-bar-seg rest" style={{ flex: 1 }} />
      )}
    </span>
  )
}

function DependencyRow({ dep, total, open, onToggle, quote }: {
  dep: Dependency
  total: number
  quote?: Quote
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
          {/* Dependency pulse: how a supported supplier moved at the last close. */}
          {quote && (
            <div className="dep-pulse" title={`Last close ${quote.as_of}`}>
              <Change pct={quote.change_pct} suffix=" last close" />
            </div>
          )}
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
