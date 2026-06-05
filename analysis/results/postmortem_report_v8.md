# Postmortem — strategy_v8 (Funded Basket)

_Window: 2020-03-01 → 2026-04-30_

_Single-cycle in-sample fit (~120 weekly obs). The dip-buying half is
exercised in essentially two declines (2020, 2022) — its measured benefit
rests on very few events. The target_w sweep traces the return/drawdown
frontier — the *shape* of a preference, not robust edge._

## 1. Headline — v8 vs B0

| arm | final_$ | return_% | max_dd_% | sharpe | sortino |
| --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 |
| v8 Funded Basket | 8674.22 | 134.44 | -61.89 | 1.524 | 3.186 |



DD shallower than B0 by:  +6.47 pp

Return gap (v8 - B0):     -18.62 pp  ($-688.94)

Sortino delta:            +0.211

Sharpe delta:             +0.030

Trades:                   1 sells, 31 buys  (gross buy $2,812.79, sell $109.56)

Fees paid:                $2.92



_With only ~10% cash and a ±3% *weight* band, breaching the upper edge takes

a very large up-week, so v8-base sells rarely (one sell over the whole window).

The buy side fires far more often, but for two different reasons across the

sample. While the book is tiny (2020-21) a single $50 deposit is a large

fraction of the portfolio and trips the lower band on its own. Once the book is

multi-thousand-dollar (2024+), a $50 deposit can no longer breach ±3% alone and

pools as cash exactly as the spec says — so the later buys are not deposit-

driven but crash-driven: the cash sleeve deployed into sharp declines._

## 2. Experiment matrix (full window)

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_sell | n_buy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan | nan |
| v8-base (t0.90 b0.03) | 8674.22 | 134.44 | -61.89 | 3.186 | 1.524 | 6.47 | -688.94 | 1.0 | 31.0 |
| v8-target-80 | 8024.15 | 116.87 | -55.82 | 3.425 | 1.552 | 12.54 | -1339.02 | 11.0 | 35.0 |
| v8-target-85 | 8540.06 | 130.81 | -58.96 | 3.325 | 1.542 | 9.4 | -823.11 | 7.0 | 34.0 |
| v8-target-90 | 8674.22 | 134.44 | -61.89 | 3.186 | 1.524 | 6.47 | -688.94 | 1.0 | 31.0 |
| v8-target-95 | 9067.03 | 145.05 | -64.99 | 3.083 | 1.511 | 3.37 | -296.13 | 0.0 | 34.0 |
| v8-band-00 | 8752.99 | 136.57 | -62.5 | 3.17 | 1.524 | 5.87 | -610.17 | 130.0 | 188.0 |
| v8-band-02 | 8664.33 | 134.17 | -62.45 | 3.168 | 1.521 | 5.92 | -698.84 | 5.0 | 46.0 |
| v8-band-03 | 8674.22 | 134.44 | -61.89 | 3.186 | 1.524 | 6.47 | -688.94 | 1.0 | 31.0 |
| v8-band-05 | 8685.73 | 134.75 | -61.37 | 3.21 | 1.528 | 6.99 | -677.44 | 0.0 | 24.0 |
| v8-vol-band (variant) | 8883.44 | 140.09 | -61.71 | 3.202 | 1.528 | 6.66 | -479.73 | 4.0 | 36.0 |
| v8-one-way (ablation) | 8675.79 | 134.48 | -61.31 | 3.209 | 1.524 | 7.05 | -687.38 | 13.0 | 74.0 |
| v8-cadence-monthly (variant) | 8593.76 | 132.26 | -61.49 | 3.235 | 1.472 | 6.87 | -769.4 | 0.0 | 27.0 |



_The target sweep is the menu — lower `target_w` = bigger funded buffer, more

drag, more dip-buying ammunition; it is a preference, not a prediction. The

band sweep trades trade-frequency against tracking: `band=0` snaps to target

every Tuesday (v6-like frequency); wider = fewer, larger rebalances. The

vol-band variant must BEAT the best static band to justify its extra knobs

(criterion 7). The one-way ablation is the load-bearing test of whether

dip-buying earns its keep (criterion 4)._



**Note on the one-way ablation — it is not a clean flag-flip.** v8 is funded

100% by DCA deposits and has no deposit-deploy step, so the position is

bootstrapped entirely through the buy branch: a deposit arrives as cash, weight

drops below target, and the buy branch is the *only* thing that ever acquires

BTC. Deposit-deployment and dip-buying are the **same operation**. Taken

