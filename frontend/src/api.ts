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

export interface Quote {
  symbol: string
  as_of: string
  price: number
  prev_close: number
  change: number
  change_pct: number | null
  returns: Partial<Record<'1W' | '1M' | '3M' | '6M', number | null>>
  range: { low: number; high: number; days: number; from: string; to: string }
  volume: number
  volume_vs_avg: number | null
  sparkline: { date: string; close: number }[]
}

export interface Quotes {
  as_of: string | null
  quotes: Record<string, Quote>
  missing: string[]
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

/** A holding a feed event reaches, and how (from the knowledge graph). */
export interface FeedTouch {
  ticker: string
  role: 'holding' | 'customer' | 'supplier' | 'indirect_customer' | 'competitor' | 'same_sector'
  explanation: string
  evidence?: Provenance[]
}

/** One development at one company, summarised from its cited articles. */
export interface FeedItem {
  id: string
  symbol: string
  company_name: string
  headline: string
  summary: string
  event_type: string
  tone: 'positive' | 'negative' | 'mixed' | 'neutral'
  importance: 'high' | 'medium' | 'low'
  first_seen: string
  last_seen: string
  sources: { headline: string; publisher: string; url: string; date: string }[]
  tier: 1 | 2 | 3
  tier_label: string
  touches: FeedTouch[]
  change_pct: number | null
}

export interface Feed {
  holdings: string[]
  unsupported: string[]
  as_of: string | null
  generated_at: string | null
  window_days: number
  counts: Record<string, number>
  items: FeedItem[]
}

/** One radar axis: the raw measure, and its rank among the covered companies. */
export interface RadarAxis {
  axis: 'growth' | 'profitability' | 'stability' | 'debt' | 'risk'
  label: string
  value: number | null
  unit: string
  /** 0-100, always oriented so higher is the more favourable end. */
  score: number | null
  available: boolean
  /** "SEC EDGAR" or "Yahoo Finance" — a filing is stronger than a vendor ratio. */
  basis: string
  explanation: string
  favourable: string
}

/** The portfolio's own average shape, for drawing the candidate over it. */
export interface PortfolioRadarAxis {
  axis: RadarAxis['axis']
  label: string
  score: number | null
  from_holdings: number
}

export type FitComponentName =
  | 'correlation'
  | 'sector_crowding'
  | 'dependency_overlap'
  | 'direct_connection'

export interface FitComponent {
  /** null when the check could not be run; it is then excluded from the score. */
  score: number | null
  measured: boolean
  /** The score in words: "Little overlap" … "Heavy overlap", or "Unknown". */
  band: string
  /** What it means for the investor, in plain words and no figures. */
  plain: string
  /** Share of the fit score this check accounts for, after renormalising. */
  weight_applied: number
  /** The numeric summary, e.g. "Average correlation +0.19". */
  label: string
  /** The figures spelled out. */
  detail: string
  evidence: Record<string, unknown>[]
}

export type Verdict = 'Good diversity' | 'Some diversification' | 'Risky overlap' | 'Not enough data'

export interface ResearchEvidence {
  id: string
  kind: 'metric' | 'diversification' | 'news'
  title: string
  detail: string
  source: string
  url: string | null
  numbers: Record<string, string | number | boolean | null>
  supporting: Record<string, unknown>[]
}

export interface BriefPoint {
  point: string
  citation_ids: string[]
}

/** A company matching what was typed in the search box. */
export interface CompanyMatch {
  ticker: string
  cik: string
  name: string
  in_universe: boolean
  match_score: number
}

export interface SearchResults {
  query: string
  matches: CompanyMatch[]
}

export interface Analysis {
  ticker: string
  name: string
  cik: string | null
  sector: string
  industry: string
  country: string
  in_universe: boolean
  in_graph: boolean
  graph_id: string | null
  already_held: boolean
  holdings: string[]
  unsupported: string[]
  /** null when none of the overlap checks could be run. */
  fit_score: number | null
  verdict: Verdict
  verdict_meaning: string
  confidence: 'high' | 'medium' | 'low'
  confidence_reason: string
  components: Record<FitComponentName, FitComponent>
  /** One line explaining what 0 and 100 mean, shown above the checks. */
  score_scale: string
  radar: RadarAxis[]
  portfolio_radar: PortfolioRadarAxis[]
  brief: {
    summary: string
    summary_citation_ids: string[]
    pros: BriefPoint[]
    cons: BriefPoint[]
    generated_at: string | null
  }
  evidence: Record<string, ResearchEvidence>
  map_placement: {
    in_graph: boolean
    nodes: (MapNode & { is_candidate: boolean })[]
    links: MapLink[]
  }
  /** How much its dependencies matter, read from the same filing. */
  concentration: ConcentrationRead | null
  /** What we read out of the company's own annual report, for anything outside
   * the 13 companies whose filings were read offline. Null for those 13. */
  filing_read: {
    summary: string
    available: boolean
    reason?: string
    form?: string
    filing_date?: string
    url?: string
    relationships?: {
      type: 'SUPPLIER' | 'CUSTOMER' | 'COMPETITOR' | 'OPERATES_IN'
      counterparty_name: string | null
      country: string | null
      detail: string | null
      evidence: string
      confidence: 'high' | 'medium' | 'low'
      is_named: boolean
    }[]
    dropped_unverified?: number
  } | null
  alternatives: CompanyMatch[]
  warnings: string[]
  disclaimer: string
}

/** A 404 or 409 from /research/analyze carries the companies it did match. */
export interface ResolutionProblem {
  message: string
  options: CompanyMatch[]
}

export class ResearchLookupError extends Error {
  problem: ResolutionProblem
  status: number
  constructor(problem: ResolutionProblem, status: number) {
    super(problem.message)
    this.name = 'ResearchLookupError'
    this.problem = problem
    this.status = status
  }
}

/** One concentration disclosure, read from a filing and quote-verified. */
export interface ConcentrationFact {
  kind: 'customer_concentration' | 'supplier_concentration'
    | 'geographic_concentration' | 'single_source' | 'none_above_threshold'
  subject: string | null
  counterparty_name: string | null
  percent: number | null
  /** The filing gave a floor ("10% or more"), not an exact share. */
  at_least: boolean
  scope: 'single' | 'group'
  basis: 'direct' | 'indirect' | 'unspecified'
  metric: string | null
  period: string | null
  threshold: number | null
  evidence: string
  confidence: 'high' | 'medium' | 'low'
}

export interface ConcentrationRead {
  available: boolean
  reason?: string
  summary: string
  headline: string | null
  largest_customer_share: number | null
  form?: string
  filing_date?: string
  url?: string
  facts?: ConcentrationFact[]
  dropped_unverified?: number
  revenue_mix: RevenueMix
}

/** One disclosed customer's share of revenue: a slice of the donut. */
export interface RevenueSlice {
  /** The name if the filing names it, else "Customer A", "Customer B". */
  label: string
  named: boolean
  /** The filing's own words, e.g. "one direct customer". */
  described_as: string | null
  percent: number
  at_least: boolean
  metric: string | null
  period: string | null
  /** This customer's share by year, oldest first, when the quote gives several. */
  history: { period: string; percent: number }[]
  evidence: string
}

/** A customer another filing names, without a share. Never matched to a slice. */
export interface NamedCustomer {
  id: string
  name: string
  in_universe: boolean
  detail: string | null
  evidence: string
  reported_by: string
  reported_by_name: string
  source: string
  filing_url: string
}

export interface MixNote {
  text: string
  percent: number | null
  at_least: boolean
  metric: string | null
  period: string | null
  evidence: string
}

/** A supported company whose own filing says this one is a big customer. */
export interface DependedOnBy {
  ticker: string
  name: string
  percent: number
  at_least: boolean
  metric: string | null
  period: string | null
  evidence: string
  form: string
  url: string
}

/** Who pays a company, from its annual report. */
export interface RevenueMix {
  ticker?: string
  name?: string
  available: boolean
  /** disclosed: slices below. none_above_threshold: no customer reaches the
   * threshold. overlapping: shares add to over 100%, so no pie. */
  status: 'disclosed' | 'none_above_threshold' | 'not_disclosed' | 'overlapping' | 'unavailable'
  summary: string
  form?: string | null
  filing_date?: string | null
  url?: string | null
  period: string | null
  threshold: number | null
  slices: RevenueSlice[]
  disclosed_total?: number
  other: { percent: number; at_most: boolean; note: string } | null
  /** Customers the filing names as over a floor ("10% or more") while giving
   * exact shares only unnamed; which share is whose is not stated. */
  named_without_share: { name: string; at_least: number; evidence: string }[]
  /** Groups and indirect customers: true, but they overlap the slices. */
  context: MixNote[]
  suppliers: MixNote[]
  geography: MixNote[]
  depended_on_by: DependedOnBy[]
  named_in_filings: NamedCustomer[]
  dropped_unverified: number
  method?: string
}

/** One holding's concentration, in the portfolio rollup. */
export interface HoldingConcentration {
  ticker: string
  name: string
  headline: string | null
  largest_customer_share: number | null
  single_source_count: number
  fact_count: number
  dropped_unverified: number
  form: string
  filing_date: string
  url: string
  facts: ConcentrationFact[]
}

/** A holding that names another holding as a material customer or supplier. */
export interface InternalConcentrationLink {
  from: string
  to: string
  role: 'customer' | 'supplier'
  percent: number | null
  metric: string | null
  quote: string
  form: string
  url: string
}

export interface PortfolioConcentration {
  holdings: HoldingConcentration[]
  internal_links: InternalConcentrationLink[]
  geography: { ticker: string; region: string | null; percent: number
               metric: string | null; quote: string; url: string }[]
  unavailable: { ticker: string; name: string; reason: string }[]
  stats: {
    holdings_requested: number
    filings_read: number
    disclosing_customer_concentration: number
    largest_disclosed_share: number | null
    holdings_with_single_source: number
    internal_links: number
    claims_dropped_unverified: number
  }
  method: string
  unsupported: string[]
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  const response = await fetch(`${BASE}${path}${query}`)
  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    // Lookup failures carry the companies that did match, so the UI can offer
    // them instead of showing a dead end.
    if (detail && typeof detail === 'object' && 'options' in detail) {
      throw new ResearchLookupError(detail as ResolutionProblem, response.status)
    }
    throw new Error(`${response.status}: ${typeof detail === 'string' ? detail : response.statusText}`)
  }
  return response.json() as Promise<T>
}

