"""
postmortem_v7.py — diagnoses strategy_v7 (Fear-Gated Warchest) vs B0 / v6 / a null.

Per strategy_v7.md §"What success means", v7 carries an ADDED burden over v6: it
reintroduced a signal, so it must justify the complexity. The load-bearing test is
criterion 1 — v7 must beat the **no-signal null** (warchest deployed on a dumb
fixed clock) on {return OR drawdown} without losing the other. If it cannot, the
fear-gate is decoration, exactly v5's verdict reproduced on the buy side, and v7
should collapse back to v6 (or a slower v6).

Sections:
  1. Headline: v7-base vs B0
  2. Experiment matrix (threshold sweep, drip sweep, warchest-in-denominator,
     backstop-K, the key no-signal null, and the no-warchest=v6 ablation)
  3. The decisive comparison: v7-base vs v7-null-no-signal vs v6-base vs B0
  4. Cross-version sanity: v6-base reproduced read-only (the warchest is what moves
     the metrics vs v6, not a re-derivation of v6 itself)
  5. Regime breakdown (Up / Down / Sideways)
  6. Success-criteria checklist (5 bullets from spec)
  7. Bootstrap 95% CIs on (v7 - null) and (v7 - v6)

Outputs:
  - analysis/results/postmortem_report_v7.md
  - analysis/output/postmortem_attribution_v7.png
  - analysis/output/postmortem_warchest_v7.png
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
    load_fng_daily,
)
from analysis_v7 import (
    VERSION, TARGET_W, BAND, FNG_BUY_THR, DRIP_WEEKS,
    simulate_v7, trim_events, warchest_buy_events,
)
# Read-only reuse of the committed v6 script for the no-warchest ablation /
# cross-version rows. v6 with proceeds dripped straight back in IS the v7
# no-warchest ablation, so we run the real v6 rather than re-deriving it.
from analysis_v6 import simulate_v6


REPORT_MD     = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG    = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")
WARCHEST_PNG  = os.path.join(OUTPUT_DIR,  f"postmortem_warchest_v{VERSION}.png")


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
            row["n_trims"] = int(action_log["action"].astype(str).str.contains("trim").sum())
            if "deployed_usd" in action_log.columns:
                row["n_wc_buys"] = int((action_log["deployed_usd"] > 0).sum())
    return row


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly = load_btc_hourly()
    daily  = daily_closes(hourly)
    weekly = weekly_closes(hourly)
    weekly = weekly[(weekly.index >= START - pd.Timedelta(weeks=SMA_WEEKS + 4))
                    & (weekly.index <= END)]
    fng    = load_fng_daily()

    deposited = len(last_friday_deposit_dates(START, END)) * MONTHLY_DEPOSIT

    v7_df, v7_log = simulate_v7(daily, fng)
    b0_df         = simulate_control(daily)

    findings = []

    # ---- 1. Headline ----
    v7_dd = max_drawdown(v7_df["value"]) * 100
    b0_dd = max_drawdown(b0_df["value"]) * 100
    v7_sh, v7_so = sharpe_sortino(v7_df)
    b0_sh, b0_so = sharpe_sortino(b0_df)
    headline = pd.DataFrame([
        {"arm": "B0 deploy-on-arrival",
         "final_$": round(b0_df["value"].iloc[-1], 2),
         "return_%": round(b0_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(b0_dd, 2), "sharpe": round(b0_sh, 3), "sortino": round(b0_so, 3)},
        {"arm": "v7 Fear-Gated Warchest",
         "final_$": round(v7_df["value"].iloc[-1], 2),
         "return_%": round(v7_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(v7_dd, 2), "sharpe": round(v7_sh, 3), "sortino": round(v7_so, 3)},
    ])
    ret_gap_pp = (v7_df["value"].iloc[-1] / deposited * 100) - (b0_df["value"].iloc[-1] / deposited * 100)
    n_wc = int((v7_log["deployed_usd"] > 0).sum())
    findings.append(("1. Headline — v7 vs B0", [
        df_to_md(headline),
        "",
        f"DD shallower than B0 by:  {v7_dd - b0_dd:+.2f} pp",
        f"Return gap (v7 - B0):     {ret_gap_pp:+.2f} pp  (${v7_df['value'].iloc[-1] - b0_df['value'].iloc[-1]:+,.2f})",
        f"Sortino delta:            {v7_so - b0_so:+.3f}",
        f"Sharpe delta:             {v7_sh - b0_sh:+.3f}",
        f"Realized harvest to chest: ${v7_df.attrs['harvest_total']:,.2f}",
        f"Warchest balance at end:   ${v7_df['warchest'].iloc[-1]:,.2f}  (idle cash, 0% yield)",
        f"Peak warchest balance:     ${v7_df['warchest'].max():,.2f}",
        f"Fees paid:                ${v7_df.attrs['fee_total']:,.2f}  "
        f"({int(v7_log['action'].str.contains('trim').sum())} trims, {n_wc} warchest deploys)",
    ]))

    # ---- 2. Experiment matrix ----
    variants = [("v7-base", lambda: simulate_v7(daily, fng))]
    for thr in (15, 20, 25, 30):                                  # threshold sweep
        variants.append((f"v7-thr-{thr}",
                         (lambda t: (lambda: simulate_v7(daily, fng, fng_buy_threshold=t)))(thr)))
    for dw in (1, 4, 8):                                          # drip sweep
        variants.append((f"v7-drip-{dw}w",
                         (lambda d_: (lambda: simulate_v7(daily, fng, drip_weeks=d_)))(dw)))
    variants.append(("v7-warchest-in-denom",
                     lambda: simulate_v7(daily, fng, include_warchest_in_w=True)))
    for k in (13, 26):                                            # backstop-K
        variants.append((f"v7-backstop-{k}",
                         (lambda kk: (lambda: simulate_v7(daily, fng, backstop_k=kk)))(k)))
    variants.append(("v7-null-no-signal",
                     lambda: simulate_v7(daily, fng, null_no_signal=True, null_drip_weeks=12)))
    variants.append(("v7-no-warchest (=v6)", lambda: simulate_v6(daily)))

    matrix_rows = [_arm_row("B0", b0_df, deposited, b0_df)]
    cache = {"v7-base": (v7_df, v7_log)}
    for name, fn in variants:
        if name == "v7-base":
            df_v, log_v = v7_df, v7_log
        else:
            df_v, log_v = fn()
        cache[name] = (df_v, log_v)
        matrix_rows.append(_arm_row(name, df_v, deposited, b0_df, action_log=log_v))

    findings.append(("2. Experiment matrix (full window)", [
        df_to_md(pd.DataFrame(matrix_rows)),
        "",
        "_`v7-no-warchest (=v6)` is the committed v6 run (proceeds dripped straight",
        "back in) — the floor that isolates what the warchest itself does. The",
        "threshold sweep tests how deep fear must be to fire (lower = rarer, deeper",
        "buys, more idle cash); the drip sweep tests lump (1w) vs spread (8w) on a",
        "trigger. `warchest-in-denom` self-damps trims as the chest grows. The two",
        "rows that decide v7's fate are `v7-null-no-signal` and `v7-no-warchest`._",
    ]))

    # ---- 3. Decisive comparison ----
    null_df, null_log = cache["v7-null-no-signal"]
    v6_df,  v6_log    = cache["v7-no-warchest (=v6)"]
    decisive = pd.DataFrame([
        _arm_row("B0",                b0_df,   deposited, b0_df),
        _arm_row("v6-base (drip-in)", v6_df,   deposited, b0_df, action_log=v6_log),
        _arm_row("v7-null (dumb clock)", null_df, deposited, b0_df, action_log=null_log),
        _arm_row("v7-base (fear-gate)",  v7_df,   deposited, b0_df, action_log=v7_log),
    ])
    findings.append(("3. The decisive comparison — does the fear-gate earn its keep?", [
        df_to_md(decisive),
        "",
        "_Criterion 1 (load-bearing): v7-base must beat **v7-null** on {return OR",
        "drawdown} without losing the other. v7-null deploys the same warchest on a",
        "dumb 12-week clock with no FNG. If the fear-gate cannot dominate the dumb",
        "clock, the FNG signal is decoration — the same conclusion v5 reached on the",
        "sell side, reproduced on the buy side. Criterion 2: v7-base must at least",
        "match v6-base on risk-adjusted metrics, or the reintroduced surface area",
        "failed to pay for itself._",
    ]))

    # ---- 4. Cross-version sanity (v6 reproduced read-only) ----
    findings.append(("4. Cross-version note", [
        "_`v7-no-warchest (=v6)` above is the committed `simulate_v6` run verbatim",
        "(read-only import). It is both the v7 no-warchest ablation and the v6",
        "cross-version anchor: every metric there is identical to analysis_report_v6",
        "by construction, so the gap between it and v7-base is purely the warchest._",
    ]))

    # ---- 5. Regime breakdown ----
    regime_by_sunday = {}
    for i, ts in enumerate(weekly.index):
        r = regime_for_week(weekly, i)
        if r is not None:
            regime_by_sunday[ts.normalize()] = r
    sundays = sorted(regime_by_sunday.keys())
    def regime_for(d):
        prior = [s for s in sundays if s <= d.normalize()]
        return regime_by_sunday[prior[-1]] if prior else None
    merged = (v7_df[["date", "value"]].rename(columns={"value": "v7"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    merged = merged[(merged["v7"] > 0) & (merged["b0"] > 0)].copy()
    merged["v7_dr"] = merged["v7"].pct_change()
    merged["b0_dr"] = merged["b0"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v7_dr", "b0_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v7_daily_mean_%": round(grp["v7_dr"].mean() * 100, 4),
            "b0_daily_mean_%": round(grp["b0_dr"].mean() * 100, 4),
            "delta_pp":        round((grp["v7_dr"].mean() - grp["b0_dr"].mean()) * 100, 4),
        })
    findings.append(("5. Regime breakdown (Up / Down / Sideways)", [
        df_to_md(pd.DataFrame(reg_rows)),
        "",
        "_v7 sheds return in Up regimes (warchest drains BTC and parks the proceeds",
        "as idle cash that misses the up-leg) and is meant to claw it back by buying",
        "the Down/Sideways fear windows. Whether the claw-back covers the give-up is",
        "the whole question._",
    ]))

    # ---- 6. Success-criteria checklist (from strategy_v7.md) ----
    null_final = null_df["value"].iloc[-1]
    v7_final   = v7_df["value"].iloc[-1]
    null_dd    = max_drawdown(null_df["value"]) * 100
    v6_dd      = max_drawdown(v6_df["value"]) * 100
    v6_sh, v6_so = sharpe_sortino(v6_df)

    # crit 1: beat the null on {return OR drawdown} without losing the other.
    beats_ret = v7_final >= null_final - 1e-9
    beats_dd  = v7_dd    >= null_dd - 1e-9          # less-negative DD = shallower = better
    # "without losing the other": dominate on one and be no worse on the other.
    crit1 = (beats_ret and beats_dd) and (v7_final > null_final + 1e-9 or v7_dd > null_dd + 1e-9)

    # crit 2: at least match v6 on risk-adjusted (DD, Sortino, Sharpe).
    crit2 = (v7_dd >= v6_dd - 1e-9) and (v7_so >= v6_so - 1e-9) and (v7_sh >= v6_sh - 1e-9)

    # crit 3: inherited v6 bars vs B0.
    crit3_dd      = (v7_dd - b0_dd) >= 8.0
    crit3_sortino = (v7_so - b0_so) >= 0.3
    crit3_sharpe  = v7_sh >= b0_sh
    crit3 = crit3_dd and crit3_sortino and crit3_sharpe

    # crit 4: the return give-up is risk-justified iff 1-3 hold.
    crit4 = crit1 and crit2 and crit3

    # crit 5: threshold sweep legible (monotone-ish). Deeper fear -> rarer/deeper buys.
    thr_arms = [(t, cache[f"v7-thr-{t}"][0]) for t in (15, 20, 25, 30)]
    thr_rets = [(d["value"].iloc[-1] / deposited - 1) * 100 for _, d in thr_arms]
    thr_dds  = [max_drawdown(d["value"]) * 100 for _, d in thr_arms]
    # legibility: no interior point should dominate BOTH endpoints on return and DD.
    interior_dominates = False
    for i in range(1, len(thr_arms) - 1):
        if thr_rets[i] >= max(thr_rets[0], thr_rets[-1]) and thr_dds[i] >= max(thr_dds[0], thr_dds[-1]):
            interior_dominates = True
    crit5 = not interior_dominates

    crit = [
        ("1. Beats v7-null on {return OR DD} without losing the other (LOAD-BEARING)",
         crit1,
         f"v7 final ${v7_final:,.0f} vs null ${null_final:,.0f} (Δ${v7_final-null_final:+,.0f}); "
         f"v7 DD {v7_dd:.2f}% vs null {null_dd:.2f}% (Δ{v7_dd-null_dd:+.2f}pp)"),
        ("2. At least matches v6-base on risk-adjusted (DD, Sortino, Sharpe)",
         crit2,
         f"DD {v7_dd:.2f} vs v6 {v6_dd:.2f}; Sortino {v7_so:.3f} vs {v6_so:.3f}; "
         f"Sharpe {v7_sh:.3f} vs {v6_sh:.3f}"),
        ("3. DD ≥ 8pp shallower than B0; Sortino ≥ B0+0.3; Sharpe ≥ B0",
         crit3,
         f"DD Δ{v7_dd-b0_dd:+.2f}pp ({'ok' if crit3_dd else 'miss'}); "
         f"Sortino Δ{v7_so-b0_so:+.3f} ({'ok' if crit3_sortino else 'miss'}); "
         f"Sharpe Δ{v7_sh-b0_sh:+.3f} ({'ok' if crit3_sharpe else 'miss'})"),
        ("4. Return give-up risk-justified (accepted cost; holds iff 1-3 all pass)",
         crit4,
         f"give-up {ret_gap_pp:+.2f}pp vs B0 — {'covered by 1-3' if crit4 else 'NOT covered: 1-3 not all met'}"),
        ("5. fng_buy_threshold sweep legible (no interior point dominates both ends)",
         crit5,
         f"returns {[round(x,1) for x in thr_rets]} / DDs {[round(x,1) for x in thr_dds]} "
         f"(thr 15→30); interior_dominates={interior_dominates}"),
    ]
    crit_lines = [f"- **[{'PASS' if ok else 'FAIL'}]** {label}  —  {detail}" for label, ok, detail in crit]
    crit_lines += [
        "",
        "_Criterion 1 is the test v7 most needs to pass. If it fails, sentiment does",
        "not help on the buy side either, and the honest conclusion — symmetric with",
        "v5 — is that the FNG signal is decoration on both sides of the trade, and v7",
        "should collapse back to v6 (or a slower-drip v6)._",
    ]
    findings.append(("6. Success-criteria checklist (from strategy_v7.md)", crit_lines))

    # ---- 7. Bootstrap CIs ----
    def weekly_rets(df):
        return df.set_index("date")["value"].resample("W").last().pct_change()
    v7_w, null_w, v6_w = weekly_rets(v7_df), weekly_rets(null_df), weekly_rets(v6_df)
    a1 = pd.concat([v7_w.rename("v7"), null_w.rename("null")], axis=1).dropna()
    a2 = pd.concat([v7_w.rename("v7"), v6_w.rename("v6")], axis=1).dropna()
    m1, lo1, hi1 = boot_ci((a1["v7"] - a1["null"]).values)
    m2, lo2, hi2 = boot_ci((a2["v7"] - a2["v6"]).values)
    findings.append(("7. Bootstrap 95% CIs (n=2000)", [
        f"Mean weekly return delta (v7 - null):  {m1*100:+.4f}%  [{lo1*100:+.4f}%, {hi1*100:+.4f}%]",
        f"Mean weekly return delta (v7 - v6):    {m2*100:+.4f}%  [{lo2*100:+.4f}%, {hi2*100:+.4f}%]",
        "",
        "_CIs that straddle zero mean the fear-gate's weekly edge over the dumb clock",
        "(and over v6) is not statistically distinguishable from noise on ~120 weekly",
        "observations — expected given only ~2 fear episodes drive the buy side._",
    ]))

    # ---- Write report ----
    overall_pass = crit1 and crit2
    verdict = ("MET (1-2): the buy-side gate earns its keep" if overall_pass
               else "NOT MET: criterion 1 and/or 2 failed — see checklist")
    md = [f"# Postmortem — strategy_v{VERSION} (Fear-Gated Warchest)", "",
          f"_Window: {START.date()} → {END.date()}_", "",
          f"**Headline verdict: {verdict}.**", "",
          "_Single-cycle in-sample fit, and worse than usual here: the buy-gate only",
          "acts in extreme-fear windows, of which there are ~2 in this sample. Read the",
          "threshold sweep as the shape of a thin bet, not as robust edge._", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plots ----
    # Warchest balance + deploy markers
    fig, ax = plt.subplots(figsize=(12, 4))
    wc = v7_df.set_index("date")["warchest"]
    ax.fill_between(wc.index.values, wc.values, color="tab:orange", alpha=0.45,
                    label="warchest balance")
    buys = warchest_buy_events(v7_log)
    if len(buys):
        bd = pd.to_datetime(buys["date"]).values
        ax.scatter(bd, [0] * len(bd), marker="^", color="tab:green", s=18,
                   zorder=5, label="warchest deploy (fear day)")
    ax.set_title("v7 warchest — fills continuously from trims, drains only in FNG ≤ 25 windows")
    ax.set_ylabel("USD"); ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(WARCHEST_PNG, dpi=120); plt.close()
    print(f"Saved {WARCHEST_PNG}")

    # attribution 2x2
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(v7_df["date"].values, v7_df["value"].values, label="v7", linewidth=1.3)
    ax.plot(null_df["date"].values, null_df["value"].values, label="v7-null", linewidth=1.1)
    ax.plot(v6_df["date"].values, v6_df["value"].values, label="v6", linewidth=1.1)
    ax.plot(b0_df["date"].values, b0_df["value"].values, label="B0", linewidth=1.3)
    ax.set_title("v7 vs v7-null vs v6 vs B0 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.fill_between(wc.index.values, wc.values, color="tab:orange", alpha=0.5)
    ax.set_title("Idle warchest balance over time (USD)"); ax.grid(alpha=0.3)

    ax = axes[1, 0]
    v7_ww = v7_df.set_index("date")["value"].resample("W").last()
    null_ww = null_df.set_index("date")["value"].resample("W").last()
    gap = (v7_ww - null_ww).dropna()
    ax.plot(gap.index.values, gap.values, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("Weekly value gap (v7 - null) — does the fear-gate add anything?"); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df)); width = 0.35
        ax.bar(x - width/2, reg_df["v7_daily_mean_%"], width, label="v7")
        ax.bar(x + width/2, reg_df["b0_daily_mean_%"], width, label="B0")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(ATTRIB_PNG, dpi=120); plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
