import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { usePortfolio } from './hooks'
import { MapPage } from './pages/MapPage'
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
            <NavLink to="/" end><Icon d={ICONS.xray} /> My Portfolio</NavLink>
            <NavLink to="/map"><Icon d={ICONS.map} /> Connection Map</NavLink>
            <NavLink to="/research"><Icon d={ICONS.research} /> Research</NavLink>
          </nav>
          <div className="sidebar-foot">v0.1 · Data from SEC filings</div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<XRayPage holdings={holdings} setHoldings={setHoldings} />} />
            <Route path="/map" element={<MapPage holdings={holdings} setHoldings={setHoldings} />} />
            <Route path="/stock/:symbol" element={<StoryPage />} />
            <Route path="/research" element={<ResearchPlaceholder />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

function ResearchPlaceholder() {
  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Research</div>
        <h1>How would this fit your portfolio?</h1>
        <p>Compare a company's shape (growth, stability, profitability, debt, risk) with what you already own, and see where it would connect.</p>
      </div>
      <div className="placeholder">
        <strong>Not built yet</strong>
        <p className="small muted">
          Needs the financial ratios for the radar shape (the FUNDAMENTALS table is empty) and a
          "how would this fit" endpoint. See Product.md, feature 5.
        </p>
      </div>
    </>
  )
}
