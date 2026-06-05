# BTC Weekly Strategy — v6 "Band Rebalance"

## What v6 is for (read this first)

v6 is **v5 with the Fear & Greed gate removed**. Mechanically it is a one-line
diff. Conceptually it is a different animal, and that difference is the whole
point — so read this section before assuming v6 ≈ v5.

The dashboard's win condition is unchanged: **risk-adjusted edge** — lower
drawdown, higher Sortino/Sharpe, return in a defensible relationship to B0. What
changes is the bet we make to get there.

- **v5** tried to harvest froth *only at euphoric tops* (band exceedance AND
  FNG ≥ 90). The FNG gate made the trim rare and concentrated it into a handful
  of moments — which, on this cycle, were mostly the wrong moments (the 2024-03
  and 2024-11 trims sold into continued upside). v5 kept almost all of B0's
  return *and* almost all of B0's drawdown. It bought nothing.
- **v6** drops the gate and trims on **weight alone**. Whenever BTC drifts above
  `target_w + band`, sell back to `target_w`. With deposits deploying weekly and
  BTC mostly rising, that fires nearly every Tuesday. v6 is therefore not an
  event-driven harvester — it is a **continuous rebalancer to a target weight**.

> **v6 in one sentence:** B0's deploy-on-arrival spine, plus a band-triggered
> rebalance that keeps BTC near `target_w` by trimming whatever drifts above the
> band — no sentiment signal, no euphoria gate, no directional call.

v6 explicitly accepts giving up return in exchange for a shallower drawdown and
a better risk-adjusted profile. It is a deliberate move to a different point on
the return/drawdown frontier — **not** an attempt to match B0's return. If you
believe BTC has strong, uninterrupted positive drift over your horizon, B0 is
the coherent choice and v6 is a tax. v6 earns its keep only if you want the
drawdown cushion and are willing to pay for it in upside.

## What changed from v5

|  | v5 (Greed-Gated Trim) | v6 (Band Rebalance) |
|---|---|---|
| Trim trigger | `w > target_w + band` **AND** `FNG_today ≥ 90` | `w > target_w + band` (weight alone) |
| Character | Rare event-driven harvest at euphoric tops | Continuous rebalance to target weight |
| Trims over cycle | ~2–8 intended (11 observed) | ~300+ by design (~every Tuesday) |
| Decision signal | Fear & Greed Index (composite sentiment) | None — position size only |
| New `common.py` deps | `load_fng_daily`, `fng_state` | None (v6 calls neither) |
| Headline bet | Keep B0 return, shave drawdown at tops | Accept return give-up for real drawdown reduction |

**Why this change, sourced to the v5 postmortem:**

- The `v5-no-fng` ablation — which *is* this strategy — already hit the original
  goal that v5 missed: **max DD −57.91% vs B0's −68.36% (10.45 pp shallower),
  Sortino 3.354 vs 2.975, Sharpe 1.544 vs 1.494**, at a cost of ~36 pp on return
  (117.41% vs 153.06%). It was sitting in the matrix mislabeled as a failed
  ablation. v6 promotes it to a spec of its own. (These are the numbers v6-base
  is expected to reproduce — it is the same code path. Still one cycle, still
  in-sample.)
- The FNG gate did not earn its keep. v5's success-criterion 5 ("v5-base
  dominates v5-no-fng on {ret OR DD} without losing the other") originally read
  PASS on a sign error — `dom_dd = v5_dd < no_fng_dd` counted v5's *deeper*
  drawdown (−67.67) as "dominating" no-fng's shallower one (−57.91). With that
  corrected to `>`, **criterion 5 now correctly reads FAIL**: v5 wins on return
  but loses ~9.8 pp on drawdown, so it does not dominate without losing the
  other. v5 is therefore a clean 5-for-5 failure on its own scorecard. The gate
  added nothing.
