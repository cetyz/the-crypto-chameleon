# Backtest report — strategy_v5 (Greed-Gated Trim)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v5.md`
- target_w: 0.92  ·  band: +0.05  (trim threshold w > 0.97)
- fng_trim_threshold: 90  ·  drip_weeks: 4
- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month.
- Fee per trade: 0.10%.  No cash yield.

## Headline results (standard scoreboard)

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v5 Greed-Gated Trim | 3700.0 | 8956.24 | 142.06 | -67.67 | 1.492 | 2.969 | 322.0 | 322.0 | 98.67 |

## v5 trim scorecard

- Distinct trim events:    **11**  (spec target: 2–8)
- Realized harvest:        $2,234.19
- Cumulative fees paid:    $8.17

Trim events (spec-mandated disclosure — date + FNG at firing):

| date | close | btc_weight | fng | usd_trimmed |
| --- | --- | --- | --- | --- |
| 2020-11-10 00:00:00+00:00 | 15297.21 | 1.0 | 90 | -51.0813 |
| 2020-12-01 00:00:00+00:00 | 18764.96 | 1.0 | 95 | -64.7417 |
| 2020-12-08 00:00:00+00:00 | 18324.11 | 1.0 | 95 | -60.4748 |
| 2020-12-15 00:00:00+00:00 | 19426.43 | 1.0 | 91 | -61.4831 |
| 2020-12-29 00:00:00+00:00 | 27385.0 | 1.0 | 91 | -91.7421 |
| 2021-01-05 00:00:00+00:00 | 33949.53 | 1.0 | 93 | -108.9006 |
| 2021-02-09 00:00:00+00:00 | 46420.42 | 1.0 | 95 | -163.0995 |
| 2021-02-16 00:00:00+00:00 | 49133.45 | 1.0 | 95 | -162.0768 |
| 2021-02-23 00:00:00+00:00 | 48891.0 | 1.0 | 94 | -154.8654 |
| 2024-03-05 00:00:00+00:00 | 63724.01 | 1.0 | 90 | -519.8127 |
| 2024-11-19 00:00:00+00:00 | 92310.79 | 1.0 | 90 | -795.9072 |

## Benchmarks

- **B0 — Deploy-on-arrival** (control). The headline comparison.

## Honest caveats (echoed from strategy_v5.md)

- Single mostly-up BTC cycle. FNG≥90 days may cluster around late-2021;
  v5's story can collapse to 'one well-timed trim'.
- FNG is composite, not orthogonal to signals we already had. Chosen for legibility.
- Drip is unconditional — gives some harvest back in regimes where the trim coincides with the top.
- If FNG≥90 never occurs in a cycle, v5 == B0. Feature, not bug, but worth saying.
- One cycle of in-sample tuning. The matrix is the only honest defense.

## Artifacts

- Equity curves: `output/equity_curves_v5.png`
- Per-decision log: `output/action_log_v5.csv`
- Postmortem: `results/postmortem_report_v5.md`
