# Backtest report

_Window: 2020-03-01 → 2026-04-30 (74 months of deposits)_

## Run parameters

- Monthly deposit: $50  ·  DCA Tuesday spend: $10
- Fee per trade: 0.10%
- Trend SMA: 20 weeks
- Funding window: 26 weeks  ·  hot/cold percentiles: 80/20
- Patience override threshold: 4 consecutive holds

## Headline results

| arm      |   deposited |   final_value |   total_return_% |   max_drawdown_% |   sharpe |   sortino |   n_trades |   time_in_market_% |   patience_fires |
|:---------|------------:|--------------:|-----------------:|-----------------:|---------:|----------:|-----------:|-------------------:|-----------------:|
| DCA      |        3700 |       8877.45 |           139.93 |           -63.85 |    1.381 |     3.206 |        nan |             nan    |              nan |
| Strategy |        3700 |       9322.72 |           151.97 |           -67.43 |    1.457 |     3.123 |        208 |              99.38 |               11 |

## Action distribution

By executed action:

| action   |   n |
|:---------|----:|
| Buy50    | 179 |
| Hold     | 113 |
| Buy100   |  22 |
| Sell50   |   7 |

By (trend, funding) cell:

| trend   | funding   |   n | natural   |
|:--------|:----------|----:|:----------|
| Down    | Cold      |  63 | Buy50     |
| Down    | Hot       |   7 | Sell50    |
| Down    | Neutral   |  58 | Hold      |
| Up      | Cold      |  22 | Buy100    |
| Up      | Hot       |  66 | Hold      |
| Up      | Neutral   | 105 | Buy50     |

## Sample weeks (first 6 in-window with both signals available)

```
  2020-03-08  close=   8033.31  sma20=   8442.08  funding_ann=+22.29%  trend=Down  funding=Neutral  natural=Hold
  2020-03-15  close=   5361.30  sma20=   8233.65  funding_ann=-15.20%  trend=Down  funding=Cold     natural=Buy50
  2020-03-22  close=   5816.19  sma20=   8064.72  funding_ann=-23.88%  trend=Down  funding=Cold     natural=Buy50
  2020-03-29  close=   5881.42  sma20=   7906.82  funding_ann= -1.48%  trend=Down  funding=Cold     natural=Buy50
  2020-04-05  close=   6772.78  sma20=   7820.34  funding_ann=-14.95%  trend=Down  funding=Cold     natural=Buy50
  2020-04-12  close=   6903.79  sma20=   7820.37  funding_ann= +2.16%  trend=Down  funding=Neutral  natural=Hold
```

## Artifacts

- Equity curves: `equity_curves.png`
- Per-decision log: `action_log.csv`
- Postmortem: `postmortem_report.md`
