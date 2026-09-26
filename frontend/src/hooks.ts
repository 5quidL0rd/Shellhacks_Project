import { useCallback, useEffect, useState } from 'react'

/** Holdings that work well for the demo: several look unrelated but share
 * TSMC, China, and Taiwan underneath (see company_universe_draft.md). */
export const SAMPLE_PORTFOLIO = ['AAPL', 'NVDA', 'AMD', 'MSFT', 'QCOM', 'CRUS', 'AMZN']

const STORAGE_KEY = 'portfolio-holdings'

function readSaved(): string[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) && parsed.every((t) => typeof t === 'string') ? parsed : null
  } catch {
    return null
  }
}

/** The user's holdings, remembered in this browser. There is no account or
 * saved-portfolio endpoint yet, so localStorage is a convenience only. */
export function usePortfolio() {
  const [holdings, setHoldingsState] = useState<string[]>(() => readSaved() ?? SAMPLE_PORTFOLIO)
  const setHoldings = useCallback((next: string[]) => {
    setHoldingsState(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* storage unavailable: keep it in memory */
    }
  }, [])
  return { holdings, setHoldings }
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
