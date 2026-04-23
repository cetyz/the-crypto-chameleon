# Dashboard Plan

The SvelteKit dashboard is a public, read-only transparency tool comparing two Crypto.com Exchange accounts: the algorithmic **Chameleon** and the dumb DCA **Control**. It reads from Supabase (populated by the scheduled GitHub Actions job) and is deployed to Vercel. This document captures the agreed v1 layout so implementation sessions can proceed section-by-section.

## Layout — single scrollable page

### 1. Header strip
- Project name + one-line tagline.
- Links: Telegram channel, GitHub repo.

### 2. Headline comparison (two tiles, side-by-side)
For **each** account (Chameleon, Control), show four metrics:
- **% return since inception** (primary, largest).
- **Portfolio value in USD**.
- **Portfolio value in BTC** (e.g. "0.0412 BTC") — shows performance independent of USD volatility.
- **Capital invested (USD)** — the account's starting capital, for reference.

Small sparkline under each tile.

### 3. Portfolio value chart
- Single chart, two lines (Chameleon vs Control).
- Default y-axis: absolute USD value (not normalized).
- USD / BTC toggle alongside the time-range selector — BTC mode plots the portfolio denominated in BTC.
- Time range selector: 1M / 3M / All.

### 4. Next scheduled run countdown
- Small strip: "Next run in 3d 14h" + last-updated timestamp.
- Reinforces the weekly cadence.

### 5. Transaction log — two side-by-side tables
- Left: Chameleon. Right: Control.
- Columns: timestamp, side, asset, amount, price, USD value.
- Newest first; "load more" pagination.
- On narrow screens: stack vertically (Chameleon above Control).

### 6. Footer
- Disclaimer ("not financial advice"), data source note, last-updated timestamp.

## Out of scope for v1
- Holdings donut / allocation charts.
- Per-asset P&L breakdown.
- Separate routes (`/transactions`, etc.) — single page only.
- Any authenticated / write features.

## File structure (under `/webapp`)
- `src/routes/+page.svelte` — composes the sections.
- `src/routes/+page.server.ts` — loads Supabase data server-side (anon key, RLS-protected reads).
- `src/lib/components/Header.svelte`
- `src/lib/components/HeadlineTiles.svelte`
- `src/lib/components/EquityChart.svelte`
- `src/lib/components/NextRun.svelte`
- `src/lib/components/TransactionTable.svelte` (rendered twice, once per account)
- `src/lib/components/Footer.svelte`
- `src/lib/supabase.ts` — client initialization.
- `src/lib/metrics.ts` — derivations (% return, BTC-denominated value, equity curve series).

## Data dependencies
The layout assumes the Supabase schema can answer:
- All transactions per account (timestamp, side, asset, amount, price).
- Current holdings per account (derivable from transactions).
- A time series of BTC/USD prices to denominate portfolios in BTC and to value non-USD holdings historically for the equity curve.

Schema design is deferred and will be its own planning session.