- **What licenses v6 is the matrix section, not the decision tree — say so
  plainly.** Be precise about the audit trail here, because the two are not the
  same. `strategy_v5.md`'s decision tree routes a total 1–4 failure to *"revisit
  `target_w`/`drip_weeks` around v5-base"* — a branch that **keeps** the FNG
  gate. The branch that drops the gate ("1–4 met **and** 5 not met") was never
  reached, because 1–4 were not met. So the literal pre-registered tree does
  *not* prescribe v6. What does support dropping the gate is the spec's *matrix
  section*, which states outright that a failed criterion 5 means the gate "is
  not earning its keep and v6 should reconsider it." v6 is therefore a
  deliberate **synthesis of two partially-conflicting instructions** — drop the
  gate (matrix section) and run the `target_w`/`drip` search on top (tree branch
  B) — plus the deeper finding that no-fng is the only matrix arm that hit the
  project's original drawdown goal. This is a documented **deviation** from the
  tree's literal branch-B prescription, not a clean derivation from it. Flagging
  it as a deviation is the honest entry for the audit trail.
- *(The v5 report's verdict was corrected by re-running a fixed `postmortem_v5.py`;
  the original committed report had the spurious PASS. Both versions of that fact
  belong in the trail.)*
- Removing the gate is consistent with the standing discipline: **prefer
  removing rules over adding them.** v6 has strictly less surface area than v5 —
  one fewer signal, two fewer `common.py` functions, one fewer parameter.

## What was kept from v5 / v3

v3's framing remains the right framing, inherited verbatim:

> **"Is BTC now a larger share of my portfolio than my target?"** That question
> is answerable without any prediction. You harvest froth as a *side effect of
> position size*, not as a directional call.

v6 keeps exactly this and removes the rest. There is no second key. The lock —
your weight relative to target — is the entire mechanism. v6 makes no claim
about whether the *market* is frothy; only about whether *your position* has
drifted above where you want it.

## Architecture: one decision day, one rule, one drip schedule

Three moving parts — same skeleton as v5, minus the signal:

1. **B0-style deploy-on-arrival.** All free cash buys BTC on the Tuesday it's
   available. This is still the spine.
2. **A band-gated rebalance.** When BTC's portfolio weight drifts above
   `target_w + band`, sell BTC back down to `target_w`. No second condition.
3. **A drip schedule for trim proceeds.** Cash from a trim splits into
   `drip_weeks` equal weekly slices released on subsequent Tuesdays. **Note the
   tension this creates under continuous trimming** (see caveats and the drip
   sweep): dripping back in re-inflates the weight, which re-triggers the trim.
   v6-base keeps `drip_weeks = 4` to reproduce the v5-no-fng ablation exactly;
   whether that churn is helping or hurting is the single most important thing
   the experiment matrix tests.

## Mechanics

State: `target_w`, `band`, `drip_weeks`, and `drip_schedule` (a queue mapping
future Tuesdays → USD to deploy). No `fng_trim_threshold`.

```
# ---- MONTHLY (last Friday): deposit lands ----
on deposit:
    cash += 50

# ---- WEEKLY (Tuesday): the only decision day ----
each Tuesday:
    # 0. drip — if a slice is due today, deploy it first
    if drip_schedule has a slice due this Tuesday:
        deploy that slice into BTC; cash -= slice; drip_schedule.pop()

    # 1. deploy any remaining free cash like B0
    if cash > 0:
        buy BTC with all free cash

    # 2. compute weight AFTER the deploy step
    w = btc_value / (btc_value + cash)

    # 3. band-gated rebalance (no sentiment gate)
    if w > target_w + band:
        sell BTC down to target_w
        split proceeds into drip_weeks equal slices,
            scheduled for the next drip_weeks Tuesdays

    # 4. otherwise: hold
```

The only change from v5's pseudocode is step 3: the `AND fng_today >= threshold`
clause is gone. Everything else — order of operations, the separate `cash` and
`drip_schedule` buckets, the rationale for trimming last — is unchanged.

