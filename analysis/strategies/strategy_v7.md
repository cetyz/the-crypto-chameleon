# BTC Weekly Strategy — v7 "Fear-Gated Warchest"

## What v7 is for (read this first)

v7 is **v6 with the trim proceeds rerouted**. In v6, cash from a trim drips
straight back into BTC over the next 4 Tuesdays, unconditionally. v7 sends that
cash into a **warchest** instead — a segregated pile that only deploys when the
Fear & Greed Index reads extreme fear (`FNG ≤ 25`). Mechanically it is a
medium-sized diff. Conceptually it is a **reversal of v6's defining choice**, and
that reversal is the whole point — so read this section before assuming v7 is a
natural extension of v6.

The dashboard's win condition is unchanged: **risk-adjusted edge** — lower
drawdown, higher Sortino/Sharpe, return in a defensible relationship to B0. What
changes is that v7 reintroduces a **directional call**, on the buy side.

- **v6** made no prediction. It harvested froth as a pure side effect of
  position size and recycled the cash back in on a fixed clock. Its honesty was
  that it never claimed to know anything about the market — only about your
  weight.
- **v7** claims something v6 refused to: that **extreme fear is a better-than-
  random time to buy**. The trim still fires on weight alone (no change there),
  but the redeployment now waits for a sentiment signal. That is a bet, and it
  should be named as one.

> **v7 in one sentence:** v6's trim, minus v6's unconditional drip, plus a
> warchest that sits in cash until `FNG ≤ 25` and then deploys over `drip_weeks`
> Tuesdays — buying fear instead of buying the calendar.

**This is the mirror image of the gate v5 had and v6 killed.** v5 gated *selling*
on euphoria (`FNG ≥ 90`); v6 removed it because, on this cycle, it "did not earn
its keep." v7 now gates *buying* on fear. That symmetry is not decoration — it is
the central, falsifiable question of the whole spec: **does a sentiment gate earn
its keep on the buy side where it failed on the sell side?** v7 exists to answer
that, and it should be judged primarily on whether the answer is yes.

Be clear-eyed about the prior. v5's postmortem found the sentiment gate added
nothing. The honest default expectation for v7 is therefore *skeptical* — the
burden of proof is on v7 to beat both v6 and a no-signal null, not on the
baselines to defend themselves. If v7 cannot clear that bar, the correct
conclusion is "sentiment doesn't help on either side," and v7 collapses back to a
slower v6.

## What changed from v6

|  | v6 (Band Rebalance) | v7 (Fear-Gated Warchest) |
|---|---|---|
| Trim trigger | `w > target_w + band` | **Unchanged** — `w > target_w + band` |
| Trim proceeds go to | A 4-week drip **back into BTC**, unconditionally | A **warchest** (cash), held until triggered |
| Redeploy trigger | Calendar (next 4 Tuesdays, no condition) | `FNG ≤ 25` (extreme fear) |
| Decision signal | None — position size only | Fear & Greed on the **buy** side |
| Directional call | None | **Yes** — "fear is a good time to buy" |
| Warchest in weight denominator? | n/a (drip cash was transient) | **No** in base (excluded); tested both ways |
| New `common.py` deps | None | **Resurrects `load_fng_daily`, `fng_state`** (dead code in v6) |
| Parameter count | One fewer than v5 | **One more than v6** (`fng_buy_threshold` returns) |
| Headline bet | Accept return give-up for drawdown reduction | Same give-up, but try to **time the redeploy** to recover some of it |

**Why this change, and why it cuts against standing discipline — say so plainly:**

- The change is motivated by a dislike of v6's mechanics, not by a v6 failure.
  v6's drip "re-inflates the weight, which re-triggers the trim" — a treadmill
  the v6 spec itself flags as possibly counterproductive (`drip=hold` exists to
  test exactly that). v7 is one answer to "what else could the trim proceeds do?"
  — hold them as dry powder and spend them when assets are cheap.
