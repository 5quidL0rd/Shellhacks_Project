import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { api, type MapLink, type MapNode, type UniverseCompany } from '../api'
import { EmptyPortfolio, HoldingsSummary, ImpactPanel } from '../components'
import { useAsync, useSize, useThemeColors } from '../hooks'

type GNode = MapNode & { x?: number; y?: number }
type GLink = Omit<MapLink, 'source' | 'target'> & { source: string | GNode; target: string | GNode }

const TOKENS = ['series-1', 'series-2', 'series-3', 'neutral-node', 'text-primary',
  'text-secondary', 'text-muted', 'grid', 'surface', 'focus', 'font']

const endId = (end: string | GNode) => (typeof end === 'string' ? end : end.id)

/** Interactive map of the holdings and everything one step away. */
export function MapPage({ holdings }: { holdings: string[] }) {
  const [countries, setCountries] = useState(true)
  const [competitors, setCompetitors] = useState(true)
  const [sharedOnly, setSharedOnly] = useState(holdings.length > 12)
  // Holdings hidden from the map. Stored as exclusions so newly added
  // holdings show up without extra clicks.
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<GNode | null>(null)
  const focused = holdings.filter((h) => !hidden.has(h))
  const map = useAsync(
    () => (focused.length ? api.map(focused, { countries, competitors }) : Promise.resolve(null)),
    `${focused.join(',')}|${countries}|${competitors}`)
  const colors = useThemeColors(TOKENS)
  const graph = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined)
  const settled = useRef(false)
  const { measure, width, height } = useSize<HTMLDivElement>()
  const mounted = width > 0 // the graph only renders once its box has a size

  // A fresh copy per load: the force layout mutates nodes and links in place.
  // "Shared only" keeps holdings plus what at least two focused holdings share,
  // which is what keeps a 40-holding map readable.
  const graphData = useMemo(() => {
    const keep = (n: MapNode) => !sharedOnly || n.is_holding || n.connected_holdings.length >= 2
    const nodes = (map.data?.nodes ?? []).filter(keep).map((n) => ({ ...n })) as GNode[]
    const ids = new Set(nodes.map((n) => n.id))
    const links = (map.data?.links ?? [])
      .filter((l) => ids.has(l.source) && ids.has(l.target))
      .map((l) => ({ ...l })) as GLink[]
    return { nodes, links }
  }, [map.data, sharedOnly])

  // Spread the layout out: the defaults pack ~70 nodes into a tight ball.
  useEffect(() => {
    const fg = graph.current
    if (!fg) return
    settled.current = false
    fg.d3Force('charge')?.strength(-260)
    fg.d3Force('link')?.distance(70)
    fg.d3ReheatSimulation()
    // Fit once the layout has mostly settled (onEngineStop fits again at the end).
    const timer = setTimeout(() => graph.current?.zoomToFit(500, 30), 1500)
    return () => clearTimeout(timer)
  }, [graphData, mounted])

  // A resize only needs a re-fit, not a new layout (and only once there is one).
  useEffect(() => {
    if (settled.current) graph.current?.zoomToFit(300, 30)
  }, [width, height])

  const highlight = useMemo(() => {
    if (!selected) return null
    const ids = new Set([selected.id])
    for (const l of graphData.links) {
      const [s, t] = [endId(l.source), endId(l.target)]
      if (s === selected.id) ids.add(t)
      if (t === selected.id) ids.add(s)
    }
    return ids
  }, [selected, graphData])

  const nodeColor = (n: GNode) =>
    n.type === 'country' ? colors['neutral-node']
      : n.is_holding ? colors['series-1']
        : n.in_universe ? colors['series-2'] : colors['series-3']
  const radius = (n: GNode) => (n.is_holding ? 7 : 4 + 1.5 * Math.min(n.connected_holdings.length, 5))

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Connection Map</div>
        <h1>How your holdings are linked</h1>
        <p>Suppliers, customers, competitors, and countries one step from what you own. Click a company to see which holdings its news would reach.</p>
      </div>
      {holdings.length === 0 ? <EmptyPortfolio /> : <HoldingsSummary holdings={holdings} unsupported={map.data?.unsupported} />}
      <div className="filters">
        <label><input type="checkbox" checked={sharedOnly} onChange={(e) => setSharedOnly(e.target.checked)} /> Shared only</label>
        <label><input type="checkbox" checked={countries} onChange={(e) => setCountries(e.target.checked)} /> Countries</label>
        <label><input type="checkbox" checked={competitors} onChange={(e) => setCompetitors(e.target.checked)} /> Competitors</label>
        <div className="legend" aria-label="Legend">
          <span><span className="swatch" style={{ background: colors['series-1'] }} />Your holdings</span>
          <span><span className="swatch" style={{ background: colors['series-2'] }} />Supported, not owned</span>
          <span><span className="swatch" style={{ background: colors['series-3'] }} />Outside company</span>
          <span><span className="swatch square" style={{ background: colors['neutral-node'] }} />Country</span>
          <span><span className="line-swatch" />Supplies (arrow → customer)</span>
          <span><span className="line-swatch dashed" />Competes / operates in</span>
        </div>
      </div>
      {map.error && <p className="error">{map.error}</p>}
      <div className="map-layout">
        <FocusRail holdings={holdings} hidden={hidden} setHidden={setHidden}
                   selectedId={selected?.id}
                   onPick={(t) => setSelected(graphData.nodes.find((n) => n.id === t) ?? null)} />
        <div className="card map-wrap" ref={measure}>
          {map.data && width > 0 && (
            <ForceGraph2D<GNode, GLink>
              ref={graph}
              graphData={graphData}
              onEngineStop={() => {
                // Fit once per layout. The event can fire again on interaction,
                // and re-fitting then moves nodes out from under the cursor.
                if (settled.current) return
                settled.current = true
                graph.current?.zoomToFit(400, 30)
              }}
              width={width}
              height={height}
              backgroundColor={colors.surface}
              cooldownTicks={120}
              nodeRelSize={1}
              nodeVal={(n) => radius(n) ** 2}
              nodeLabel={(n) => `${n.name}${n.connected_holdings.length ? ` · connected to ${n.connected_holdings.join(', ')}` : ''}`}
              linkColor={(l) => {
                const lit = !highlight || (highlight.has(endId(l.source)) && highlight.has(endId(l.target)))
                if (!lit) return colors.grid
                return l.type === 'supplies' ? colors['text-secondary'] : colors['text-muted']
              }}
              linkLineDash={(l) => (l.type === 'supplies' ? null : [3, 3])}
              linkWidth={(l) => (l.type === 'supplies' ? 1.5 : 1)}
              linkDirectionalArrowLength={(l) => (l.type === 'supplies' ? 4 : 0)}
              linkDirectionalArrowRelPos={0.9}
              onNodeClick={(n) => setSelected(selected?.id === n.id ? null : n)}
              onBackgroundClick={() => setSelected(null)}
              nodeCanvasObject={(n, ctx, scale) => {
                const r = radius(n)
                const dim = highlight && !highlight.has(n.id)
                ctx.globalAlpha = dim ? 0.2 : 1
                ctx.fillStyle = nodeColor(n)
                ctx.beginPath()
                if (n.type === 'country') ctx.rect(n.x! - r, n.y! - r, 2 * r, 2 * r)
                else ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI)
                ctx.fill()
                // 2px surface ring so overlapping nodes stay distinct.
                ctx.lineWidth = 2 / scale
                ctx.strokeStyle = colors.surface
                ctx.stroke()
                // Holdings get an outer ring: the second cue that keeps them
                // distinct from outside companies for color-blind readers.
                if (n.is_holding) {
                  ctx.lineWidth = 1.5 / scale
                  ctx.strokeStyle = colors['series-1']
                  ctx.beginPath()
                  ctx.arc(n.x!, n.y!, r + 2.5, 0, 2 * Math.PI)
                  ctx.stroke()
                }
                if (selected?.id === n.id) {
                  ctx.lineWidth = 2 / scale
                  ctx.strokeStyle = colors.focus
                  ctx.beginPath()
                  ctx.arc(n.x!, n.y!, r + 3, 0, 2 * Math.PI)
                  ctx.stroke()
                }
                // Label holdings, supported companies, countries, and outside
                // companies shared by 3+ holdings; the rest when highlighted or
                // on hover (nodeLabel), so the center doesn't turn into a smear.
                const label = n.is_holding || n.in_universe || n.type === 'country'
                  || n.connected_holdings.length >= 3 || (highlight && !dim)
                if (label) {
                  const text = n.type === 'company' && n.in_universe ? n.id : n.name
                  ctx.font = `${n.is_holding ? 700 : 400} ${11 / scale}px ${colors.font}`
                  ctx.textAlign = 'center'
                  ctx.textBaseline = 'top'
                  ctx.fillStyle = n.is_holding ? colors['text-primary'] : colors['text-secondary']
                  ctx.fillText(text.length > 24 ? `${text.slice(0, 22)}…` : text, n.x!, n.y! + r + 2 / scale)
                }
                ctx.globalAlpha = 1
              }}
              nodePointerAreaPaint={(n, color, ctx) => {
                ctx.fillStyle = color
                ctx.beginPath()
                ctx.arc(n.x!, n.y!, radius(n) + 4, 0, 2 * Math.PI) // hit target bigger than the mark
                ctx.fill()
              }}
            />
          )}
          {map.loading && <p className="muted" style={{ padding: 16 }}>Loading…</p>}
          {!map.loading && holdings.length > 0 && focused.length === 0 && (
            <p className="muted" style={{ padding: 16 }}>Check holdings on the left to put them on the map.</p>
          )}
        </div>
        <aside className="card">
          {!selected && (
            <p className="secondary small">
              Click any company to see which of your holdings its news would reach. Bigger dots are
              connected to more of your holdings.
            </p>
          )}
          {selected?.type === 'company' && <ImpactPanel company={selected.id} holdings={holdings} />}
          {selected?.type === 'country' && (
            <>
              <h2>{selected.name}</h2>
              <p className="secondary small">
                {selected.connected_holdings.length} of your holdings manufacture in, sell into, or are
                headquartered in {selected.name}: {selected.connected_holdings.join(', ')}.
              </p>
            </>
          )}
        </aside>
      </div>
    </>
  )
}

