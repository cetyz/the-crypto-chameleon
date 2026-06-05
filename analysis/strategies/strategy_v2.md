# BTC Weekly Strategy — v2 "Tilt"

## What changed from v1, and why

v1's backtest was a clean negative result. The diagnostic wasn't the headline ($445 over DCA); it was the counterfactual table, where **every ablation beat the assembled strategy** and a brain-dead "deploy 100% every week" baseline beat it by ~10 points. The damage localized to two places:

1. **Hold-to-cash and Sell cells.** No-sell and less-Hold variants both outperformed live. In a positive-drift asset, sitting out forfeits drift the weak signals couldn't earn back.
2. **The Up+Hot cell specifically.** v1 held there to "not chase euphoria." That cell was followed by **+22% over 12 weeks** — the euphoria was the rally. Refusing to participate was the single most expensive decision in the policy.

v2 keeps v1's two signals but changes how they're *used*. The governing rule:

> **Always deploy something. Never go to cash on a signal. Never sell as a directional bet.** The only thing a signal is allowed to do is change *how much* you deploy this week.

This strips out exactly the machinery that bled return and keeps only the part the data supported (the Buy cells, especially Up-trend cells, had genuinely strong forward returns).

## The honest tension this design carries

"Always buy, but sometimes buy more" is not free. To buy *more* on a good week you must have held *something back* on prior weeks — and held-back cash is drag. There is no version of size-tilting that avoids this short of leverage (out of scope). So v2 maintains a **bounded reserve** as working capital, and accepts the resulting drag.

That makes the entire experiment precise:

> **v2 wins only if concentrating deployment into high-signal weeks out-earns the drag cost of the cash it holds back.** Given that trend is weakly predictive and funding tested at ~zero correlation, this is a real bar, not a formality. Expect a small effect at best.

## Signals (inherited from v1, unchanged)

- **Trend:** weekly close vs 20-week SMA → `Up` / `Down`.
- **Funding:** 8h Binance perp funding, trailing-7d avg, annualized, bucketed `Hot`/`Neutral`/`Cold` by rolling 26-week 80/20 percentiles.

**Signal weighting is not symmetric.** Trend is the dominant axis: in v1's postmortem, Up-weeks' forward-1w return CI excluded zero ([+0.38%, +2.72%]) while Down straddled it, and trend-only was one of the stronger ablations. Funding is on probation: corr(funding, fwd_1w) = −0.05, i.e. no measured predictive power, and what little directionality existed ran *opposite* to v1's contrarian assumption. So in v2, **trend sets the base deployment fraction; funding only nudges it.**

## Action space

v1's discrete actions (Buy100 / Buy50 / Hold / Sell50) are replaced by a single continuous lever: a deployment fraction **f**, the share of the current reserve to deploy into BTC this week.

| | |
|---|---|
| Floor | f is never 0 — every week deploys something |
| Ceiling | f = 1.0 deploys the entire reserve |
| No sell | BTC is never reduced on a signal |

## Mechanics (per week)

```
reserve += weekly_deposit            # contribute first
f       = base_f[trend] + funding_nudge[funding]   # clamp to [F_MIN, 1.0]
deploy  = f * reserve
buy(deploy)                          # 0.1% fee
reserve -= deploy

# reserve is bounded working capital, not a hoard:
if reserve > RESERVE_CAP * portfolio_value:
    force-deploy the excess this week   # prevents indefinite hoarding
```

`F_MIN` (e.g. 0.4) guarantees the floor; `RESERVE_CAP` (e.g. 0.25) prevents the reserve from quietly becoming a permanent USD position and re-creating v1's cash-drag problem by the back door.

## Deployment table

Base fraction from trend, nudged by funding. Note this directly fixes the Up+Hot error — that cell now deploys a healthy chunk instead of holding.