- **v7 deliberately adds surface area, against the project's "prefer removing
  rules over adding them" discipline.** It reintroduces a signal, two
  `common.py` functions, and a parameter that v6 had removed. That is a real cost
  and the spec does not pretend otherwise. Adding back complexity is only
  justified if it buys risk-adjusted edge that v6 and a dumb null cannot. v7
  therefore carries a *higher* burden of proof than v6 did.
- **The audit-trail entry should read as a bet, not a derivation.** Nothing in
  the v6 spec prescribes v7; v6's open question was about `drip_weeks`, and
  `drip=hold` (keep trimmed cash as cash, deploy never) is the v6-native way to
  test "stop recycling." v7 goes further: it keeps the cash *and* adds a
  conditional spend rule. That is a new directional thesis layered on top, and it
  is honest to log it as a deviation motivated by (a) a mechanical dislike of the
  drip and (b) curiosity about whether the buy-side gate behaves differently from
  the sell-side one v5 discarded.

## What was kept from v6 / v5 / v3

The trim half of the machine is **untouched**. v3's framing still governs it:

> **"Is BTC now a larger share of my portfolio than my target?"** That question
> is answerable without any prediction. You harvest froth as a *side effect of
> position size*, not as a directional call.

v7 keeps that lock exactly. What v7 adds is a *second* key — but only on the
redeployment side. The sell decision remains prediction-free; only the buy
decision now makes a claim about the market. This asymmetry is intentional and
worth stating out loud: **v7 is prediction-free when reducing risk and
prediction-bearing when adding it.** Whether that asymmetry is wise is part of
what the experiment tests.

## Architecture: one decision day, two rules, one warchest

Four moving parts — v6's three, with the drip schedule replaced by a warchest and
a gated deployment rule:

1. **B0-style deploy-on-arrival.** Fresh monthly deposits buy BTC on the Tuesday
   they're available. Unchanged. Only *trim proceeds* are diverted to the
   warchest — new deposits are never withheld.
2. **A band-gated trim.** When BTC's weight drifts above `target_w + band`, sell
   BTC back to `target_w`. **Unchanged from v6.**
3. **A warchest.** Trim proceeds accumulate as cash in a segregated balance. It
   is not auto-deployed on any clock. In the base, this cash is **excluded from
   the weight denominator** (see Mechanics and caveats — this was a deliberate
   choice, and it has consequences).
4. **A fear-gated deployment rule.** A deployment *run* arms when `FNG ≤
   fng_buy_threshold` and no run is currently active. On arming, the run locks a
   slice size of `warchest / drip_weeks` and pays out one slice per subsequent
   `FNG ≤ threshold` Tuesday. **Any Tuesday where `FNG > threshold` cancels the
   run** — the remaining balance stays in the warchest and waits. The next time
   fear returns, a *fresh* run arms and re-slices the *then-current* balance.

## Mechanics

State: `target_w`, `band`, `drip_weeks`, `fng_buy_threshold`, `warchest` (USD),
and the run state `slices_remaining` and `slice_size`. The v6 `drip_schedule`
queue is gone; the warchest plus run-state replaces it.

```
# ---- MONTHLY (last Friday): deposit lands ----
on deposit:
    cash += 50

# ---- WEEKLY (Tuesday): the only decision day ----
each Tuesday:
    # 1. deploy any free DEPOSIT cash like B0 (warchest is NOT touched here)
    if cash > 0:
        buy BTC with all free cash

    # 2. compute weight. In the BASE, the warchest is EXCLUDED from the denominator:
    #    w = btc_value / (btc_value + cash)        # warchest not counted
    #    (the "included" variant uses btc_value + cash + warchest)
    w = btc_value / (btc_value + cash)

    # 3. band-gated trim (unchanged from v6) — proceeds go to the WARCHEST, not a drip
    if w > target_w + band:
        sell BTC down to target_w
        warchest += proceeds

    # 4. fear-gated warchest deployment
    fear = (FNG_today <= fng_buy_threshold)

    if not fear:
        slices_remaining = 0          # FNG recovered -> cancel any active run

    if fear and slices_remaining == 0 and warchest > 0:
        # arm a fresh run on the CURRENT balance
        slice_size = warchest / drip_weeks
        slices_remaining = drip_weeks

    if fear and slices_remaining > 0 and warchest > 0:
        amount = min(slice_size, warchest)
        buy BTC with amount; warchest -= amount
        slices_remaining -= 1
```

