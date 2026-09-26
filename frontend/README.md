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
| **Research** | `/research` | none yet | Placeholder |
| **What Changed feed** | none | none yet | Not started |

## Files

| File | What it does |
|---|---|
| `src/api.ts` | Typed client for every endpoint. Start here to see what data each screen gets. |
| `src/hooks.ts` | Portfolio state (remembered in this browser; defaults to the sample portfolio), data loading, theme colors for canvas charts, element size |
| `src/components.tsx` | Portfolio bar, evidence quote (filing quote + source link), impact panel |
| `src/pages/XRayPage.tsx` | Home screen |
| `src/pages/MapPage.tsx` | Connection Map (react-force-graph-2d) |
| `src/pages/StoryPage.tsx` | Story Mode (TradingView Lightweight Charts v5) |
| `src/index.css` | Design tokens and styles (dark theme) |

## Design notes

- **Look:** dark slate with one amber accent, JetBrains Mono throughout (bundled via `@fontsource-variable/jetbrains-mono`), uppercase letter-spaced section labels, and a left sidebar. Dark only.
- **Colors are tokens** in `src/index.css`. Canvas charts (map, price chart) read the same tokens and the font through `useThemeColors`, so a token change restyles everything.
- **Bright amber (`--accent`) is for UI only** (active nav, buttons, focus, highlights). Data uses a darker amber (`--series-1`), because the bright one fails the chart lightness check on the dark background.
- **Map node colors are validated** for color-vision deficiency on the card surface: holdings amber, supported-not-owned blue, outside companies aqua. Countries are gray squares, so shape also carries the difference.
- **Up and down moves use arrows (▲▼) and a sign**, not color alone.
- **Every claim links to its source.** Graph edges show the filing quote; story explanations show numbered citations that open the evidence.
- **No buy/sell language.** Competitors appear as "also affected", never as winners or losers.

## Known gaps

- There are no accounts; holdings are stored in the browser's localStorage.
- Map labels can overlap in the dense center; hover shows the full name.
- The production build is one ~640 KB bundle; code-split the map and chart pages if load time matters.
