import { createChart, createSeriesMarkers, LineSeries, type ISeriesMarkersPluginApi, type Time } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Beat, type Evidence, type Story } from '../api'
import { AsOf, Change, Cite, CiteGuide } from '../components'
import { EVIDENCE_LABEL } from '../evidence'
import { money } from '../format'
import { useAsync, useThemeColors } from '../hooks'
import { RevenueMixCard } from '../RevenueMix'

const TOKENS = ['price-line', 'up', 'down', 'text-muted', 'grid', 'baseline', 'surface', 'font']

/** Story Mode: a stock's price with each major move explained and cited. */
export function StoryPage() {
  const { symbol = '' } = useParams()
  const story = useAsync(() => api.story(symbol), symbol)
  const quotes = useAsync(api.quotes, 'quotes')
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
      <div className="page-head">
        <div className="eyebrow"><Link to="/">Portfolio</Link> / Story Mode</div>
        <h1>{s.company_name} <span className="muted">{s.symbol}</span></h1>
        {quotes.data?.quotes[s.symbol] && (
          <div className="quote-line">
            <span className="price">{money(quotes.data.quotes[s.symbol].price)}</span>
            <Change pct={quotes.data.quotes[s.symbol].change_pct} suffix=" today" />
            <AsOf date={quotes.data.as_of} />
          </div>
        )}
      </div>
      <p className="secondary" style={{ maxWidth: 820, marginTop: 0 }}>
        {s.arc}
        {s.arc_citation_ids.map((id, i) => (
          <Cite key={id} n={i + 1} id={id} active={citation === id} onClick={setCitation} evidence={s.evidence[id]} />
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
          <section className="card" aria-label="Who pays it" style={{ marginBottom: 16 }}>
            <RevenueMixCard ticker={s.symbol} />
          </section>
          <section className="card" aria-label="Major moves">
            <div className="card-label">Major moves</div>
            {s.beats.map((b) => (
              <BeatItem key={b.date} beat={b} selected={selected === b.date} citation={citation}
                        evidence={s.evidence} onSelect={() => setSelected(b.date)} onCite={setCitation} />
            ))}
          </section>
        </div>
        <aside className="card" style={{ position: 'sticky', top: 16 }}>
          {citation && s.evidence[citation]
            ? <EvidencePanel e={s.evidence[citation]} onClose={() => setCitation(null)} />
            : <CiteGuide kinds={[...s.arc_citation_ids, ...s.beats.flatMap((b) => b.citation_ids)]
                .map((id) => s.evidence[id]?.kind).filter(Boolean) as string[]} />}
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
      layout: { background: { color: colors.surface }, textColor: colors['text-muted'], fontFamily: colors.font, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: colors.grid } },
      rightPriceScale: { borderColor: colors.baseline },
      timeScale: { borderColor: colors.baseline },
      crosshair: { horzLine: { labelBackgroundColor: colors['price-line'] }, vertLine: { labelBackgroundColor: colors['price-line'] } },
    })
    const series = chart.addSeries(LineSeries, { color: colors['price-line'], lineWidth: 2, priceLineVisible: false })
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

function BeatItem({ beat, selected, citation, evidence, onSelect, onCite }: {
  beat: Beat
  selected: boolean
  citation: string | null
  evidence: Story['evidence']
  onSelect: () => void
  onCite: (id: string | null) => void
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
          <Cite key={id} n={i + 1} id={id} active={citation === id} onClick={onCite} evidence={evidence[id]} />
        ))}
      </div>
    </div>
  )
}

function EvidencePanel({ e, onClose }: { e: Evidence; onClose: () => void }) {
  const numbers = Object.entries(e.numbers)
  return (
    <div>
      <div className="role">{EVIDENCE_LABEL[e.kind] ?? e.kind} · {e.occurred_on}</div>
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
      <div className="row-between">
        <button className="ghost-btn small" onClick={onClose}>Close</button>
        <span className="small muted">Click the highlighted citation again for the guide</span>
      </div>
    </div>
  )
}
