# Frontend

React + TypeScript (Vite). Screens for the product in [../Product.md](../Product.md), built on the backend API ([../backend/README.md](../backend/README.md)).

## Run it

Two terminals.

```bash
# 1. The API (from backend/)
../.venv/bin/uvicorn app.main:app --reload        # http://127.0.0.1:8000

# 2. The app (from frontend/)
npm install        # first time only
npm run dev        # http://localhost:5173
```

In development, requests to `/api/*` are forwarded to the API (see `vite.config.ts`), so there is no cross-origin setup. To point at an API elsewhere, set `API_URL` when starting Vite, or `VITE_API_BASE` for a build.

```bash
npm run build      # type-check and build to dist/
npm run lint       # oxlint
```

## What's here

| Screen | Route | Backend endpoint | Status |
|---|---|---|---|
| **Portfolio X-Ray** (home) | `/` | `/portfolio/xray`, `/portfolio/impact` | Working: shared dependencies ranked, evidence per holding, "if news hits this supplier" panel |
| **Connection Map** | `/map` | `/portfolio/map`, `/portfolio/impact` | Working: force-directed map, click a company to highlight it and see affected holdings |
| **Story Mode** | `/stock/:symbol` | `/story/{symbol}` | Working: price chart with numbered move markers, explanations, clickable citations |
| **Research** | `/research` | `/research/search`, `/research/analyze` | Working: search any SEC filer; fit score, radar vs your holdings, overlap checks, cited brief (first search of a company is live and slow; see `research_mode.md`) |
| **What Changed** | `/changes` | `/feed` | Working: ranked events with tier tabs, the holdings each reaches and how, last-close move, and cited sources |

## Files

| File | What it does |
|---|---|
| `src/api.ts` | Typed client for every endpoint. Start here to see what data each screen gets. |
| `src/hooks.ts` | Portfolio state (remembered in this browser; defaults to the sample portfolio), data loading, theme colors for canvas charts, element size |
| `src/components.tsx` | Portfolio bar, evidence quote (filing quote + source link), impact panel |
| `src/pages/XRayPage.tsx` | Home screen |
| `src/pages/MapPage.tsx` | Connection Map (react-force-graph-2d) |
| `src/pages/StoryPage.tsx` | Story Mode (TradingView Lightweight Charts v5) |
| `src/index.css` | Design tokens and styles |

## Design notes

- **Palette** (from the team's `pallette_03.jpg`): deep teal `#2b6777` (sidebar, primary buttons, price line), blue-gray `#c8d8e4` (soft fills), white cards on light gray `#f2f2f2`, and green-teal `#52ab98` (highlights). Light theme. JetBrains Mono throughout, bundled via `@fontsource-variable/jetbrains-mono`.
- **Soft components:** no hard outlines. Cards separate from the page by fill and a faint shadow; buttons, inputs, chips, and badges use tinted fills; focus shows a soft green-teal ring.
- **Colors are tokens** in `src/index.css`. Canvas charts (map, price chart) read the same tokens and the font through `useThemeColors`, so a token change restyles everything.
- **Map node colors are validated** for color-vision deficiency on white: holdings teal `#0086a4`, supported-not-owned orange, outside companies violet. The palette's own teals are too muted for data (they read as gray), so the map uses a more saturated teal of the same hue. Teal vs violet needs a second cue, which the map gives: holdings are larger, ringed, and always labeled; countries are gray squares.
- **The Connection Map has its own dark teal canvas** (`--map-bg: #122b33`) with light lines and labels, so the graph stands out from the light page. The node colors pass the same checks on it as on white.
- **Text contrast:** the green-teal `#52ab98` is too light for text on white/gray, so text uses a darker `#2f8a76`; muted text is 4.6:1 on white.
- **Prices are last-close facts, not live.** Quotes (`/quotes`) come from the saved Story Mode data and every screen labels them "Prices as of … close". Holdings are treated equally (no share counts), so nothing shows dollar portfolio value.
- **Up and down moves use arrows (▲▼) and a sign**, not color alone (`<Change>` in `src/components.tsx`).
- **Every claim links to its source.** Graph edges show the filing quote; story explanations show numbered citations that open the evidence.
- **No buy/sell language.** Competitors appear as "also affected", never as winners or losers.

## Known gaps

- There are no accounts; holdings are stored in the browser's localStorage.
- Map labels can overlap in the dense center; hover shows the full name.
- The production build is one ~640 KB bundle; code-split the map and chart pages if load time matters.
