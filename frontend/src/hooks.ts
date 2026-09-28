import { useCallback, useEffect, useState } from 'react'

/** Holdings that work well for the demo: several look unrelated but share
 * TSMC, China, and Taiwan underneath (see company_universe_draft.md). */
export const SAMPLE_PORTFOLIO = ['AAPL', 'NVDA', 'AMD', 'MSFT', 'QCOM', 'CRUS', 'AMZN']

const STORAGE_KEY = 'portfolio-holdings'
const POSITIONS_KEY = 'portfolio-positions'
const DEMO_POSITIONS_KEY = 'portfolio-demo-positions'
const MODE_KEY = 'portfolio-mode'

export interface Position { shares: number | null; averageCost: number | null }

export const SAMPLE_POSITIONS: Record<string, Position> = {
  AAPL: { shares: 80, averageCost: null },
  NVDA: { shares: 120, averageCost: null },
  AMD: { shares: 25, averageCost: null },
  MSFT: { shares: 40, averageCost: null },
  QCOM: { shares: 50, averageCost: null },
  CRUS: { shares: 40, averageCost: null },
  AMZN: { shares: 70, averageCost: null },
}

function readPositions(key = POSITIONS_KEY): Record<string, Position> {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? '{}')
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
    return Object.fromEntries(Object.entries(raw).filter(([, value]) =>
      value && typeof value === 'object' && !Array.isArray(value))) as Record<string, Position>
  } catch { return {} }
}

function readSaved(): string[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) && parsed.every((t) => typeof t === 'string') ? parsed : null
  } catch {
    return null
  }
}

function readDemoMode(): boolean {
  try {
    const saved = localStorage.getItem(MODE_KEY)
    if (saved === 'demo') return true
    if (saved === 'custom') return false
    return !Object.values(readPositions()).some((p) => (p.shares ?? 0) > 0 || (p.averageCost ?? 0) > 0)
  } catch { return true }
}

/** The user's holdings, remembered in this browser. There is no account or
 * saved-portfolio endpoint yet, so localStorage is a convenience only. */
export function usePortfolio() {
  const [holdings, setHoldingsState] = useState<string[]>(() => readSaved() ?? SAMPLE_PORTFOLIO)
  const [demo, setDemo] = useState(readDemoMode)
  const [customPositions, setCustomPositions] = useState<Record<string, Position>>(readPositions)
  const [demoPositions, setDemoPositions] = useState<Record<string, Position>>(
    () => ({ ...SAMPLE_POSITIONS, ...readPositions(DEMO_POSITIONS_KEY) }))
  const positions = demo ? demoPositions : customPositions
  const setHoldings = useCallback((next: string[]) => {
    setHoldingsState(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* storage unavailable: keep it in memory */
    }
  }, [])
  const setPosition = useCallback((symbol: string, field: keyof Position, value: number | null) => {
    const update = demo ? setDemoPositions : setCustomPositions
    const key = demo ? DEMO_POSITIONS_KEY : POSITIONS_KEY
    update((current) => {
      const next = { ...current,
        [symbol]: { ...(current[symbol] ?? { shares: null, averageCost: null }), [field]: value } }
      try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* keep in memory */ }
      return next
    })
  }, [demo])
  const useSamplePortfolio = useCallback(() => {
    setHoldings(SAMPLE_PORTFOLIO)
    setDemoPositions(SAMPLE_POSITIONS)
    setDemo(true)
    try {
      localStorage.setItem(MODE_KEY, 'demo')
      localStorage.removeItem(DEMO_POSITIONS_KEY)
    } catch { /* keep in memory */ }
  }, [setHoldings])
  const startCustomPortfolio = useCallback(() => {
    setDemo(false)
    try { localStorage.setItem(MODE_KEY, 'custom') } catch { /* keep in memory */ }
  }, [])
  return { holdings, setHoldings, positions, setPosition, demo,
    useSamplePortfolio, startCustomPortfolio }
}

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

/** Run an async loader whenever `key` changes; ignore stale responses. */
export function useAsync<T>(loader: () => Promise<T>, key: string): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true })
  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    loader()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((e: Error) => !cancelled && setState({ data: null, error: e.message, loading: false }))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return state
}

/** Read the current design tokens so canvas-drawn charts match the CSS, and
 * re-read them when the OS switches between light and dark. */
export function useThemeColors(names: string[]): Record<string, string> {
  const read = useCallback(() => {
    const style = getComputedStyle(document.documentElement)
    return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(`--${n}`).trim()]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [names.join(',')])
  const [colors, setColors] = useState(read)
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setColors(read())
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [read])
  return colors
}

/** Width and height of an element, kept up to date. Attach `measure` as the
 * element's ref callback. */
export function useSize<T extends HTMLElement>() {
  const [node, setNode] = useState<T | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    if (!node) return
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    observer.observe(node)
    return () => observer.disconnect()
  }, [node])
  return { measure: setNode, ...size }
}

/** Tickers found in pasted text or a CSV: split on commas, spaces, tabs,
 * semicolons, and new lines; numbers (share counts) and known header words are
 * ignored. `known` tickers are returned in `found`; ticker-shaped leftovers in
 * `unknown`, so the user sees what was skipped. */
export function parseTickers(text: string, known: Set<string>): { found: string[]; unknown: string[] } {
  const found: string[] = []
  const unknown: string[] = []
  for (const raw of text.split(/[\s,;|]+/)) {
    const token = raw.replace(/^["']|["']$/g, '').trim().toUpperCase()
    if (!token || /^[\d.$%-]+$/.test(token)) continue
    if (known.has(token)) {
      if (!found.includes(token)) found.push(token)
    } else if (/^[A-Z][A-Z.]{0,5}$/.test(token) && !HEADER_WORDS.has(token) && !unknown.includes(token)) {
      unknown.push(token)
    }
  }
  return { found, unknown }
}

const HEADER_WORDS = new Set(['SYMBOL', 'TICKER', 'SHARES', 'QTY', 'QUANTITY', 'NAME', 'PRICE', 'VALUE', 'COST', 'USD'])
