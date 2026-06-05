# BTC Weekly Strategy — v8 "Funded Basket"

## What v8 is for (read this first)

v8 throws out the machine and keeps the question. The whole v3→v7 lineage was
secretly asking "is BTC a larger share of my portfolio than my target?" while
funding the cash side of that comparison by *accident* — the trim manufactured a
transient cash sleeve, the drip drained it back, and the weight was always
measured against a number the trim itself had just conjured. v8 stops smuggling
the cash sleeve and **funds it on purpose**.

v8 is a **funded BTC/cash basket held at a constant target weight by a two-way
weekly rebalance.** Each Tuesday: look at the whole portfolio, and set BTC back to
`target_w`. If BTC has drifted *above* target, sell some. If it has drifted
*below* target — because price fell, or because a fresh deposit just landed as
cash — *buy* some. One rule. No drip. No signal. No B0 spine bolted on the side.

> **v8 in one sentence:** hold a BTC/cash basket at a constant target weight,
> rebalanced two-way — sell BTC when it drifts above target, buy when it drifts
> below, but only once it has drifted past a no-trade band — with the cash side a
> deliberate funded allocation rather than a by-product of trimming.

The win condition is unchanged: **risk-adjusted edge** — shallower drawdown,
better Sortino/Sharpe, return in a defensible relationship to B0. What changes is
that the cash position is now real, permanent, and chosen — and that brings one
genuinely new capability and one genuinely new cost, both of which the lineage
never had to confront:

- **New capability: v8 buys dips.** v6 only ever *sold* (and redripped its own
  proceeds). It never deployed cash into a falling market. v8 does — when BTC
  drops, weight falls below target, and the rule buys. This is the missing half
  of "rebalance," and it is the entire reason the basket framing is different
  from v6 rather than a cosmetic relabel.
- **New cost: a permanent funded cash drag.** v6's cash sleeve was transient — it
  existed only in the gap between a trim and the drip that erased it. v8's cash
  sleeve is standing, deliberate, and (at `cash_yield = 0`) a continuous tax on
  return through a mostly-rising market. This is the price of admission and the
  spec does not soften it.

v8 makes **no market prediction.** Buying a dip here is not a forecast that the
dip will recover — it is the mechanical consequence of holding a constant weight.
That keeps v8 squarely in the prediction-free camp v6 occupied, and *out* of the
directional territory v7 wandered into. If anything, v8 is the most honest
expression of the lineage's founding question: it is the only version where the
target you measure against is one you actually funded.

## What changed from v6

|  | v6 (Band Rebalance) | v8 (Funded Basket) |
|---|---|---|
| Mechanism | One-way trim (sell only) + 4-week drip back into BTC | **Two-way** rebalance (buy *and* sell) to target |
| Cash sleeve | Transient — trim-created, drip-drained | **Funded, persistent, deliberate** |
| Buys BTC on a dip? | No — only redeploys its own trim cash via the drip | **Yes** — deploys the cash sleeve as price falls |
| Deposit handling | Separate B0 deploy-on-arrival step | **Subsumed** — a deposit is just cash the next rebalance redistributes |
| Drip | Yes (`drip_weeks`) | **Removed** |
| Band | One-sided (0.05, upper only — the trim trigger) | **Two-sided** no-trade zone; static in base, optionally volatility-scaled |
| Moving parts | Three (spine, trim, drip) | **One** (rebalance) |
| Directional call | None | None |
| Parameter count | One fewer than v5 | **Fewer than v6** (`drip_weeks` gone; net no signal params) |

**Why this change — and why it is consistent with standing discipline:**

- It is the direct answer to the mechanical complaint that surfaced reviewing v6:
  the trim conjures its own cash sleeve and the drip immediately drains it, so the
  weight never settles and the trim fires almost every week. v8 removes the
  feedback loop by giving the cash sleeve an independent, funded existence. The
  weight only moves when *the market* moves it (or a deposit lands), not when the
  strategy's own plumbing moves it.
- **v8 has strictly less surface area than v6**, which lands on the right side of
  the project's "prefer removing rules over adding them" discipline. One rule
  replaces three; the drip and its schedule queue are gone; there is no signal and
  no FNG dependency. This is the rare change that is both more capable (two-way)
  *and* simpler.
- It also retires the warchest/v7 question by absorbing it. v7 tried to give
  trim cash a smarter spend rule via a fear gate; v8 says the cash side should be
  a funded allocation rebalanced mechanically, with no spend *signal* at all. If
  v8 works, the entire warchest line of inquiry is moot — log that explicitly.

## What was kept from v6 / v3

v3's framing is kept and **completed**:

> **"Is BTC now a larger share of my portfolio than my target?"** That question
> is answerable without any prediction.

