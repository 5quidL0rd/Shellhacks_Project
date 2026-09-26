/** Line icons for each kind of evidence a citation can point to (Story Mode
 * and Research). 24-unit paths drawn at 11px, stroke = currentColor. */
export const EVIDENCE_ICON: Record<string, string> = {
  news: 'M4 5h13v14H4zM17 9h3v8a2 2 0 0 1-2 2M7 9h7M7 13h7M7 17h4',
  filing: 'M7 3h7l4 4v14H7zM14 3v4h4M9 12h6M9 16h6',
  price: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  peer_move: 'M9 15l6-6M10 6l1-1a4 4 0 0 1 6 6l-1 1M14 18l-1 1a4 4 0 0 1-6-6l1-1',
  fundamental: 'M5 20V10M12 20V4M19 20v-7',
  metric: 'M5 20V10M12 20V4M19 20v-7',
  sector: 'M3 20h18M5 20V9l5 3V9l5 3V5h4v15',
  diversification: 'M9 12m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0M15 12m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0',
}

export const EVIDENCE_LABEL: Record<string, string> = {
  news: 'News article',
  filing: 'SEC filing',
  price: 'Price move',
  peer_move: 'Connected company',
  fundamental: 'Quarterly results',
  metric: 'Measured figure',
  sector: 'Industry data',
  diversification: 'Portfolio overlap',
}

/** One line per kind, for the "How to read the citations" section. */
export const EVIDENCE_DESCRIPTION: Record<string, string> = {
  price: "The stock's own move that day: the % change, closing price, and trading volume compared with normal.",
  news: 'A news article published on the day of the move or the day before, with a link to the original.',
  filing: 'An SEC filing dated near the move, such as a quarterly report (10-Q) or a company announcement (8-K).',
  peer_move: 'How a supplier, customer, or competitor moved the same day, which shows whether the move was shared or company-specific.',
  fundamental: "Quarterly revenue or profit from the company's SEC filings. Used for the overall summary, not single days.",
  sector: 'Federal industry statistics, such as US chip production. Used for the overall summary, not single days.',
  metric: 'A figure measured for this company (growth, margin, debt, volatility, or drawdown) and where it came from.',
  diversification: 'One of the overlap checks comparing this company with what you already hold.',
}
