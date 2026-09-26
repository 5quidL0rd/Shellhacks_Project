import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { Change } from './components'
import { useAsync, usePortfolio } from './hooks'
import { FeedPage } from './pages/FeedPage'
import { HoldingsPage } from './pages/HoldingsPage'
import { MapPage } from './pages/MapPage'
import { ResearchPage } from './pages/ResearchPage'
import { StoryPage } from './pages/StoryPage'
import { XRayPage } from './pages/XRayPage'

// Minimal line icons (16px, stroke = currentColor) so they follow the nav color.
const Icon = ({ d }: { d: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
)
const ICONS = {
  logo: 'M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  xray: 'M3 12h4l3-8 4 16 3-8h4',
  map: 'M6 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M12 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7.5 7.5l3.5 9M16.5 7.5l-3.5 9M8 6h8',
  research: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-5-5',
  holdings: 'M4 6h16M4 12h16M4 18h10',
  changes: 'M5 4h14v16H5zM9 8h6M9 12h6M9 16h3',
}

export default function App() {
  const { holdings, setHoldings } = usePortfolio()
  return (
    <BrowserRouter>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-name"><Icon d={ICONS.logo} /> Portfolio X-Ray</div>
            <div className="brand-sub">What you actually depend on</div>
          </div>
          <nav className="nav" aria-label="Main">
            <NavLink to="/holdings"><Icon d={ICONS.holdings} /> Holdings</NavLink>
            <NavLink to="/" end><Icon d={ICONS.xray} /> X-Ray</NavLink>
            <NavLink to="/changes"><Icon d={ICONS.changes} /> What Changed</NavLink>
            <NavLink to="/map"><Icon d={ICONS.map} /> Connection Map</NavLink>
            <NavLink to="/research"><Icon d={ICONS.research} /> Research</NavLink>
          </nav>
          <SidebarHoldings holdings={holdings} />
          <div className="sidebar-foot">v0.1 · Data from SEC filings</div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<XRayPage holdings={holdings} />} />
            <Route path="/changes" element={<FeedPage holdings={holdings} />} />
            <Route path="/map" element={<MapPage holdings={holdings} />} />
            <Route path="/holdings" element={<HoldingsPage holdings={holdings} setHoldings={setHoldings} />} />
            <Route path="/stock/:symbol" element={<StoryPage />} />
            <Route path="/research" element={<ResearchPage holdings={holdings} />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

/** Every holding at a glance, one click from its story. Scrolls when long. */
function SidebarHoldings({ holdings }: { holdings: string[] }) {
  const quotes = useAsync(api.quotes, 'quotes')
  return (
    <div className="sidebar-holdings">
      <div className="row-between">
        <span className="eyebrow">Holdings · {holdings.length}</span>
        <Link to="/holdings" className="small">Edit</Link>
      </div>
      {holdings.length === 0
        ? <Link to="/holdings" className="small">+ Add holdings</Link>
        : (
          <div className="sidebar-tickers">
            {[...holdings].sort().map((t) => (
              <NavLink key={t} to={`/stock/${t}`} className="ticker-link">
                <span>{t}</span>
                <Change pct={quotes.data?.quotes[t]?.change_pct} />
              </NavLink>
            ))}
          </div>
        )}
    </div>
  )
}
