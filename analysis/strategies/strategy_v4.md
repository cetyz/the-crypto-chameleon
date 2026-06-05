# BTC Weekly Strategy — v4 "Active Sleeve"

## What v4 is for (read this first — the goal is not what it was)

v4 is **not** a return-optimization strategy and is not trying to beat B0 on the return/drawdown ratio. Its explicit design goal is to be a **visibly different, watchable arm on a dashboard** that runs alongside the B0 control (monthly $50 dumped straight in). v2 and v3 both failed at *being interesting*: v2 converged to B0 (avg reserve 0.4%), and v3 traded only twice in six years — so for ~99% of weeks both looked identical to the control.

The honest trade v4 makes:

> **v4 spends some expected return to buy continuous, signal-driven weekly activity.** It is a toy built for divergence-on-a-chart, not an edge. Any drawdown benefit it retains is a bonus, not the objective.

This is greenlit on purpose. The job below is to make the arm *move every Tuesday* while doing the least avoidable damage to return — which means routing the extra activity through the **buy side** (deploying into the asset you want anyway), not the sell side (trims, which realize sales of an appreciating asset and are the expensive way to look busy).

## The cadence constraint that shapes the whole design

- **Deposits are monthly:** $50 lands on the **last Friday** of each calendar month.
- **Decisions are weekly:** every **Tuesday**.
- So **~3 Tuesdays out of 4 have no new capital.** B0 dumps its one $50 the Tuesday after the deposit and then sits idle until the next month.

This is the key fact. If v4 tried to create activity by varying *deposit deployment* (the v2-style tilt), it would only ever act once a month — same cadence as B0, same boring chart. **To act every week, v4 must hold a standing cash sleeve and spend it weekly.** The sleeve is the engine of visible activity; deposits merely refill it.

## Architecture: a fed-monthly, spent-weekly cash sleeve

Three moving parts:

1. **A standing dry-powder sleeve.** A target slice of the portfolio (e.g. 12%) held as cash, on purpose, as ammunition. Unlike v3's cash — which only existed as a side effect of rare trims — this sleeve is deliberate and always present, so there is always something to deploy on a dip.
2. **Dip-weighted weekly buys (the activity engine).** Every Tuesday, v4 checks BTC against its recent high. The deeper the dip, the bigger the slice of sleeve it deploys. This fires on down weeks — exactly when B0 is doing nothing — so the two arms diverge most when the chart is most interesting, and it *adds* return by buying weakness.
3. **Lazy trims (rare, wide band).** v4 trims only when BTC gets *far* overweight, so it almost never sells into a bull. Trims refill the sleeve. They're deliberately infrequent — the sell side is the costly side, so we let the buy side do the visible work.

## Mechanics

State: `target_w` (target BTC weight), `sleeve_target` (target cash fraction), `upper_band` (wide), `lower_band` (tight), `dip_ref_weeks` (lookback for the high), `dip_buy_curve` (how dip depth maps to deploy size).

```
# ---- MONTHLY (last Friday): refill the sleeve ----
on deposit:
    cash += 50                      # the whole deposit lands in the cash sleeve first

# ---- WEEKLY (every Tuesday): the action engine ----
each Tuesday:
    w        = btc_value / (btc_value + cash_value)
    high     = trailing dip_ref_weeks-week max of BTC close
    dip_pct  = (high - price) / high          # 0 if at/above high

    # 1. LAZY TRIM — only when far overweight (rarely fires in a bull)
    if w > target_w + upper_band:
        sell BTC down to target_w             # proceeds -> cash sleeve

    # 2. DIP BUY — the weekly activity engine, scales with dip depth
    elif dip_pct >= dip_min:
        size = dip_buy_curve(dip_pct)         # e.g. bigger dip -> bigger slice
        deploy = size * cash                  # spend a slice of the sleeve
        buy(deploy); cash -= deploy

    # 3. DRIFT REDEPLOY — if underweight and no dip, top up gently toward target
    elif w < target_w - lower_band:
        buy enough to move partway to target_w from cash

    # 4. otherwise: hold (in-band, no dip) — but keep the sleeve, don't force-deploy

    # all trades pay 0.10% fee
```

Notes on the shape:

- **`target_w` is set high (e.g. 0.85)** so trims are rare — we are not trying to harvest froth, we're trying to keep return close to B0.
- **`sleeve_target` (e.g. 0.12)** is the permanent ammunition. It's the main return cost: ~12% of capital sits in cash on average. That's the price of having something to do every week. Lower it for less drag / less activity; raise it for more.
- **`dip_buy_curve`** is what makes most Tuesdays *do something*: even shallow dips (a few %) trigger a small buy, so the arm twitches weekly rather than sitting flat. Tune `dip_min` low for more activity.
- The sleeve naturally **refills monthly** from deposits and **occasionally from trims**, and **drains on dips** — so on the dashboard you'll see cash breathing up and down every week, visibly out of step with B0's flat line.

