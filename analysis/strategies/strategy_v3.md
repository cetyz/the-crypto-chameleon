# BTC Weekly Strategy — v3 "Allocation Rebalancer"

## Why this is a separate strategy, not a v2 variant

v2 only ever buys. v3 is the version that legitimately *sells* — but as **rebalancing**, not as a directional bet. This is the closed-loop idea: trim BTC when it grows past a target weight, bank the proceeds as cash, and redeploy that cash when BTC falls back below target. The money never leaves the system; it sloshes between BTC and a cash buffer that funds the over-buys.

This is a genuinely different architecture from v2 (which has no target weight and never sells), so it gets its own spec rather than living as a knob-flip.

## The key move: "high" is allocation-relative, never price-relative

v1 sold on a *price/positioning* signal (Down+Hot → "both bearish, get out"). That fired during trends and got punished — the Up+Hot cell that "looked high" returned +22% over the next 12 weeks. **Price-relative "high" is unforecastable in a drift-up asset**, because most "high" is just "higher-soon."

v3 sidesteps the forecasting problem entirely. It never asks "is the price high?" It only asks:

> **"Is BTC now a larger share of my portfolio than my target?"**

That question is answerable without any prediction. If you target 75% BTC and a rally pushes you to 85%, you trim back to 75% — not because you forecast a top, but because your allocation drifted. You harvest froth as a *side effect of position size*, not as a directional call. This is the documented "rebalancing bonus": mechanically selling strength and buying weakness.

## Mechanics

State: `target_w` (target BTC weight), `band` (tolerance), weekly deposit.

```
each week:
    deposit cash into cash bucket
    w = btc_value / (btc_value + cash_value)        # current BTC weight

    if w > target_w + band:                          # overweight → harvest
        sell BTC down to target_w                    # proceeds → cash bucket
    elif w < target_w - band:                        # underweight → redeploy
        buy BTC up to target_w using cash bucket
    else:
        deploy this week's deposit toward target_w   # normal drift-correction

    # all trades pay 0.1% fee
```

Weekly deposits naturally flow toward whichever side is underweight, so in normal conditions you're mostly just buying with deposits (like DCA) and only actively trim/redeploy at the band edges.

## What this buys and what it costs — be clear-eyed

A rebalancer in a single-asset-plus-cash setup is a **volatility-harvesting and risk-control tool, not a return maximizer.**

- **In a relentless bull run: it underperforms buy-and-hold and v2.** You trim into strength and hold cash that lags. This is expected and not a bug — you greenlit being less effective in the experimental arm.
- **In choppy / sideways / mean-reverting regimes: it earns its keep** by harvesting the swings and entering dips with dry powder.
- **Across the whole window: lower drawdown, smoother equity, a permanent cash reserve** — paid for with forfeited upside.

So the honest pitch for v3 is *not* "beats DCA." It's "trades expected return for lower variance and a dip-buying reserve." Whether that's worth it is a preference question, and you've already said you're fine with the tradeoff for the experiment.

## Benchmarks

Same three as v2 (B0 deploy-on-arrival, B1 flat DCA, B2 v1), plus:

- **B3 — buy-and-hold of v3's deposits** — the apples-to-apples "what if I never rebalanced" arm. v3's job is to *lose less* than this in drawdowns and ideally come out ahead in choppy stretches, not to beat it on raw bull-run return.

The interesting metric for v3 isn't final value — it's the **shape**: max drawdown and Sortino relative to B3, and behavior segmented by regime (the postmortem already showed Down vs Up regime splits — reuse that breakdown).

## Experiment matrix

| Variant | Change | Tests |
|---|---|---|
| **v3-base** | target 75%, band 10% | does rebalancing deliver lower drawdown / better Sortino? |
| **v3-target-sweep** | target_w ∈ {60%, 70%, 80%} | how much permanent cash is worth holding |
| **v3-band-sweep** | band ∈ {5%, 10%, 15%} | wider band = fewer trades, less harvest; find the fee/harvest balance |
| **v3-no-deposit-steer** | deposits go 100% to BTC always; rebalance only via explicit trim/redeploy | isolates the rebalancing effect from the DCA effect |

## Metrics

All of v2's, plus: **rebalance trade count** (fee drag scales with this), **realized harvest** (cash banked from trims), **regime-split performance** (Up vs Down vs sideways), and drawdown vs B3 as the headline.

## Implementation notes

Same discipline as v2: identical capital/timing across arms, no look-ahead, 0.1% fee per trade, warmup mirrors B0. One extra: **count rebalance trades carefully** — a tight band in a volatile asset can fire often, and 0.1% per round-trip adds up. Watch the fee total against the harvest.

## Honest caveat specific to v3

The rebalancing bonus is real but modest and regime-dependent, and on one BTC cycle (mostly up) the most likely backtest outcome is **v3 underperforms B3 on raw return while showing a shallower max drawdown.** That is the "working as intended" result, not a failure — but don't expect the dashboard to show v3 winning on the value chart. Its win, if any, is on the risk axis.