// Typed client for the FastAPI backend (see backend/README.md for endpoints).
// In development, Vite forwards /api/* to the backend (vite.config.ts).

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/** Why a graph edge exists: the filing quote and where it came from. */
export interface Provenance {
  relationship: string
  kind: string | null
  detail: string | null
  evidence: string | null
  source: string | null // "10-K", "20-F", "manual", "config"
  filing_url: string | null
  confidence: string | null
  note: string | null
}

export interface GraphNode {
  id: string
  name: string
  type: 'company' | 'country'
  in_universe: boolean
  is_holding: boolean
  sector: string | null
}

export interface Dependency extends GraphNode {
  holding_count: number
  holdings: { ticker: string; how: string[]; evidence: Provenance[] }[]
}

export interface XRay {
  holdings: string[]
  unsupported: string[]
  shared_count: number
  dependencies: Dependency[]
}

export interface MapNode extends GraphNode {
  connected_holdings: string[]
}

export interface MapLink {
  source: string
  target: string
  type: 'supplies' | 'competes_with' | 'operates_in'
  kind: string | null
  provenance: Provenance
}

export interface PortfolioMap {
  holdings: string[]
  unsupported: string[]
  nodes: MapNode[]
  links: MapLink[]
}

export interface ImpactConnection {
  role: 'customer' | 'supplier' | 'indirect_customer' | 'competitor'
  path: string[]
  explanation: string
  evidence: Provenance[]
}

export interface Impact {
  holdings: string[]
  unsupported: string[]
  company: GraphNode
  affected: { ticker: string; name: string; connections: ImpactConnection[] }[]
  unaffected: string[]
}

export interface UniverseCompany {
  symbol: string
  name: string
  sector: string
}

export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  pct_change: number
}

export interface Beat {
  date: string
  pct_change: number
  close: number
  direction: 'up' | 'down'
  headline: string
  explanation: string
  confidence: 'high' | 'medium' | 'low'
  citation_ids: string[]
}

export interface Evidence {
  id: string
  kind: 'news' | 'filing' | 'price' | 'fundamental' | 'peer_move' | 'sector'
  title: string
  detail: string
  source: string
  url: string | null
  occurred_on: string
  numbers: Record<string, string | number>
}

export interface Story {
  symbol: string
  company_name: string
  generated_at: string
  bars: Bar[]
  beats: Beat[]
  evidence: Record<string, Evidence>
  arc: string
  arc_citation_ids: string[]
  warnings: string[]
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  const response = await fetch(`${BASE}${path}${query}`)
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(`${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

const holdingsParam = (holdings: string[]) => holdings.join(',')
let universeRequest: Promise<UniverseCompany[]> | null = null

export const api = {
  /** The supported companies; fetched once per page load and shared. */
  universe: () => (universeRequest ??= get<UniverseCompany[]>('/universe').catch((e) => {
    universeRequest = null // let the next caller retry
    throw e
  })),
  xray: (holdings: string[]) => get<XRay>('/portfolio/xray', { holdings: holdingsParam(holdings) }),
  map: (holdings: string[], opts: { countries: boolean; competitors: boolean }) =>
    get<PortfolioMap>('/portfolio/map', {
      holdings: holdingsParam(holdings),
      include_countries: String(opts.countries),
      include_competitors: String(opts.competitors),
    }),
  impact: (company: string, holdings: string[]) =>
    get<Impact>('/portfolio/impact', { company, holdings: holdingsParam(holdings) }),
  story: (symbol: string) => get<Story>(`/story/${encodeURIComponent(symbol)}`),
}