literally, 'never buy when under' leaves the portfolio permanently all-cash

(return 0). To make a *meaningful* one-way arm — the spec's own 'v6 with a

funded sleeve and no drip' — we had to reintroduce the B0 deposit-deploy spine

v8 removed: deploy deposits unconditionally, sell-only on over-weight, hold

proceeds as a non-redeployed sleeve. **The consequence is conceptual, not

numerical: 'one rule' can only express the TWO-way basket. Isolating the buy

half forces v8 back into a v6-shaped object, so criterion 4 (two-way vs

one-way) is essentially the same question as criterion 3 (v8 vs v6).** Read

the two together._

## 3. Cross-version — v8-base vs v6-base vs B0 (the decisive row)

| arm | final_$ | return_% | max_dd_% | sortino | sharpe | dd_vs_B0_pp | ret_vs_B0_$ | n_sell | n_buy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 9363.17 | 153.06 | -68.36 | 2.975 | 1.494 | 0.0 | 0.0 | nan | nan |
| v6-base | 8044.1 | 117.41 | -57.91 | 3.354 | 1.544 | 10.45 | -1319.07 | 318.0 | 0.0 |
| v8-base | 8674.22 | 134.44 | -61.89 | 3.186 | 1.524 | 6.47 | -688.94 | 1.0 | 31.0 |



_This is the row that justifies v8's existence over its predecessor. If the

funded two-way basket can't beat the transient one-way trimmer (v6) on

{risk-adjusted OR drawdown} without losing the other, the permanent cash drag

wasn't worth paying and v6 stands (criterion 3). `n_sell` for v6 counts trims._

## 4. Regime breakdown (Up / Down / Sideways)

| regime | days | v8_daily_mean_% | b0_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 771 | 0.225 | 0.2272 | -0.0023 |
| Sideways | 313 | -0.0105 | -0.0166 | 0.0061 |
| Up | 1141 | 0.409 | 0.4325 | -0.0236 |



_The rebalancing bonus (buy-low/sell-high) should show up as a positive delta

in Down/Sideways; the cash drag and early-selling show up as a negative delta

in Up. Over one mostly-up cycle the Up weeks dominate the headline._

## 5. Success criteria checklist (from strategy_v8.md)

- **[FAIL]** 1. Sortino ≥ B0 + 0.3 AND Sharpe ≥ B0  —  Sortino +0.211 (B0 2.975, v8 3.186); Sharpe +0.030 (B0 1.494, v8 1.524)

- **[PASS]** 2. Max DD not worse than B0  —  v8 -61.89% vs B0 -68.36%  (+6.47 pp)

- **[FAIL]** 3. Beats v6-base on {risk-adj OR drawdown} without losing the other  —  v8 vs v6: Sortino -0.168, Sharpe -0.021, DD -3.98 pp (v6 DD -57.91%)

- **[FAIL]** 4. Two-way beats v8-one-way (dip-buying earns its keep; one-way = v6-shaped, deposit-deploy spine + sell-only — see §2 note)  —  two-way Sortino 3.186/Sharpe 1.524 vs one-way 3.209/1.524 (one-way return 134.48%, DD -61.31%)

- **[FAIL]** 5. Return give-up is risk-justified (accepted cost; fails only if 1-2 miss)  —  give-up -18.62 pp — NOT covered: 1-2 not both met

- **[PASS]** 6. target_w sweep monotone-ish and legible  —  returns [116.9, 130.8, 134.4, 145.1] / DDs [-55.8, -59.0, -61.9, -65.0] (target 0.80→0.95); interior_dominates=False

- **[FAIL]** 7. If kept, vol-band beats best static band (v8-band-05)  —  vol-band Sortino 3.202/Sharpe 1.528 vs best static 3.210/1.528 — does not beat it, DROP the variant



_Load-bearing rows: **criterion 4** (does buying dips help?) and **criterion 3**

(does the permanent cash drag pay for itself vs v6?). If 1, 3, and 4 hold, v8 is

both simpler and better than v6 and becomes the lineage's main line. If 3 fails,

v8's cleanliness isn't worth its drag and v6 stands. If 4 fails, the basket

should be one-way and you've rederived v6-without-drip._

## 6. Bootstrap 95% CIs (n=2000)

Mean weekly return delta (v8 - B0):  -0.0829%  [-0.1747%, +0.0123%]

Mean weekly value gap (v8 - B0):     $-389.53  [-445.00, -337.45]
