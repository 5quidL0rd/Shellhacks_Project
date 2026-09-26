import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FeedItem, type FeedTouch } from '../api'
import { Change, EmptyPortfolio, HoldingsSummary } from '../components'
import { useAsync } from '../hooks'

const TABS = [
  { tier: 0, label: 'All' },
  { tier: 1, label: 'Your holdings' },
  { tier: 2, label: 'Connected companies' },
  { tier: 3, label: 'Same sector' },
] as const

const ROLE_WORD: Record<FeedTouch['role'], string> = {
  holding: 'you own it',
  customer: 'buys from it',
  supplier: 'supplies it',
  indirect_customer: 'via the supply chain',
  competitor: 'competitor',
  same_sector: 'same sector',
}

const TYPE_WORD: Record<string, string> = {
  earnings: 'Earnings', guidance: 'Guidance', product: 'Product', supply_chain: 'Supply chain',
  regulation: 'Regulation', legal: 'Legal', deal: 'Deal', analyst: 'Analyst', management: 'Management',
  market_move: 'Market move', other: 'News',
}

const fmtDay = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

/** What Changed: last week's developments that touch the portfolio, ranked by
 * how directly they touch it (your holding, then connected, then same sector). */
export function FeedPage({ holdings }: { holdings: string[] }) {
  const feed = useAsync(() => (holdings.length ? api.feed(holdings) : Promise.resolve(null)),
    holdings.join(','))
  const [tab, setTab] = useState<number>(0)

  const items = feed.data?.items ?? []
  const shown = tab ? items.filter((i) => i.tier === tab) : items
  const countFor = (tier: number) => (tier ? items.filter((i) => i.tier === tier).length : items.length)

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">What changed</div>
        {feed.data ? (
          <h1>
            {items.length} {items.length === 1 ? 'development touches' : 'developments touch'} your
            portfolio this week
          </h1>
        ) : <h1>What changed this week</h1>}
        <p>
          News about your holdings and the companies they depend on, summarised from the articles
          and ranked by how directly it reaches what you own.
          {feed.data?.as_of && <span className="as-of"> News through {fmtDay(feed.data.as_of)}.</span>}
        </p>
      </div>
      {holdings.length === 0 && <EmptyPortfolio />}
      {feed.data && <HoldingsSummary holdings={holdings} unsupported={feed.data.unsupported} />}
      {feed.error && <p className="error">{feed.error}</p>}
      {feed.loading && !feed.data && holdings.length > 0 && <p className="muted">Loading…</p>}

      {feed.data && (
        <>
          <div className="tabs" role="tablist" aria-label="Filter by relevance">
            {TABS.map((t) => (
              <button key={t.tier} role="tab" aria-selected={tab === t.tier}
                      className={`tab ${tab === t.tier ? 'active' : ''}`} onClick={() => setTab(t.tier)}>
                {t.label} <span className="tab-count">{countFor(t.tier)}</span>
              </button>
            ))}
          </div>
          {items.length === 0 && (
            <div className="placeholder">
              <strong>Nothing this week</strong>
              <p className="small muted">No recent news about your holdings or the companies they depend on.</p>
            </div>
          )}
          {items.length > 0 && shown.length === 0 && (
            <p className="muted small">Nothing in this group this week.</p>
          )}
          <div className="feed-list">
            {shown.map((item) => <FeedCard key={item.id} item={item} />)}
          </div>
        </>
      )}
    </>
  )
}

function FeedCard({ item }: { item: FeedItem }) {
  const [open, setOpen] = useState(false)
  const reach = item.touches.filter((t) => t.role !== 'holding')
  return (
    <article className={`card feed-card tier-${item.tier}`}>
      <div className="feed-meta">
        <span className={`tier-badge tier-${item.tier}`}>{item.tier_label}</span>
        <Link to={`/stock/${item.symbol}`} className="feed-company">
          <strong>{item.symbol}</strong> <span className="secondary">{item.company_name}</span>
        </Link>
        <Change pct={item.change_pct} suffix=" last close" />
        <span className="feed-spacer" />
        <span className="small muted">
          {TYPE_WORD[item.event_type] ?? 'News'} · {item.importance} importance ·{' '}
          {item.first_seen === item.last_seen ? fmtDay(item.last_seen)
            : `${fmtDay(item.first_seen)}–${fmtDay(item.last_seen)}`}
        </span>
      </div>

      <h2 className="feed-headline">{item.headline}</h2>
      <p className="feed-summary">{item.summary}</p>

      {reach.length > 0 && (
        <div className="feed-touches">
          <span className="role">{item.tier === 1 ? 'Also reaches' : 'Reaches'}</span>
          {reach.map((t) => (
            <span key={t.ticker} className="touch" title={t.explanation}>
              <Link to={`/stock/${t.ticker}`}><strong>{t.ticker}</strong></Link>
              <span className="muted"> {ROLE_WORD[t.role]}</span>
            </span>
          ))}
        </div>
      )}
      {item.tier === 2 && reach[0] && <p className="small muted feed-why">{reach[0].explanation}</p>}

      <button className="ghost-btn feed-sources-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? 'Hide' : 'Show'} {item.sources.length} {item.sources.length === 1 ? 'source' : 'sources'}
      </button>
      {open && (
        <ul className="feed-sources">
          {item.sources.map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noreferrer">{s.headline}</a>
              <span className="small muted"> · {s.publisher} · {fmtDay(s.date)}</span>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}
