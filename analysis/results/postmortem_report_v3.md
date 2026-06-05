# Postmortem — strategy_v3 (Rebalancer)

_Window: 2020-03-01 → 2026-04-30_

## 1. Headline — drawdown / Sortino vs B3 (the actual scoreboard)

| arm | final_$ | return_% | max_dd_% | sharpe | sortino |
| --- | --- | --- | --- | --- | --- |
| B3 buy-and-hold | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 |
| v3 Rebalancer | 8207.21 | 121.82 | -54.15 | 1.601 | 3.581 |



DD shallower than B3 by:  -14.22 pp

Sortino delta vs B3:      +0.606

Return delta vs B3:       -1,155.96 USD

## 2. Rebalance activity

Trims:        2

Redeploys:    4

Deposit-buys: 73

In-band none: 242



Realized harvest (cash banked from trims): $1,152.42

Total fees paid:                            $4.13

Harvest − fees:                             $+1,148.28

## 3. Experiment matrix

| arm | final_$ | return_% | max_dd_% | sortino | vs_B3_dd_pp |
| --- | --- | --- | --- | --- | --- |
| v3-base (75/10) | 8207.21 | 121.82 | -54.15 | 3.581 | 14.22 |
| target=0.6 | 7022.74 | 89.8 | -43.73 | 4.199 | 24.64 |
| target=0.7 | 7837.02 | 111.81 | -50.75 | 3.75 | 17.61 |
| target=0.8 | 8246.43 | 122.88 | -57.07 | 3.371 | 11.29 |
| band=0.05 | 7954.53 | 114.99 | -53.58 | 3.563 | 14.78 |
| band=0.1 | 8207.21 | 121.82 | -54.15 | 3.581 | 14.22 |
| band=0.15 | 7964.88 | 115.27 | -53.98 | 3.484 | 14.39 |
| no-deposit-steer | 9066.63 | 145.04 | -62.12 | 3.235 | 6.24 |
| B3 (buy-and-hold) | 9363.17 | 153.06 | -68.36 | 2.975 | 0.0 |

## 4. Regime breakdown (Up / Down / Sideways)

| regime | days | v3_daily_mean_% | b3_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 771 | 0.223 | 0.2272 | -0.0042 |
| Sideways | 313 | -0.0076 | -0.0166 | 0.009 |
| Up | 1141 | 0.3855 | 0.4325 | -0.0471 |

## 5. BTC weight stats (live phase, post first deposit)

Mean:   76.95%

Min:    43.99%

Max:    85.87%

Target: 75.00%  ·  Band: ±10.00%
