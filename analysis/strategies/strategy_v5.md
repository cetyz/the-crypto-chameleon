# BTC Weekly Strategy — v5 "Greed-Gated Trim"

## What v5 is for (read this first — the goal has changed back)

v5 abandons v4's "activity is the product" framing. The dashboard's actual win condition (per `placeholder_strat.md` / `PRODUCT.md`) is **risk-adjusted edge**: lower drawdown, higher Sortino, return within shouting distance of B0. v4 explicitly traded return for visible weekly activity and produced neither edge nor an honest activity story (its trim trigger was mathematically unreachable, so the "sleeve" emptied permanently and the strategy degenerated into "B0 with a leaky cash bucket and 6× the fees").

The good news from the v3 postmortem is that the right shape was already there — it just gave up too much return:

- **v3 base** trimmed twice in six years, cut max drawdown by ~14 pp and improved Sortino by +0.6 vs B0/B3 — at a cost of ~31 pp on return.
- **v3 `no-deposit-steer`** (deposits go straight to BTC, only the trim/redeploy logic runs) finished only ~8 pp behind B0 on return while still being ~6 pp shallower on max drawdown.

v5 keeps v3's "allocation drift triggers the sell," drops the parts of v3 that bled return, and adds a **legible euphoria gate** so that the rare trim only fires when the sell is genuinely defensible — not just because the weight wandered slightly above the band during an ordinary up-week.

> **v5 in one sentence:** B0 by default, with rare trims gated by both *band exceedance* and *Fear & Greed Index ≥ 90*, where trim proceeds are dripped back into BTC over a short window so cash drag is bounded and temporary, not standing.

## What changed from v4

|  | v4 (rejected) | v5 |
|---|---|---|
| Stated goal | Activity & divergence | Risk-adjusted edge vs B0 |
| Default behavior | Permanent sleeve + weekly dip-buys | Deploy deposits to BTC on arrival (B0-style) |
| Cash drag | Standing ~12% sleeve | Only the post-trim drip window (~4 weeks) |
| Trim trigger | `w > 0.85 + 0.15 = 1.00` (literally unreachable; `w ≤ 1`) | `w > target_w + band` AND `FNG_today ≥ 90` |
| Trims observed | 0 in 6 years (broken) | 2–8 expected over the cycle |
| Activity rate | ~50% of weeks (forced) | ~3% of weeks (incidental) |
| Decision signal | None (dip-depth heuristic only) | Fear & Greed Index (composite sentiment) |
| Scorecard | `active_weeks_%`, divergence | Max DD, Sortino, return-gap-to-B0 |

The single line you can copy out of v4 into v5's epitaph: *"the activity is the product, not the returns"* turned out to be a worse product than B0 was already shipping. v5 stops paying for activity.

## What was kept from v3

v3's framing is still the right framing — and the spec for v3 already named it well, so we inherit it verbatim:

> **"Is BTC now a larger share of my portfolio than my target?"** That question is answerable without any prediction. You harvest froth as a *side effect of position size*, not as a directional call.

v5 only adds: *and is the rest of the market also acting like froth right now?* The FNG gate is the second key — both the lock (your weight) and the key (market sentiment) have to be in the right place for the trim to fire. Either one alone is not enough.

## Architecture: one decision day, one signal, one drip schedule

Three moving parts, all deliberately less than v4 had:

1. **B0-style deploy-on-arrival.** All free cash buys BTC on the Tuesday it's available. No sleeve, no held-back ammunition. This is the spine of the strategy — most weeks, v5 is indistinguishable from B0.
2. **A signal-gated trim.** When BTC's portfolio weight drifts above `target_w + band` *and* daily FNG is ≥ 90, sell BTC back down to `target_w`. Both conditions are required; either alone is insufficient.
3. **A drip schedule for trim proceeds.** Cash from a trim does **not** become free cash. It splits into `drip_weeks` equal weekly slices, each released on a subsequent Tuesday. This bounds the post-trim cash drag to a known window, and prevents the trim from immediately undoing itself with a "deploy all free cash" buy on the same day.

## Mechanics

State: `target_w`, `band`, `fng_trim_threshold`, `drip_weeks`, and `drip_schedule` — a small queue mapping future Tuesdays → USD to deploy.

