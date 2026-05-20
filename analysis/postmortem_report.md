# Postmortem report

## 1. Headline gap

```
Deposited:   $1,400.00
```
```
DCA final:   $1,391.82   (-0.6%)
```
```
Strat final: $1,370.71   (-2.1%)
```
```
Gap (strat - dca): $-21.11
```
```
Best  gap moment: 2025-10-06  $+68.26
```
```
Worst gap moment: 2026-02-24  $-45.88
```

## 2. Per-decision attribution (mean BTC fwd-return after each decision)

```
By policy cell:
```
```
trend funding natural  n  fwd_1w  fwd_4w  fwd_12w
 Down    Cold   Buy50 23  +0.80%  +1.72%  +19.87%
 Down     Hot  Sell50  1  +4.07%  +2.11%  -20.73%
 Down Neutral    Hold 19  -0.03%  -1.69%   -3.34%
   Up    Cold  Buy100 14  -0.85%  +1.54%   +6.26%
   Up     Hot    Hold 22  +2.81%  +6.61%   +7.73%
   Up Neutral   Buy50 42  +0.20%  +3.64%   +5.93%
```
```

```
```
By executed action:
```
```
 final  n  fwd_1w  fwd_4w  fwd_12w
Buy100 14  -0.85%  +1.54%   +6.26%
 Buy50 69  +0.60%  +2.63%   +8.32%
  Hold 37  +1.26%  +3.67%   +4.05%
Sell50  1  +4.07%  +2.11%  -20.73%
```
```

```
```
Patience override: 4 patience-forced buys; mean fwd 4w = -2.92%
```

## 3. Cash drag

```
Avg fraction of portfolio sitting in cash: 8.0%
```
```
Sum of daily USD-cash balances:            $37,384 USD-days
```
```
Hypothetical foregone $ if every Sunday's idle cash had been deployed
```
```
  and held to END: $-335.89
```
```
(Upper bound — assumes perfect deploy with no signal cost.)
```

## 4. Counterfactual arms

```
                     arm   final  return_%  max_dd_%
  Baseline DCA ($10/Tue) 1391.82     -0.58    -36.19
       Baseline Strategy 1370.71     -2.09    -40.90
Policy-off (100% Sunday) 1421.45      1.53    -42.10
              Trend-only 1404.40      0.31    -40.01
            Funding-only 1391.81     -0.58    -41.44
             No-patience 1384.43     -1.11    -39.91
                 No-sell 1384.75     -1.09    -40.45
```

## 5. Signal quality

```
n weekly observations: 120
```
```

By trend:
```
```
  Down     n= 43  mean fwd_1w=+0.51%  95% CI [-1.23%, +2.27%]
```
```
  Up       n= 77  mean fwd_1w=+0.77%  95% CI [-0.59%, +2.15%]
```
```

By funding:
```
```
  Cold     n= 36  mean fwd_1w=+0.21%  95% CI [-1.69%, +2.05%]
```
```
  Hot      n= 23  mean fwd_1w=+2.86%  95% CI [+0.11%, +5.89%]
```
```
  Neutral  n= 61  mean fwd_1w=+0.13%  95% CI [-1.33%, +1.64%]
```
```

Pearson corr(raw funding ann%, fwd_1w) = +0.028
```

## 6. Regime breakdown (strat vs dca within trend regimes)

```
regime  days  dca_total_%  strat_total_%
  Down   301       332.28         320.62
    Up   550      2683.64        2641.42
```
