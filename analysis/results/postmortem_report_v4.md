# Postmortem — strategy_v4 (Active Sleeve)

_Window: 2020-03-01 → 2026-04-30_

_Per spec: this is a toy fit to a single mostly-up BTC cycle. 
Sweep results show the *shape* of trade-offs, not robust edge._

## 1. Headline — v4 vs B0 (standard + activity scoreboard)

| arm | final_$ | return_% | max_dd_% | sharpe | sortino |
| --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 |
| v4 Active Sleeve | 8995.76 | 143.13 | -67.66 | 1.495 | 2.966 |



DD shallower than B0 by:  -0.70 pp

Return delta vs B0:       -367.41 USD



v4 activity scoreboard (the actual goal):

| n_decisions_live | n_active | active_weeks_% | mean_abs_value_gap_$ | mean_abs_weight_gap | avg_sleeve_frac | trim | dip_buy | drift_redeploy | hold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 322.0 | 162.0 | 50.31 | 215.85 | 0.017 | 0.0275 | 0.0 | 161.0 | 1.0 | 160.0 |

## 2. Rebalance activity (live phase)

Trims:           0

Dip-buys:        161

Drift-redeploys: 1

Holds:           160



Realized harvest from trims: $0.00

Total fees paid:              $3.70

Harvest − fees:               $-3.70

## 3. Experiment matrix (full window)

| arm | final_$ | return_% | max_dd_% | sortino | vs_B0_dd_pp | vs_B0_ret_$ | active_% | divergence_$ | avg_sleeve | n_trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 0.0 | 0.0 | nan | nan | nan | nan |
| v4-base | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-sleeve-06 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-sleeve-12 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-sleeve-20 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-dipmin-1 | 9007.44 | 143.44 | -67.68 | 2.967 | 0.69 | -355.72 | 56.83 | 209.62 | 0.0268 | 183.0 |
| v4-dipmin-3 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-dipmin-6 | 8920.84 | 141.1 | -67.54 | 2.965 | 0.83 | -442.32 | 40.06 | 259.76 | 0.0305 | 129.0 |
| v4-curve-linear | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-curve-convex | 8643.23 | 133.6 | -67.06 | 2.961 | 1.3 | -719.94 | 51.55 | 429.51 | 0.0428 | 166.0 |
| v4-eager-redeploy | 8996.0 | 143.14 | -67.66 | 2.966 | 0.7 | -367.17 | 50.62 | 215.69 | 0.0273 | 163.0 |
| v4-trim-10 | 8810.95 | 138.13 | -62.36 | 3.148 | 6.0 | -552.22 | 77.95 | 372.8 | 0.0999 | 251.0 |
| v4-trim-15 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |
| v4-trim-20 | 8995.76 | 143.13 | -67.66 | 2.966 | 0.7 | -367.41 | 50.31 | 215.85 | 0.0275 | 162.0 |

## 4. Regime breakdown (Up / Down / Sideways) — labeling only

| regime | days | v4_daily_mean_% | b0_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 771 | 0.2312 | 0.2272 | 0.0039 |
| Sideways | 313 | -0.019 | -0.0166 | -0.0024 |
| Up | 1141 | 0.4242 | 0.4325 | -0.0083 |

## 5. Bootstrap 95% CIs (n=2000)

Mean |weekly value gap vs B0|:  $215.85  [198.53, 234.16]

Active-week rate:               50.31%  [44.72%, 55.59%]
