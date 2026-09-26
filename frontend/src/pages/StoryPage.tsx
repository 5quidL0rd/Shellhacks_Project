import { createChart, createSeriesMarkers, LineSeries, type ISeriesMarkersPluginApi, type Time } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Beat, type Evidence, type Story } from '../api'
import { useAsync, useThemeColors } from '../hooks'

const TOKENS = ['series-1', 'up', 'down', 'text-muted', 'grid', 'baseline', 'surface']

/** Story Mode: a stock's price with each major move explained and cited. */
export function StoryPage() {
  const { symbol = '' } = useParams()
  const story = useAsync(() => api.story(symbol), symbol)
  const [selected, setSelected] = useState<string | null>(null)
  const [citation, setCitation] = useState<string | null>(null)

  if (story.error) return <p className="error">{story.error}</p>
  if (!story.data) return <p className="muted">Loading {symbol}…</p>
  const s = story.data
  const selectBeat = (date: string) => {
    setSelected(date)
    document.getElementById(`beat-${date}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  return (
    <>
      <p className="small"><Link to="/">← My portfolio</Link></p>
      <h1>{s.company_name} <span className="muted">{s.symbol}</span></h1>
      <p className="secondary" style={{ maxWidth: 820 }}>
        {s.arc}
        {s.arc_citation_ids.map((id, i) => (
          <CiteButton key={id} n={i + 1} id={id} active={citation === id} onClick={setCitation} />
        ))}
      </p>
      <div className="two-col">
        <div>
          <div className="card chart-box">
            <PriceChart story={s} selected={selected} onSelect={selectBeat} />
          </div>
          <p className="small muted">
            ▲▼ mark the {s.beats.length} biggest moves. Click a marker or a move below to read why it happened.
          </p>
          <section className="card" aria-label="Major moves">
            {s.beats.map((b) => (
              <BeatItem key={b.date} beat={b} selected={selected === b.date} citation={citation}
                        onSelect={() => setSelected(b.date)} onCite={setCitation} />
            ))}
          </section>
        </div>
        <aside className="card" style={{ position: 'sticky', top: 16 }}>
          {citation && s.evidence[citation]
            ? <EvidencePanel e={s.evidence[citation]} onClose={() => setCitation(null)} />
            : <p className="secondary small">
                Every explanation cites the evidence it was written from. Click a numbered citation to see the
                source.
              </p>}
        </aside>
      </div>
    </>
  )
}

function PriceChart({ story, selected, onSelect }: {
  story: Story
  selected: string | null
  onSelect: (date: string) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])
  const colors = useThemeColors(TOKENS)

  // Build the chart once per story (and when the theme changes).
  useEffect(() => {
    if (!box.current) return
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { color: colors.surface }, textColor: colors['text-muted'], attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: colors.grid } },
      rightPriceScale: { borderColor: colors.baseline },
      timeScale: { borderColor: colors.baseline },
      crosshair: { horzLine: { labelBackgroundColor: colors['series-1'] }, vertLine: { labelBackgroundColor: colors['series-1'] } },
    })
    const series = chart.addSeries(LineSeries, { color: colors['series-1'], lineWidth: 2, priceLineVisible: false })
    series.setData(story.bars.map((b) => ({ time: b.date as Time, value: b.close })))
    markersRef.current = createSeriesMarkers(series, [])
    chart.timeScale().fitContent()
    // Clicking within three days of a marker selects that move.
    chart.subscribeClick((param) => {
      if (typeof param.time !== 'string') return
      const clicked = new Date(param.time).getTime()
      const nearest = story.beats
        .map((b) => ({ date: b.date, gap: Math.abs(new Date(b.date).getTime() - clicked) / 86_400_000 }))
        .sort((a, b) => a.gap - b.gap)[0]
      if (nearest && nearest.gap <= 3) onSelectRef.current(nearest.date)
    })
    return () => {
      markersRef.current = null
      chart.remove()
    }
  }, [story, colors])

  // Markers change with the selection; the chart itself does not.
  useEffect(() => {
    markersRef.current?.setMarkers(story.beats.map((b, i) => ({
      time: b.date as Time,
      position: b.direction === 'up' ? 'belowBar' : 'aboveBar',
      shape: b.direction === 'up' ? 'arrowUp' : 'arrowDown',
      color: b.direction === 'up' ? colors.up : colors.down,
      text: String(i + 1),
      size: selected === b.date ? 2 : 1,
    })))
  }, [story, colors, selected])

  return <div ref={box} style={{ width: '100%', height: '100%' }} />
}

function BeatItem({ beat, selected, citation, onSelect, onCite }: {
  beat: Beat
  selected: boolean
  citation: string | null
  onSelect: () => void
  onCite: (id: string) => void
}) {
  const sign = beat.pct_change > 0 ? '+' : ''
  return (
    <div id={`beat-${beat.date}`} className={`beat ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="beat-head">
        <span className={`move ${beat.direction}`}>{beat.direction === 'up' ? '▲' : '▼'} {sign}{beat.pct_change.toFixed(2)}%</span>
        <span className="small muted">{beat.date}</span>
        <span className="confidence" title="How well the evidence explains the move">{beat.confidence} confidence</span>
      </div>
      <div style={{ fontWeight: 600 }}>{beat.headline}</div>
      <div className="small secondary">
        {beat.explanation}
        {beat.citation_ids.map((id, i) => (
          <CiteButton key={id} n={i + 1} id={id} active={citation === id} onClick={onCite} />
        ))}
      </div>
    </div>
  )
}

function CiteButton({ n, id, active, onClick }: { n: number; id: string; active: boolean; onClick: (id: string) => void }) {
  return (
    <button className={`cite ${active ? 'active' : ''}`} aria-label={`Citation ${n}`}
            onClick={(e) => { e.stopPropagation(); onClick(id) }}>{n}</button>
  )
}

const KIND_LABEL: Record<Evidence['kind'], string> = {
  news: 'News article',
  filing: 'SEC filing',
  price: 'Price move',
  fundamental: 'Quarterly results',
  peer_move: 'Connected company',
  sector: 'Industry data',
}

function EvidencePanel({ e, onClose }: { e: Evidence; onClose: () => void }) {
  const numbers = Object.entries(e.numbers)
  return (
    <div>
      <div className="role">{KIND_LABEL[e.kind] ?? e.kind} · {e.occurred_on}</div>
      <h2 style={{ marginTop: 4 }}>{e.title}</h2>
      {e.detail && <p className="small secondary">{e.detail}</p>}
      {numbers.length > 0 && (
        <dl className="numbers">
          {numbers.map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{typeof v === 'number' ? v.toLocaleString() : v}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="small">
        {e.url ? <a href={e.url} target="_blank" rel="noreferrer">Open source · {e.source}</a> : e.source}
      </p>
      <button className="ghost-btn small" onClick={onClose}>Close</button>
    </div>
  )
}
