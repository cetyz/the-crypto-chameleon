# Dashboard Edit Plan

Tweaks to the working SvelteKit mock-up. Companion to [dashboard_plan.md](dashboard_plan.md) — apply these on top of the v1 layout.

## Changes

### 1. Headline tiles — add "Capital invested"
Each summary tile (Chameleon, Control) gains a fourth metric: **Capital invested (USD)**, the account's starting capital.

- Render under the existing USD / BTC values in the same left-side stack.
- Use the existing `fmtUSD` helper.
- Source: `account.starting_capital_usd` is already on `Account` ([webapp/src/lib/types.ts:7](webapp/src/lib/types.ts#L7)) and reachable from `AccountSummary.account` — no schema change.

File: [webapp/src/lib/components/HeadlineTiles.svelte](webapp/src/lib/components/HeadlineTiles.svelte).

### 2. Equity chart — absolute USD default, BTC toggle
The big chart (currently "Return since inception", % normalized) becomes **Portfolio value** in absolute terms.

- Default y-axis: **absolute $USD value**.
- New toggle next to the time-range buttons: **USD / BTC**.
  - USD mode plots `chameleon_usd` / `control_usd` (already on `EquityPoint`, [webapp/src/lib/types.ts:25](webapp/src/lib/types.ts#L25)).
  - BTC mode plots the same series denominated in BTC.
- Time range selector (1M / 3M / All) stays as is.
- Y-domain: `[min * 0.98, max * 1.02]` (absolute values, no forced zero).
- Y-tick formatting: `$X,XXX` in USD mode, `0.0XXX BTC` in BTC mode.
- Heading: "Portfolio value" (was "Return since inception").

File: [webapp/src/lib/components/EquityChart.svelte](webapp/src/lib/components/EquityChart.svelte).

### 3. Supporting types/metrics
To keep the chart a dumb renderer, extend the equity series with BTC-denominated values:

- Add `chameleon_btc: number` and `control_btc: number` to `EquityPoint` in [webapp/src/lib/types.ts](webapp/src/lib/types.ts).
- Populate them in `buildEquitySeries` ([webapp/src/lib/metrics.ts](webapp/src/lib/metrics.ts)) using the existing `PriceMap` (BTC/USD already consulted there).

### 4. Update [dashboard_plan.md](dashboard_plan.md)
Reflect the spec changes:

- §2 "Headline comparison": list **Capital invested (USD)** as a fourth per-tile metric.
- §3 rename to "Portfolio value chart":
  - Default y-axis: absolute USD value (was: normalized % return since inception).
  - Add USD / BTC toggle alongside the 1M / 3M / All time-range selector.

## Out of scope for this edit
- No changes to header, sparklines, next-run strip, transaction tables, footer.
- No new routes; still single-page.
- No data-source or fixture changes beyond the BTC fields on `EquityPoint`.

## Verification
- `cd webapp && npm run dev`, open the page.
- Tiles show "Capital invested: $X" matching `accounts.json` for both accounts.
- Chart defaults to USD axis with `$` ticks; toggle flips to BTC values; time-range buttons still narrow the window in both modes.
- `npm run check` and `npm run build` pass after the `EquityPoint` extension.
