# Postmortem — strategy_v7 (Fear-Gated Warchest)

_Window: 2020-03-01 → 2026-04-30_

**Headline verdict: NOT MET: criterion 1 and/or 2 failed — see checklist.**

_Single-cycle in-sample fit, and worse than usual here: the buy-gate only
acts in extreme-fear windows, of which there are ~2 in this sample. Read the
threshold sweep as the shape of a thin bet, not as robust edge._

## 1. Headline — v7 vs B0

| arm | final_$ | return_% | max_dd_% | sharpe | sortino |
| --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 |
| v7 Fear-Gated Warchest | 4352.02 | 17.62 | -43.01 | 1.569 | 3.818 |



DD shallower than B0 by:  +25.35 pp

Return gap (v7 - B0):     -135.44 pp  ($-5,011.15)

Sortino delta:            +0.843

Sharpe delta:             +0.075

Realized harvest to chest: $20,427.62

Warchest balance at end:   $1,318.70  (idle cash, 0% yield)

Peak warchest balance:     $4,086.49

Fees paid:                $43.26  (318 trims, 67 warchest deploys)

## 2. Experiment matrix (full window)

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_trims | n_wc_buys |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan | nan |
| v7-base | 4352.02 | 17.62 | -43.01 | 3.818 | 1.569 | 25.35 | -5011.15 | 318.0 | 67.0 |
| v7-thr-15 | 4296.09 | 16.11 | -29.5 | 5.439 | 1.638 | 38.86 | -5067.07 | 318.0 | 23.0 |
| v7-thr-20 | 4406.15 | 19.09 | -38.28 | 4.495 | 1.616 | 30.09 | -4957.02 | 318.0 | 40.0 |
| v7-thr-25 | 4352.02 | 17.62 | -43.01 | 3.818 | 1.569 | 25.35 | -5011.15 | 318.0 | 67.0 |
| v7-thr-30 | 4828.88 | 30.51 | -47.54 | 3.694 | 1.569 | 20.83 | -4534.28 | 318.0 | 96.0 |
| v7-drip-1w | 4528.28 | 22.39 | -56.07 | 2.829 | 1.492 | 12.29 | -4834.88 | 318.0 | 67.0 |
| v7-drip-4w | 4352.02 | 17.62 | -43.01 | 3.818 | 1.569 | 25.35 | -5011.15 | 318.0 | 67.0 |
| v7-drip-8w | 4314.06 | 16.6 | -31.44 | 4.932 | 1.614 | 36.93 | -5049.11 | 318.0 | 67.0 |
| v7-warchest-in-denom | 9338.63 | 152.4 | -65.56 | 3.122 | 1.519 | 2.8 | -24.54 | 26.0 | 67.0 |
| v7-backstop-13 | 4886.14 | 32.06 | -43.22 | 3.927 | 1.586 | 25.14 | -4477.03 | 318.0 | 80.0 |
| v7-backstop-26 | 4518.24 | 22.11 | -43.06 | 3.747 | 1.569 | 25.3 | -4844.92 | 318.0 | 74.0 |
| v7-null-no-signal | 6605.36 | 78.52 | -36.58 | 4.68 | 1.648 | 31.78 | -2757.8 | 318.0 | 318.0 |
| v7-no-warchest (=v6) | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 | nan |



_`v7-no-warchest (=v6)` is the committed v6 run (proceeds dripped straight

back in) — the floor that isolates what the warchest itself does. The

threshold sweep tests how deep fear must be to fire (lower = rarer, deeper

buys, more idle cash); the drip sweep tests lump (1w) vs spread (8w) on a

trigger. `warchest-in-denom` self-damps trims as the chest grows. The two

rows that decide v7's fate are `v7-null-no-signal` and `v7-no-warchest`._

## 3. The decisive comparison — does the fear-gate earn its keep?

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_trims | n_wc_buys |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan | nan |
| v6-base (drip-in) | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 | nan |
| v7-null (dumb clock) | 6605.36 | 78.52 | -36.58 | 4.68 | 1.648 | 31.78 | -2757.8 | 318.0 | 318.0 |
| v7-base (fear-gate) | 4352.02 | 17.62 | -43.01 | 3.818 | 1.569 | 25.35 | -5011.15 | 318.0 | 67.0 |



_Criterion 1 (load-bearing): v7-base must beat **v7-null** on {return OR

drawdown} without losing the other. v7-null deploys the same warchest on a

dumb 12-week clock with no FNG. If the fear-gate cannot dominate the dumb

clock, the FNG signal is decoration — the same conclusion v5 reached on the

sell side, reproduced on the buy side. Criterion 2: v7-base must at least

match v6-base on risk-adjusted metrics, or the reintroduced surface area

failed to pay for itself._

## 4. Cross-version note

_`v7-no-warchest (=v6)` above is the committed `simulate_v6` run verbatim

(read-only import). It is both the v7 no-warchest ablation and the v6

cross-version anchor: every metric there is identical to analysis_report_v6

by construction, so the gap between it and v7-base is purely the warchest._

## 5. Regime breakdown (Up / Down / Sideways)

| regime | days | v7_daily_mean_% | b0_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 771 | 0.2353 | 0.2272 | 0.0081 |
| Sideways | 313 | 0.0286 | -0.0166 | 0.0452 |
| Up | 1141 | 0.2844 | 0.4325 | -0.1481 |



_v7 sheds return in Up regimes (warchest drains BTC and parks the proceeds

as idle cash that misses the up-leg) and is meant to claw it back by buying

the Down/Sideways fear windows. Whether the claw-back covers the give-up is

the whole question._

## 6. Success-criteria checklist (from strategy_v7.md)

- **[FAIL]** 1. Beats v7-null on {return OR DD} without losing the other (LOAD-BEARING)  —  v7 final $4,352 vs null $6,605 (Δ$-2,253); v7 DD -43.01% vs null -36.58% (Δ-6.43pp)

- **[PASS]** 2. At least matches v6-base on risk-adjusted (DD, Sortino, Sharpe)  —  DD -43.01 vs v6 -57.91; Sortino 3.818 vs 3.354; Sharpe 1.569 vs 1.544

- **[PASS]** 3. DD ≥ 8pp shallower than B0; Sortino ≥ B0+0.3; Sharpe ≥ B0  —  DD Δ+25.35pp (ok); Sortino Δ+0.843 (ok); Sharpe Δ+0.075 (ok)

- **[FAIL]** 4. Return give-up risk-justified (accepted cost; holds iff 1-3 all pass)  —  give-up -135.44pp vs B0 — NOT covered: 1-3 not all met

- **[PASS]** 5. fng_buy_threshold sweep legible (no interior point dominates both ends)  —  returns [16.1, 19.1, 17.6, 30.5] / DDs [-29.5, -38.3, -43.0, -47.5] (thr 15→30); interior_dominates=False



_Criterion 1 is the test v7 most needs to pass. If it fails, sentiment does

not help on the buy side either, and the honest conclusion — symmetric with

v5 — is that the FNG signal is decoration on both sides of the trade, and v7

should collapse back to v6 (or a slower-drip v6)._

## 7. Bootstrap 95% CIs (n=2000)

Mean weekly return delta (v7 - null):  -0.1568%  [-0.3981%, +0.0889%]

Mean weekly return delta (v7 - v6):    -0.3316%  [-0.7590%, +0.0703%]



_CIs that straddle zero mean the fear-gate's weekly edge over the dumb clock

(and over v6) is not statistically distinguishable from noise on ~120 weekly

observations — expected given only ~2 fear episodes drive the buy side._
