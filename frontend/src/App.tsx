import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { usePortfolio } from './hooks'
import { MapPage } from './pages/MapPage'
import { StoryPage } from './pages/StoryPage'
import { XRayPage } from './pages/XRayPage'

export default function App() {
  const { holdings, setHoldings } = usePortfolio()
  return (
    <BrowserRouter>
      <div className="shell">
        <header className="topbar">
          <div className="brand">Portfolio X-Ray <span>· what you actually depend on</span></div>
          <nav className="nav">
            <NavLink to="/" end>My Portfolio</NavLink>
            <NavLink to="/map">Connection Map</NavLink>
            <NavLink to="/research">Research</NavLink>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<XRayPage holdings={holdings} setHoldings={setHoldings} />} />
          <Route path="/map" element={<MapPage holdings={holdings} setHoldings={setHoldings} />} />
          <Route path="/stock/:symbol" element={<StoryPage />} />
          <Route path="/research" element={<ResearchPlaceholder />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

function ResearchPlaceholder() {
  return (
    <div className="card">
      <h2>Research a new investment</h2>
      <p className="secondary">
        Not built yet. It needs the financial ratios for the radar shape (the FUNDAMENTALS table is empty) and a
        "how would this fit your portfolio" endpoint. See Product.md, feature 5.
      </p>
    </div>
  )
}
