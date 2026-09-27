import { useEffect, useMemo, useState } from 'react'
import { api, type MapLink, type MapNode, type PortfolioMap } from '../api'
import { EmptyPortfolio, HoldingsSummary, ImpactPanel } from '../components'
import { useAsync } from '../hooks'

type ConnectionKind = 'Suppliers' | 'Customers' | 'Competitors' | 'Markets'

type Connection = { other: MapNode; kind: ConnectionKind; link: MapLink }

const COLORS: Record<ConnectionKind, string> = {
  Suppliers: '#0086a4', Customers: '#52ab98', Competitors: '#d9531e', Markets: '#9c6ad6',
}

const kindFor = (ticker: string, link: MapLink): ConnectionKind => {
  if (link.type === 'competes_with') return 'Competitors'
  if (link.type === 'operates_in') return 'Markets'
  return link.target === ticker ? 'Suppliers' : 'Customers'
}

/** A visual, one-holding-at-a-time view of the existing cited map data. */
export function MapPage({ holdings }: { holdings: string[] }) {
  const [ticker, setTicker] = useState(holdings[0] ?? '')
  const [activeKind, setActiveKind] = useState<ConnectionKind | null>(null)
  const [selected, setSelected] = useState<MapNode | null>(null)
  const map = useAsync(
    () => (holdings.length ? api.map(holdings, { countries: true, competitors: true }) : Promise.resolve(null)),
    holdings.join(','),
  )

  useEffect(() => { if (!holdings.includes(ticker)) setTicker(holdings[0] ?? '') }, [holdings, ticker])

  const connections = useMemo(() => makeConnections(map.data, ticker), [map.data, ticker])
  const groups = useMemo(() => groupConnections(connections), [connections])
  const visibleKinds = activeKind ? [activeKind] : Object.keys(groups) as ConnectionKind[]
  const visibleConnections = visibleKinds.flatMap((kind) => groups[kind] ?? [])
  const selectedName = map.data?.nodes.find((node) => node.id === ticker)?.name ?? ticker

  useEffect(() => { setActiveKind(null); setSelected(null) }, [ticker])

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Connection Map</div>
        <h1>Explore a holding’s connections</h1>
        <p>Choose one investment to see the suppliers, customers, competitors, and markets connected to it. Select a section or connection for the supporting detail.</p>
      </div>
      {holdings.length === 0 ? <EmptyPortfolio /> : <HoldingsSummary holdings={holdings} unsupported={map.data?.unsupported} />}
      {map.error && <p className="error">{map.error}</p>}
      {map.loading && <p className="muted">Loading connections…</p>}
      {map.data && ticker && (
        <div className="connection-explorer">
          <section className="card explorer-selector">
            <label htmlFor="map-holding" className="card-label">Choose a holding</label>
            <select id="map-holding" value={ticker} onChange={(event) => setTicker(event.target.value)}>
              {holdings.map((symbol) => {
                const node = map.data!.nodes.find((item) => item.id === symbol)
                return <option key={symbol} value={symbol}>{symbol} — {node?.name ?? symbol}</option>
              })}
            </select>
            <p className="secondary small">Showing direct relationships recorded for <strong>{selectedName}</strong>.</p>
          </section>

          <div className="explorer-layout">
            <section className="card donut-card">
              <div className="card-label">Connection mix</div>
              <h2>What {ticker} is connected to</h2>
              <DonutChart groups={groups} activeKind={activeKind} onSelect={setActiveKind} />
              <p className="secondary small chart-note">Each section is the share of saved direct connections, not an estimate of financial impact.</p>
            </section>

            <section className="card connection-list">
              <div className="row-between">
                <div><div className="card-label">{activeKind ?? 'All connections'}</div><h2>{activeKind ? `${activeKind} linked to ${ticker}` : `Direct connections to ${ticker}`}</h2></div>
                {activeKind && <button className="ghost-btn" onClick={() => setActiveKind(null)}>Show all</button>}
              </div>
              {visibleConnections.length === 0 ? <p className="secondary">No saved connections in this category.</p> : (
                <div className="connection-entities">
                  {visibleConnections.map(({ other, kind, link }) => (
                    <button className={`connection-entity ${selected?.id === other.id ? 'active' : ''}`} key={`${kind}-${link.source}-${link.target}-${other.id}`}
                            onClick={() => setSelected(other)}>
                      <span className="entity-dot" style={{ background: COLORS[kind] }} />
                      <span><strong>{other.name}</strong><small>{entityExplanation(ticker, kind)}</small></span>
                      <span className="entity-arrow">›</span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <aside className="card explorer-detail">
              {!selected && <><div className="card-label">Select a connection</div><h2>Why it matters</h2><p className="secondary small">Click a chart section to focus the list, then select a company or market to see which portfolio holdings it reaches and the evidence behind it.</p></>}
              {selected?.type === 'company' && <ImpactPanel company={selected.id} holdings={holdings} />}
              {selected?.type === 'country' && <><div className="card-label">Market exposure</div><h2>{selected.name}</h2><p className="secondary small">Saved connections show exposure to {selected.name} for: {selected.connected_holdings.join(', ')}.</p></>}
            </aside>
          </div>
        </div>
      )}
    </>
  )
}

function makeConnections(map: PortfolioMap | null, ticker: string): Connection[] {
  if (!map) return []
  const byId = new Map(map.nodes.map((node) => [node.id, node]))
  const seen = new Set<string>()
  return map.links.flatMap((link) => {
    if (link.source !== ticker && link.target !== ticker) return []
    const other = byId.get(link.source === ticker ? link.target : link.source)
    if (!other) return []
    const kind = kindFor(ticker, link)
    const key = `${kind}-${other.id}`
    if (seen.has(key)) return []
    seen.add(key)
    return [{ other, kind, link }]
  })
}

function groupConnections(connections: Connection[]): Partial<Record<ConnectionKind, Connection[]>> {
  return connections.reduce<Partial<Record<ConnectionKind, Connection[]>>>((groups, connection) => {
    ;(groups[connection.kind] ??= []).push(connection)
    return groups
  }, {})
}

function entityExplanation(ticker: string, kind: ConnectionKind) {
  if (kind === 'Suppliers') return `Input to ${ticker}`
  if (kind === 'Customers') return `Customer linked to ${ticker}`
  if (kind === 'Competitors') return `Competes with ${ticker}`
  return `${ticker} has exposure to this market`
}

function DonutChart({ groups, activeKind, onSelect }: {
  groups: Partial<Record<ConnectionKind, Connection[]>>
  activeKind: ConnectionKind | null
  onSelect: (kind: ConnectionKind | null) => void
}) {
  const entries = (Object.keys(COLORS) as ConnectionKind[])
    .map((kind) => ({ kind, count: groups[kind]?.length ?? 0 })).filter((entry) => entry.count > 0)
  const total = entries.reduce((sum, entry) => sum + entry.count, 0)
  let progress = 0
  return (
    <div className="donut-wrap">
      <div className="donut" role="img" aria-label={`${total} saved direct connections`}>
        <svg viewBox="0 0 42 42" aria-hidden="true">
          {entries.map(({ kind, count }) => {
            const share = (count / total) * 100
            const offset = 25 - progress
            progress += share
            return <circle key={kind} className={activeKind && activeKind !== kind ? 'dim' : ''}
              cx="21" cy="21" r="15.9155" fill="transparent" stroke={COLORS[kind]} strokeWidth="6"
              strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={offset}
              onClick={() => onSelect(activeKind === kind ? null : kind)} />
          })}
        </svg>
        <div className="donut-center"><strong>{total}</strong><span>direct links</span></div>
      </div>
      <div className="donut-legend">
        {entries.map(({ kind, count }) => <button key={kind} className={activeKind === kind ? 'active' : ''}
          onClick={() => onSelect(activeKind === kind ? null : kind)}>
          <span className="legend-dot" style={{ background: COLORS[kind] }} /><span>{kind}</span><strong>{count}</strong>
        </button>)}
      </div>
    </div>
  )
}