## Why this fits the goal better than "more trims"

Forcing trims (tightening the upper band) produces *lumpy, clustered* sells during rallies and dead air otherwise — and every trim costs return by selling the appreciating asset. Dip-weighted buys instead produce activity on the **down** weeks, every week there's a wobble, while deploying into the asset you want to hold anyway. More action, cheaper, and pointed at the moments where divergence from B0 reads most clearly on a chart.

## Benchmarks

- **B0 — Deploy-on-arrival** (the control; monthly $50 dumped the next Tuesday). The *only* comparison that matters now. B3 is identical to B0 by construction and is dropped.
- Report v4 against B0 on **both** value and drawdown, but interpret with the goal in mind: v4 is *expected* to trail B0 on return (it holds a permanent ~12% sleeve). The point is the **divergence and activity**, with drawdown-reduction as a possible bonus.

## What "success" means for v4 (redefined for this purpose)

This arm has a different scorecard than v2/v3. Track:

| Metric | Why it matters here |
|---|---|
| **Active weeks %** (weeks with a non-`none` action) | the headline. The whole point is "stuff happens." Aim high — most weeks should act. |
| **n_trades / n_decisions** | the activity contrast vs B0's ~12 buys/year |
| **Divergence from B0** (mean abs weekly gap in value or BTC weight) | how visibly different the two lines are |
| Return vs B0 | the cost of the fun — expected to be negative, just bound how negative |
| Max drawdown & Sortino vs B0 | the bonus axis — if dip-buying happens to cut drawdown, great |
| Avg sleeve fraction | the drag you're paying for activity |

A "good" v4 here = **acts most weeks, visibly diverges from B0, and gives up only a modest slice of return** (not the 31pp v3-base bled). Beating B0 on drawdown is upside, not the bar.

## Experiment matrix

| Variant | Change | Tests |
|---|---|---|
| **v4-base** | target 0.85, sleeve 0.12, upper_band +0.15, dip_min 3%, linear dip curve | does it act most weeks while keeping return close to B0? |
| **v4-sleeve-sweep** | sleeve_target ∈ {0.06, 0.12, 0.20} | activity & drawdown vs return drag — how much ammunition is worth holding |
| **v4-dipmin-sweep** | dip_min ∈ {1%, 3%, 6%} | lower = more weekly twitches but smaller/noisier buys; find the activity/cost balance |
| **v4-curve-sweep** | dip curve ∈ {linear, convex} | convex = save powder for deep dips (fewer but bigger buys); linear = act often |
| **v4-eager-redeploy** | tighten lower_band so drift-redeploys fire more | adds activity on the buy side without touching trims |
| **v4-lazy-vs-active-trim** | upper_band ∈ {+0.10, +0.15, +0.20} | confirm wide band keeps trims rare and return high |

## Metrics

All of v3's, plus the activity-focused set above. Segment by regime (Up / Down / Sideways) as before — expect v4's *added* return, if any, to show up in Down/Sideways weeks (dip-buying) and its drag to show up in Up weeks (sleeve sitting idle).

## Implementation notes

- Same discipline as v2/v3: identical capital and timing across arms, no look-ahead (signal on Tuesday close, execute same close), 0.10% fee per trade, warmup mirrors B0.
- **The sleeve must be modeled explicitly as cash** that earns nothing (no cash yield assumed) — that's the honest drag.
- **Count trades carefully.** Dip-weighted weekly buys can fire often; at 0.10% each the fee total is small but non-zero — watch it against any harvest, as in v3.
- The trailing-high lookback (`dip_ref_weeks`) needs its own warmup; before it's ready, deploy deposits like B0.

## Honest caveats specific to v4

- **This is a toy tuned to one mostly-up BTC cycle.** Every knob (sleeve size, dip curve, bands) is fit to this window and *will* look better in backtest than live. For a dashboard that's fine — just don't read the curve as evidence of edge.
- **The activity is the product, not the returns.** If v4 ends up beating B0 on drawdown, treat it as a happy accident of dip-buying in this sample, not a robust property.
- **Dip-buying in a single bull cycle flatters itself:** "buy the dip" always looks good when every dip recovered. In a regime where a dip *keeps* dipping, the sleeve empties early and the strategy is just long with extra steps. The backtest cannot show you that failure mode because this window doesn't contain it.
- **Permanent sleeve = permanent drag.** The ~12% cash is a standing tax on return in exchange for weekly liveliness. That's the deal you're knowingly taking.