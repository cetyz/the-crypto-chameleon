# Backtest report — strategy_v2 (Tilt)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v2.md`
- Action space: continuous f in [0.4, 1.0]; never sells.
- RESERVE_CAP: 0.25 of portfolio_value.
- Deposit cadence: $50 on the last Friday of each calendar month.
- Warmup: SMA20w + funding26w; mirrors B0 (deploy on next Tue).
- Fee per trade: 0.10%

## Headline results

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| B2 v1 (new cadence) | 3700.0 | 8854.07 | 139.3 | -66.94 | 1.502 | 3.043 | nan | nan | nan |
| v2 Tilt | 3700.0 | 9415.05 | 154.46 | -68.12 | 1.511 | 2.973 | 286.0 | 321.0 | 98.76 |

## Action stats (live-phase only)

- Live weekly decisions: 321
- Avg cash-reserve fraction: 0.4%
- Forced-deploy events (reserve > cap): 1

By (trend, funding) cell:

| trend | funding | n | f |
| --- | --- | --- | --- |
| Down | Cold | 63 | 0.65 |
| Down | Hot | 7 | 0.4 |
| Down | Neutral | 58 | 0.5 |
| Up | Cold | 22 | 1.0 |
| Up | Hot | 66 | 0.7 |
| Up | Neutral | 105 | 0.85 |

## Benchmarks

- **B0 — Deploy-on-arrival** (the control account, the real bar).
- **B2 — v1 strategy** re-simulated on the monthly-last-Friday calendar.

## Artifacts

- Equity curves: `output/equity_curves_v2.png`
- Per-decision log: `output/action_log_v2.csv`
- Postmortem: `results/postmortem_report_v2.md`
