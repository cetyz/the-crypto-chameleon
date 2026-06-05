# Backtest report — strategy_v7 (Fear-Gated Warchest)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v7.md`
- target_w: 0.92  ·  band: +0.05  (trim threshold w > 0.97)  — **unchanged from v6**
- fng_buy_threshold: 25  (deploy warchest only on FNG ≤ 25)  ·  drip_weeks: 4
- Warchest accounting: **excluded** from the weight denominator (base).
- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month.
- Fee per trade: 0.10%.  No cash yield (penalizes the idle warchest — see caveats).

v7 keeps v6's band-gated trim **exactly**, but reroutes the proceeds: instead
of v6's unconditional 4-week drip back into BTC, the cash accumulates in a
segregated warchest that only deploys when the Fear & Greed Index reads extreme
fear (≤ 25). It is a directional bet — *fear is a better-than-random time to
buy* — and it should be judged on whether that bet beats (a) a no-signal slow
drip and (b) just dripping straight back in (v6). See `postmortem_report_v7.md`.

## Headline results (standard scoreboard)

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v7 Fear-Gated Warchest | 3700.0 | 4352.02 | 17.62 | -43.01 | 1.569 | 3.818 | 322.0 | 322.0 | 98.67 |

## v7 warchest scorecard

- Distinct trim events:        **318**  (continuous by design — same machine as v6)
- Distinct warchest deploys:   **67**  (only fire inside FNG ≤ 25 windows)
- Realized harvest (to chest): $20,427.62
- Warchest balance at window end: $1,318.70  (idle cash never redeployed)
- Peak warchest balance:       $4,086.49
- Cumulative fees paid:        $43.26

Warchest deployments (date + FNG at firing; `warchest` is the balance
*after* the slice was paid out):

| date | close | fng | warchest | usd_deployed |
| --- | --- | --- | --- | --- |
| 2020-03-31 00:00:00+00:00 | 6410.44 | 12 | 2.99 | 1.0 |
| 2020-04-07 00:00:00+00:00 | 7197.32 | 20 | 6.21 | 1.0 |
| 2020-04-14 00:00:00+00:00 | 6868.7 | 15 | 8.99 | 1.0 |
| 2020-04-21 00:00:00+00:00 | 6841.37 | 17 | 11.53 | 1.0 |
| 2021-05-18 00:00:00+00:00 | 42849.78 | 21 | 691.04 | 230.35 |
| 2021-05-25 00:00:00+00:00 | 38324.72 | 22 | 488.67 | 230.35 |
| 2021-06-01 00:00:00+00:00 | 36693.09 | 20 | 304.57 | 230.35 |
| 2021-06-08 00:00:00+00:00 | 33380.81 | 13 | 129.66 | 230.35 |
| 2021-06-22 00:00:00+00:00 | 32509.56 | 10 | 206.47 | 68.82 |
| 2021-06-29 00:00:00+00:00 | 35911.73 | 25 | 210.89 | 68.82 |
| 2021-07-06 00:00:00+00:00 | 34220.01 | 20 | 211.52 | 68.82 |
| 2021-07-13 00:00:00+00:00 | 32729.77 | 20 | 209.07 | 68.82 |
| 2021-07-20 00:00:00+00:00 | 29790.35 | 19 | 202.23 | 67.41 |
| 2021-09-28 00:00:00+00:00 | 41026.54 | 25 | 663.83 | 221.28 |
| 2021-12-07 00:00:00+00:00 | 50588.95 | 25 | 989.73 | 329.91 |
| 2021-12-14 00:00:00+00:00 | 48343.28 | 21 | 721.55 | 329.91 |
| 2022-01-04 00:00:00+00:00 | 45832.01 | 23 | 713.66 | 237.89 |
| 2022-01-11 00:00:00+00:00 | 42729.29 | 21 | 554.13 | 237.89 |
| 2022-01-18 00:00:00+00:00 | 42352.12 | 24 | 406.51 | 237.89 |
| 2022-01-25 00:00:00+00:00 | 36958.32 | 12 | 257.67 | 237.89 |
| 2022-02-22 00:00:00+00:00 | 38230.33 | 20 | 505.0 | 168.33 |
| 2022-03-08 00:00:00+00:00 | 38730.63 | 21 | 527.14 | 175.71 |
| 2022-03-15 00:00:00+00:00 | 39280.33 | 21 | 447.82 | 175.71 |
| 2022-04-12 00:00:00+00:00 | 40074.94 | 20 | 649.03 | 216.34 |
| 2022-05-10 00:00:00+00:00 | 31017.1 | 10 | 727.79 | 242.6 |
| 2022-05-17 00:00:00+00:00 | 30444.93 | 8 | 558.62 | 242.6 |
| 2022-05-24 00:00:00+00:00 | 29654.58 | 12 | 400.69 | 242.6 |
| 2022-05-31 00:00:00+00:00 | 31801.04 | 16 | 266.38 | 242.6 |
| 2022-06-07 00:00:00+00:00 | 31125.33 | 15 | 287.14 | 95.71 |
| 2022-06-14 00:00:00+00:00 | 22136.41 | 8 | 273.07 | 95.71 |
| 2022-06-21 00:00:00+00:00 | 20723.52 | 9 | 254.82 | 95.71 |
| 2022-06-28 00:00:00+00:00 | 20281.29 | 10 | 240.33 | 95.71 |
| 2022-07-05 00:00:00+00:00 | 20175.83 | 19 | 241.7 | 80.57 |
| 2022-07-12 00:00:00+00:00 | 19328.75 | 16 | 239.52 | 80.57 |
| 2022-09-06 00:00:00+00:00 | 18790.61 | 22 | 608.3 | 202.77 |
| 2022-09-20 00:00:00+00:00 | 18875.0 | 23 | 546.96 | 182.32 |
| 2022-09-27 00:00:00+00:00 | 19079.13 | 20 | 431.4 | 182.32 |
| 2022-10-04 00:00:00+00:00 | 20337.82 | 20 | 334.06 | 182.32 |
| 2022-10-11 00:00:00+00:00 | 19060.0 | 24 | 238.65 | 182.32 |
| 2022-10-18 00:00:00+00:00 | 19327.44 | 22 | 250.87 | 83.62 |
| 2022-10-25 00:00:00+00:00 | 20080.07 | 20 | 265.79 | 83.62 |
| 2022-11-15 00:00:00+00:00 | 16900.57 | 22 | 395.43 | 131.81 |
| 2022-11-22 00:00:00+00:00 | 16226.94 | 22 | 337.43 | 131.81 |
| 2022-12-06 00:00:00+00:00 | 17088.96 | 25 | 375.54 | 125.18 |
| 2024-08-06 00:00:00+00:00 | 56022.01 | 17 | 2097.59 | 699.2 |
| 2025-02-25 00:00:00+00:00 | 88680.4 | 25 | 2473.49 | 824.5 |
| 2025-03-04 00:00:00+00:00 | 87281.98 | 15 | 1735.24 | 824.5 |
| 2025-03-11 00:00:00+00:00 | 82932.99 | 24 | 1048.69 | 824.5 |
| 2025-04-08 00:00:00+00:00 | 76322.42 | 24 | 1305.51 | 435.17 |
| 2025-11-04 00:00:00+00:00 | 101497.22 | 21 | 3087.8 | 1029.27 |
| 2025-11-18 00:00:00+00:00 | 92960.83 | 11 | 2469.56 | 823.19 |
| 2025-11-25 00:00:00+00:00 | 87369.96 | 20 | 1788.51 | 823.19 |
| 2025-12-02 00:00:00+00:00 | 91277.88 | 23 | 1174.59 | 823.19 |
| 2025-12-09 00:00:00+00:00 | 92678.8 | 22 | 613.62 | 823.19 |
| 2025-12-16 00:00:00+00:00 | 87863.42 | 11 | 678.48 | 226.16 |
| 2025-12-23 00:00:00+00:00 | 87486.0 | 24 | 736.88 | 226.16 |
| 2025-12-30 00:00:00+00:00 | 88485.49 | 23 | 797.76 | 226.16 |
| 2026-02-03 00:00:00+00:00 | 75770.21 | 17 | 1510.4 | 503.47 |
| 2026-02-10 00:00:00+00:00 | 68841.29 | 9 | 1191.46 | 503.47 |
| 2026-02-17 00:00:00+00:00 | 67503.52 | 10 | 893.87 | 503.47 |
| 2026-02-24 00:00:00+00:00 | 64058.15 | 8 | 608.29 | 503.47 |
| 2026-03-03 00:00:00+00:00 | 68338.0 | 14 | 651.76 | 217.25 |
| 2026-03-10 00:00:00+00:00 | 69948.63 | 13 | 697.78 | 217.25 |
| 2026-03-24 00:00:00+00:00 | 70556.74 | 11 | 909.68 | 303.23 |
| 2026-03-31 00:00:00+00:00 | 68284.48 | 11 | 848.34 | 303.23 |
| 2026-04-07 00:00:00+00:00 | 71924.22 | 11 | 805.01 | 303.23 |
| 2026-04-14 00:00:00+00:00 | 74131.55 | 21 | 773.18 | 303.23 |