| Trend | base_f | Funding | nudge | final f | vs v1 |
|---|---|---|---|---|---|
| Up | 0.85 | Cold | +0.15 | 1.00 | was Buy100 ✓ |
| Up | 0.85 | Neutral | 0.00 | 0.85 | was Buy50 (more aggressive) |
| Up | 0.85 | Hot | −0.15 | 0.70 | **was Hold — now deploys (fixes the +22% miss)** |
| Down | 0.50 | Cold | +0.15 | 0.65 | was Buy50 ✓ |
| Down | 0.50 | Neutral | 0.00 | 0.50 | was Hold — now deploys |
| Down | 0.50 | Hot | −0.10 | 0.40 | **was Sell50 — now buys least, but still buys** |

The funding nudge is deliberately small (±0.10–0.15) and **flagged for ablation** — see experiment matrix. If removing it doesn't hurt (likely, given corr≈0), funding gets dropped in v2.1.

## Benchmarks — the bar is NOT just DCA

Report against all three, in this order of importance:

| Benchmark | What it is | Why it matters |
|---|---|---|
| **B0 — Deploy-on-arrival** | Deploy 100% of each deposit the week it lands; zero reserve, zero drag | **The real bar.** This is "do nothing clever." v2 must beat this or the tilt adds nothing and you should just deploy everything immediately. |
| B1 — Flat weekly DCA | Fixed $X every week | The familiar comparison. With weekly deposits, B1 ≈ B0. |
| B2 — v1 strategy | The original | Sanity check that v2 actually repaired the damage |

If v2 beats B1 but loses to B0, that is **not** a win — it means the tilt is worse than the trivial baseline and only "beat DCA" via cadence artifacts. Surface B0 prominently.

## Experiment matrix (ablations to run on the v2 base)

These are knob-flips on one strategy, run as a sweep — not separate strategies.

| Variant | Change | Hypothesis / what it tests |
|---|---|---|
| **v2-base** | as specified | does signal-concentration beat drag? |
| **v2-trend-only** | drop funding nudge entirely | is funding adding anything, or is it dead weight? (expected: no loss) |
| **v2-flip-funding** | reverse the funding nudge (Hot → +, Cold → −) | your idea. Tests the postmortem hint that funding ran backwards. **Honest expectation: near-zero effect.** corr is −0.05 and the Hot/Cold forward-return CIs overlap heavily, so this is noise. If flipped-funding *meaningfully* beats base, treat that as a red flag for one-cycle overfitting, not a discovery. |
| **v2-reserve-sweep** | RESERVE_CAP ∈ {0.10, 0.25, 0.40} | how much does the drag/concentration tradeoff move with reserve size? |
| **v2-floor-sweep** | F_MIN ∈ {0.25, 0.40, 0.60} | how much "always-in" is optimal vs how much flex |

## Metrics (carry forward from v1, plus)

Total value vs each benchmark; max drawdown; Sharpe **and Sortino** (v1's win condition was risk-adjusted — track it); time-in-market %; n_trades; **avg reserve fraction** (the drag you're paying); confidence intervals on the edge (sample is one cycle, ~320 weeks — point estimates are noisy, show it).

## Implementation notes (close v1's loose ends)

1. **Apples-to-apples.** All arms get identical capital on identical timing; the signal is the *only* variable. v1's backtest mixed monthly deposits with $10/Tue DCA spend — that cadence mismatch alone could manufacture the gap. Fix before drawing conclusions.
2. **No look-ahead.** Signal on weekly close, execute same close, 0.1% fee.
3. **Warmup.** During the 20-week SMA + 26-week funding warmup, deploy-on-arrival (mirror B0) so early-period comparison is clean.

## Caveats carried forward

- One BTC cycle of usable data. "Trend works" is hard to separate from "the asset went up." Don't over-fit the deployment fractions to this window.
- The funding signal showed no edge in v1. v2 keeps it on a short leash; be ready to drop it.
- Even a clean v2 win over B0 is likely small. The realistic outcome is "comparable to deploy-on-arrival with slightly different risk profile," which is itself a useful, honest result for the dashboard.