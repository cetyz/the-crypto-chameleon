"""
postmortem_v3.py — diagnoses strategy_v3 vs B3.

Per spec §Honest caveat: v3's win, if any, is on the risk axis (drawdown,
Sortino). Don't expect raw return to beat B3 in a mostly-up window.

Sections:
  1. Headline: drawdown / Sortino vs B3
  2. Rebalance activity: trim count, harvest vs fees
  3. Experiment matrix (target sweep, band sweep, no-deposit-steer)
  4. Regime breakdown (Up / Down / Sideways)
  5. BTC weight over time

Outputs:
  - analysis/results/postmortem_report_v3.md
  - analysis/output/postmortem_attribution_v3.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, SMA_WEEKS, FUNDING_WINDOW,
    load_btc_hourly, weekly_closes, daily_closes,
    fetch_funding, weekly_funding_annpct,
    trend_state,
    last_friday_deposit_dates, simulate_control,
    max_drawdown, sharpe_sortino, df_to_md,
)
from analysis_v3 import (
    VERSION, TARGET_W, BAND, simulate_v3, simulate_b3,
)


REPORT_MD  = os.path.join(RESULTS_DIR, f"postmortem_report_v{VERSION}.md")
ATTRIB_PNG = os.path.join(OUTPUT_DIR,  f"postmortem_attribution_v{VERSION}.png")


def regime_for_week(weekly_px, i):
    """Up / Down / Sideways. Sideways = |close/SMA20 - 1| < 5%."""
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

    v3_df, action_log = simulate_v3(daily, weekly, weekly_fund)
    b3_df             = simulate_b3(daily)

    findings = []

    # ---- 1. Headline ----
    v3_dd = max_drawdown(v3_df["value"]) * 100
    b3_dd = max_drawdown(b3_df["value"]) * 100
    v3_sh, v3_so = sharpe_sortino(v3_df)
    b3_sh, b3_so = sharpe_sortino(b3_df)
    headline = pd.DataFrame([
        {"arm": "B3 buy-and-hold", "final_$": round(b3_df["value"].iloc[-1], 2),
         "return_%": round(b3_df["value"].iloc[-1]/deposited*100 - 100, 2),
         "max_dd_%": round(b3_dd, 2), "sharpe": round(b3_sh, 3), "sortino": round(b3_so, 3)},
        {"arm": "v3 Rebalancer",   "final_$": round(v3_df["value"].iloc[-1], 2),
         "return_%": round(v3_df["value"].iloc[-1]/deposited*100 - 100, 2),
         "max_dd_%": round(v3_dd, 2), "sharpe": round(v3_sh, 3), "sortino": round(v3_so, 3)},
    ])
    findings.append(("1. Headline — drawdown / Sortino vs B3 (the actual scoreboard)", [
        df_to_md(headline),
        "",
        f"DD shallower than B3 by:  {b3_dd - v3_dd:+.2f} pp",
        f"Sortino delta vs B3:      {v3_so - b3_so:+.3f}",
        f"Return delta vs B3:       {(v3_df['value'].iloc[-1] - b3_df['value'].iloc[-1]):+,.2f} USD",
    ]))

    # ---- 2. Rebalance activity ----
    live = action_log[action_log["phase"] == "live"].copy()
    counts = live["action"].value_counts().to_dict()
    findings.append(("2. Rebalance activity", [
        f"Trims:        {counts.get('trim', 0)}",
        f"Redeploys:    {counts.get('redeploy', 0)}",
        f"Deposit-buys: {counts.get('deposit_buy', 0)}",
        f"In-band none: {counts.get('none', 0)}",
        f"",
        f"Realized harvest (cash banked from trims): ${v3_df.attrs['harvest_total']:,.2f}",
        f"Total fees paid:                            ${v3_df.attrs['fee_total']:,.2f}",
        f"Harvest − fees:                             ${v3_df.attrs['harvest_total'] - v3_df.attrs['fee_total']:+,.2f}",
    ]))

    # ---- 3. Experiment matrix ----
    cf = {}
    cf["v3-base (75/10)"] = v3_df
    for tw in (0.60, 0.70, 0.80):
        cf[f"target={tw}"] = simulate_v3(daily, weekly, weekly_fund, target_w=tw)[0]
    for bw in (0.05, 0.10, 0.15):
        cf[f"band={bw}"]   = simulate_v3(daily, weekly, weekly_fund, band=bw)[0]
    cf["no-deposit-steer"] = simulate_v3(daily, weekly, weekly_fund, deposit_steer=False)[0]
    cf["B3 (buy-and-hold)"] = b3_df

    rows = []
    for name, df in cf.items():
        final = df["value"].iloc[-1]
        sh, so = sharpe_sortino(df)
        rows.append({
            "arm": name,
            "final_$": round(final, 2),
            "return_%": round((final/deposited - 1)*100, 2),
            "max_dd_%": round(max_drawdown(df["value"])*100, 2),
            "sortino": round(so, 3),
            "vs_B3_dd_pp": round((max_drawdown(df["value"]) - max_drawdown(b3_df["value"]))*100, 2),
        })
    findings.append(("3. Experiment matrix", [df_to_md(pd.DataFrame(rows))]))

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
    merged = (v3_df[["date", "value"]].rename(columns={"value": "v3"})
              .merge(b3_df[["date", "value"]].rename(columns={"value": "b3"}), on="date"))
    merged["regime"] = merged["date"].apply(regime_for)
    # Drop warmup days (equity == 0) before computing daily returns; otherwise
    # the first 0 -> positive step is +inf and poisons whichever regime it
    # lands in. Compute pct_change on the full series, then group.
    merged = merged[(merged["v3"] > 0) & (merged["b3"] > 0)].copy()
    merged["v3_dr"] = merged["v3"].pct_change()
    merged["b3_dr"] = merged["b3"].pct_change()
    merged = merged.replace([np.inf, -np.inf], np.nan)
    reg_rows = []
    for state, grp in (merged.dropna(subset=["regime", "v3_dr", "b3_dr"])
                             .groupby("regime")):
        reg_rows.append({
            "regime": state, "days": len(grp),
            "v3_daily_mean_%":  round(grp["v3_dr"].mean()*100, 4),
            "b3_daily_mean_%":  round(grp["b3_dr"].mean()*100, 4),
            "delta_pp":         round((grp["v3_dr"].mean() - grp["b3_dr"].mean())*100, 4),
        })
    findings.append(("4. Regime breakdown (Up / Down / Sideways)",
                     [df_to_md(pd.DataFrame(reg_rows))]))

    # ---- 5. BTC weight over time stats ----
    # Filter to rows where BTC is actually held — the first live Sunday can fire
    # before the first deposit lands, giving a spurious 0% weight.
    live_deployed = live[live["btc_weight"] > 0]
    findings.append(("5. BTC weight stats (live phase, post first deposit)", [
        f"Mean:   {live_deployed['btc_weight'].mean():.2%}",
        f"Min:    {live_deployed['btc_weight'].min():.2%}",
        f"Max:    {live_deployed['btc_weight'].max():.2%}",
        f"Target: {TARGET_W:.2%}  ·  Band: ±{BAND:.2%}",
    ]))

    # ---- Write report ----
    md = [f"# Postmortem — strategy_v{VERSION} (Rebalancer)", "",
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
    ax.plot(v3_df["date"].values, v3_df["value"].values, label="v3", linewidth=1.3)
    ax.plot(b3_df["date"].values, b3_df["value"].values, label="B3 buy-and-hold", linewidth=1.3)
    ax.set_title("v3 vs B3 — equity"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    live_dates = pd.to_datetime(live["date"]).values
    ax.plot(live_dates, live["btc_weight"].values)
    ax.axhline(TARGET_W, color="black", linewidth=0.8, label=f"target={TARGET_W}")
    ax.axhline(TARGET_W + BAND, color="red", linewidth=0.6, linestyle="--", label="band")
    ax.axhline(TARGET_W - BAND, color="red", linewidth=0.6, linestyle="--")
    ax.set_title("BTC weight over time"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1, 0]
    cum_harvest = (live["trade_usd"].where(live["trade_usd"] < 0, 0).abs().cumsum())
    ax.plot(live_dates, cum_harvest.values, label="cumulative harvest")
    ax.set_title("Cumulative trim proceeds (harvest)"); ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    reg_df = pd.DataFrame(reg_rows)
    if len(reg_df):
        x = np.arange(len(reg_df))
        width = 0.35
        ax.bar(x - width/2, reg_df["v3_daily_mean_%"], width, label="v3")
        ax.bar(x + width/2, reg_df["b3_daily_mean_%"], width, label="B3")
        ax.set_xticks(x); ax.set_xticklabels(reg_df["regime"])
        ax.set_title("Mean daily return by regime (%)"); ax.legend(); ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(ATTRIB_PNG, dpi=120)
    plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