```
# ---- MONTHLY (last Friday): deposit lands ----
on deposit:
    cash += 50                                   # raw cash, not earmarked

# ---- WEEKLY (Tuesday): the only decision day ----
each Tuesday:
    # 0. drip — if a slice is due today, deploy it first
    if drip_schedule has a slice due this Tuesday:
        deploy that slice into BTC; cash -= slice; drip_schedule.pop()

    # 1. deploy any remaining free cash like B0 (deposits + any leftover)
    if cash > 0:
        buy BTC with all free cash                # no holding back

    # 2. compute weight AFTER the deploy step
    w = btc_value / (btc_value + cash)            # cash is ~0 here after step 1

    # 3. signal-gated trim (rare)
    if w > target_w + band AND fng_today >= fng_trim_threshold:
        sell BTC down to target_w
        split proceeds into drip_weeks equal slices,
            scheduled for the next drip_weeks Tuesdays
        # proceeds DO NOT enter free cash; they live in drip_schedule

    # 4. otherwise: hold
```

Notes on shape:

- **Order matters.** Drip fires *before* deposit-deploy so a drip slice doesn't get caught up in a "deploy all cash" sweep; deposit-deploy fires *before* the weight check so the trim measures the position you actually hold. Trim fires last because it's the only step that creates new cash.
- **`cash` and `drip_schedule` are separate buckets.** The "deploy all free cash" rule only touches `cash`. Drip slices are paid from the schedule, not from cash, so the trim is genuinely unwound over `drip_weeks` rather than instantly.
- **The trim band is reachable.** With `target_w = 0.92` and `band = +0.05`, the threshold is `w > 0.97`. After a long up-grind and a recent deposit-deploy, that's hit when BTC has materially out-grown the cash that arrived in the last few weeks. v4's mistake (`target + band = 1.00`, i.e. "trim when you own more than 100% of your portfolio in BTC") is explicitly the reason we tightened these numbers.
- **No lower-band drift-redeploy.** v3 had one; v5 doesn't need one. Because deposits already deploy on arrival, the only event that *creates* cash is a trim — and the drip already handles that re-entry mechanically. Less surface area, fewer parameters, fewer chances to do the wrong thing.

## Parameters (v5-base)

| Param | Value | Rationale |
|---|---|---|
| `target_w` | 0.92 | High enough that v5 mostly tracks B0; low enough that `target + band` sits below 1 with room to spare. |
| `band` | +0.05 | Trim threshold = 0.97. Reachable in practice but only after sustained up-runs — not on weekly noise. |
| `fng_trim_threshold` | 90 | "Extreme Greed" per Fear & Greed Index. Historically a rare daily value (≤ a few % of all days since 2018). |
| `drip_weeks` | 4 | One month of equal weekly re-entries. Bounds drag without instantly un-doing the trim. |
| Deposit | $50, last Friday of month | Unchanged. Same calendar as B0 / v3 / v4. |
| Decision day | Tuesday | Unchanged. Same as B0. |
| Fee | 0.10% per trade (`FEE_RATE`) | Unchanged. |
| Cash yield | 0 | Unchanged. Honest drag — we are not modeling T-bill yield on cash. |

## New infrastructure required

v5 needs two new pieces in `common.py` — the spec names them so the implementation isn't ambiguous:

1. **`load_fng_daily()`** — loads the Fear & Greed Index from `analysis/data/fng_daily.csv`, fetching from `https://api.alternative.me/fng/?limit=0&format=json` if the cache is absent. The API is free, no key required, and provides daily history back to **2018-02-01** — comfortably before our `START = 2020-03-01`. CSV columns: `date` (UTC date), `value` (int 0–100), `classification` (str, e.g. "Extreme Greed"). Returns `Series[date → int]`.
2. **`fng_state(daily_fng, d, threshold=90)`** — returns the integer FNG value at date `d` (forward-filled to the prior available date if `d` is missing — the API has occasional holes), or `None` if no prior value exists. The simulator queries this each Tuesday rather than re-indexing the raw CSV.

