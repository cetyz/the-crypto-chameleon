# Backtest report — strategy_v3 (Allocation Rebalancer)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v3.md`
- target_w: 0.75  ·  band: ±0.1
- Rebalance-only sells (no directional sells).
- Deposit cadence: $50 on the last Friday of each calendar month.
- Warmup: SMA20w + funding26w; mirrors B0 (deploy on next Tue).
- Fee per trade: 0.10%

## Headline results

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| B2 v1 (new cadence) | 3700.0 | 8854.07 | 139.3 | -66.94 | 1.502 | 3.043 | nan | nan | nan |
| B3 buy-and-hold | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v3 Rebalancer | 3700.0 | 8207.21 | 121.82 | -54.15 | 1.601 | 3.581 | 79.0 | 321.0 | 98.76 |

## Rebalance activity (live phase)

- Live weekly decisions: 321
- Avg BTC weight: 76.95%
- Cumulative realized harvest (cash banked from trims): $1,152.42
- Cumulative fees paid: $4.13

By action:

| action | n |
| --- | --- |
| none | 242 |
| deposit_buy | 73 |
| redeploy | 4 |
| trim | 2 |

## Benchmarks

- **B0 — Deploy-on-arrival** (control).
- **B2 — v1 strategy** on the new calendar.
- **B3 — Buy-and-hold of v3's deposits** (the headline comparison; see spec §Benchmarks).
  Note: with monthly deposits fully deployed on arrival, B3 == B0 by construction.

## Artifacts

- Equity curves: `output/equity_curves_v3.png`
- Per-decision log: `output/action_log_v3.csv`
- Postmortem: `results/postmortem_report_v3.md`