v6 only ever acted on the "larger" half. v8 acts on both halves — larger *and*
smaller — which is what "rebalance" actually means. It is still a side-effect-of-
position-size strategy, still prediction-free, still judged on risk-adjusted edge.
`target_w` remains the frontier dial. Tuesday remains the decision day, the $50
last-Friday deposit is unchanged, the 0.10%/trade fee is unchanged, `cash_yield`
stays 0 for comparability, and B0 remains the baseline.

## Architecture: one rule

There is one moving part. Each Tuesday, rebalance the entire portfolio — BTC plus
all cash, including any deposit that has just landed — back to `target_w`. Selling
and buying are the same rule pointed in opposite directions. Deposits, price
drift, and dips are all handled by it; none needs special-casing.

## Mechanics

State: `target_w`, `band`, and the two balances `btc` and `cash`. No
`drip_schedule`, no `drip_weeks`, no FNG.

```
# ---- MONTHLY (last Friday): deposit lands ----
on deposit:
    cash += 50           # just becomes cash; the weekly rule redistributes it

# ---- WEEKLY (Tuesday): the only decision day, the only rule ----
each Tuesday:
    total          = btc_value + cash
    target_value   = target_w * total
    drift          = btc_value - target_value          # >0 over target, <0 under

    if drift > band * total:        # BTC too heavy -> SELL down to target
        sell drift of BTC;  cash += drift
    elif drift < -band * total:     # BTC too light -> BUY up to target
        buy -drift of BTC;  cash -= (-drift)
    # else: within the no-trade band -> hold
```

For **v8-base, `band = 0.03`**: a two-sided ±3% no-trade zone. The portfolio is
left alone while weight sits between 0.87 and 0.93, and only when it drifts past
that does the rule fire. When it fires, it rebalances **all the way back to
target** (trigger on the band, correct to the centre — not just to the band edge);
that keeps the logic to one number and makes each trade meaningful enough to be
worth its fee. `band = 0` (snap to exactly target every week) is retained only as
the zero-hysteresis reference point in the sweep.

One consequence to note up front: with a band, a $50 deposit on a multi-thousand-
dollar portfolio is far too small to breach ±3% on its own, so it **pools as cash
until some other move trips the band.** Deposits no longer deploy promptly — a
minor extra cash drag the band buys in exchange for fewer trades (see caveats).

Worked example, `target_w = 0.90`, `band = 0.03`, rebalance-to-target, fees
ignored for legibility:

| Wk | BTC price | Pre-rebalance BTC / cash | Total | Weight | drift vs band | Action | Post BTC / cash |
|---|---|---|---|---|---|---|---|
| 1 | $100 | $10,000 / $0 | $10,000 | 1.000 | $1,000 vs $300 | sell $1,000 | $9,000 / $1,000 |
| 2 | $105 (+5%) | $9,450 / $1,000 | $10,450 | 0.904 | $45 vs $314 | **hold** | $9,450 / $1,000 |
| 3 | $68 (−35%) | $6,120 / $1,000 | $7,120 | 0.860 | −$288 vs $214 | **buy $288** | $6,408 / $712 |
| 4 | $75 +$50 dep | $7,068 / $762 | $7,830 | 0.903 | $21 vs $235 | **hold** | $7,068 / $762 |

Four behaviours in four weeks: **week 1** sells the over-weight BTC down to target;
**week 2** a small +5% move leaves weight at 0.904, inside the band, so the rule
*holds* — the fee saving the band exists for; **week 3** is the half v6 never had —
a 35% crash drops weight to 0.860, past the band, so the rule *buys $288 into the
decline* with the cash sleeve; **week 4** the $50 deposit lands but the portfolio
is near target, so it just sits as cash rather than triggering a buy.

## The band: static (base) and volatility-scaled (variant)

Both band forms are **prediction-free** — a band is a statement about *when a
trade is worth making*, not about where the market is going. That is why they
belong inside v8 rather than forking a new strategy.

**Static band (base).** A fixed ±`band` zone around target. The only knob is
width, and it trades one thing for another: wider = fewer trades, lower fee/tax
drag, looser weight control (you spend more time off-target); narrower = tighter
tracking, more trades. `0.03` is a reasonable middle for a 10% cash buffer — note
that with only ~10% cash, breaching a ±3% *weight* band takes a sizable price
move, so in practice the base rebalances every several weeks, not weekly.

**Volatility-scaled band (variant).** Widen the no-trade zone when BTC is choppy
so noise doesn't churn the book:

```
band(t) = base_band × clamp( σ_t / σ_median , lo , hi )
```

where `σ_t` is **realized volatility** — `stdev(log daily returns, trailing 30d)`
— and `σ_median` is its full-sample median, with the multiplier clamped to e.g.
`[0.5, 3.0]` so the band never collapses to zero or blows up.