These are the only `common.py` additions v5 introduces. Everything else (`last_friday_deposit_dates`, `next_tuesday`, `simulate_control`, `summarize_arm`, `max_drawdown`, `sharpe_sortino`, `boot_ci`) is reused unchanged.

## Experiment matrix (for `postmortem_v5.py`)

| Variant | Change | What it tests |
|---|---|---|
| **v5-base** | target 0.92, band +0.05, fng_thr 90, drip 4w | Headline. |
| **v5-fng-sweep** | `fng_trim_threshold ∈ {85, 90, 95}` | How rare should "extreme greed" need to be? 85 = more permissive (more trims, more drag); 95 = stricter (maybe zero trims this cycle). |
| **v5-drip-sweep** | `drip_weeks ∈ {1, 4, 8}` | 1 ≈ "trim and immediately un-trim" (near no-op); 8 = longer drag but smoother re-entry. |
| **v5-target-sweep** | `target_w ∈ {0.85, 0.92, 0.98}` | Confirm 0.92 is near the sweet spot; lower drags return, higher leaves no room for the band. |
| **v5-band-sweep** | `band ∈ {0.03, 0.05, 0.08}` | Sensitivity of trim frequency to the band width. |
| **v5-no-fng (ablation)** | Drop the FNG gate; trim on band alone | Isolates FNG's contribution. ≈ v3 with deposit-steer off. **If v5-base does not clearly dominate this on at least one of {return, max DD}, the FNG gate is not earning its keep** and v6 should reconsider it. |
| **v5-no-trim (ablation)** | Disable trims entirely (= B0 by construction) | The floor. Confirms the trim path adds value, not subtracts. |

The two ablations are the most important rows in the matrix: they're what make v5's claim falsifiable.

## What "success" means for v5

A "good" v5 over the 2020-03 → 2026-04 window means **all five** of these:

1. **Max drawdown shallower than B0 by ≥ 8 pp.** (v3 hit ~14 pp; v5 spends fewer weeks defensive, so this is a softer but still meaningful bar.)
2. **Sortino ≥ B0's + 0.3.**
3. **Return within 10 pp of B0.** This is the new headline bar — pay much less for the risk reduction than v3 did.
4. **Trim count between 2 and 8** over the full cycle. Fewer = signal too strict to be useful; more = signal too loose, activity creeping back in.
5. **v5-base strictly dominates v5-no-fng** on at least one of {return, max DD} without losing the other. Otherwise the FNG gate is decoration.

If criteria 1–4 are met and 5 is not, the next iteration is "v6 = v3 no-deposit-steer cleaned up" — drop FNG, keep the band-only trim. If 1–4 are missed entirely, the next iteration is "v6 = revisit target_w / drip_weeks search around v5-base."

## Honest caveats specific to v5

- **Single mostly-up BTC cycle.** FNG ≥ 90 days in this window may all cluster around the late-2021 top — in which case v5's whole story collapses into "we got lucky with one well-timed trim." The postmortem must explicitly report **how many distinct trim events occurred** and **the FNG value at each**, not just a trim count.
- **FNG is composite, not independent.** Its inputs (volatility, momentum, dominance, social, surveys, sometimes funding) overlap with signals we already had in `common.py`. It is *not* an orthogonal signal — it's a more legible one. We chose it because "extreme greed = 90" is dashboard-narratable in a way "funding annualized > 80th percentile of trailing 26w" is not.
- **Drip is unconditional.** In a regime where the trim coincides with the actual top (e.g. late 2021), dripping back in over 4 weeks gives back some of the harvest. We are accepting that, because the alternative — gating re-entry on a signal — is another forecast we don't want to make. The drip is a procrastination tactic, not a forecast.
- **If FNG ≥ 90 never occurs in some cycle, v5 == B0.** That is a feature, not a bug, but it must be said out loud: in a low-greed cycle (think 2022–2023's range), v5 collects no harvest and provides no drawdown protection beyond what B0 gives you. v5's benefit is concentrated at euphoric tops; everywhere else, it is the control.
- **As always, this is one cycle of in-sample tuning.** The threshold 90, the band 0.05, the drip 4 — all chosen with hindsight. The postmortem's experiment matrix is the only honest defense, and it is still a defense against a single sample.
