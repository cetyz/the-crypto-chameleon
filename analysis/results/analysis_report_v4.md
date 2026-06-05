# Backtest report — strategy_v4 (Active Sleeve)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v4.md`
- target_w: 0.85  ·  sleeve_target: 0.12
- upper_band: +0.15  ·  lower_band: −0.05
- dip_min: 3.00%  ·  dip_ref_weeks: 26  ·  curve: linear (cap 25%)
- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month.
- Warmup: until 26 trailing weekly closes; falls back to B0.
- Fee per trade: 0.10%.  No cash yield.

## Headline results (standard scoreboard)

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v4 Active Sleeve | 3700.0 | 8995.76 | 143.13 | -67.66 | 1.495 | 2.966 | 322.0 | 322.0 | 98.67 |

## v4 activity metrics (the actual scoreboard per spec)

Per strategy_v4.md, v4's job is visible weekly activity and divergence from B0,
not return. Return drag is expected; treat any drawdown win as bonus.

| n_decisions_live | n_active | active_weeks_% | mean_abs_value_gap_$ | mean_abs_weight_gap | avg_sleeve_frac | trim | dip_buy | drift_redeploy | hold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 322.0 | 162.0 | 50.31 | 215.85 | 0.017 | 0.0275 | 0.0 | 161.0 | 1.0 | 160.0 |

- Realized harvest from trims: $0.00
- Cumulative fees paid:        $3.70

## Benchmarks

- **B0 — Deploy-on-arrival** (control). Per spec, the *only* comparison that matters here.
  B3 is identical to B0 by construction and is dropped.

## Honest caveats (echoed from strategy_v4.md)

- This is a toy tuned to one mostly-up BTC cycle. Knobs are fit to this window.
- The activity is the product, not the returns.
- Dip-buying in a single bull cycle flatters itself; backtest can't show the failure mode where a dip keeps dipping.
- The ~12% permanent sleeve is a standing tax on return.

## Artifacts

- Equity curves: `output/equity_curves_v4.png`
- Per-decision log: `output/action_log_v4.csv`
- Postmortem: `results/postmortem_report_v4.md`