**Two consequences of step 4 that follow directly from your chosen rule — flagged,
not hidden:**

- **The trim is computed *before* the warchest deploys (step 3 before step 4).**
  So a fear-day warchest buy can push weight above the band, but it won't trigger
  a same-Tuesday trim of itself — that check already ran this week. It could
  contribute to a trim *next* Tuesday. This avoids an instant buy→trim loop but
  does not eliminate churn entirely (see caveats).
- **Cancel-and-re-arm, not pause-and-resume.** Per your spec: if `FNG` recovers
  mid-run, the run is cancelled outright (`slices_remaining → 0`), not paused. The
  undeployed balance waits. When fear returns, a *new* run re-slices the current
  balance into `drip_weeks` again. Net effect: in a V-shaped scare (fear spikes,
  recovers fast), you deploy only the slices that fell inside the fear window and
  keep the rest — you intentionally do **not** chase the recovery. This is
  conservative by design; its cost is named in the caveats.

The re-arm condition is **level-based** (`fear and slices_remaining == 0 and
warchest > 0`), which also cleanly handles a *prolonged* bear: once a run's slices
are spent, if fear persists and trims have refilled the warchest, a new run arms
the following week and keeps buying. You do not have to wait for FNG to bounce
out of the zone and back in.

## Parameters (v7-base)

| Param | Value | Rationale |
|---|---|---|
| `target_w` | 0.92 | Inherited from v6 unchanged. Still the frontier dial; swept in the matrix. |
| `band` | +0.05 | Trim threshold 0.97. Inherited unchanged. The trim half is untouched. |
| `fng_buy_threshold` | 25 | **New (returning).** Extreme fear. Deliberately the mirror of v5's `90` sell threshold, so the buy-side/sell-side comparison is symmetric. Swept, not fit. |
| `drip_weeks` | 4 | **Repurposed.** No longer "how trim cash re-enters" — now "how many weekly slices a *triggered* warchest deployment is spread over." Kept at 4 for continuity; swept. |
| Warchest accounting | **Excluded** from weight denominator | Your choice for the base: the warchest is a sidecar, so `target_w` is a target on *invested* capital, not net worth. The "included" treatment is a tested variant. |
| Deposit | $50, last Friday of month | Unchanged. Deposits deploy-on-arrival; only trim proceeds feed the warchest. |
| Decision day | Tuesday | Unchanged. |
| Fee | 0.10% per trade | Unchanged. Trade *count* will differ from v6 (buys now cluster in fear windows rather than every Tuesday) — report cumulative fees explicitly. |
| Cash yield | 0 | Unchanged, and **this penalizes v7 harder than v6** — the warchest can sit idle for months, not days. Kept at 0 for comparability; see caveats. |

One parameter more than v6, which had one fewer than v5. v7 is back to v5's
parameter count, with the signal on the opposite side of the trade.

## New infrastructure required

**Resurrect, don't rebuild.** v6 left `load_fng_daily()` and `fng_state()` in
`common.py` as dead code "for v5's audit trail." v7 calls `load_fng_daily()`
again. No new `common.py` functions are needed beyond what already exists; the
warchest and run-state are local simulation state in `simulate_v7`. Per the
"no code changes to prior-version scripts" discipline, `analysis_v7.py` should
define its own `simulate_v7` rather than re-flagging `simulate_v5`.

## Experiment matrix (for `postmortem_v7.py`)

