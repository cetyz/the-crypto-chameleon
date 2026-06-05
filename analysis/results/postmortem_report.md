# Postmortem report

## 1. Headline gap

```
Deposited:   $3,700.00
```
```
DCA final:   $8,877.45   (+139.9%)
```
```
Strat final: $9,322.72   (+152.0%)
```
```
Gap (strat - dca): $+445.28
```
```
Best  gap moment: 2025-10-06  $+1,188.77
```
```
Worst gap moment: 2022-08-13  $-96.98
```

## 2. Per-decision attribution (mean BTC fwd-return after each decision)

```
By policy cell:
```
```
trend funding natural   n  fwd_1w  fwd_4w  fwd_12w
 Down    Cold   Buy50  63  +1.44%  +6.03%  +21.07%
 Down     Hot  Sell50   7  +1.45%  +3.95%   -2.48%
 Down Neutral    Hold  58  -1.18%  -2.58%   -0.05%
   Up    Cold  Buy100  22  +1.11%  +4.13%  +22.14%
   Up     Hot    Hold  66  +1.99%  +6.60%  +22.34%
   Up Neutral   Buy50 105  +1.39%  +6.74%  +17.78%
```
```

```
```
By executed action:
```
```
 final   n  fwd_1w  fwd_4w  fwd_12w
Buy100  22  +1.11%  +4.13%  +22.14%
 Buy50 179  +1.24%  +5.83%  +18.22%
  Hold 113  +0.68%  +3.02%  +12.42%
Sell50   7  +1.45%  +3.95%   -2.48%
```
```

```
```
Patience override: 11 patience-forced buys; mean fwd 4w = -3.97%
```

## 3. Cash drag

```
Avg fraction of portfolio sitting in cash: 7.5%
```
```
Sum of daily USD-cash balances:            $353,291 USD-days
```
```
Hypothetical foregone $ if every Sunday's idle cash had been deployed
```
```
  and held to END: $+76,467.06
```
```
(Upper bound — assumes perfect deploy with no signal cost.)
```

## 4. Counterfactual arms

```
                     arm   final  return_%  max_dd_%
  Baseline DCA ($10/Tue) 8877.45    139.93    -63.85
       Baseline Strategy 9322.72    151.97    -67.43
Policy-off (100% Sunday) 9697.84    162.10    -68.79
              Trend-only 9634.39    160.39    -68.34
            Funding-only 9728.76    162.94    -68.53
             No-patience 9353.30    152.79    -66.95
                 No-sell 9733.21    163.06    -68.20
```

## 5. Signal quality

```
n weekly observations: 320
```
```

By trend:
```
```
  Down     n=128  mean fwd_1w=+0.25%  95% CI [-1.13%, +1.61%]
```
```
  Up       n=192  mean fwd_1w=+1.57%  95% CI [+0.38%, +2.72%]
```
```

By funding:
```
```
  Cold     n= 84  mean fwd_1w=+1.36%  95% CI [-0.08%, +2.70%]
```
```
  Hot      n= 73  mean fwd_1w=+1.94%  95% CI [+0.23%, +3.73%]
```
```
  Neutral  n=163  mean fwd_1w=+0.48%  95% CI [-0.88%, +1.83%]
```
```

Pearson corr(raw funding ann%, fwd_1w) = -0.053
```

## 6. Regime breakdown (strat vs dca within trend regimes)

```
regime  days  dca_total_%  strat_total_%
  Down   896     18243.54       18858.42
    Up  1356     17654.89       18545.45
```
