import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type MixNote, type RevenueMix } from './api'
import { useAsync } from './hooks'

/** "22%" or "10%+" when the filing gave a floor. */
function pct(value: number, atLeast = false) {
  return `${value % 1 ? value.toFixed(1) : value.toFixed(0)}%${atLeast ? '+' : ''}`
}

/** Fetches and shows who pays one company. Any SEC ticker. */
export function RevenueMixCard({ ticker }: { ticker: string }) {
  const mix = useAsync(() => api.revenueMix(ticker), ticker)
  if (mix.loading) {
    return <p className="muted small">Reading {ticker}'s annual report… (the first read of a company takes up to a minute)</p>
  }
  if (mix.error) return <p className="error small">{mix.error}</p>
  return <RevenueMixPanel mix={mix.data!} />
}

/** Who pays a company, from its own annual report: each disclosed customer's
 * share of revenue as a donut slice, the rest as "all other customers". */
export function RevenueMixPanel({ mix, name }: { mix: RevenueMix; name?: string }) {
  const [active, setActive] = useState<number | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const who = name ?? mix.name ?? mix.ticker ?? 'this company'
  const chartable = mix.status === 'disclosed' || mix.status === 'none_above_threshold'

  return (
    <div className="mix">
      <div className="mix-head">
        <div>
          <h2>Who pays {who}</h2>
          <p className="small muted" style={{ margin: 0 }}>
            Share of revenue by customer{mix.period ? `, ${mix.period}` : ''}
            {mix.url && <> · <a href={mix.url} target="_blank" rel="noreferrer">{mix.form} filed {mix.filing_date}</a></>}
          </p>
        </div>
      </div>

      {!mix.available && <p className="secondary small">{mix.summary}</p>}
      {mix.status === 'not_disclosed' && (
        <p className="secondary small">
          {mix.context.length
            ? 'Its annual report gives shares only for groups of customers, not for any one of them. They are listed below.'
            : "Its annual report states no customer's share of revenue, and does not say that none is large."}
        </p>
      )}
      {mix.status === 'overlapping' && (
        <p className="secondary small">
          The disclosed shares add up to more than 100%, so they overlap in a way the filing does not
          explain. They are listed below instead of drawn.
        </p>
      )}

      {(chartable || mix.status === 'overlapping') && (
        <div className={chartable ? 'mix-body' : ''}>
          {chartable && <Donut mix={mix} active={active} setActive={setActive} />}
          <table className="mix-table">
            <caption className="sr-only">Share of {who}'s revenue by customer</caption>
            <tbody>
              {mix.slices.map((s, i) => (
                <FragmentRow key={i} open={open === i}
                             onToggle={() => setOpen(open === i ? null : i)}
                             active={active === i} onHover={(on) => setActive(on ? i : null)}
                             swatch="mix-swatch" label={s.label}
                             tag={s.named ? null : 'unnamed'}
                             sub={s.described_as}
                             trend={s.history.length > 1
                               ? s.history.map((h) => `${h.period.match(/\d{4}/)?.[0] ?? h.period} ${pct(h.percent)}`).join(' → ')
                               : null}
                             value={pct(s.percent, s.at_least)}
                             quote={s.evidence} url={mix.url} />
              ))}
              {mix.other && (
                <tr className={`mix-row ${active === -1 ? 'active' : ''}`}
                    onMouseEnter={() => setActive(-1)} onMouseLeave={() => setActive(null)}>
                  <td><span className="mix-swatch rest" aria-hidden="true" /></td>
                  <td>
                    All other customers
                    <div className="small muted">{mix.other.note}</div>
                  </td>
                  <td className="mix-pct">{mix.other.at_most ? '≤' : ''}{pct(mix.other.percent)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {mix.named_without_share.length > 0 && (
        <div className="mix-named">
          <div className="small">
            The filing names{' '}
            <strong>{mix.named_without_share.map((n) => n.name).join(', ')}</strong>{' '}
            as customers of {mix.named_without_share[0].at_least}% or more, but does not say which share above belongs to which.
          </div>
          <div className="evidence"><q>{mix.named_without_share[0].evidence}</q></div>
        </div>
      )}
      {mix.named_in_filings.length > 0 && (
        <NamedInFilings who={who} customers={mix.named_in_filings} hasUnnamed={mix.slices.some((s) => !s.named)} />
      )}
      {mix.slices.some((s) => s.at_least) && (
        <p className="small muted">
          A “+” means the filing gives a floor (“10% or more”), not an exact share. The slice is drawn at the
          floor, so the true share is at least that and the rest is at most what is shown.
        </p>
      )}
      {mix.slices.some((s) => !s.named) && (
        <p className="small muted">
          Unnamed customers are as the filing describes them. The company does not name them, and we do not guess.
        </p>
      )}

      <Notes title="Also disclosed" hint="These overlap the customers above, so they are not slices." notes={mix.context} url={mix.url} />
      <Notes title="What it depends on" hint="Filings name sole or limited sources but almost never give a share of spending, so none is shown."
             notes={mix.suppliers} url={mix.url} noValue="share not disclosed" />
      <Notes title="Where the revenue comes from" notes={mix.geography} url={mix.url} />

      {mix.depended_on_by.length > 0 && (
        <div className="mix-section">
          <div className="card-label">Companies that depend on {who}</div>
          <p className="small muted" style={{ marginTop: 0 }}>From their own filings: how much of <em>their</em> revenue comes from {who}.</p>
          {mix.depended_on_by.map((d) => (
            <div key={d.ticker} className="mix-dep">
              <div className="row-between">
                <span><Link to={`/stock/${d.ticker}`}><strong>{d.ticker}</strong></Link> <span className="small secondary">{d.name}</span></span>
                <strong className="mix-pct">{pct(d.percent, d.at_least)}</strong>
              </div>
              <div className="evidence">
                <q>{d.evidence}</q>
                <div className="small muted"><a href={d.url} target="_blank" rel="noreferrer">{d.form} filing</a>{d.period ? ` · ${d.period}` : ''}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {mix.available && (
        <p className="small muted mix-method">
          Every quote was matched word for word against the filing, and every number and name against its quote.
          {mix.dropped_unverified > 0 && ` ${mix.dropped_unverified} claim${mix.dropped_unverified === 1 ? ' was' : 's were'} dropped because ${mix.dropped_unverified === 1 ? 'it' : 'they'} did not match.`}
        </p>
      )}
    </div>
  )
}

/** Customers other filings name, as names only: which (if any) is behind an
 * unnamed slice is not stated anywhere, so they are listed, never matched. */
function NamedInFilings({ who, customers, hasUnnamed }: {
  who: string
  customers: RevenueMix['named_in_filings']
  hasUnnamed: boolean
}) {
  const [open, setOpen] = useState<string | null>(null)
  const shown = customers.find((c) => c.id === open)
  return (
    <div className="mix-named">
      <div className="small">
        <strong>Customers named in filings</strong>{' '}
        <span className="muted">
          · share not stated{hasUnnamed ? '; not matched to the unnamed slices above' : ''}
        </span>
      </div>
      <div className="named-chips">
        {customers.map((c) => (
          <button key={c.id} type="button" className={`named-chip ${open === c.id ? 'selected' : ''}`}
                  aria-expanded={open === c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
            {c.name}
          </button>
        ))}
      </div>
      {shown && (
        <div className="evidence">
          <q>{shown.evidence}</q>
          <div className="small muted">
            {shown.detail ? `${shown.detail} · ` : ''}
            <a href={shown.filing_url} target="_blank" rel="noreferrer">{shown.reported_by_name}'s {shown.source}</a>
          </div>
        </div>
      )}
      {!shown && <div className="small muted">Click a name to see the quote showing it buys from {who.replace(/\.$/, '')}.</div>}
    </div>
  )
}

function FragmentRow({ open, onToggle, active, onHover, swatch, label, tag, sub, trend, value, quote, url }: {
  open: boolean
  onToggle: () => void
  active: boolean
  onHover: (on: boolean) => void
  swatch: string
  label: string
  tag: string | null
  sub: string | null
  trend: string | null
  value: string
  quote: string
  url?: string | null
}) {
  return (
    <>
      <tr className={`mix-row clickable ${active ? 'active' : ''}`} tabIndex={0} aria-expanded={open}
          onClick={onToggle} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle() } }}
          onMouseEnter={() => onHover(true)} onMouseLeave={() => onHover(false)}
          onFocus={() => onHover(true)} onBlur={() => onHover(false)}>
        <td><span className={swatch} aria-hidden="true" /></td>
        <td>
          {label}{tag && <span className="tag">{tag}</span>}
          {sub && <div className="small muted">“{sub}”</div>}
          {trend && <div className="small mix-trend" title="Share of revenue by year, from the same quote">{trend}</div>}
        </td>
        <td className="mix-pct">{value}</td>
      </tr>
      {open && (
        <tr>
          <td />
          <td colSpan={2}>
            <div className="evidence">
              <q>{quote}</q>
              {url && <div className="small muted"><a href={url} target="_blank" rel="noreferrer">Open the filing</a></div>}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Notes({ title, hint, notes, url, noValue }: {
  title: string
  hint?: string
  notes: MixNote[]
  url?: string | null
  noValue?: string
}) {
  if (!notes.length) return null
  return (
    <details className="mix-section">
      <summary><span className="card-label">{title}</span> <span className="small muted">({notes.length})</span></summary>
      {hint && <p className="small muted" style={{ marginTop: 0 }}>{hint}</p>}
      {notes.map((n, i) => (
        <div key={i} className="mix-dep">
          <div className="row-between">
            <span className="small">{n.text}</span>
            <span className={n.percent == null ? 'small muted' : 'mix-pct'}>
              {n.percent == null ? noValue ?? '' : pct(n.percent, n.at_least)}
            </span>
          </div>
          <div className="evidence">
            <q>{n.evidence}</q>
            {url && <div className="small muted"><a href={url} target="_blank" rel="noreferrer">Filing</a>{n.period ? ` · ${n.period}` : ''}</div>}
          </div>
        </div>
      ))}
    </details>
  )
}

const SIZE = 184
const R = 88
const WIDTH = 20
const GAP = 2 // px of surface between slices

/** SVG donut. Disclosed customers share one teal (the question is how
 * concentrated, not which color is which); the rest is neutral gray. Slices run
 * clockwise from 12 o'clock, largest first, in table order. */
function Donut({ mix, active, setActive }: {
  mix: RevenueMix
  active: number | null
  setActive: (i: number | null) => void
}) {
  const segments = [
    ...mix.slices.map((s, i) => ({ key: i, value: s.percent, label: s.label, text: pct(s.percent, s.at_least), rest: false })),
    ...(mix.other && mix.other.percent > 0
      ? [{ key: -1, value: mix.other.percent, label: 'All other customers',
           text: `${mix.other.at_most ? '≤' : ''}${pct(mix.other.percent)}`, rest: true }]
      : []),
  ]
  const total = segments.reduce((a, s) => a + s.value, 0) || 1
  const r = R - WIDTH / 2
  const circumference = 2 * Math.PI * r
  const gap = segments.length > 1 ? GAP : 0
  let offset = 0

  const disclosed = mix.slices.reduce((a, s) => a + s.percent, 0)
  const floor = mix.slices.some((s) => s.at_least)
  const shown = active != null ? segments.find((s) => s.key === active) : null

  return (
    <svg className="donut" width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
         aria-label={segments.map((s) => `${s.label} ${s.text}`).join(', ')}>
      <g transform={`translate(${SIZE / 2} ${SIZE / 2}) rotate(-90)`}>
        {segments.map((s) => {
          const length = (s.value / total) * circumference
          const dash = Math.max(0.5, length - gap)
          const el = (
            <circle key={s.key} r={r} fill="none"
                    className={`donut-seg ${s.rest ? 'rest' : ''} ${active != null && active !== s.key ? 'dim' : ''}`}
                    strokeWidth={active === s.key ? WIDTH + 4 : WIDTH}
                    strokeDasharray={`${dash} ${circumference - dash}`}
                    strokeDashoffset={-offset}
                    onMouseEnter={() => setActive(s.key)} onMouseLeave={() => setActive(null)}>
              <title>{`${s.label}: ${s.text} of revenue`}</title>
            </circle>
          )
          offset += length
          return el
        })}
      </g>
      <text x="50%" y="47%" textAnchor="middle" className="donut-value">
        {shown ? shown.text : mix.status === 'none_above_threshold' ? `<${mix.threshold ?? 10}%` : pct(disclosed, floor)}
      </text>
      <text x="50%" y="60%" textAnchor="middle" className="donut-caption">
        {shown ? truncate(shown.label, 20)
          : mix.status === 'none_above_threshold' ? 'largest customer'
          : `from ${mix.slices.length} customer${mix.slices.length === 1 ? '' : 's'}`}
      </text>
    </svg>
  )
}

function truncate(text: string, n: number) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text
}
