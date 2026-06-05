"""
postmortem_v8.py — diagnoses strategy_v8 (Funded Basket) vs v6 and B0.

Per strategy_v8.md §"What success means": v8 is a frontier choice judged on
risk-adjusted edge, with TWO added burdens over v6 — it must justify a *permanent*
funded cash drag, and it must show the dip-buying earns its keep. The two
load-bearing rows are:
  - v8-one-way (does buying dips help, or is the funded cash pure drag?), and
  - the cross-version row (does the permanent cash drag pay for itself vs v6?).

Sections:
  1. Headline: v8-base vs B0
  2. Experiment matrix (target sweep, band sweep, vol-band variant,
     one-way ablation, monthly-cadence variant)
  3. Cross-version: v8-base vs v6-base vs B0 (the decisive comparison;
     re-runs committed v6 code read-only)
  4. Regime breakdown (Up / Down / Sideways)
  5. Success criteria checklist (7 bullets from the spec)
  6. Bootstrap 95% CIs on (v8 - B0) return and value gap

Outputs:
  - analysis/results/postmortem_report_v8.md
  - analysis/output/postmortem_weights_v8.png
  - analysis/output/postmortem_attribution_v8.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, SMA_WEEKS,
    load_btc_hourly, weekly_closes, daily_closes,
    trend_state,
    last_friday_deposit_dates, simulate_control,
    max_drawdown, sharpe_sortino, boot_ci, df_to_md,
)
from analysis_v8 import (
    VERSION, TARGET_W, BAND,
    simulate_v8,
)
# Read-only reuse of the committed v6 script for the cross-version row only.
from analysis_v6 import simulate_v6


REPORT_MD   = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG  = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")
WEIGHTS_PNG = os.path.join(OUTPUT_DIR,  f"postmortem_weights_v{VERSION}.png")


def regime_for_week(weekly_px, i):
    t = trend_state(weekly_px, i)
    if t is None:
        return None
    sma = weekly_px.iloc[i - SMA_WEEKS + 1:i + 1].mean()
    if sma == 0:
        return t
    dev = weekly_px.iloc[i] / sma - 1
    if abs(dev) < 0.05:
        return "Sideways"
    return t


def _arm_row(name, df, deposited, b0_df, action_log=None):
    final = df["value"].iloc[-1]
    sh, so = sharpe_sortino(df)
    dd     = max_drawdown(df["value"])
    b0_dd  = max_drawdown(b0_df["value"])
    row = {
        "arm": name,
        "final_$":      round(final, 2),
        "return_%":     round((final / deposited - 1) * 100, 2),
        "max_dd_%":     round(dd * 100, 2),
        "sortino":      round(so, 3),
        "sharpe":       round(sh, 3),
        "dd_vs_B0_pp":  round((dd - b0_dd) * 100, 2),
        "ret_vs_B0_$":  round(final - b0_df["value"].iloc[-1], 2),
    }
    if action_log is not None and len(action_log):
        if "action" in action_log.columns:
            act = action_log["action"].astype(str)
            # one-way logs a compound "buy+sell" when a deposit-deploy and a trim
            # land on the same Tuesday; count each side via substring.
            row["n_sell"] = int(act.str.contains("sell").sum())
            row["n_buy"]  = int(act.str.contains("buy").sum())
            # v6 logs trims under "trim"; surface them in the n_sell column
            n_trim = int((act == "trim").sum())
            if n_trim:
                row["n_sell"] = n_trim
                row["n_buy"]  = 0
    return row


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly = load_btc_hourly()
    daily  = daily_closes(hourly)
    weekly = weekly_closes(hourly)
    weekly = weekly[(weekly.index >= START - pd.Timedelta(weeks=SMA_WEEKS + 4))
                    & (weekly.index <= END)]

    deposited = len(last_friday_deposit_dates(START, END)) * MONTHLY_DEPOSIT

    v8_df, v8_log = simulate_v8(daily)
    b0_df         = simulate_control(daily)

    findings = []

    # ---- 1. Headline ----
    v8_dd = max_drawdown(v8_df["value"]) * 100
    b0_dd = max_drawdown(b0_df["value"]) * 100
    v8_sh, v8_so = sharpe_sortino(v8_df)
    b0_sh, b0_so = sharpe_sortino(b0_df)
    headline = pd.DataFrame([
        {"arm": "B0 deploy-on-arrival",
         "final_$": round(b0_df["value"].iloc[-1], 2),
         "return_%": round(b0_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(b0_dd, 2), "sharpe": round(b0_sh, 3), "sortino": round(b0_so, 3)},
        {"arm": "v8 Funded Basket",
         "final_$": round(v8_df["value"].iloc[-1], 2),
         "return_%": round(v8_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(v8_dd, 2), "sharpe": round(v8_sh, 3), "sortino": round(v8_so, 3)},
    ])
    ret_gap_pp = (v8_df["value"].iloc[-1] / deposited * 100) - (b0_df["value"].iloc[-1] / deposited * 100)
    n_sell = int((v8_log["action"] == "sell").sum())
    n_buy  = int((v8_log["action"] == "buy").sum())
    findings.append(("1. Headline — v8 vs B0", [
        df_to_md(headline),
        "",
        f"DD shallower than B0 by:  {v8_dd - b0_dd:+.2f} pp",
        f"Return gap (v8 - B0):     {ret_gap_pp:+.2f} pp  (${v8_df['value'].iloc[-1] - b0_df['value'].iloc[-1]:+,.2f})",
        f"Sortino delta:            {v8_so - b0_so:+.3f}",
        f"Sharpe delta:             {v8_sh - b0_sh:+.3f}",
        f"Trades:                   {n_sell} sells, {n_buy} buys  (gross buy ${v8_df.attrs['buy_total']:,.2f}, sell ${v8_df.attrs['sell_total']:,.2f})",
        f"Fees paid:                ${v8_df.attrs['fee_total']:,.2f}",
        "",
        "_With only ~10% cash and a ±3% *weight* band, breaching the upper edge takes",
        "a very large up-week, so v8-base sells rarely (one sell over the whole window).",
        "The buy side fires far more often, but for two different reasons across the",
        "sample. While the book is tiny (2020-21) a single $50 deposit is a large",
        "fraction of the portfolio and trips the lower band on its own. Once the book is",
        "multi-thousand-dollar (2024+), a $50 deposit can no longer breach ±3% alone and",
        "pools as cash exactly as the spec says — so the later buys are not deposit-",
        "driven but crash-driven: the cash sleeve deployed into sharp declines._",
    ]))

    # ---- 2. Experiment matrix ----
    variants = [("v8-base (t0.90 b0.03)", {})]
    for tw in (0.80, 0.85, 0.90, 0.95):                  # target sweep — the menu
        variants.append((f"v8-target-{int(tw*100)}", {"target_w": tw}))
    for b in (0.0, 0.02, 0.03, 0.05):                    # band sweep
        variants.append((f"v8-band-{int(b*100):02d}", {"band": b}))
    variants.append(("v8-vol-band (variant)", {"vol_scaled": True}))
    variants.append(("v8-one-way (ablation)", {"two_way": False}))
    variants.append(("v8-cadence-monthly (variant)", {"cadence": "monthly"}))

    matrix_rows = [_arm_row("B0", b0_df, deposited, b0_df)]
    cache = {}
    for name, kw in variants:
        if name == "v8-base (t0.90 b0.03)":
            df_v, log_v = v8_df, v8_log
        else:
            df_v, log_v = simulate_v8(daily, **kw)
        cache[name] = (df_v, log_v)
        matrix_rows.append(_arm_row(name, df_v, deposited, b0_df, action_log=log_v))

    findings.append(("2. Experiment matrix (full window)", [
        df_to_md(pd.DataFrame(matrix_rows)),
        "",
        "_The target sweep is the menu — lower `target_w` = bigger funded buffer, more",
        "drag, more dip-buying ammunition; it is a preference, not a prediction. The",
        "band sweep trades trade-frequency against tracking: `band=0` snaps to target",
        "every Tuesday (v6-like frequency); wider = fewer, larger rebalances. The",
        "vol-band variant must BEAT the best static band to justify its extra knobs",
        "(criterion 7). The one-way ablation is the load-bearing test of whether",
        "dip-buying earns its keep (criterion 4)._",
        "",
        "**Note on the one-way ablation — it is not a clean flag-flip.** v8 is funded",
        "100% by DCA deposits and has no deposit-deploy step, so the position is",
        "bootstrapped entirely through the buy branch: a deposit arrives as cash, weight",
        "drops below target, and the buy branch is the *only* thing that ever acquires",
        "BTC. Deposit-deployment and dip-buying are the **same operation**. Taken",
        "literally, 'never buy when under' leaves the portfolio permanently all-cash",
        "(return 0). To make a *meaningful* one-way arm — the spec's own 'v6 with a",
        "funded sleeve and no drip' — we had to reintroduce the B0 deposit-deploy spine",
        "v8 removed: deploy deposits unconditionally, sell-only on over-weight, hold",
        "proceeds as a non-redeployed sleeve. **The consequence is conceptual, not",
        "numerical: 'one rule' can only express the TWO-way basket. Isolating the buy",
        "half forces v8 back into a v6-shaped object, so criterion 4 (two-way vs",
        "one-way) is essentially the same question as criterion 3 (v8 vs v6).** Read",
        "the two together._",
    ]))

    # ---- 3. Cross-version: v8-base vs v6-base vs B0 ----
    v6_df, v6_log = simulate_v6(daily)   # committed v6 code, read-only
    xrows = [
        _arm_row("B0",      b0_df, deposited, b0_df),
        _arm_row("v6-base", v6_df, deposited, b0_df, action_log=v6_log),
        _arm_row("v8-base", v8_df, deposited, b0_df, action_log=v8_log),
    ]
    findings.append(("3. Cross-version — v8-base vs v6-base vs B0 (the decisive row)", [
        df_to_md(pd.DataFrame(xrows)),
        "",
        "_This is the row that justifies v8's existence over its predecessor. If the",
        "funded two-way basket can't beat the transient one-way trimmer (v6) on",
        "{risk-adjusted OR drawdown} without losing the other, the permanent cash drag",
        "wasn't worth paying and v6 stands (criterion 3). `n_sell` for v6 counts trims._",
    ]))

    # ---- 4. Regime breakdown ----
    regime_by_sunday = {}
    for i, ts in enumerate(weekly.index):
        r = regime_for_week(weekly, i)
        if r is not None:
            regime_by_sunday[ts.normalize()] = r
    sundays = sorted(regime_by_sunday.keys())
    def regime_for(d):
        prior = [s for s in sundays if s <= d.normalize()]
        return regime_by_sunday[prior[-1]] if prior else None
    merged = (v8_df[["date", "value"]].rename(columns={"value": "v8"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    merged = merged[(merged["v8"] > 0) & (merged["b0"] > 0)].copy()
    merged["v8_dr"] = merged["v8"].pct_change()
    merged["b0_dr"] = merged["b0"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v8_dr", "b0_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v8_daily_mean_%": round(grp["v8_dr"].mean() * 100, 4),
            "b0_daily_mean_%": round(grp["b0_dr"].mean() * 100, 4),
            "delta_pp":        round((grp["v8_dr"].mean() - grp["b0_dr"].mean()) * 100, 4),
        })
    findings.append(("4. Regime breakdown (Up / Down / Sideways)", [
        df_to_md(pd.DataFrame(reg_rows)),
        "",
        "_The rebalancing bonus (buy-low/sell-high) should show up as a positive delta",
        "in Down/Sideways; the cash drag and early-selling show up as a negative delta",
        "in Up. Over one mostly-up cycle the Up weeks dominate the headline._",
    ]))

    # ---- 5. Success criteria checklist (from strategy_v8.md) ----
    v8_ret_pp = (v8_df["value"].iloc[-1] / deposited - 1) * 100
    b0_ret_pp = (b0_df["value"].iloc[-1] / deposited - 1) * 100
    v6_dd = max_drawdown(v6_df["value"]) * 100
    v6_sh, v6_so = sharpe_sortino(v6_df)

    # crit 1: Sortino >= B0+0.3 AND Sharpe >= B0
    sortino_ok = (v8_so - b0_so) >= 0.3
    sharpe_ok  = v8_sh >= b0_sh
    risk_adj_ok = sortino_ok and sharpe_ok
    # crit 2: max DD not worse than B0 (v8_dd less negative => shallower)
    dd_ok = v8_dd >= b0_dd
    # crit 3: beats v6-base on {risk-adj OR drawdown} without losing the other
    beats_v6_riskadj = (v8_so >= v6_so) and (v8_sh >= v6_sh)
    beats_v6_dd      = v8_dd >= v6_dd
    not_worse_riskadj = (v8_so >= v6_so - 1e-9) and (v8_sh >= v6_sh - 1e-9)
    not_worse_dd      = v8_dd >= v6_dd - 1e-9
    beats_v6 = (beats_v6_riskadj and not_worse_dd) or (beats_v6_dd and not_worse_riskadj)
    # crit 4: two-way beats one-way (risk-adjusted)
    ow_df, ow_log = cache["v8-one-way (ablation)"]
    ow_sh, ow_so = sharpe_sortino(ow_df)
    ow_dd = max_drawdown(ow_df["value"]) * 100
    twoway_beats_oneway = (v8_so >= ow_so) and (v8_sh >= ow_sh)
    # crit 5: return give-up risk-justified (accepted cost iff crit 1-2 hold)
    risk_justified = risk_adj_ok and dd_ok
    # crit 6: target_w sweep monotone-ish and legible
    tsweep = [(tw, cache[f"v8-target-{int(tw*100)}"][0]) for tw in (0.80, 0.85, 0.90, 0.95)]
    rets = [(d["value"].iloc[-1] / deposited - 1) * 100 for _, d in tsweep]
    dds  = [max_drawdown(d["value"]) * 100 for _, d in tsweep]
    ret_monotone = all(rets[i] <= rets[i+1] + 1e-6 for i in range(len(rets)-1))   # ↑ target → ↑ return
    dd_monotone  = all(dds[i]  >= dds[i+1]  - 1e-6 for i in range(len(dds)-1))    # ↑ target → deeper DD
    interior_dominates = False
    for i in range(1, len(tsweep) - 1):
        if rets[i] >= max(rets[0], rets[-1]) and dds[i] >= max(dds[0], dds[-1]):
            interior_dominates = True
    legible = (ret_monotone and dd_monotone) and not interior_dominates
    # crit 7: vol-band must BEAT the best static band (risk-adjusted), else drop it
    static_bands = {f"v8-band-{int(b*100):02d}": b for b in (0.0, 0.02, 0.03, 0.05)}
    best_static_name, best_static_so = None, -np.inf
    for nm in static_bands:
        _, _so = sharpe_sortino(cache[nm][0])
        if _so > best_static_so:
            best_static_so, best_static_name = _so, nm
    vb_df, _ = cache["v8-vol-band (variant)"]
    vb_sh, vb_so = sharpe_sortino(vb_df)
    bs_sh, bs_so = sharpe_sortino(cache[best_static_name][0])
    volband_beats = (vb_so > bs_so) and (vb_sh >= bs_sh)

    crit = [
        ("1. Sortino ≥ B0 + 0.3 AND Sharpe ≥ B0", risk_adj_ok,
            f"Sortino {v8_so - b0_so:+.3f} (B0 {b0_so:.3f}, v8 {v8_so:.3f}); "
            f"Sharpe {v8_sh - b0_sh:+.3f} (B0 {b0_sh:.3f}, v8 {v8_sh:.3f})"),
        ("2. Max DD not worse than B0", dd_ok,
            f"v8 {v8_dd:.2f}% vs B0 {b0_dd:.2f}%  ({v8_dd - b0_dd:+.2f} pp)"),
        ("3. Beats v6-base on {risk-adj OR drawdown} without losing the other", beats_v6,
            f"v8 vs v6: Sortino {v8_so - v6_so:+.3f}, Sharpe {v8_sh - v6_sh:+.3f}, "
            f"DD {v8_dd - v6_dd:+.2f} pp (v6 DD {v6_dd:.2f}%)"),
        ("4. Two-way beats v8-one-way (dip-buying earns its keep; one-way = v6-shaped, "
         "deposit-deploy spine + sell-only — see §2 note)", twoway_beats_oneway,
            f"two-way Sortino {v8_so:.3f}/Sharpe {v8_sh:.3f} vs one-way "
            f"{ow_so:.3f}/{ow_sh:.3f} (one-way return {(ow_df['value'].iloc[-1]/deposited-1)*100:.2f}%, DD {ow_dd:.2f}%)"),
        ("5. Return give-up is risk-justified (accepted cost; fails only if 1-2 miss)",
            risk_justified,
            f"give-up {v8_ret_pp - b0_ret_pp:+.2f} pp — "
            f"{'risk-justified by 1-2' if risk_justified else 'NOT covered: 1-2 not both met'}"),
        ("6. target_w sweep monotone-ish and legible", legible,
            f"returns {[round(float(x),1) for x in rets]} / DDs {[round(float(x),1) for x in dds]} "
            f"(target 0.80→0.95); interior_dominates={interior_dominates}"),
        (f"7. If kept, vol-band beats best static band ({best_static_name})", volband_beats,
            f"vol-band Sortino {vb_so:.3f}/Sharpe {vb_sh:.3f} vs best static "
            f"{bs_so:.3f}/{bs_sh:.3f} — {'beats it, keep' if volband_beats else 'does not beat it, DROP the variant'}"),
    ]
    crit_lines = []
    for label, ok, detail in crit:
        crit_lines.append(f"- **[{'PASS' if ok else 'FAIL'}]** {label}  —  {detail}")
    crit_lines += [
        "",
        "_Load-bearing rows: **criterion 4** (does buying dips help?) and **criterion 3**",
        "(does the permanent cash drag pay for itself vs v6?). If 1, 3, and 4 hold, v8 is",
        "both simpler and better than v6 and becomes the lineage's main line. If 3 fails,",
        "v8's cleanliness isn't worth its drag and v6 stands. If 4 fails, the basket",
        "should be one-way and you've rederived v6-without-drip._",
    ]
    findings.append(("5. Success criteria checklist (from strategy_v8.md)", crit_lines))

    # ---- 6. Bootstrap CIs ----
    v8_w = v8_df.set_index("date")["value"].resample("W").last()
    b0_w = b0_df.set_index("date")["value"].resample("W").last()
    aligned = pd.concat([v8_w.pct_change().rename("v8"),
                         b0_w.pct_change().rename("b0")], axis=1).dropna()
    diff_ret = (aligned["v8"] - aligned["b0"]).values
    d_mean, d_lo, d_hi = boot_ci(diff_ret)
    gap = (v8_w - b0_w).dropna().values
    g_mean, g_lo, g_hi = boot_ci(gap)
    findings.append(("6. Bootstrap 95% CIs (n=2000)", [
        f"Mean weekly return delta (v8 - B0):  {d_mean*100:+.4f}%  [{d_lo*100:+.4f}%, {d_hi*100:+.4f}%]",
        f"Mean weekly value gap (v8 - B0):     ${g_mean:+,.2f}  [{g_lo:+,.2f}, {g_hi:+,.2f}]",
    ]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Funded Basket)", "",
          f"_Window: {START.date()} → {END.date()}_", "",
          "_Single-cycle in-sample fit (~120 weekly obs). The dip-buying half is",
          "exercised in essentially two declines (2020, 2022) — its measured benefit",
          "rests on very few events. The target_w sweep traces the return/drawdown",
          "frontier — the *shape* of a preference, not robust edge._", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plots ----
    log_dates  = pd.to_datetime(v8_log["date"]).values
    buy_log    = v8_log[v8_log["action"] == "buy"]
    sell_log   = v8_log[v8_log["action"] == "sell"]
    buy_dates  = pd.to_datetime(buy_log["date"]).values
    sell_dates = pd.to_datetime(sell_log["date"]).values

    # weights plot — weight after rebalance, with the two-sided band
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(log_dates, v8_log["btc_weight_after"].values, linewidth=1.0, color="tab:gray",
            label="BTC weight (post-rebalance)")
    ax.axhline(TARGET_W, color="black", linewidth=0.8, label=f"target={TARGET_W}")
    ax.axhline(TARGET_W + BAND, color="red", linewidth=0.6, linestyle="--",
               label=f"band (±{BAND})")
    ax.axhline(TARGET_W - BAND, color="red", linewidth=0.6, linestyle="--")
    if len(sell_dates):
        ax.scatter(sell_dates, [TARGET_W + BAND] * len(sell_dates),
                   marker="v", color="red", s=18, label="sell fired", zorder=5)
    if len(buy_dates):
        ax.scatter(buy_dates, [TARGET_W - BAND] * len(buy_dates),
                   marker="^", color="green", s=12, label="buy fired", zorder=5)
    ax.set_title("v8 BTC weight (post-rebalance) — two-sided band; buys dominate, sells are rare")
    ax.legend(fontsize=8, ncol=2); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(WEIGHTS_PNG, dpi=120); plt.close()
    print(f"Saved {WEIGHTS_PNG}")

    # attribution 2x2
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(v8_df["date"].values, v8_df["value"].values, label="v8", linewidth=1.3)
    ax.plot(v6_df["date"].values, v6_df["value"].values, label="v6", linewidth=1.1)
    ax.plot(b0_df["date"].values, b0_df["value"].values, label="B0", linewidth=1.3)
    ax.set_title("v8 vs v6 vs B0 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.plot(v8_df["date"].values, v8_df["cash"].values, color="tab:green", linewidth=1.0)
    ax.set_title("v8 standing cash sleeve over time (USD) — the permanent drag")
    ax.grid(alpha=0.3)

    ax = axes[1, 0]
    weekly_gap = (v8_w - b0_w).dropna()
    ax.plot(weekly_gap.index.values, weekly_gap.values, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("Weekly value gap (v8 - B0)"); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df))
        width = 0.35
        ax.bar(x - width/2, reg_df["v8_daily_mean_%"], width, label="v8")
        ax.bar(x + width/2, reg_df["b0_daily_mean_%"], width, label="B0")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout(); plt.savefig(ATTRIB_PNG, dpi=120); plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
