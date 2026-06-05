# Postmortem — strategy_v6 (Band Rebalance)

_Window: 2020-03-01 → 2026-04-30_

_Single-cycle in-sample fit. The target_w sweep traces the return/drawdown
frontier — it shows the *shape* of a preference, not robust edge._

## 1. Headline — v6 vs B0

| arm | final_$ | return_% | max_dd_% | sharpe | sortino |
| --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 |
| v6 Band Rebalance | 8044.1 | 117.41 | -57.91 | 1.544 | 3.354 |



DD shallower than B0 by:  +10.45 pp

Return gap (v6 - B0):     -35.65 pp  ($-1,319.07)

Sortino delta:            +0.379

Sharpe delta:             +0.050

Realized harvest:         $93,345.71

Fees paid:                $189.06  (318 trims)

## 2. Experiment matrix (full window)

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_trims |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan |
| v6-base | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |
| v6-target-80 | 6546.26 | 76.93 | -43.25 | 4.114 | 1.602 | 25.11 | -2816.9 | 318.0 |
| v6-target-85 | 7103.49 | 91.99 | -49.3 | 3.766 | 1.581 | 19.07 | -2259.68 | 318.0 |
| v6-target-92 | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |
| v6-target-98 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | 0.0 |
| v6-drip-1w | 8589.44 | 132.15 | -63.82 | 3.111 | 1.51 | 4.55 | -773.73 | 318.0 |
| v6-drip-4w | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |
| v6-drip-8w | 7529.12 | 103.49 | -51.1 | 3.693 | 1.582 | 17.26 | -1834.05 | 318.0 |
| v6-drip-hold | 9073.57 | 145.23 | -62.12 | 3.157 | 1.522 | 6.25 | -289.6 | 6.0 |
| v6-band-03 | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |
| v6-band-05 | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |
| v6-band-08 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | 0.0 |
| v6-no-trim (ablation) | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | 0.0 |



_`v6-no-trim` equals B0 by construction (asserted). The target sweep is the

menu — lower target_w = more cushion, more give-up; it is a preference, not a

prediction. The drip sweep resolves the churn tension: `hold` parks trim

proceeds as standing cash at the lower weight instead of dripping back in._

## 3. Cross-version — v6-base vs v5-base vs B0

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_trims |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan |
| v5-base | 8956.24 | 142.06 | -67.67 | 2.969 | 1.492 | 0.69 | -406.92 | 11.0 |
| v6-base | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 |



_The falsifiable check on 'the FNG gate was decoration': v5-base (gate ON)

barely moved off B0 (DD ~-67.7%, 11 trims), while v6-base (gate OFF) trades

real return for a materially shallower drawdown. If v5-base and v6-base were

close, the gate would be doing the work; they are not._

## 4. Regime breakdown (Up / Down / Sideways)

| regime | days | v6_daily_mean_% | b0_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 771 | 0.2219 | 0.2272 | -0.0053 |
| Sideways | 313 | -0.0076 | -0.0166 | 0.009 |
| Up | 1141 | 0.393 | 0.4325 | -0.0396 |

## 5. Success criteria checklist (from strategy_v6.md)

- **[PASS]** 1. Max DD ≥ 8pp shallower than B0  —  actual: +10.45 pp (B0 -68.36%, v6 -57.91%)

- **[PASS]** 2. Sortino ≥ B0 + 0.3  —  actual: +0.379  (B0 2.975, v6 3.354)

- **[PASS]** 3. Sharpe ≥ B0  —  actual: +0.050  (B0 1.494, v6 1.544)

- **[PASS]** 4. Return give-up is risk-justified (accepted cost; fails only if 1-3 miss)  —  give-up -35.65 pp — risk-justified by 1-3

- **[PASS]** 5. target_w sensitivity monotone-ish and legible  —  returns [76.9, 92.0, 117.4, 153.1] / DDs [-43.3, -49.3, -57.9, -68.4] (target 0.80→0.98); interior_dominates=False



_Criteria 1–3 are the real test. If met, v6 is a valid frontier point and the

choice between it and B0 is a risk-tolerance decision, not a backtest decision._

## 6. Bootstrap 95% CIs (n=2000)

Mean weekly return delta (v6 - B0):  -0.1442%  [-0.2954%, +0.0092%]

Mean weekly value gap (v6 - B0):     $-733.20  [-829.75, -641.86]