On the measure: **use realized vol, not ATR.** ATR needs the daily high/low/close;
if the backtest carries only a *close* series (as the lineage's loaders do),
realized vol falls straight out of data already in hand while ATR would require a
new OHLC feed — added surface area for no clear gain on a weekly single-asset
rebalance. Realized vol is the path of least resistance and least dependency.

**The trade-off that makes this a real question, not a free win:** high-volatility
periods are *exactly* when the rebalancing harvest (buy-low/sell-high) is largest.
Widening the band in high vol to save fees therefore **trades away harvest to
avoid churn** — the two effects point in opposite directions and which wins is
empirical, not obvious. The variant must be judged against the static band as a
nested baseline (below); if vol-scaling can't beat a well-chosen fixed width, it's
extra knobs (`base_band`, window, clamp bounds, `σ_median`) earning nothing — and
on ~120 observations, extra knobs are exactly what overfits.

| Param | Value | Rationale |
|---|---|---|
| `target_w` | 0.90 | The funded BTC share. Lower than v6's 0.92 because the cash side is now a deliberate, standing 10% buffer rather than a transient artifact. It is the frontier dial and is swept, not fit. |
| `band` | 0.03 | A ±3% two-sided no-trade zone, rebalance-to-target on breach. Primarily fee/tax control. Swept `{0, 0.02, 0.03, 0.05}`; the volatility-scaled form is a variant. |
| Deposit | $50, last Friday of month | Unchanged. No longer deploy-on-arrival — it lands as cash and the next rebalance handles it. |
| Decision day | Tuesday | Unchanged. |
| Fee | 0.10% per trade | Unchanged. The ±3% base band suppresses most small weekly rebalances, so trade count is well below v6's; report it explicitly. |
| Cash yield | 0 | Unchanged, and **this penalizes v8 harder than any prior version** — the cash position is now permanent and larger, not transient. See caveats. |

`drip_weeks` and `fng_buy_threshold` are gone. v8 introduces no new parameters and
removes two relative to the v7 line.

## New infrastructure required

**None — and some removed.** No drip queue, no FNG load. Everything v8 needs
(`last_friday_deposit_dates`, `next_tuesday`, `summarize_arm`, `max_drawdown`,
`sharpe_sortino`, `boot_ci`) is already shared. `analysis_v8.py` defines its own
`simulate_v8` per the "no changes to prior scripts" discipline; it is shorter than
`simulate_v6` because it has fewer parts.

## Experiment matrix (for `postmortem_v8.py`)

| Variant | Change | What it tests |
|---|---|---|
| **v8-base** | target 0.90, band 0, two-way snap | Headline. The funded two-way basket. |
| **v8-target-sweep** | `target_w ∈ {0.80, 0.85, 0.90, 0.95}` | **The main exploration.** Traces the return/drawdown frontier. 0.95 ≈ near-B0 (thin cash); lower = bigger buffer, more drag, more dip-buying ammunition. A preference menu, not a fit. |
| **v8-band-sweep** | `band ∈ {0, 0.02, 0.03, 0.05}` | Trade frequency vs tracking. `0` = zero-hysteresis snap (reference); wider = fewer, larger rebalances, less fee/tax drag, looser weight control, slower deposit deployment. |
| **v8-vol-band (variant)** | `band(t) = base_band × clamp(σ_t/σ_median, 0.5, 3.0)`, realized 30d vol | Whether scaling the band by volatility beats a fixed width. **Judged against the best static band as a nested baseline** — must beat it, or the extra knobs are noise. Remember it trades away harvest in high vol to save fees. |
| **v8-one-way (ablation)** | Sell when over target, but **never buy** when under (cash just accrues) | **Isolates the dip-buying.** This is roughly "v6 with a funded sleeve and no drip." If two-way doesn't beat one-way on risk-adjusted terms, the buy half isn't earning its keep and the funded cash is pure drag. |
| **v8-cadence (variant)** | Rebalance monthly instead of weekly | Whether weekly tracking is worth its trade count, or a slower rebalance captures most of the benefit far cheaper. (Note: with a band, weekly cadence already fires rarely — this variant and the band interact.) |
| **v8 vs v6 vs B0 (cross-version)** | — | The decisive comparison. Does the funded two-way basket beat the transient one-way trimmer (v6) and buy-hold (B0) on risk-adjusted edge? |

The load-bearing rows are **v8-one-way** (does buying dips help?) and the
**cross-version** row (does the permanent cash drag pay for itself vs v6?).

## What "success" means for v8

v8 is a frontier choice, judged on risk-adjusted edge, **with two added burdens**:
it must justify a *permanent* cash drag, and it must show the dip-buying earns its
keep. A "good" v8 over the 2020-03 → 2026-04 window means:

1. **Sortino ≥ B0 + 0.3 and Sharpe ≥ B0.** Inherited bars. The core test.
2. **Max drawdown not worse than B0** — and ideally meaningfully shallower. Note
   this is *not* assumed (see caveats): the standing cash buffer cushions the
   initial drop, but dip-buying *raises* exposure into the decline, so the net
   effect on max-DD is an empirical question this row answers, not a given.
3. **Beats v6-base on {risk-adjusted OR drawdown} without losing the other.** If
   the funded basket can't beat the transient trimmer, the permanent cash drag
   wasn't worth paying and v6 is the better object. This is the row that justifies
   v8's existence over its predecessor.
4. **Two-way beats v8-one-way.** Confirms the dip-buying — not just the funded
   buffer — is doing real work. If one-way wins, drop the buy side.
5. **The return give-up is risk-justified**, as in v6 — the accepted cost, not a
   failure, unless 1–4 are missed.
6. **`target_w` sweep is monotone-ish and legible.** A clean return-for-drawdown
   trade across the sweep is expected; an interior point that dominates both
   endpoints is an in-sample artifact to distrust.
7. **If kept, `v8-vol-band` must beat the best static band** on risk-adjusted
   terms — not just match it. A volatility-scaled band that ties a fixed one has
   added four knobs for nothing and should be dropped; the same nested-baseline
   logic that governs every variant in this project.

If 1, 3, and 4 hold, v8 is both simpler and better than v6 and becomes the
lineage's main line. If 3 fails, v8's cleanliness is not worth its drag and v6
stands. If 4 fails, the basket should be one-way and you've essentially rederived
v6-without-drip.

## Honest caveats specific to v8

- **Permanent funded cash drag is the central cost, and `cash_yield = 0` makes it
  worst here.** v8 holds ~10% (more at lower `target_w`) in cash *continuously*,
  through every up-leg, earning nothing in this model. v6's drag was transient;
  v8's is structural. **Real-world v8 — cash in T-bills/stables at ~4–5% — is
  materially better than this backtest, more so than for any prior version.**
  Modelling yield is the single highest-value honest change before judging v8;
  it is deferred only to keep the comparison to v6/B0 clean. Read every v8 return
  number with this asterisk.
- **Dip-buying's effect on drawdown is genuinely ambiguous — do not assume it
  helps.** Two opposing forces: the standing cash buffer softens the *start* of a
  decline, but rebalancing *into* the decline increases BTC exposure as price
  falls, so at the very trough v8 can hold *more* BTC than it started with —
  catching a falling knife. The buffer helps the early drawdown; the dip-buying
  can deepen the trough while setting up a stronger recovery. Net max-DD could be
  better or worse than B0. This is exactly what criterion 2 measures; the spec
  refuses to promise a cushion it cannot guarantee.
- **The "rebalancing bonus" is regime-dependent and not a free lunch.** Buy-low-
  sell-high adds return mainly in choppy / mean-reverting markets. In a sustained
  up-trend the dominant effects are cash drag and selling winners early — i.e.
  return *lag*, the same headwind v6 paid. Over this single mostly-up cycle,
  expect v8 to trail B0 on return; whether it earns that back in risk-adjusted
  terms is the open question, not a foregone conclusion.
- **Fees and taxes scale with rebalance frequency — the band is the main lever.**
  The ±3% base band suppresses most small weekly rebalances, so v8's trade count
  should sit well below v6's, and every *sell* is still a realized-gain event in a
  taxable account. Wider bands cut this further; `band = 0` restores v6-like
  frequency. Tax remains unmodelled and remains the biggest pre-live check.
- **The band adds two small costs of its own.** First, deposits no longer deploy
  promptly — a $50 deposit can't breach ±3% alone, so it pools as idle cash until
  some larger move trips the band, a minor addition to the cash drag above.
  Second, the volatility-scaled variant *deliberately widens the band in high vol*,
  which is precisely when the rebalancing harvest is largest — so it can suppress
  the most valuable trades to save the cheapest fees. Whether vol-scaling nets out
  positive is an open empirical question, and its extra parameters (`base_band`,
  vol window, clamp bounds) are fresh overfitting surface on a thin sample. Treat
  a good in-sample vol-band result with the same suspicion as any other.
- **Behaviorally, v8 demands discipline on *both* sides.** You must hold it through
  bull runs while it lags (hard), *and* keep buying BTC as it falls 50–70% in a
  crash (much harder — deploying cash into a collapse feels insane in the moment),
  *and* tolerate idle cash earning nothing in between. v6 only tested your nerve in
  one direction; v8 tests it in three. The math pays out only to the version of
  you that does all three, and the backtest cannot test that.
- **Single mostly-up, in-sample cycle (~120 weekly obs).** Same standing
  limitation. The dip-buying half is exercised in essentially two declines (2020,
  2022), so its measured benefit rests on very few events. Freeze the last 20–26
  weeks as OOS before committing to a `target_w`.