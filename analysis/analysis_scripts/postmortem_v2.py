"""
postmortem_v2.py — diagnoses *why* strategy_v2 lands where it does vs B0.

No tuning, diagnosis only. Sweeps are the spec's §Experiment matrix run as a
fixed set, not optimized over.

Sections:
  1. Headline gap vs B0
  2. Cash drag (the central question for v2)
  3. Per-cell forward returns
  4. Experiment matrix (trend-only, flip-funding, reserve sweep, floor sweep)
  5. Signal-quality CIs
  6. Regime breakdown (Up vs Down)

Outputs:
  - analysis/results/postmortem_report_v2.md
  - analysis/output/postmortem_attribution_v2.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, FEE_RATE, SMA_WEEKS, FUNDING_WINDOW,
    load_btc_hourly, weekly_closes, daily_closes,
    fetch_funding, weekly_funding_annpct,
    trend_state, funding_state,
    last_friday_deposit_dates, simulate_control,
    max_drawdown, boot_ci, fwd_return, df_to_md,
)
from analysis_v2 import (
    VERSION, FINAL_F, F_MIN, RESERVE_CAP, simulate_v2,
)


REPORT_MD  = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")


def flip_table(table):
    out = {}
    base_up   = table[("Up", "Neutral")]
    base_down = table[("Down", "Neutral")]
    for (t, f), v in table.items():
        if t == "Up":
            base = base_up
        else:
            base = base_down
        nudge = v - base   # nudge as encoded
        out[(t, f)] = base - nudge
    return out


def zero_nudge_table(table):
    out = {}
    base_up   = table[("Up", "Neutral")]
    base_down = table[("Down", "Neutral")]
    for (t, f) in table:
        out[(t, f)] = base_up if t == "Up" else base_down
    return out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly  = load_btc_hourly()
    daily   = daily_closes(hourly)
    weekly  = weekly_closes(hourly)
    weekly  = weekly[(weekly.index >= START - pd.Timedelta(weeks=SMA_WEEKS + FUNDING_WINDOW + 4))
                     & (weekly.index <= END)]
    funding = fetch_funding()
    weekly_fund = weekly_funding_annpct(funding, weekly.index)

    deposited = len(last_friday_deposit_dates(START, END)) * MONTHLY_DEPOSIT

    # ---- baseline arms ----
    v2_df, action_log = simulate_v2(daily, weekly, weekly_fund)
    b0_df             = simulate_control(daily)

    findings = []

    # ---- 1. Headline gap ----
    merged = (v2_df[["date", "value"]].rename(columns={"value": "v2"})
              .merge(b0_df[["date", "value"]].rename(columns={"value": "b0"}), on="date"))
    merged["gap"] = merged["v2"] - merged["b0"]
    worst = merged.loc[merged["gap"].idxmin()]
    best  = merged.loc[merged["gap"].idxmax()]
    final_gap = merged["gap"].iloc[-1]
    findings.append(("1. Headline gap (v2 − B0)", [
        f"Final B0:  ${b0_df['value'].iloc[-1]:,.2f}",
        f"Final v2:  ${v2_df['value'].iloc[-1]:,.2f}",
        f"Final gap: ${final_gap:+,.2f}  ({final_gap/b0_df['value'].iloc[-1]:+.2%} of B0)",
        f"Best  gap: {best['date'].date()}  ${best['gap']:+,.2f}",
        f"Worst gap: {worst['date'].date()}  ${worst['gap']:+,.2f}",
    ]))

    # ---- 2. Cash drag ----
    live = action_log[action_log["phase"] == "live"].copy()
    avg_reserve_frac = (live["cash_after"] / live["value_after"]).mean()
    # Foregone $: if every Sunday's idle cash had been deployed and held to END.
    end_price = v2_df["price"].iloc[-1]
    # value if cash converted to BTC at that Sunday and held
    live["could_buy_btc"] = live["cash_after"] * (1 - FEE_RATE) / live["close"]
    foregone = (live["could_buy_btc"] * end_price - live["cash_after"]).sum()
    findings.append(("2. Cash drag (central question for v2)", [
        f"Avg cash-reserve fraction (live phase): {avg_reserve_frac:.2%}",
        f"Hypothetical foregone $ if every Sunday's idle cash had been deployed and held to END:",
        f"  ${foregone:+,.2f}   (upper bound — no signal cost in the counterfactual)",
        f"Forced-deploy events (reserve > {RESERVE_CAP*100:.0f}%): "
            f"{int((live['forced_usd'] > 0).sum())}",
    ]))

    # ---- 3. Per-cell forward returns ----
    for h in (1, 4, 12):
        live[f"fwd_{h}w"] = live["date"].apply(lambda ts: fwd_return(weekly, ts, h))
    by_cell = (live.groupby(["trend", "funding"])
               .agg(n=("f", "size"),
                    f=("f", "first"),
                    fwd_1w=("fwd_1w", "mean"),
                    fwd_4w=("fwd_4w", "mean"),
                    fwd_12w=("fwd_12w", "mean"))
               .reset_index())
    for c in ("fwd_1w", "fwd_4w", "fwd_12w"):
        by_cell[c] = by_cell[c].map(lambda x: f"{x:+.2%}" if pd.notna(x) else "")
    findings.append(("3. Per-cell forward returns (BTC fwd return after each weekly decision)",
                     [df_to_md(by_cell)]))

    # ---- 4. Experiment matrix ----
    trend_only_tbl = zero_nudge_table(FINAL_F)
    flipped_tbl    = flip_table(FINAL_F)

    cf = {}
    cf["v2-base"]        = v2_df
    cf["v2-trend-only"]  = simulate_v2(daily, weekly, weekly_fund,
                                       final_f_table=trend_only_tbl)[0]
    cf["v2-flip-funding"] = simulate_v2(daily, weekly, weekly_fund,
                                        final_f_table=flipped_tbl)[0]
    for cap in (0.10, 0.25, 0.40):
        cf[f"reserve={cap}"] = simulate_v2(daily, weekly, weekly_fund,
                                           reserve_cap=cap)[0]
    for fm in (0.25, 0.40, 0.60):
        cf[f"f_min={fm}"]   = simulate_v2(daily, weekly, weekly_fund,
                                          f_min=fm)[0]
    cf["B0 (control)"]    = b0_df

    cf_rows = []
    for name, df in cf.items():
        final = df["value"].iloc[-1]
        cf_rows.append({
            "arm": name,
            "final_$": round(final, 2),
            "return_%": round((final / deposited - 1) * 100, 2),
            "max_dd_%": round(max_drawdown(df["value"]) * 100, 2),
            "vs_B0_%":  round((final - b0_df["value"].iloc[-1]) / b0_df["value"].iloc[-1] * 100, 2),
        })
    cf_table = pd.DataFrame(cf_rows)
    findings.append(("4. Experiment matrix (spec §Experiment matrix)", [df_to_md(cf_table)]))

    # ---- 5. Signal-quality CIs ----
    sig_rows = []
    for i, ts in enumerate(weekly.index):
        if ts < START or ts > END:
            continue
        t = trend_state(weekly, i)
        f = funding_state(weekly_fund, i)
        if t is None or f is None:
            continue
        sig_rows.append({
            "date": ts, "trend": t, "funding": f,
            "fund_ann": weekly_fund.iloc[i],
            "fwd_1w": fwd_return(weekly, ts, 1),
        })
    sig = pd.DataFrame(sig_rows).dropna(subset=["fwd_1w"])
    sq_lines = [f"n weekly observations (in-window, signals ready): {len(sig)}"]
    for col in ("trend", "funding"):
        sq_lines.append(f"\nBy {col}:")
        for state, grp in sig.groupby(col):
            m, lo, hi = boot_ci(grp["fwd_1w"].values)
            sq_lines.append(f"  {state:<8} n={len(grp):>3}  mean fwd_1w={m:+.2%}  "
                            f"95% CI [{lo:+.2%}, {hi:+.2%}]")
    if len(sig) > 5:
        corr = sig[["fund_ann", "fwd_1w"]].corr().iloc[0, 1]
        sq_lines.append(f"\nPearson corr(raw funding ann%, fwd_1w) = {corr:+.3f}")
    findings.append(("5. Signal quality", sq_lines))

    # ---- 6. Regime breakdown ----
    trend_by_sunday = {}
    for i, ts in enumerate(weekly.index):
        t = trend_state(weekly, i)
        if t is not None:
            trend_by_sunday[ts.normalize()] = t
    sundays = sorted(trend_by_sunday.keys())
    def trend_for(d):
        prior = [s for s in sundays if s <= d.normalize()]
        return trend_by_sunday[prior[-1]] if prior else None
    merged["trend"] = merged["date"].apply(trend_for)
    # Drop warmup (equity == 0) and compute daily returns on the contiguous
    # series before grouping — iloc[-1]/iloc[0] across a discontiguous regime
    # segment isn't a meaningful "regime return," and a leading 0 produces inf.
    reg_src = merged[(merged["b0"] > 0) & (merged["v2"] > 0)].copy()
    reg_src["b0_dr"] = reg_src["b0"].pct_change()
    reg_src["v2_dr"] = reg_src["v2"].pct_change()
    reg_src = reg_src.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (reg_src.dropna(subset=["trend", "b0_dr", "v2_dr"])
                              .groupby("trend")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "B0_daily_mean_%": round(grp["b0_dr"].mean()*100, 4),
            "v2_daily_mean_%": round(grp["v2_dr"].mean()*100, 4),
            "delta_pp":        round((grp["v2_dr"].mean() - grp["b0_dr"].mean())*100, 4),
        })
    findings.append(("6. Regime breakdown (v2 vs B0 within trend regimes)",
                     [df_to_md(pd.DataFrame(reg_rows))]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Tilt)", "",
          f"_Window: {START.date()} → {END.date()}_", ""]
    for heading, lines in findings:
        md.append(f"## {heading}\n")
        for ln in lines:
            md.append(str(ln))
            md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")

    # ---- Plot ----
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    ax = axes[0, 0]
    ax.plot(merged["date"].values, merged["gap"].values)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("v2 − B0 (USD)"); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    labels = [f"{r['trend']}+{r['funding']}" for _, r in by_cell.iterrows()]
    fwd4 = [float(s.strip("%+"))/100 if s else 0 for s in by_cell["fwd_4w"]]
    ax.bar(labels, [v*100 for v in fwd4])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.tick_params(axis="x", rotation=30)
    ax.set_title("Mean BTC fwd 4w return by policy cell (%)")

    ax = axes[1, 0]
    for name, df in cf.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.0)
    ax.set_title("Experiment matrix — equity curves")
    ax.legend(fontsize=7); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    live_dates = pd.to_datetime(live["date"])
    reserve_frac = (live["cash_after"] / live["value_after"]).values
    ax.plot(live_dates.values, reserve_frac)
    ax.axhline(RESERVE_CAP, color="red", linewidth=0.8, label=f"RESERVE_CAP={RESERVE_CAP}")
    ax.set_title("v2 cash-reserve fraction over time")
    ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(ATTRIB_PNG, dpi=120)
    plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
