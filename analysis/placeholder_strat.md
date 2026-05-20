# BTC Weekly Trading Strategy — v1 Specification

## Project Context

A "fun" A/B testing dashboard comparing a signal-driven weekly BTC strategy against vanilla weekly DCA. Both arms receive identical capital deposits ($50–100/week); the comparison is purely about *deployment timing and sizing*, not capital input. Hoarding USD is permitted on the strategy side — the dashboard tracks total USD deposited equally for both accounts and compares resulting account values.

Self-improvement / continuous re-optimization is **out of scope** for v1.

## Scope

| Item | Decision |
|---|---|
| Asset | BTC only |
| Cadence | Weekly |
| Capital per week | $50–100 USD |
| Position types | Long or cash (no margin) |
| "Short" semantics | Reducing/exiting long, never true short |
| Fee assumption | 0.1% per trade |
| Benchmark | Vanilla weekly DCA (always buys $X) |

## Signals

Two signals, deliberately uncorrelated in nature: one price-based, one positioning-based.

### Signal 1 — Trend (price-based)

- **Rule:** Weekly close vs 20-week SMA
- **States:** `Up` (close > SMA) / `Down` (close < SMA)
- **Data source:** OHLCV from any free public exchange API (Binance / Coinbase / Kraken / CoinGecko)
- **Rationale:** 20W ≈ 140 days, the weekly-cadence cousin of the widely-watched 200-day MA. Schelling-point validity — many participants watch this level.

### Signal 2 — Funding Rate (positioning-based)

- **Rule:** 8-hour perpetual funding from Binance, averaged over trailing 7 days, expressed as annualized % (×3 ×365)
- **States:** `Hot` / `Neutral` / `Cold` based on dynamic percentile thresholds
- **Thresholds:** Dynamic, computed from a rolling historical window. Specific window length and percentile cutoffs to be calibrated from actual data distribution (TBD).
- **Data source:** Binance `fapi/v1/fundingRate` (public, no auth)
- **Rationale:** Captures leveraged-trader positioning, genuinely independent of price level. Extreme positive funding = crowded longs (contrarian bearish); near-zero or negative = capitulation/apathy (contrarian bullish).
- **Data limitation:** Funding history starts ~2019–2020 depending on exchange. Backtest window is ~5–6 years, ~250–300 weekly observations. Statistically thin — frame conclusions accordingly.

## Action Space

| Action | Meaning |
|---|---|
| Buy 100% | Deploy all available USD |
| Buy 50% | Deploy half of available USD |
| Hold | Do nothing |
| Sell 50% | Sell half of current BTC holdings |

(10% and 100% sell sizes considered and rejected for v1: 10% feels like noise relative to action friction; 100% sell feels too dramatic for a single weekly signal.)

## Policy Table

The policy maps each combination of signal states to an action. Six states, one action each.

| Trend | Funding | Action | Reasoning |
|---|---|---|---|
| Up | Cold | Buy 100% | Trend confirms, no euphoria — best setup |
| Up | Neutral | Buy 50% | Trend confirms but no contrarian tailwind |
| Up | Hot | Hold | Don't chase euphoria even in uptrend |
| Down | Cold | Buy 50% | Contrarian capitulation buy against trend |
| Down | Neutral | Hold | No reason to act |
| Down | Hot | Sell 50% | Both signals bearish |

## Patience Override

Layered on top of the policy table — separate from it.

- **Trigger:** Counter `consecutive_holds` increments on any Hold week, resets to 0 on any Buy or Sell.
- **Threshold:** When `consecutive_holds >= 4` and the natural action is Hold → override to **Buy 50%**, then reset counter.
- **Philosophy:** The policy table represents what the strategy *believes* given current signals; the patience override represents the strategy *acknowledging it might be wrong* about prolonged inaction. Kept architecturally separate.

### Decision flow (pseudocode)

```
natural_action = policy_table[trend_state][funding_state]

if natural_action == Hold and consecutive_holds >= 4:
    final_action = Buy 50%
    consecutive_holds = 0
else:
    final_action = natural_action
    if final_action == Hold:
        consecutive_holds += 1
    else:
        consecutive_holds = 0

execute(final_action)
```

### Note on expected firing frequency

Only 2 of 6 policy states are Hold (Up+Hot, Down+Neutral). Four consecutive Holds requires the market to keep returning to those specific states for 4 weeks running — plausible but not common. The patience trigger may fire rarely in backtest; calibrate expectations.

## Open Items for Backtest Implementation

These were flagged but not finalized — to address before/during implementation:

1. **Execution timing.** Signal evaluated on weekly close. Execution assumed at same weekly close with 0.1% fee. Confirm no look-ahead.
2. **Warmup period.** 20-week SMA needs 20 weeks of data; dynamic funding thresholds need their rolling window. **Decision needed:** during warmup, does the strategy sit in cash, mirror DCA, or something else? Affects early-period comparison.
3. **Dynamic funding threshold spec.** Rolling window length (26 weeks?) and percentile cutoffs (80/20? 90/10?) to be set from data distribution inspection.
4. **Patience override edge case.** A Sell resets the counter (any deliberate action = strategy is "engaged"). Confirmed.

## Dashboard / Metrics

Beyond the obvious "total account value over time" comparison, surface:

- **Max drawdown** (each arm)
- **Time-in-market %** (strategy arm only — DCA is always 100%)
- **Number of trades** (strategy arm)
- **Sharpe and/or Sortino ratio** — important so risk-adjusted outcomes are visible (e.g. "DCA wins on raw return but strategy has half the volatility")
- **Confidence intervals** on outcomes — sample size is small (~250–300 weeks), so point estimates of edge are noisy. Show this explicitly rather than hiding it.
- **Patience-override flag** — when a forced Buy 50% fires, distinguish it visually from a signal-driven Buy. It's information about strategy behavior, not market state.

## Honest Caveats Carried Forward

- **Small sample.** ~5–6 years of usable history at weekly cadence covers roughly one full BTC cycle plus change. Don't over-interpret backtest Sharpe.
- **Signal correlation.** Trend and funding are reasonably independent in spirit, but both can fire bearish during major drawdowns simultaneously. The policy table accounts for this by design but watch for regimes where both are pinned in extreme states.
- **DCA is a strong baseline.** In a secular uptrend asset, "always invested" is hard to beat on raw return. Strategy's win condition is more likely risk-adjusted (lower drawdowns, better Sharpe) than absolute return.
- **No self-improvement.** Parameters are set once and held. Any "tuning" after seeing backtest results risks overfitting; if done, document what was changed and why.

## What v1 Deliberately Does NOT Include

- Multi-timeframe analysis
- Additional signals (F&G index, on-chain, stablecoin supply, hash rate)
- Volatility-based position sizing
- Stop-losses or take-profit rules
- Regime detection / parameter switching
- Any form of online learning or self-tuning