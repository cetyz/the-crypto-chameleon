# Postmortem — strategy_v2 (Tilt)

_Window: 2020-03-01 → 2026-04-30_

## 1. Headline gap (v2 − B0)

Final B0:  $9,363.17

Final v2:  $9,415.05

Final gap: $+51.89  (+0.55% of B0)

Best  gap: 2025-10-06  $+81.56

Worst gap: 2020-05-07  $-0.61

## 2. Cash drag (central question for v2)

Avg cash-reserve fraction (live phase): 0.42%

Hypothetical foregone $ if every Sunday's idle cash had been deployed and held to END:

  $+2,431.13   (upper bound — no signal cost in the counterfactual)

Forced-deploy events (reserve > 25%): 1

## 3. Per-cell forward returns (BTC fwd return after each weekly decision)

| trend | funding | n | f | fwd_1w | fwd_4w | fwd_12w |
| --- | --- | --- | --- | --- | --- | --- |
| Down | Cold | 63 | 0.65 | +1.44% | +6.03% | +21.07% |
| Down | Hot | 7 | 0.4 | +1.45% | +3.95% | -2.48% |
| Down | Neutral | 58 | 0.5 | -1.18% | -2.58% | -0.05% |
| Up | Cold | 22 | 1.0 | +1.11% | +4.13% | +22.14% |
| Up | Hot | 66 | 0.7 | +1.99% | +6.60% | +22.34% |
| Up | Neutral | 105 | 0.85 | +1.39% | +6.74% | +17.78% |

## 4. Experiment matrix (spec §Experiment matrix)

| arm | final_$ | return_% | max_dd_% | vs_B0_% |
| --- | --- | --- | --- | --- |
| v2-base | 9415.05 | 154.46 | -68.12 | 0.55 |
| v2-trend-only | 9417.99 | 154.54 | -68.12 | 0.59 |
| v2-flip-funding | 9419.53 | 154.58 | -68.13 | 0.6 |
| reserve=0.1 | 9448.0 | 155.35 | -68.18 | 0.91 |
| reserve=0.25 | 9415.05 | 154.46 | -68.12 | 0.55 |
| reserve=0.4 | 9405.39 | 154.2 | -68.1 | 0.45 |
| f_min=0.25 | 9415.05 | 154.46 | -68.12 | 0.55 |
| f_min=0.4 | 9415.05 | 154.46 | -68.12 | 0.55 |
| f_min=0.6 | 9422.53 | 154.66 | -68.18 | 0.63 |
| B0 (control) | 9363.17 | 153.06 | -68.36 | 0.0 |

## 5. Signal quality

n weekly observations (in-window, signals ready): 320


By trend:

  Down     n=128  mean fwd_1w=+0.25%  95% CI [-1.13%, +1.61%]

  Up       n=192  mean fwd_1w=+1.57%  95% CI [+0.38%, +2.72%]


By funding:

  Cold     n= 84  mean fwd_1w=+1.36%  95% CI [-0.08%, +2.70%]

  Hot      n= 73  mean fwd_1w=+1.94%  95% CI [+0.23%, +3.73%]

  Neutral  n=163  mean fwd_1w=+0.48%  95% CI [-0.88%, +1.83%]


Pearson corr(raw funding ann%, fwd_1w) = -0.053

## 6. Regime breakdown (v2 vs B0 within trend regimes)

| regime | days | B0_daily_mean_% | v2_daily_mean_% | delta_pp |
| --- | --- | --- | --- | --- |
| Down | 876 | 0.1894 | 0.1867 | -0.0027 |
| Up | 1349 | 0.3689 | 0.3694 | 0.0005 |
