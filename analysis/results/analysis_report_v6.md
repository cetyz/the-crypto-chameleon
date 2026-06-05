# Backtest report — strategy_v6 (Band Rebalance)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v6.md`
- target_w: 0.92  ·  band: +0.05  (trim threshold w > 0.97)
- drip_weeks: 4  ·  **no Fear & Greed gate** — trim on weight alone.
- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month.
- Fee per trade: 0.10%.  No cash yield.

v6 is a **continuous rebalancer to a target weight**, not an event-driven
harvester. With deposits deploying weekly and BTC mostly rising, the band
trigger fires nearly every Tuesday. v6 deliberately accepts giving up return
in exchange for a shallower drawdown and a better risk-adjusted profile — it
is a frontier choice, **not** an attempt to match B0's return.

## Headline results (standard scoreboard)

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v6 Band Rebalance | 3700.0 | 8044.1 | 117.41 | -57.91 | 1.544 | 3.354 | 322.0 | 322.0 | 98.67 |

## v6 rebalance scorecard

There is **no trim-count target** — v6 trims continuously by construction,
so counting trims is meaningless. Fee drag is the relevant frequency check.

- Distinct trim events:    **318**  (continuous by design — informational)
- Realized harvest:        $93,345.71
- Cumulative fees paid:    $189.06  (larger than v5's $8.17 — already baked into the headline)

## Benchmarks

- **B0 — Deploy-on-arrival** (control). The headline comparison.

## Honest caveats (echoed from strategy_v6.md)

- **Single mostly-up BTC cycle.** v6's drawdown advantage is earned almost
  entirely in the 2022 decline and the chop; its return cost is paid in the
  up-legs. ~120 weekly observations is one cycle — point estimates are wide.
- **The return give-up is real and front-loaded.** v6 lags B0 during bull
  runs, persistently and visibly, because every rebalance sells into a rising
  market — psychologically the hardest time to hold it.
- **The drip may be working against the goal.** Under near-weekly trimming the
  4-week drip re-inflates weight back toward 1.0, partially undoing the cushion.
  drip=4 was inherited for reproducibility, not chosen — the postmortem's
  drip=hold variant tests whether removing the churn deepens the cushion.
- **Cash yield = 0 specifically penalizes v6.** It holds more cash-in-transit;
  real cash earns ~4–5%, so real-world v6 is somewhat better than this backtest.
- **Tax is not modeled, and v6 is the strategy most exposed to it.** ~300+ trims
  means ~300+ realized-gain events; in a taxable account this drag could erase
  much of the edge. The single biggest check before treating v6 as live-viable.
- **v6 only helps if you hold it through both directions** — through the
  drawdown *and* through the bull-market lag. That is a behavioral assumption
  the backtest cannot test.

## Artifacts

- Equity curves: `output/equity_curves_v6.png`
- Per-decision log: `output/action_log_v6.csv`
- Postmortem: `results/postmortem_report_v6.md`
