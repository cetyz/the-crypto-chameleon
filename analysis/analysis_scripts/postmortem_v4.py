"""
postmortem_v4.py — diagnoses strategy_v4 (Active Sleeve) vs B0.

Per spec §What "success" means: v4's scoreboard is activity & divergence,
not return. Drawdown is a bonus axis. The experiment matrix sweeps the
knobs that shape activity and sleeve drag.

Sections:
  1. Headline: v4-base vs B0 on standard + activity metrics
  2. Action breakdown & rebalance activity
  3. Experiment matrix (sleeve / dipmin / curve / eager-redeploy / trim-band)
  4. Regime breakdown (Up / Down / Sideways) — labeling only
  5. Bootstrap CIs on divergence & active_weeks%

Outputs:
  - analysis/results/postmortem_report_v4.md
  - analysis/output/postmortem_attribution_v4.png
  - analysis/output/postmortem_weights_v4.png
  - analysis/output/postmortem_sleeve_v4.png
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
from analysis_v4 import (
    VERSION, TARGET_W, SLEEVE_TARGET, UPPER_BAND, LOWER_BAND,
    DIP_MIN, DIP_REF_WEEKS,
    simulate_v4, v4_activity_metrics,
)


REPORT_MD   = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG  = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")
WEIGHTS_PNG = os.path.join(OUTPUT_DIR,  f"postmortem_weights_v{VERSION}.png")
SLEEVE_PNG  = os.path.join(OUTPUT_DIR,  f"postmortem_sleeve_v{VERSION}.png")


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
    """Compact row for the experiment matrix."""
    final = df["value"].iloc[-1]
    sh, so = sharpe_sortino(df)
    row = {
        "arm": name,
        "final_$":   round(final, 2),
        "return_%":  round((final / deposited - 1) * 100, 2),
        "max_dd_%":  round(max_drawdown(df["value"]) * 100, 2),
        "sortino":   round(so, 3),
        "vs_B0_dd_pp":  round((max_drawdown(df["value"]) - max_drawdown(b0_df["value"])) * 100, 2),
        "vs_B0_ret_$":  round(final - b0_df["value"].iloc[-1], 2),
    }
    if action_log is not None:
        act = v4_activity_metrics(df, action_log, b0_df)
        row["active_%"]   = act["active_weeks_%"]
        row["divergence_$"] = act["mean_abs_value_gap_$"]
        row["avg_sleeve"] = act["avg_sleeve_frac"]
        row["n_trades"]   = act["trim"] + act["dip_buy"] + act["drift_redeploy"]
    return row


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly = load_btc_hourly()
    daily  = daily_closes(hourly)
    weekly = weekly_closes(hourly)
    weekly = weekly[(weekly.index >= START - pd.Timedelta(weeks=DIP_REF_WEEKS + 4))
                    & (weekly.index <= END)]

    deposited = len(last_friday_deposit_dates(START, END)) * MONTHLY_DEPOSIT

    # v4-base
    v4_df, v4_log = simulate_v4(daily, weekly)
    b0_df         = simulate_control(daily)

    findings = []

    # ---- 1. Headline ----
    v4_dd = max_drawdown(v4_df["value"]) * 100
    b0_dd = max_drawdown(b0_df["value"]) * 100
    v4_sh, v4_so = sharpe_sortino(v4_df)
    b0_sh, b0_so = sharpe_sortino(b0_df)
    headline = pd.DataFrame([
        {"arm": "B0 deploy-on-arrival",
         "final_$": round(b0_df["value"].iloc[-1], 2),
         "return_%": round(b0_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(b0_dd, 2), "sharpe": round(b0_sh, 3), "sortino": round(b0_so, 3)},
        {"arm": "v4 Active Sleeve",
         "final_$": round(v4_df["value"].iloc[-1], 2),
         "return_%": round(v4_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(v4_dd, 2), "sharpe": round(v4_sh, 3), "sortino": round(v4_so, 3)},
    ])
    activity = v4_activity_metrics(v4_df, v4_log, b0_df)
    findings.append(("1. Headline — v4 vs B0 (standard + activity scoreboard)", [
        df_to_md(headline),
        "",
        f"DD shallower than B0 by:  {b0_dd - v4_dd:+.2f} pp",
        f"Return delta vs B0:       {v4_df['value'].iloc[-1] - b0_df['value'].iloc[-1]:+,.2f} USD",
        "",
        "v4 activity scoreboard (the actual goal):",
        df_to_md(pd.DataFrame([activity])),
    ]))

    # ---- 2. Activity breakdown ----
    live = v4_log[v4_log["phase"] == "live"].copy()
    counts = live["action"].value_counts().to_dict()
    findings.append(("2. Rebalance activity (live phase)", [
        f"Trims:           {counts.get('trim', 0)}",
        f"Dip-buys:        {counts.get('dip_buy', 0)}",
        f"Drift-redeploys: {counts.get('drift_redeploy', 0)}",
        f"Holds:           {counts.get('hold', 0)}",
        "",
        f"Realized harvest from trims: ${v4_df.attrs['harvest_total']:,.2f}",
        f"Total fees paid:              ${v4_df.attrs['fee_total']:,.2f}",
        f"Harvest − fees:               ${v4_df.attrs['harvest_total'] - v4_df.attrs['fee_total']:+,.2f}",
    ]))

    # ---- 3. Experiment matrix ----
    variants = []
    variants.append(("v4-base", {}))
    # sleeve sweep
    for s in (0.06, 0.12, 0.20):
        variants.append((f"v4-sleeve-{int(s*100):02d}", {"sleeve_target": s}))
    # dipmin sweep
    for m in (0.01, 0.03, 0.06):
        variants.append((f"v4-dipmin-{int(m*100)}", {"dip_min": m}))
    # curve sweep
    variants.append(("v4-curve-linear", {"curve": "linear"}))
    variants.append(("v4-curve-convex", {"curve": "convex"}))
    # eager-redeploy
    variants.append(("v4-eager-redeploy", {"lower_band": 0.02}))
    # trim-band sweep
    for ub in (0.10, 0.15, 0.20):
        variants.append((f"v4-trim-{int(ub*100):02d}", {"upper_band": ub}))

    matrix_rows = [_arm_row("B0", b0_df, deposited, b0_df)]
    for name, kw in variants:
        if name == "v4-base":
            df_v, log_v = v4_df, v4_log
        else:
            df_v, log_v = simulate_v4(daily, weekly, **kw)
        matrix_rows.append(_arm_row(name, df_v, deposited, b0_df, action_log=log_v))
    findings.append(("3. Experiment matrix (full window)", [
        df_to_md(pd.DataFrame(matrix_rows)),
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
    merged = (v4_df[["date", "value"]].rename(columns={"value": "v4"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    merged = merged[(merged["v4"] > 0) & (merged["b0"] > 0)].copy()
    merged["v4_dr"] = merged["v4"].pct_change()
    merged["b0_dr"] = merged["b0"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v4_dr", "b0_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v4_daily_mean_%": round(grp["v4_dr"].mean() * 100, 4),
            "b0_daily_mean_%": round(grp["b0_dr"].mean() * 100, 4),
            "delta_pp":        round((grp["v4_dr"].mean() - grp["b0_dr"].mean()) * 100, 4),
        })
    findings.append(("4. Regime breakdown (Up / Down / Sideways) — labeling only", [
        df_to_md(pd.DataFrame(reg_rows)),
    ]))

    # ---- 5. Bootstrap CIs on activity metrics ----
    # weekly value gap series
    v4_w = v4_df.set_index("date")["value"].resample("W").last()
    b0_w = b0_df.set_index("date")["value"].resample("W").last()
    gap = (v4_w - b0_w).dropna().values
    g_mean, g_lo, g_hi = boot_ci(np.abs(gap))
    # active-week indicator series
    is_active = (live["action"] != "hold").astype(float).values
    a_mean, a_lo, a_hi = boot_ci(is_active)
    findings.append(("5. Bootstrap 95% CIs (n=2000)", [
        f"Mean |weekly value gap vs B0|:  ${g_mean:,.2f}  [{g_lo:,.2f}, {g_hi:,.2f}]",
        f"Active-week rate:               {a_mean*100:.2f}%  [{a_lo*100:.2f}%, {a_hi*100:.2f}%]",
    ]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Active Sleeve)", "",
          f"_Window: {START.date()} → {END.date()}_", "",
          "_Per spec: this is a toy fit to a single mostly-up BTC cycle. ",
          "Sweep results show the *shape* of trade-offs, not robust edge._", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plots ----
    # weights over time (live phase)
    live_dates = pd.to_datetime(live["date"]).values
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(live_dates, live["btc_weight"].values, linewidth=1.0)
    ax.axhline(TARGET_W, color="black", linewidth=0.8, label=f"target={TARGET_W}")
    ax.axhline(TARGET_W + UPPER_BAND, color="red", linewidth=0.6, linestyle="--",
               label=f"trim band (+{UPPER_BAND})")
    ax.axhline(TARGET_W - LOWER_BAND, color="orange", linewidth=0.6, linestyle="--",
               label=f"redeploy band (−{LOWER_BAND})")
    ax.set_title("v4 BTC weight over time"); ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(WEIGHTS_PNG, dpi=120); plt.close()
    print(f"Saved {WEIGHTS_PNG}")

    # sleeve fraction over time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(live_dates, live["sleeve_frac"].values, linewidth=1.0, color="tab:green")
    ax.axhline(SLEEVE_TARGET, color="black", linewidth=0.8, label=f"sleeve target={SLEEVE_TARGET}")
    ax.set_title("v4 cash sleeve fraction over time"); ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(SLEEVE_PNG, dpi=120); plt.close()
    print(f"Saved {SLEEVE_PNG}")

    # attribution: equity + per-action cumulative deploy + regime bars
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(v4_df["date"].values, v4_df["value"].values, label="v4", linewidth=1.3)
    ax.plot(b0_df["date"].values, b0_df["value"].values, label="B0", linewidth=1.3)
    ax.set_title("v4 vs B0 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    for kind, color in (("dip_buy", "tab:blue"),
                        ("drift_redeploy", "tab:orange"),
                        ("trim", "tab:red")):
        sub = live[live["action"] == kind]
        if len(sub):
            cum = sub["trade_usd"].abs().cumsum()
            ax.plot(pd.to_datetime(sub["date"]).values, cum.values, label=kind, linewidth=1.2, color=color)
    ax.set_title("Cumulative notional traded by action type")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1, 0]
    weekly_gap = (v4_w - b0_w).dropna()
    ax.plot(weekly_gap.index.values, weekly_gap.values, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("Weekly value gap (v4 − B0)"); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df))
        width = 0.35
        ax.bar(x - width/2, reg_df["v4_daily_mean_%"], width, label="v4")
        ax.bar(x + width/2, reg_df["b0_daily_mean_%"], width, label="B0")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout(); plt.savefig(ATTRIB_PNG, dpi=120); plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
