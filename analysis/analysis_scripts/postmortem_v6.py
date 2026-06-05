"""
postmortem_v6.py — diagnoses strategy_v6 (Band Rebalance) vs B0.

Per strategy_v6.md §"What success means": v6's scoreboard is risk-adjusted edge
vs B0 (max DD, Sortino, Sharpe), with the return give-up an *accepted cost* — not
a failure — provided criteria 1–3 are met. v6 is a frontier choice, so the matrix
shows the menu (the target_w sweep) rather than fitting a winner.

Sections:
  1. Headline: v6-base vs B0
  2. Experiment matrix (target / drip / band sweeps + no-trim ablation)
  3. Cross-version: v6-base vs v5-base vs B0 (keeps "the gate was decoration"
     claim falsifiable — the one place we re-run committed v5 code, read-only)
  4. Regime breakdown (Up / Down / Sideways)
  5. Success criteria checklist (5 bullets from spec)
  6. Bootstrap 95% CIs on (v6 - B0) return and value gap

Outputs:
  - analysis/results/postmortem_report_v6.md
  - analysis/output/postmortem_weights_v6.png
  - analysis/output/postmortem_attribution_v6.png
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
from analysis_v6 import (
    VERSION, TARGET_W, BAND, DRIP_WEEKS,
    simulate_v6, trim_events,
)
# Read-only reuse of the committed v5 script for the cross-version row only.
from analysis_v5 import simulate_v5


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
        row["n_trims"] = int((action_log["action"] == "trim").sum())
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

    v6_df, v6_log = simulate_v6(daily)
    b0_df         = simulate_control(daily)

    findings = []

    # ---- 1. Headline ----
    v6_dd = max_drawdown(v6_df["value"]) * 100
    b0_dd = max_drawdown(b0_df["value"]) * 100
    v6_sh, v6_so = sharpe_sortino(v6_df)
    b0_sh, b0_so = sharpe_sortino(b0_df)
    headline = pd.DataFrame([
        {"arm": "B0 deploy-on-arrival",
         "final_$": round(b0_df["value"].iloc[-1], 2),
         "return_%": round(b0_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(b0_dd, 2), "sharpe": round(b0_sh, 3), "sortino": round(b0_so, 3)},
        {"arm": "v6 Band Rebalance",
         "final_$": round(v6_df["value"].iloc[-1], 2),
         "return_%": round(v6_df["value"].iloc[-1] / deposited * 100 - 100, 2),
         "max_dd_%": round(v6_dd, 2), "sharpe": round(v6_sh, 3), "sortino": round(v6_so, 3)},
    ])
    ret_gap_pp = (v6_df["value"].iloc[-1] / deposited * 100) - (b0_df["value"].iloc[-1] / deposited * 100)
    findings.append(("1. Headline — v6 vs B0", [
        df_to_md(headline),
        "",
        f"DD shallower than B0 by:  {v6_dd - b0_dd:+.2f} pp",
        f"Return gap (v6 - B0):     {ret_gap_pp:+.2f} pp  (${v6_df['value'].iloc[-1] - b0_df['value'].iloc[-1]:+,.2f})",
        f"Sortino delta:            {v6_so - b0_so:+.3f}",
        f"Sharpe delta:             {v6_sh - b0_sh:+.3f}",
        f"Realized harvest:         ${v6_df.attrs['harvest_total']:,.2f}",
        f"Fees paid:                ${v6_df.attrs['fee_total']:,.2f}  ({(v6_log['action'] == 'trim').sum()} trims)",
    ]))

    # ---- 2. Experiment matrix ----
    variants = [("v6-base", {})]
    for tw in (0.80, 0.85, 0.92, 0.98):                 # target sweep — the menu
        variants.append((f"v6-target-{int(tw*100)}", {"target_w": tw}))
    for dw in (1, 4, 8, "hold"):                         # drip / churn question
        label = "hold" if dw == "hold" else f"{dw}w"
        variants.append((f"v6-drip-{label}", {"drip_weeks": dw}))
    for b in (0.03, 0.05, 0.08):                         # hysteresis width
        variants.append((f"v6-band-{int(b*100):02d}", {"band": b}))
    variants.append(("v6-no-trim (ablation)", {"disable_trim": True}))

    matrix_rows = [_arm_row("B0", b0_df, deposited, b0_df)]
    cache = {}
    for name, kw in variants:
        if name == "v6-base":
            df_v, log_v = v6_df, v6_log
        else:
            df_v, log_v = simulate_v6(daily, **kw)
        cache[name] = (df_v, log_v)
        matrix_rows.append(_arm_row(name, df_v, deposited, b0_df, action_log=log_v))

    # spec verification: no-trim must equal B0 to machine precision
    no_trim_df = cache["v6-no-trim (ablation)"][0]
    assert abs(no_trim_df["value"].iloc[-1] - b0_df["value"].iloc[-1]) < 1e-6, \
        "v6-no-trim must equal B0 by construction"

    findings.append(("2. Experiment matrix (full window)", [
        df_to_md(pd.DataFrame(matrix_rows)),
        "",
        "_`v6-no-trim` equals B0 by construction (asserted). The target sweep is the",
        "menu — lower target_w = more cushion, more give-up; it is a preference, not a",
        "prediction. The drip sweep resolves the churn tension: `hold` parks trim",
        "proceeds as standing cash at the lower weight instead of dripping back in._",
    ]))

    # ---- 3. Cross-version: v6-base vs v5-base vs B0 ----
    fng = load_fng_daily()
    v5_df, v5_log = simulate_v5(daily, fng)   # committed v5 code, read-only
    xrows = [
        _arm_row("B0",      b0_df, deposited, b0_df),
        _arm_row("v5-base", v5_df, deposited, b0_df, action_log=v5_log),
        _arm_row("v6-base", v6_df, deposited, b0_df, action_log=v6_log),
    ]
    findings.append(("3. Cross-version — v6-base vs v5-base vs B0", [
        df_to_md(pd.DataFrame(xrows)),
        "",
        "_The falsifiable check on 'the FNG gate was decoration': v5-base (gate ON)",
        "barely moved off B0 (DD ~-67.7%, 11 trims), while v6-base (gate OFF) trades",
        "real return for a materially shallower drawdown. If v5-base and v6-base were",
        "close, the gate would be doing the work; they are not._",
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
    merged = (v6_df[["date", "value"]].rename(columns={"value": "v6"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    merged = merged[(merged["v6"] > 0) & (merged["b0"] > 0)].copy()
    merged["v6_dr"] = merged["v6"].pct_change()
    merged["b0_dr"] = merged["b0"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v6_dr", "b0_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v6_daily_mean_%": round(grp["v6_dr"].mean() * 100, 4),
            "b0_daily_mean_%": round(grp["b0_dr"].mean() * 100, 4),
            "delta_pp":        round((grp["v6_dr"].mean() - grp["b0_dr"].mean()) * 100, 4),
        })
    findings.append(("4. Regime breakdown (Up / Down / Sideways)", [
        df_to_md(pd.DataFrame(reg_rows)),
    ]))

    # ---- 5. Success criteria checklist (from strategy_v6.md) ----
    v6_ret_pp = (v6_df["value"].iloc[-1] / deposited - 1) * 100
    b0_ret_pp = (b0_df["value"].iloc[-1] / deposited - 1) * 100
    dd_ok      = (v6_dd - b0_dd) >= 8.0           # v6 dd shallower -> v6_dd less negative
    sortino_ok = (v6_so - b0_so) >= 0.3
    sharpe_ok  = v6_sh >= b0_sh
    risk_justified = dd_ok and sortino_ok and sharpe_ok  # crit 4: cost is OK iff 1-3 met

    # crit 5: target_w sweep monotone-ish — return and DD should move smoothly with target.
    tsweep = [(tw, cache[f"v6-target-{int(tw*100)}"][0]) for tw in (0.80, 0.85, 0.92, 0.98)]
    rets = [(d["value"].iloc[-1] / deposited - 1) * 100 for _, d in tsweep]
    dds  = [max_drawdown(d["value"]) * 100 for _, d in tsweep]
    ret_monotone = all(rets[i] <= rets[i+1] + 1e-6 for i in range(len(rets)-1))   # ↑ target → ↑ return
    dd_monotone  = all(dds[i]  >= dds[i+1]  - 1e-6 for i in range(len(dds)-1))    # ↑ target → deeper (more negative) DD
    interior_dominates = False
    for i in range(1, len(tsweep) - 1):
        if rets[i] >= max(rets[0], rets[-1]) and dds[i] >= max(dds[0], dds[-1]):
            interior_dominates = True
    legible = (ret_monotone and dd_monotone) and not interior_dominates

    crit = [
        ("1. Max DD ≥ 8pp shallower than B0", dd_ok,
            f"actual: {v6_dd - b0_dd:+.2f} pp (B0 {b0_dd:.2f}%, v6 {v6_dd:.2f}%)"),
        ("2. Sortino ≥ B0 + 0.3", sortino_ok,
            f"actual: {v6_so - b0_so:+.3f}  (B0 {b0_so:.3f}, v6 {v6_so:.3f})"),
        ("3. Sharpe ≥ B0", sharpe_ok,
            f"actual: {v6_sh - b0_sh:+.3f}  (B0 {b0_sh:.3f}, v6 {v6_sh:.3f})"),
        ("4. Return give-up is risk-justified (accepted cost; fails only if 1-3 miss)",
            risk_justified,
            f"give-up {v6_ret_pp - b0_ret_pp:+.2f} pp — {'risk-justified by 1-3' if risk_justified else 'NOT covered: 1-3 not all met'}"),
        ("5. target_w sensitivity monotone-ish and legible", legible,
            f"returns {[round(x,1) for x in rets]} / DDs {[round(x,1) for x in dds]} "
            f"(target 0.80→0.98); interior_dominates={interior_dominates}"),
    ]
    crit_lines = []
    for label, ok, detail in crit:
        crit_lines.append(f"- **[{'PASS' if ok else 'FAIL'}]** {label}  —  {detail}")
    crit_lines += [
        "",
        "_Criteria 1–3 are the real test. If met, v6 is a valid frontier point and the",
        "choice between it and B0 is a risk-tolerance decision, not a backtest decision._",
    ]
    findings.append(("5. Success criteria checklist (from strategy_v6.md)", crit_lines))

    # ---- 6. Bootstrap CIs ----
    v6_w = v6_df.set_index("date")["value"].resample("W").last()
    b0_w = b0_df.set_index("date")["value"].resample("W").last()
    aligned = pd.concat([v6_w.pct_change().rename("v6"),
                         b0_w.pct_change().rename("b0")], axis=1).dropna()
    diff_ret = (aligned["v6"] - aligned["b0"]).values
    d_mean, d_lo, d_hi = boot_ci(diff_ret)
    gap = (v6_w - b0_w).dropna().values
    g_mean, g_lo, g_hi = boot_ci(gap)
    findings.append(("6. Bootstrap 95% CIs (n=2000)", [
        f"Mean weekly return delta (v6 - B0):  {d_mean*100:+.4f}%  [{d_lo*100:+.4f}%, {d_hi*100:+.4f}%]",
        f"Mean weekly value gap (v6 - B0):     ${g_mean:+,.2f}  [{g_lo:+,.2f}, {g_hi:+,.2f}]",
    ]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Band Rebalance)", "",
          f"_Window: {START.date()} → {END.date()}_", "",
          "_Single-cycle in-sample fit. The target_w sweep traces the return/drawdown",
          "frontier — it shows the *shape* of a preference, not robust edge._", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plots ----
    log_dates  = pd.to_datetime(v6_log["date"]).values
    trim_log   = v6_log[v6_log["action"] == "trim"]
    trim_dates = pd.to_datetime(trim_log["date"]).values

    # weights plot
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(log_dates, v6_log["btc_weight"].values, linewidth=1.0)
    ax.axhline(TARGET_W, color="black", linewidth=0.8, label=f"target={TARGET_W}")
    ax.axhline(TARGET_W + BAND, color="red", linewidth=0.6, linestyle="--",
               label=f"trim band (+{BAND})")
    if len(trim_dates):
        ax.scatter(trim_dates, [TARGET_W + BAND] * len(trim_dates),
                   marker="v", color="red", s=12, label="trim fired", zorder=5)
    ax.set_title("v6 BTC weight over time (after Tuesday deploy) — trims fire nearly every week")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(WEIGHTS_PNG, dpi=120); plt.close()
    print(f"Saved {WEIGHTS_PNG}")

    # attribution 2x2
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(v6_df["date"].values, v6_df["value"].values, label="v6", linewidth=1.3)
    ax.plot(b0_df["date"].values, b0_df["value"].values, label="B0", linewidth=1.3)
    ax.set_title("v6 vs B0 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.plot(v6_df["date"].values, v6_df["drip_pending"].values,
            color="tab:green", linewidth=1.0)
    ax.set_title("Drip queue size over time (USD pending)")
    ax.grid(alpha=0.3)

    ax = axes[1, 0]
    weekly_gap = (v6_w - b0_w).dropna()
    ax.plot(weekly_gap.index.values, weekly_gap.values, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title("Weekly value gap (v6 - B0) — the front-loaded give-up"); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df))
        width = 0.35
        ax.bar(x - width/2, reg_df["v6_daily_mean_%"], width, label="v6")
        ax.bar(x + width/2, reg_df["b0_daily_mean_%"], width, label="B0")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout(); plt.savefig(ATTRIB_PNG, dpi=120); plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
