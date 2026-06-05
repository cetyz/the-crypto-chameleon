"""
postmortem_v5.py — diagnoses strategy_v5 (Greed-Gated Trim) vs B0.

Per strategy_v5.md §"What success means": v5's scoreboard is risk-adjusted
edge vs B0 (max DD, Sortino, return-gap). The experiment matrix sweeps each
v5 knob and runs the two ablations the spec mandates.

Sections:
  1. Headline: v5-base vs B0
  2. Trim event log (spec-mandated distinct-events disclosure)
  3. Experiment matrix (fng / drip / target / band sweeps + 2 ablations)
  4. Regime breakdown (Up / Down / Sideways)
  5. Success criteria checklist (5 bullets from spec)
  6. Bootstrap 95% CIs on (v5 − B0) return and DD gap

Outputs:
  - analysis/results/postmortem_report_v5.md
  - analysis/output/postmortem_weights_v5.png
  - analysis/output/postmortem_fng_v5.png
  - analysis/output/postmortem_attribution_v5.png
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
from analysis_v5 import (
    VERSION, TARGET_W, BAND, FNG_TRIM_THR, DRIP_WEEKS,
    simulate_v5, trim_events,
)


REPORT_MD   = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG  = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")
WEIGHTS_PNG = os.path.join(OUTPUT_DIR,  f"postmortem_weights_v{VERSION}.png")
FNG_PNG     = os.path.join(OUTPUT_DIR,  f"postmortem_fng_v{VERSION}.png")


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
        n_trims = int((action_log["action"] == "trim").sum())
        row["n_trims"] = n_trims
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

    v5_df, v5_log = simulate_v5(daily, fng)
    b0_df         = simulate_control(daily)

    findings = []

    # ---- 1. Headline ----
    v5_dd = max_drawdown(v5_df["value"]) * 100
    b0_dd = max_drawdown(b0_df["value"]) * 100
    v5_sh, v5_so = sharpe_sortino(v5_df)
    b0_sh, b0_so = sharpe_sortino(b0_df)
    headline = pd.DataFrame([
        {"arm": "B0 deploy-on-arrival",
         "final_$": round(b0_df["value"].iloc[-1], 2),
         "return_%": round(b0_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(b0_dd, 2), "sharpe": round(b0_sh, 3), "sortino": round(b0_so, 3)},
        {"arm": "v5 Greed-Gated Trim",
         "final_$": round(v5_df["value"].iloc[-1], 2),
         "return_%": round(v5_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(v5_dd, 2), "sharpe": round(v5_sh, 3), "sortino": round(v5_so, 3)},
    ])
    ret_gap_pp = (v5_df["value"].iloc[-1] / deposited * 100) - (b0_df["value"].iloc[-1] / deposited * 100)
    findings.append(("1. Headline — v5 vs B0", [
        df_to_md(headline),
        "",
        f"DD shallower than B0 by:  {v5_dd - b0_dd:+.2f} pp",
        f"Return gap (v5 − B0):     {ret_gap_pp:+.2f} pp  (${v5_df['value'].iloc[-1] - b0_df['value'].iloc[-1]:+,.2f})",
        f"Sortino delta:            {v5_so - b0_so:+.3f}",
        f"Realized harvest:         ${v5_df.attrs['harvest_total']:,.2f}",
        f"Fees paid:                ${v5_df.attrs['fee_total']:,.2f}",
    ]))

    # ---- 2. Trim event log ----
    trims_df = trim_events(v5_log)
    n_trims = len(trims_df)
    findings.append(("2. Trim events — spec-mandated disclosure", [
        f"Distinct trim events: **{n_trims}**  (spec target: 2–8)",
        "",
        df_to_md(trims_df) if n_trims else "_No trims fired._",
    ]))

    # ---- 3. Experiment matrix ----
    variants = [("v5-base", {})]
    for thr in (85, 90, 95):
        variants.append((f"v5-fng-{thr}", {"fng_trim_threshold": thr}))
    for dw in (1, 4, 8):
        variants.append((f"v5-drip-{dw}", {"drip_weeks": dw}))
    for tw in (0.85, 0.92, 0.98):
        variants.append((f"v5-target-{int(tw*100)}", {"target_w": tw}))
    for b in (0.03, 0.05, 0.08):
        variants.append((f"v5-band-{int(b*100):02d}", {"band": b}))
    variants.append(("v5-no-fng (ablation)",  {"disable_fng_gate": True}))
    variants.append(("v5-no-trim (ablation)", {"disable_trim": True}))

    matrix_rows = [_arm_row("B0", b0_df, deposited, b0_df)]
    cache = {}
    for name, kw in variants:
        if name == "v5-base":
            df_v, log_v = v5_df, v5_log
        else:
            df_v, log_v = simulate_v5(daily, fng, **kw)
        cache[name] = (df_v, log_v)
        matrix_rows.append(_arm_row(name, df_v, deposited, b0_df, action_log=log_v))

    # spec verification: no-trim must equal B0 to machine precision
    no_trim_df = cache["v5-no-trim (ablation)"][0]
    assert abs(no_trim_df["value"].iloc[-1] - b0_df["value"].iloc[-1]) < 1e-6, \
        "v5-no-trim must equal B0 by construction"

    findings.append(("3. Experiment matrix (full window)", [
        df_to_md(pd.DataFrame(matrix_rows)),
        "",
        "_Note: `v5-no-trim` equals B0 by construction (asserted)._",
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
    merged = (v5_df[["date", "value"]].rename(columns={"value": "v5"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    merged = merged[(merged["v5"] > 0) & (merged["b0"] > 0)].copy()
    merged["v5_dr"] = merged["v5"].pct_change()
    merged["b0_dr"] = merged["b0"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v5_dr", "b0_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v5_daily_mean_%": round(grp["v5_dr"].mean() * 100, 4),
            "b0_daily_mean_%": round(grp["b0_dr"].mean() * 100, 4),
            "delta_pp":        round((grp["v5_dr"].mean() - grp["b0_dr"].mean()) * 100, 4),
        })
    findings.append(("4. Regime breakdown (Up / Down / Sideways)", [
        df_to_md(pd.DataFrame(reg_rows)),
    ]))

    # ---- 5. Success criteria checklist ----
    no_fng_df, no_fng_log = cache["v5-no-fng (ablation)"]
    no_fng_dd  = max_drawdown(no_fng_df["value"]) * 100
    no_fng_ret = (no_fng_df["value"].iloc[-1] / deposited - 1) * 100
    v5_ret_pp  = (v5_df["value"].iloc[-1] / deposited - 1) * 100
    b0_ret_pp  = (b0_df["value"].iloc[-1] / deposited - 1) * 100
    dom_dd  = v5_dd > no_fng_dd
    dom_ret = v5_ret_pp > no_fng_ret
    dom_either = dom_dd or dom_ret
    dom_no_loss = (dom_dd and v5_ret_pp >= no_fng_ret) or (dom_ret and v5_dd >= no_fng_dd)
    crit = [
        ("1. Max DD ≥ 8pp shallower than B0", (v5_dd - b0_dd) >= 8.0,
            f"actual: {v5_dd - b0_dd:+.2f} pp"),
        ("2. Sortino ≥ B0 + 0.3", (v5_so - b0_so) >= 0.3,
            f"actual: {v5_so - b0_so:+.3f}"),
        ("3. Return within 10pp of B0", abs(v5_ret_pp - b0_ret_pp) <= 10.0,
            f"actual gap: {v5_ret_pp - b0_ret_pp:+.2f} pp"),
        ("4. Trim count in [2, 8]", 2 <= n_trims <= 8,
            f"actual: {n_trims}"),
        ("5. v5-base dominates v5-no-fng on {ret OR DD} w/o losing the other",
            dom_either and dom_no_loss,
            f"DD: v5={v5_dd:.2f}% vs no-fng={no_fng_dd:.2f}%  ·  "
            f"ret: v5={v5_ret_pp:.2f}% vs no-fng={no_fng_ret:.2f}%"),
    ]
    crit_lines = []
    for label, ok, detail in crit:
        mark = "PASS" if ok else "FAIL"
        crit_lines.append(f"- **[{mark}]** {label}  —  {detail}")
    findings.append(("5. Success criteria checklist (from strategy_v5.md)", crit_lines))

    # ---- 6. Bootstrap CIs ----
    v5_w = v5_df.set_index("date")["value"].resample("W").last()
    b0_w = b0_df.set_index("date")["value"].resample("W").last()
    weekly_ret_v5 = v5_w.pct_change().dropna()
    weekly_ret_b0 = b0_w.pct_change().dropna()
    aligned = pd.concat([weekly_ret_v5.rename("v5"), weekly_ret_b0.rename("b0")], axis=1).dropna()
    diff_ret = (aligned["v5"] - aligned["b0"]).values
    d_mean, d_lo, d_hi = boot_ci(diff_ret)
    gap = (v5_w - b0_w).dropna().values
    g_mean, g_lo, g_hi = boot_ci(gap)
    findings.append(("6. Bootstrap 95% CIs (n=2000)", [
        f"Mean weekly return delta (v5 − B0):  {d_mean*100:+.4f}%  [{d_lo*100:+.4f}%, {d_hi*100:+.4f}%]",
        f"Mean weekly value gap (v5 − B0):     ${g_mean:+,.2f}  [{g_lo:+,.2f}, {g_hi:+,.2f}]",
    ]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Greed-Gated Trim)", "",
          f"_Window: {START.date()} → {END.date()}_", "",
          "_Single-cycle in-sample fit. Sweep results show the *shape* of trade-offs,",
          "not robust edge._", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plots ----
    log_dates = pd.to_datetime(v5_log["date"]).values
    trim_log  = v5_log[v5_log["action"] == "trim"]
    trim_dates = pd.to_datetime(trim_log["date"]).values

    # weights plot
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(log_dates, v5_log["btc_weight"].values, linewidth=1.0)
    ax.axhline(TARGET_W, color="black", linewidth=0.8, label=f"target={TARGET_W}")
    ax.axhline(TARGET_W + BAND, color="red", linewidth=0.6, linestyle="--",
               label=f"trim band (+{BAND})")
    if len(trim_dates):
        ax.scatter(trim_dates, [TARGET_W + BAND] * len(trim_dates),
                   marker="v", color="red", s=40, label="trim fired", zorder=5)
    ax.set_title("v5 BTC weight over time (after Tuesday deploy)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(WEIGHTS_PNG, dpi=120); plt.close()
    print(f"Saved {WEIGHTS_PNG}")

    # FNG plot with threshold + trim markers
    fig, ax = plt.subplots(figsize=(12, 4))
    fng_in_window = fng[(fng.index >= START.normalize()) & (fng.index <= END.normalize())]
    ax.plot(fng_in_window.index.values, fng_in_window.values, linewidth=0.8, color="tab:purple")
    ax.axhline(FNG_TRIM_THR, color="red", linewidth=0.8, linestyle="--",
               label=f"trim threshold = {FNG_TRIM_THR}")
    if len(trim_dates):
        ax.scatter(trim_dates, trim_log["fng"].astype(int).values,
                   marker="v", color="red", s=40, label="trim fired", zorder=5)
    ax.set_title("Fear & Greed Index — daily, with trim events marked")
    ax.set_ylabel("FNG (0..100)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FNG_PNG, dpi=120); plt.close()
    print(f"Saved {FNG_PNG}")

    # attribution 2x2
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(v5_df["date"].values, v5_df["value"].values, label="v5", linewidth=1.3)
    ax.plot(b0_df["date"].values, b0_df["value"].values, label="B0", linewidth=1.3)
    ax.set_title("v5 vs B0 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.plot(v5_df["date"].values, v5_df["drip_pending"].values,
            color="tab:green", linewidth=1.0)
    ax.set_title("Drip queue size over time (USD pending)")
    ax.grid(alpha=0.3)

    ax = axes[1, 0]
    weekly_gap = (v5_w - b0_w).dropna()
    ax.plot(weekly_gap.index.values, weekly_gap.values, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("Weekly value gap (v5 − B0)"); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df))
        width = 0.35
        ax.bar(x - width/2, reg_df["v5_daily_mean_%"], width, label="v5")
        ax.bar(x + width/2, reg_df["b0_daily_mean_%"], width, label="B0")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout(); plt.savefig(ATTRIB_PNG, dpi=120); plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
