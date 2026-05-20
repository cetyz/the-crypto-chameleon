"""
Postmortem for analysis.py
==========================
Diagnoses *why* the signal strategy underperformed DCA. No tuning — diagnosis only.

Reuses loaders, signal functions, and constants from analysis.py.

Sections:
  1. Headline gap (strategy vs DCA over time)
  2. Per-decision attribution (forward returns by policy cell / action / patience)
  3. Cash drag / opportunity cost
  4. Counterfactual arms (policy-off, trend-only, funding-only, no-patience, no-sell)
  5. Signal quality (mean forward return by state, with bootstrap CI)
  6. Regime breakdown (Up vs Down)

Outputs: console summary, postmortem_report.md, postmortem_attribution.png.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from analysis import (
    load_btc_hourly, weekly_closes, daily_closes,
    fetch_funding, weekly_funding_annpct,
    trend_state, funding_state,
    simulate_dca, simulate_strategy,
    max_drawdown,
    POLICY, START, END, N_MONTHS, MONTHLY_DEPOSIT, FEE_RATE,
    SMA_WEEKS, PATIENCE_LIMIT,
)

HERE          = os.path.dirname(os.path.abspath(__file__))
ACTION_LOG    = os.path.join(HERE, "action_log.csv")
REPORT_MD     = os.path.join(HERE, "postmortem_report.md")
ATTRIB_PNG    = os.path.join(HERE, "postmortem_attribution.png")


# ---------- Helpers ----------
def fwd_return(weekly_px, ts, horizon_weeks):
    """BTC return from weekly close at ts to weekly close horizon_weeks later."""
    idx = weekly_px.index
    if ts not in idx:
        return np.nan
    i = idx.get_loc(ts)
    j = i + horizon_weeks
    if j >= len(idx):
        return np.nan
    return weekly_px.iloc[j] / weekly_px.iloc[i] - 1


def daterange(start, end):
    return pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")


# ---------- Counterfactual simulators ----------
def simulate_weekly_full_dca(daily_px, weekly_px):
    """Deposits monthly, buys 100% of cash every Sunday close. Isolates timing."""
    cash, btc = 0.0, 0.0
    rows = []
    week_dates = set(ts.normalize() for ts in weekly_px.index if START <= ts <= END)
    for d in daterange(START, END):
        if d.day == 1:
            cash += MONTHLY_DEPOSIT
        if d.normalize() in week_dates and cash > 0:
            px = weekly_px.loc[d.normalize()] if d.normalize() in weekly_px.index else weekly_px.asof(d)
            btc += (cash * (1 - FEE_RATE)) / px
            cash = 0.0
        px = daily_px.loc[d] if d in daily_px.index else daily_px.asof(d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px, "value": cash + btc * px})
    return pd.DataFrame(rows)


def simulate_custom_policy(daily_px, weekly_px, weekly_funding, policy_fn, use_patience=True):
    """Generic weekly-decision simulator. policy_fn(trend, funding) -> action string."""
    cash, btc = 0.0, 0.0
    holds = 0
    week_idx_by_date = {ts.normalize(): i for i, ts in enumerate(weekly_px.index)}
    rows = []
    for d in daterange(START, END):
        if d.day == 1:
            cash += MONTHLY_DEPOSIT
        if d.normalize() in week_idx_by_date:
            i = week_idx_by_date[d.normalize()]
            t = trend_state(weekly_px, i)
            f = funding_state(weekly_funding, i)
            if t is not None and f is not None:
                action = policy_fn(t, f)
                if action == "Hold" and use_patience and holds >= PATIENCE_LIMIT:
                    action = "Buy50"
                    holds = 0
                elif action == "Hold":
                    holds += 1
                else:
                    holds = 0
                px = weekly_px.iloc[i]
                if action == "Buy100" and cash > 0:
                    btc += (cash * (1 - FEE_RATE)) / px
                    cash = 0.0
                elif action == "Buy50" and cash > 0:
                    spend = cash * 0.5
                    btc += (spend * (1 - FEE_RATE)) / px
                    cash -= spend
                elif action == "Sell50" and btc > 0:
                    sell = btc * 0.5
                    cash += sell * px * (1 - FEE_RATE)
                    btc -= sell
        px = daily_px.loc[d] if d in daily_px.index else daily_px.asof(d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px, "value": cash + btc * px})
    return pd.DataFrame(rows)


# ---------- Bootstrap CI ----------
def boot_ci(x, n_boot=2000, alpha=0.05, seed=0):
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return (float(x.mean()),
            float(np.quantile(means, alpha / 2)),
            float(np.quantile(means, 1 - alpha / 2)))


# ---------- Main ----------
def main():
    if not os.path.exists(ACTION_LOG):
        raise SystemExit(f"Missing {ACTION_LOG}. Run analysis.py first.")

    hourly = load_btc_hourly()
    daily_px = daily_closes(hourly)
    weekly_px_full = weekly_closes(hourly)
    weekly_px = weekly_px_full[(weekly_px_full.index >= pd.Timestamp("2023-06-01", tz="UTC"))
                               & (weekly_px_full.index <= END)]
    funding = fetch_funding()
    weekly_fund = weekly_funding_annpct(funding, weekly_px.index)

    # Baseline arms (recompute so we have aligned series)
    dca_df = simulate_dca(daily_px)
    strat_df, _ = simulate_strategy(daily_px, weekly_px, weekly_fund)
    action_log = pd.read_csv(ACTION_LOG)
    action_log["date"] = pd.to_datetime(action_log["date"], utc=True)

    findings = []  # (heading, lines[])

    # ---- 1. Headline gap ----
    deposited = N_MONTHS * MONTHLY_DEPOSIT
    final_dca = dca_df["value"].iloc[-1]
    final_str = strat_df["value"].iloc[-1]
    merged = dca_df[["date", "value"]].rename(columns={"value": "dca"}).merge(
        strat_df[["date", "value"]].rename(columns={"value": "strat"}), on="date")
    merged["gap"] = merged["strat"] - merged["dca"]
    worst = merged.loc[merged["gap"].idxmin()]
    best  = merged.loc[merged["gap"].idxmax()]
    findings.append(("1. Headline gap", [
        f"Deposited:   ${deposited:,.2f}",
        f"DCA final:   ${final_dca:,.2f}   ({final_dca/deposited - 1:+.1%})",
        f"Strat final: ${final_str:,.2f}   ({final_str/deposited - 1:+.1%})",
        f"Gap (strat - dca): ${final_str - final_dca:+,.2f}",
        f"Best  gap moment: {best['date'].date()}  ${best['gap']:+,.2f}",
        f"Worst gap moment: {worst['date'].date()}  ${worst['gap']:+,.2f}",
    ]))

    # ---- 2. Per-decision attribution ----
    # Forward returns from each decision week.
    weekly_px_only = weekly_px[(weekly_px.index >= START) & (weekly_px.index <= END)]
    for h in (1, 4, 12):
        action_log[f"fwd_{h}w"] = action_log["date"].apply(
            lambda ts: fwd_return(weekly_px_only, ts, h))

    by_cell = action_log.groupby(["trend", "funding"]).agg(
        n=("final", "size"),
        fwd_1w=("fwd_1w", "mean"),
        fwd_4w=("fwd_4w", "mean"),
        fwd_12w=("fwd_12w", "mean"),
    ).reset_index()
    by_cell["natural"] = by_cell.apply(lambda r: POLICY[(r["trend"], r["funding"])], axis=1)
    by_cell = by_cell[["trend", "funding", "natural", "n", "fwd_1w", "fwd_4w", "fwd_12w"]]

    by_action = action_log.groupby("final").agg(
        n=("final", "size"),
        fwd_1w=("fwd_1w", "mean"),
        fwd_4w=("fwd_4w", "mean"),
        fwd_12w=("fwd_12w", "mean"),
    ).reset_index()

    pat = action_log[action_log["patience_fire"] == True]
    pat_line = (f"{len(pat)} patience-forced buys; mean fwd 4w = "
                f"{pat['fwd_4w'].mean():+.2%}" if len(pat) else "0 patience fires")

    findings.append(("2. Per-decision attribution (mean BTC fwd-return after each decision)", [
        "By policy cell:",
        by_cell.to_string(index=False, float_format=lambda x: f"{x:+.2%}" if isinstance(x, float) else str(x)),
        "",
        "By executed action:",
        by_action.to_string(index=False, float_format=lambda x: f"{x:+.2%}" if isinstance(x, float) else str(x)),
        "",
        f"Patience override: {pat_line}",
    ]))

    # ---- 3. Cash drag ----
    cash_days   = strat_df["cash"].sum()  # USD-days (daily steps)
    pct_in_cash = (strat_df["cash"] / strat_df["value"].replace(0, np.nan)).mean()
    # "If idle cash had been deployed at the start of each week" — quick approximation:
    # at every Sunday, hypothetically deploy whatever cash sits in strat at Sunday close.
    counter_cash = strat_df.copy()
    cf_cash, cf_btc = 0.0, 0.0
    cf_values = []
    week_dates = set(ts.normalize() for ts in weekly_px.index if START <= ts <= END)
    last_strat_cash = 0.0
    for _, row in counter_cash.iterrows():
        d = row["date"]
        delta_cash = row["cash"] - last_strat_cash
        # mirror deposits/withdrawals from strat into cf account
        # net change in strat cash = deposits - spends; harder to invert cleanly.
        # Simpler: track BTC purchased per Sunday using strat's available cash at Sunday close.
        cf_values.append(np.nan)
        last_strat_cash = row["cash"]
    # Simpler cash-drag estimate: for each Sunday where strat had idle cash,
    # how much BTC could it have bought?
    sun = strat_df[strat_df["date"].apply(lambda d: d.normalize() in week_dates)].copy()
    sun["could_buy_btc"] = sun["cash"] * (1 - FEE_RATE) / sun["price"]
    # Compound forward: BTC bought on each Sunday and held to END
    end_price = strat_df["price"].iloc[-1]
    foregone = (sun["could_buy_btc"] * end_price).sum() - sun["cash"].sum()
    findings.append(("3. Cash drag", [
        f"Avg fraction of portfolio sitting in cash: {pct_in_cash:.1%}",
        f"Sum of daily USD-cash balances:            ${cash_days:,.0f} USD-days",
        f"Hypothetical foregone $ if every Sunday's idle cash had been deployed",
        f"  and held to END: ${foregone:+,.2f}",
        "(Upper bound — assumes perfect deploy with no signal cost.)",
    ]))

    # ---- 4. Counterfactual arms ----
    cf_results = {}
    cf_results["Baseline DCA ($10/Tue)"] = dca_df
    cf_results["Baseline Strategy"]       = strat_df
    cf_results["Policy-off (100% Sunday)"]= simulate_weekly_full_dca(daily_px, weekly_px)
    cf_results["Trend-only"]              = simulate_custom_policy(
        daily_px, weekly_px, weekly_fund,
        lambda t, f: "Buy100" if t == "Up" else "Hold")
    cf_results["Funding-only"]            = simulate_custom_policy(
        daily_px, weekly_px, weekly_fund,
        lambda t, f: {"Cold": "Buy100", "Neutral": "Buy50", "Hot": "Hold"}[f])
    cf_results["No-patience"]             = simulate_custom_policy(
        daily_px, weekly_px, weekly_fund,
        lambda t, f: POLICY[(t, f)], use_patience=False)
    cf_results["No-sell"]                 = simulate_custom_policy(
        daily_px, weekly_px, weekly_fund,
        lambda t, f: "Hold" if POLICY[(t, f)] == "Sell50" else POLICY[(t, f)])

    cf_rows = []
    for name, df in cf_results.items():
        final = df["value"].iloc[-1]
        mdd = max_drawdown(df["value"])
        cf_rows.append({
            "arm": name,
            "final": round(final, 2),
            "return_%": round((final / deposited - 1) * 100, 2),
            "max_dd_%": round(mdd * 100, 2),
        })
    cf_table = pd.DataFrame(cf_rows)
    findings.append(("4. Counterfactual arms", [cf_table.to_string(index=False)]))

    # ---- 5. Signal quality ----
    # Forward 1-week returns for every in-window weekly observation.
    sig_rows = []
    for i, ts in enumerate(weekly_px.index):
        if ts < START or ts > END:
            continue
        t = trend_state(weekly_px, i)
        f = funding_state(weekly_fund, i)
        if t is None or f is None:
            continue
        sig_rows.append({
            "date": ts, "trend": t, "funding": f,
            "fund_ann": weekly_fund.iloc[i],
            "fwd_1w": fwd_return(weekly_px, ts, 1),
        })
    sig = pd.DataFrame(sig_rows).dropna(subset=["fwd_1w"])

    sq_lines = [f"n weekly observations: {len(sig)}"]
    for col in ("trend", "funding"):
        sq_lines.append(f"\nBy {col}:")
        for state, grp in sig.groupby(col):
            m, lo, hi = boot_ci(grp["fwd_1w"].values)
            sq_lines.append(f"  {state:<8} n={len(grp):>3}  mean fwd_1w={m:+.2%}  "
                            f"95% CI [{lo:+.2%}, {hi:+.2%}]")
    # Correlation of raw funding ann% with fwd 1w return
    if len(sig) > 5:
        corr = sig[["fund_ann", "fwd_1w"]].corr().iloc[0, 1]
        sq_lines.append(f"\nPearson corr(raw funding ann%, fwd_1w) = {corr:+.3f}")
    findings.append(("5. Signal quality", sq_lines))

    # ---- 6. Regime breakdown ----
    # Tag each daily row of strat_df + dca_df with prevailing trend state from
    # the most recent Sunday.
    trend_by_sunday = {}
    for i, ts in enumerate(weekly_px.index):
        t = trend_state(weekly_px, i)
        if t is not None:
            trend_by_sunday[ts.normalize()] = t

    sundays = sorted(trend_by_sunday.keys())
    def trend_for(d):
        # find most recent Sunday <= d
        prior = [s for s in sundays if s <= d.normalize()]
        return trend_by_sunday[prior[-1]] if prior else None

    merged["trend"] = merged["date"].apply(trend_for)
    reg_rows = []
    for state, grp in merged.dropna(subset=["trend"]).groupby("trend"):
        # daily pct changes within each regime
        dca_ret  = grp["dca"].pct_change().dropna()
        str_ret  = grp["strat"].pct_change().dropna()
        reg_rows.append({
            "regime": state,
            "days": len(grp),
            "dca_total_%":   round((grp["dca"].iloc[-1]/grp["dca"].iloc[0] - 1)*100, 2)
                              if len(grp) > 1 and grp["dca"].iloc[0] > 0 else np.nan,
            "strat_total_%": round((grp["strat"].iloc[-1]/grp["strat"].iloc[0] - 1)*100, 2)
                              if len(grp) > 1 and grp["strat"].iloc[0] > 0 else np.nan,
        })
    findings.append(("6. Regime breakdown (strat vs dca within trend regimes)",
                     [pd.DataFrame(reg_rows).to_string(index=False)]))

    # ---- Render console + markdown ----
    md = ["# Postmortem report", ""]
    for heading, lines in findings:
        print(f"\n=== {heading} ===")
        md.append(f"## {heading}\n")
        for ln in lines:
            print(ln)
            md.append("```")
            md.append(str(ln))
            md.append("```")
        md.append("")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nSaved {REPORT_MD}")

    # ---- Plot ----
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    # (a) gap over time
    ax = axes[0, 0]
    ax.plot(merged["date"], merged["gap"])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Strategy − DCA (USD)")
    ax.grid(alpha=0.3)
    # (b) per-cell mean fwd 4w
    ax = axes[0, 1]
    cells = by_cell.copy()
    cells["label"] = cells["trend"] + "+" + cells["funding"]
    ax.bar(cells["label"], cells["fwd_4w"] * 100)
    ax.set_title("Mean BTC fwd 4w return by policy cell (%)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.tick_params(axis="x", rotation=30)
    # (c) counterfactual equity curves
    ax = axes[1, 0]
    for name, df in cf_results.items():
        ax.plot(df["date"], df["value"], label=name, linewidth=1.1)
    ax.set_title("Counterfactual equity curves")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    # (d) by action fwd 4w
    ax = axes[1, 1]
    ax.bar(by_action["final"], by_action["fwd_4w"] * 100)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Mean BTC fwd 4w return by executed action (%)")
    plt.tight_layout()
    plt.savefig(ATTRIB_PNG, dpi=120)
    plt.close()
    print(f"Saved {ATTRIB_PNG}")


if __name__ == "__main__":
    main()