const holdingsParam = (holdings: string[]) => holdings.join(',')
let universeRequest: Promise<UniverseCompany[]> | null = null
let quotesRequest: Promise<Quotes> | null = null

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
  /** What Changed: last week's events that touch these holdings, ranked. */
  feed: (holdings: string[]) => get<Feed>('/feed', { holdings: holdingsParam(holdings), limit: '60' }),
  /** Who pays a company, from its annual report. Any SEC filer. */
  revenueMix: (ticker: string) =>
    get<RevenueMix>(`/company/${encodeURIComponent(ticker)}/revenue-mix`),
  /** How concentrated each holding is, read from their annual reports. */
  concentration: (holdings: string[]) =>
    get<PortfolioConcentration>('/portfolio/concentration', {
      holdings: holdingsParam(holdings),
    }),
  /** Companies matching a typed query; any SEC filer, not just our 13. */
  researchSearch: (q: string, limit = 8) =>
    get<SearchResults>('/research/search', { q, limit: String(limit) }),
  /** Full analysis of one company against the holdings. Spends a Gemini call
   * on the backend the first time, then serves from cache. */
  researchAnalyze: (q: string, holdings: string[]) =>
    get<Analysis>('/research/analyze', { q, holdings: holdingsParam(holdings) }),
  /** Last-close quotes for every supported company; small, so fetched once and shared. */
  quotes: () => (quotesRequest ??= get<Quotes>('/quotes').catch((e) => {
    quotesRequest = null
    throw e
  })),
}