| Variant | Change | What it tests |
|---|---|---|
| **v7-base** | thr 25, drip 4, warchest excluded | Headline. Fear-gated redeploy of trim proceeds. |
| **v7-threshold-sweep** | `fng_buy_threshold ∈ {15, 20, 25, 30}` | How deep must fear be to fire. Lower = rarer, deeper buys, more idle cash. Legibility check: does the curve behave monotonically? |
| **v7-drip-sweep** | `drip_weeks ∈ {1, 4, 8}` | Lump vs spread on a trigger. `1` = empty the chest in one fear-day buy (concentrated timing bet); `8` = spread thin (more likely to be cut short by FNG recovery). |
| **v7-warchest-in-denominator (variant)** | Include warchest in `w` | Tests the accounting choice you excluded from the base. Including it self-damps trims (chest grows → `w` reads lower → fewer trims); excluding it does the opposite. This is a real, non-cosmetic difference. |
| **v7-backstop-K (variant)** | Deploy a slice anyway if it has sat `> K` weeks; `K ∈ {13, 26}` | The anti-idle floor you asked to keep out of the base. Bounds the dead-cash drag. If the backstop helps materially, the pure fear-gate is leaving money idle too long. |
| **v7-null-no-signal (the key null)** | Warchest deploys on a fixed 12-week drip, **no FNG** | **The "does the gate earn its keep" test.** If the FNG buy-gate cannot beat a dumb slow drip on risk-adjusted terms, the signal is decoration — exactly v5's verdict, reproduced on the buy side. |
| **v7-no-warchest (ablation)** | Send trim proceeds straight back in (= v6) | The floor on the other side. Confirms the warchest is what moves the metrics, and isolates v7's effect vs v6. |

The two rows that matter most are **v7-null-no-signal** and the cross-version
**v7-base vs v6-base vs B0**. Together they answer the only question that
justifies v7's existence: does fear-timing the redeploy beat (a) timing it on a
dumb clock and (b) not warchesting at all? Everything else is secondary.

## What "success" means for v7

v7 is still a frontier choice, but it carries an **added burden**: it must justify
the complexity it reintroduced. A "good" v7 over the 2020-03 → 2026-04 window
means:

1. **Beats `v7-null-no-signal` on {return OR drawdown} without losing the other.**
   This is the load-bearing criterion and the direct mirror of v5's failed
   criterion 5. If the FNG buy-gate does not dominate a no-signal slow drip, the
   gate adds nothing and v7 should be abandoned in favour of v6 (or a longer-drip
   v6). **This is the test v7 most needs to pass.**
2. **At least matches v6-base on risk-adjusted metrics (DD, Sortino, Sharpe).**
   If v7 adds a signal and *doesn't* beat v6 on risk-adjusted terms, the added
   surface area failed to pay for itself — judge against the discipline, not just
   against B0.
3. **Max drawdown still shallower than B0 by ≥ 8 pp; Sortino ≥ B0 + 0.3;
   Sharpe ≥ B0.** Inherited v6 bars — v7 must not *break* what v6 achieved while
   chasing the redeploy edge.
4. **The return give-up remains risk-justified.** As in v6, lagging B0 on return
   is the accepted cost, not a failure — it fails only if 1–3 are missed.
5. **`fng_buy_threshold` sensitivity is legible.** Deeper fear thresholds should
   trade deploy-frequency for buy-quality smoothly. A jagged or non-monotone
   sweep is an in-sample artifact (there are very few fear episodes to fit to —
   see caveats), to be distrusted, not chased.

If 1–2 are met, the buy-side gate earns its keep and v7 is a real improvement on
v6's mechanics. **If 1 is missed, sentiment does not help on the buy side either,
and the honest conclusion — symmetric with v5 — is that the FNG signal is
decoration on both sides of the trade.**

## Honest caveats specific to v7