/** Pick which holdings the map shows. Grouped by sector, searchable, with
 * all/none, so it stays usable with dozens of holdings. Clicking a name
 * selects that holding on the map. */
function FocusRail({ holdings, hidden, setHidden, selectedId, onPick }: {
  holdings: string[]
  hidden: Set<string>
  setHidden: (s: Set<string>) => void
  selectedId?: string
  onPick: (ticker: string) => void
}) {
  const universe = useAsync(api.universe, 'universe')
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const bySymbol = new Map((universe.data ?? []).map((c: UniverseCompany) => [c.symbol, c]))
  const groups = new Map<string, string[]>()
  for (const t of [...holdings].sort()) {
    const c = bySymbol.get(t)
    if (q && !t.toLowerCase().includes(q) && !(c?.name.toLowerCase().includes(q))) continue
    const sector = c?.sector ?? 'Other'
    groups.set(sector, [...(groups.get(sector) ?? []), t])
  }
  const shown = holdings.length - hidden.size
  const flip = (tickers: string[], show: boolean) => {
    const next = new Set(hidden)
    for (const t of tickers) {
      if (show) next.delete(t)
      else next.add(t)
    }
    setHidden(next)
  }

  return (
    <aside className="card focus-rail" aria-label="Holdings on the map">
      <div className="row-between">
        <div className="card-label" style={{ margin: 0 }}>On the map · {shown}/{holdings.length}</div>
      </div>
      <div className="row" style={{ margin: '8px 0' }}>
        <button className="ghost-btn" onClick={() => setHidden(new Set())}>All</button>
        <button className="ghost-btn" onClick={() => setHidden(new Set(holdings))}>None</button>
      </div>
      {holdings.length > 8 && (
        <input type="search" className="search" placeholder="Filter holdings" value={query}
               onChange={(e) => setQuery(e.target.value)} aria-label="Filter holdings" />
      )}
      <div className="focus-list">
        {[...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([sector, tickers]) => {
          const on = tickers.filter((t) => !hidden.has(t)).length
          return (
            <div key={sector} className="sector-group">
              <label className="sector-head">
                <input type="checkbox" checked={on === tickers.length}
                       ref={(el) => { if (el) el.indeterminate = on > 0 && on < tickers.length }}
                       onChange={(e) => flip(tickers, e.target.checked)} />
                <span>{sector}</span>
                <span className="muted small">{on}/{tickers.length}</span>
              </label>
              {tickers.map((t) => (
                <div key={t} className={`focus-item ${selectedId === t ? 'active' : ''}`}>
                  <input type="checkbox" checked={!hidden.has(t)} aria-label={`Show ${t} on the map`}
                         onChange={(e) => flip([t], e.target.checked)} />
                  <button className="link-btn" disabled={hidden.has(t)} onClick={() => onPick(t)}
                          title={bySymbol.get(t)?.name}>{t}</button>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
