# Backtest report — strategy_v8 (Funded Basket)

_Window: 2020-03-01 → 2026-04-30 (74 monthly deposits)_

## Spec

- Source: `analysis/strategies/strategy_v8.md`
- target_w: 0.9  ·  band: ±0.03  (two-sided no-trade zone, weight in [0.87, 0.93])
- **Two-way** rebalance: SELL above target+band, BUY below target-band, HOLD inside. On a breach, correct **all the way to target**.
- **No drip, no FNG, no B0 spine.** The cash side is a funded, standing, deliberate allocation — not a trim by-product.
- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month — lands as cash, the next rebalance redistributes it.
- Fee per trade: 0.10%.  Cash yield: 0 (penalizes v8 hardest — the cash sleeve is now permanent).

v8 is a **funded BTC/cash basket held at a constant target weight by a
two-way weekly rebalance.** It makes no market prediction: buying a dip is
the mechanical consequence of holding a constant weight, not a forecast that
the dip recovers. It is a frontier choice judged on risk-adjusted edge, with
two added burdens over v6 — a *permanent* funded cash drag, and the need to
show the dip-buying earns its keep.

## Headline results (standard scoreboard)

| arm | deposited | final_value | total_return_% | max_drawdown_% | sharpe | sortino | n_trades | n_decisions | time_in_market_% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 deploy-on-arrival | 3700.0 | 9363.17 | 153.06 | -68.36 | 1.494 | 2.975 | nan | nan | nan |
| v8 Funded Basket | 3700.0 | 8674.22 | 134.44 | -61.89 | 1.524 | 3.186 | 32.0 | 322.0 | 98.67 |

## v8 rebalance scorecard

The ±3% base band suppresses most small weekly rebalances, so v8's trade
count should sit well below v6's continuous trimming. The buy count is the
half v6 never had — cash deployed into declines.

- Total trades:        **32**  (1 sells, 31 buys)
- Gross sold (over-weight trims):  $109.56
- Gross bought (dip-buys):         $2,812.79
- Cumulative fees paid:            $2.92

## Benchmarks

- **B0 — Deploy-on-arrival** (control). The headline comparison.
- v6 (Band Rebalance) is the decisive cross-version comparison — see the postmortem.

## Honest caveats (echoed from strategy_v8.md)

- **Permanent funded cash drag is the central cost, and `cash_yield = 0`
  makes it worst here.** v8 holds ~10% (more at lower `target_w`) in cash
  continuously, earning nothing in this model. Real-world v8 — cash in
  T-bills/stables at ~4–5% — is materially better than this backtest. Read
  every v8 return number with that asterisk.
- **Dip-buying's effect on drawdown is genuinely ambiguous.** The standing
  cash buffer softens the *start* of a decline, but rebalancing *into* the
  decline raises BTC exposure as price falls — at the trough v8 can hold more
  BTC than it started with. Net max-DD vs B0 is an empirical question.
- **The rebalancing bonus is regime-dependent.** Buy-low/sell-high adds
  return mainly in choppy / mean-reverting markets. Over this single mostly-up
  cycle, expect v8 to trail B0 on raw return.
- **The band pools deposits as idle cash.** A $50 deposit can't breach ±3%
  alone, so it sits until some larger move trips the band — a minor extra drag.
- **Behaviorally, v8 demands discipline on three sides** — hold through bull
  lag, keep buying into a 50–70% crash, and tolerate idle cash in between. The
  backtest cannot test that.
- **Single mostly-up, in-sample cycle (~120 weekly obs).** The dip-buying half
  is exercised in essentially two declines (2020, 2022) — few events.

## Artifacts

- Equity curves: `output/equity_curves_v8.png`
- Per-decision log: `output/action_log_v8.csv`
- Postmortem: `results/postmortem_report_v8.md`