## Benchmarks

- **B0 — Deploy-on-arrival** (control). The headline comparison.
- The decisive comparisons (vs v6, and vs a no-signal slow drip) live in the
  postmortem — v7's whole justification is whether the fear-gate earns its keep.

## Honest caveats (echoed from strategy_v7.md)

- **Almost nothing to calibrate the buy-gate against.** The trim harvests across
  the whole cycle, but the *buy* half only acts in extreme-fear windows — over
  2020→2026 there are essentially two (2020 COVID, 2022 bear). The threshold is
  fit to ~2 events; treat any in-sample-optimal value with heavy suspicion.
- **v7 reintroduces a directional call after v6 worked to remove one.** The prior
  from v5 is unfavourable: the sentiment gate did not earn its keep on the sell
  side. v7 must overcome that with evidence, not assume the buy side is different.
- **FNG ≤ 25 is largely a proxy for 'price already fell a lot.'** The buy-gate may
  be little more than a drawdown-from-high trigger with an extra data dependency.
- **Idle-cash drag is worse than v6's, and cash yield = 0 punishes it harder.** The
  warchest can sit for months between fear episodes; at 0% that is pure opportunity
  cost. Real-world v7 (warchest in T-bills/stables at ~4–5%) is meaningfully better
  than this backtest shows.
- **Excluding the warchest from the denominator is not free.** target_w = 0.92 is a
  target on *invested* capital; a growing chest does NOT damp future trims, so
  trims and warchest growth mildly reinforce each other. The included-denominator
  variant in the postmortem shows how much this choice distorts the metrics.
- **The conservative re-arm rule won't catch sharp V-bottoms.** Cancelling a run
  the moment FNG recovers under-deploys into fast recoveries by design.
- **Single mostly-up cycle, in-sample, ~120 weekly observations** — doubly binding
  here because the buy-gate only acts in the rarest part of the sample.

## Artifacts

- Equity curves: `output/equity_curves_v7.png`
- Per-decision log: `output/action_log_v7.csv`
- Postmortem: `results/postmortem_report_v7.md`