Implementation note: `analysis_v5.py`'s `simulate_v5(...)` already exposes
`disable_fng_gate=True`, and the v5-no-fng matrix row uses exactly that path.
v6-base = `simulate_v5(daily, fng, disable_fng_gate=True)` with all other params
at their v5 defaults. `analysis_v6.py` should call its own `simulate_v6` (a copy
with the gate physically removed, per "no code changes to prior-version scripts"
discipline) so the v6 spec is self-contained and the FNG argument disappears
entirely.

## Parameters (v6-base)

| Param | Value | Rationale |
|---|---|---|
| `target_w` | 0.92 | Inherited from v5 **unchanged** — no re-tuning for the base. This is the dial that sets where on the frontier you sit; it is swept (not pre-fit) in the matrix. |
| `band` | +0.05 | Trim threshold = 0.97. Inherited unchanged. Acts as hysteresis: a no-trade zone between 0.92 and 0.97. |
| `drip_weeks` | 4 | Inherited unchanged so v6-base reproduces the v5-no-fng ablation exactly. Its appropriateness under continuous trimming is the matrix's main question. |
| Deposit | $50, last Friday of month | Unchanged. |
| Decision day | Tuesday | Unchanged. |
| Fee | 0.10% per trade | Unchanged. With ~300+ trims, report cumulative fees explicitly — they are larger than v5's $8.17, though already baked into the −57.91%/117.41% numbers. |
| Cash yield | 0 | Unchanged, and **this assumption specifically penalizes v6** (see caveats). Kept at 0 to stay comparable to v5/B0. |

No new parameters are introduced. v6 has one fewer than v5.

## New infrastructure required

**None.** This is the point. v5 introduced `load_fng_daily()` and `fng_state()`;
v6 calls neither. They stay in `common.py` for v5's audit trail but are dead code
from v6's perspective. Everything v6 needs (`last_friday_deposit_dates`,
`next_tuesday`, `simulate_control`, `summarize_arm`, `max_drawdown`,
`sharpe_sortino`, `boot_ci`) is already shared and reused unchanged.

## Experiment matrix (for `postmortem_v6.py`)

| Variant | Change | What it tests |
|---|---|---|
| **v6-base** | target 0.92, band +0.05, drip 4w | Headline. Reproduces v5-no-fng. |
| **v6-target-sweep** | `target_w ∈ {0.80, 0.85, 0.92, 0.98}` | **The main exploration.** Traces the return/drawdown frontier. 0.98 ≈ B0; lower = more cushion, more give-up. This is "where do I want to sit," and it is a *preference*, not a prediction — so the matrix shows the menu rather than fitting a winner. |
| **v6-drip-sweep** | `drip_weeks ∈ {1, 4, 8, hold}` | The churn question. `hold` = trimmed cash stays as cash at the lower weight instead of dripping back. If `hold` reduces drawdown further without much extra return cost, the drip is counterproductive under continuous trimming and v7 should drop it. |
| **v6-band-sweep** | `band ∈ {0.03, 0.05, 0.08}` | Hysteresis width → trim frequency and fee drag. Wider band = fewer, larger rebalances. |
| **v6-no-trim (ablation)** | Disable trims (= B0 by construction) | The floor. Confirms the rebalance path is what moves the metrics. |

The `v6-target-sweep` and `v6-drip-sweep` rows are the important ones: the first
defines the strategy's identity (it is a frontier choice), the second resolves a
genuine design tension inherited from v5's mechanics.

A cross-version row comparing **v6-base vs v5-base vs B0** should be reported so
the "the gate was decoration" claim stays visible and falsifiable.

## What "success" means for v6

v6 is a frontier choice, so its criteria are framed around risk-adjusted edge,
**not** return-matching. A "good" v6 over the 2020-03 → 2026-04 window means:

1. **Max drawdown shallower than B0 by ≥ 8 pp.** (v5-no-fng: −10.45 pp — expected PASS.)
2. **Sortino ≥ B0 + 0.3.** (v5-no-fng: +0.379 — expected PASS.)
3. **Sharpe ≥ B0.** (v5-no-fng: +0.05 — expected PASS. New bar; v5 didn't have one.)
4. **The return give-up is risk-justified.** The ~36 pp return shortfall vs B0
   is the *accepted cost*, reported and flagged — not a failure. It fails only if
   criteria 1–3 are NOT met, i.e. if you give up the return *without* getting the
   drawdown/risk-adjusted improvement in return. (Replaces v5's "within 10 pp"
   bar, which v6 cannot and should not meet.)
5. **`target_w` sensitivity is monotone-ish and legible.** Lowering `target_w`
   should trade return for drawdown smoothly across the sweep. If it doesn't —
   if some interior `target_w` dominates the endpoints on both axes — that is an
   in-sample artifact to distrust, not a free lunch to chase.

Criteria 1–3 are the real test. There is no trim-count criterion: v6 trims
continuously by construction, so counting trims is meaningless — fee drag (a
small, reportable number) is the relevant frequency check instead.

If 1–3 are met: v6 is a valid frontier point and the choice between it and B0 is
a risk-tolerance decision, not a backtest decision. If 1–3 are missed, the
rebalance is not buying risk-adjusted edge and v7 should reconsider whether any
weight-management beats plain B0 on this data.

## Honest caveats specific to v6

- **Single mostly-up BTC cycle.** Same limitation as everything in this project.
  v6's drawdown advantage is earned almost entirely in the one deep decline
  (2022) and the chop; its return cost is paid in the up-legs. A different cycle
  mix changes the trade-off. ~120 weekly observations is one cycle — point
  estimates are wide.
- **The return give-up is real and front-loaded.** v6 lags B0 *during bull
  runs*, persistently and visibly, because every rebalance sells into a rising
  market. This is psychologically the hardest time to hold it — the lag peaks
  exactly when abandoning it feels most justified, which is the wrong time.
- **The drip may be working against the goal.** Under near-weekly trimming, the
  4-week drip re-inflates weight back toward 1.0, partially undoing the cushion
  it just bought. The −57.91% DD already reflects this churn; the `drip=hold`
  variant tests whether removing the churn deepens the cushion. Do not treat
  drip=4 as settled — it was inherited for reproducibility, not chosen.
- **Cash yield = 0 specifically penalizes v6.** v6 holds more cash-in-transit
  (the drip queue) and, at lower `target_w`, more standing cash than B0. Real
  cash earns ~4–5% in T-bills/stables, which lowers the opportunity cost of
  being underweight. **Real-world v6 is somewhat better than this backtest
  shows.** Modeling yield is a `common.py` infrastructure change, deferred to
  keep v6 directly comparable to v5/B0 — flag it as the highest-value honest
  change for v7.
- **Tax is not modeled, and v6 is the strategy most exposed to it.** ~300+ trims
  means ~300+ realized-gain events. In a taxable account this drag could
  plausibly erase much of the risk-adjusted edge; in a tax-sheltered account it
  mostly vanishes. The backtest is silent on this — it is the single biggest
  check before treating v6 as live-viable.
- **v6 only helps if you hold it through both directions.** A −58% drawdown you
  sit through beats a −68% you panic-sell, and also beats a −58% strategy you
  quit during the bull because it was lagging. The math pays out only to the
  version of you that flinches in neither direction. That is a behavioral
  assumption, not a financial one, and the backtest cannot test it.
- **As always, one cycle of in-sample work.** Even though v6 *removes* a tuned
  parameter rather than adding one, the `target_w` sweep explores the frontier on
  in-sample data. Before selecting a `target_w` to commit to, designate the most
  recent 20–26 weeks as frozen out-of-sample and re-introduce them only after the
  choice is made. The experiment matrix is the only defense, and it is still a
  defense against a single sample.