- **Almost nothing to calibrate the buy-gate against.** This is the dominant
  caveat. The trim half harvests across the whole cycle, but the *buy* half only
  acts in extreme-fear windows, and over 2020→2026 there are essentially **two**
  (the 2020 COVID crash and the 2022 bear, plus a few brief touches). The fear
  threshold is therefore being fit to ~2 events. This is *worse* overfitting
  exposure than v6's trim, which at least fired continuously. Treat any
  `fng_buy_threshold` that looks optimal in-sample with heavy suspicion, and hold
  out the last 20–26 weeks as frozen OOS before committing to one. The matrix is
  the only defence and it is a thin one here.
- **v7 reintroduces a directional call after v6 worked to remove one.** That is a
  philosophical reversal, and the prior from v5 is unfavourable: the sentiment
  gate did not earn its keep on the sell side. v7 must overcome that prior with
  evidence, not assume the buy side is different because it feels different.
- **FNG ≤ 25 is largely a proxy for "price already fell a lot."** Extreme fear and
  deep drawdown are highly correlated, so the buy-gate may be doing little more
  than a drawdown-from-high trigger would, but with an extra data dependency. If
  v7 works, a follow-up should check whether a pure price-drawdown trigger (no
  FNG, no `common.py` resurrection) captures the same edge more cheaply. If they
  perform identically, prefer the one with less surface area.
- **Idle-cash drag is worse than v6's, and `cash yield = 0` punishes it more.**
  The warchest can sit for months between fear episodes. At 0% yield that idle
  cash is pure opportunity cost, and during a long bull with no fear touch the
  chest just grows and rots. **Real-world v7 (warchest in T-bills/stables at
  ~4–5%) is meaningfully better than this backtest shows — more so than for v6.**
  Modelling yield is the highest-value honest change before taking v7 seriously,
  and it is deferred only to stay comparable to v5/v6/B0.
- **Excluding the warchest from the denominator is not free.** It means
  `target_w = 0.92` is a target on *invested* capital, with the warchest as an
  off-book sidecar. Because the chest doesn't count, a growing chest does **not**
  damp future trims (unlike the "included" variant) — so trims and warchest
  growth mildly reinforce each other. The reading of `w` is also "optimistic" in
  the sense that it ignores real cash you hold. The included-denominator variant
  exists precisely to show how much this choice flatters or distorts the metrics.
- **The conservative re-arm rule won't catch sharp V-bottoms.** By cancelling a
  run the moment FNG recovers and only re-arming on the next fear entry, v7
  deliberately under-deploys into fast recoveries — you buy a little of a V-shaped
  dip and keep the rest as dry powder. In a cycle full of sharp recoveries this
  leaves the chest persistently under-spent. That is the price of the rule you
  chose; it is a feature if you distrust fast bounces and a bug if you don't.
- **Churn is reduced, not eliminated.** v6's complaint — drip re-inflates weight,
  re-triggering the trim — is mostly gone, since the redeploy now waits for fear.
  But a fear-day warchest buy still raises weight and can trigger a trim the
  following week if weight was already near the band. In practice fear (low
  weight) and trims (high weight) are anti-correlated, so this is rare — but it is
  not impossible, and the spec does not claim a churn-free machine.
- **Tax exposure is between v6 and v5.** Trims are unchanged from v6, so the
  realized-gain count on the *sell* side is similar; the buy side adds no taxable
  events. As with v6, this matters enormously in a taxable account and mostly
  vanishes in a sheltered one. Still unmodelled; still the biggest check before
  live use.
- **Single mostly-up cycle, in-sample, ~120 weekly observations.** Same standing
  limitation as everything in this project — doubly binding here because the
  buy-gate only acts in the rarest part of the sample.
- **v7 only helps if you hold it through both directions** — the same behavioural
  assumption v6 carries, plus a new one: you also have to tolerate watching a
  growing pile of cash sit idle through a bull, doing nothing, waiting for a fear
  that may not come for a year. That is psychologically harder than v6's
  always-invested drip, and the backtest cannot test whether you'd actually leave
  the warchest alone.