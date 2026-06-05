"""
analysis_v4.py — runs strategy_v4 ("Active Sleeve") on cached BTC data.

Spec: analysis/strategies/strategy_v4.md
  - Permanent cash sleeve fed monthly, drained weekly by dip-weighted buys.
  - Lazy trims only when far overweight. Drift redeploys if underweight.
  - Goal is visible weekly activity and divergence from B0, not return.
  - No funding/trend signals.

Benchmarks:
  - B0 — Deploy-on-arrival (control). The only comparison per spec; B3 dropped.

Outputs:
  - analysis/results/analysis_report_v4.md
  - analysis/output/equity_curves_v4.png
  - analysis/output/action_log_v4.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, FEE_RATE,
    load_btc_hourly, weekly_closes, daily_closes,
    last_friday_deposit_dates, daterange, price_on,
    simulate_control, max_drawdown, sharpe_sortino, summarize_arm, df_to_md,
)


VERSION = 4
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# v4-base parameters (pinned in the plan)
TARGET_W       = 0.85
SLEEVE_TARGET  = 0.12
UPPER_BAND     = 0.15   # trim when w > target_w + upper_band
LOWER_BAND     = 0.05   # drift-redeploy when w < target_w - lower_band
DIP_MIN        = 0.03
DIP_REF_WEEKS  = 26
DIP_CAP        = 0.25   # dip% at/above this deploys the full sleeve-slice
CURVE_DEFAULT  = "linear"
REDEPLOY_FRAC  = 0.50   # on drift_redeploy, move halfway toward target_w


def _dip_size_frac(dip_pct, curve):
    """Maps dip depth -> fraction of cash sleeve to deploy. Clamped at DIP_CAP."""
    x = max(0.0, min(dip_pct, DIP_CAP)) / DIP_CAP
    if curve == "linear":
        return x
    if curve == "convex":
        return x * x
    raise ValueError(f"unknown curve {curve!r}")


def simulate_v4(daily_px, weekly_px,
                target_w=TARGET_W, sleeve_target=SLEEVE_TARGET,
                upper_band=UPPER_BAND, lower_band=LOWER_BAND,
                dip_min=DIP_MIN, dip_ref_weeks=DIP_REF_WEEKS,
                curve=CURVE_DEFAULT, redeploy_frac=REDEPLOY_FRAC):
    """Strategy v4 'Active Sleeve'.

    Daily loop:
      - Monthly deposit lands in cash sleeve.
      - Every Tuesday, decide: trim / dip_buy / drift_redeploy / hold.
      - Trailing dip_ref_weeks-week high is computed from weekly Sunday closes
        with index <= current Tuesday.
      - Warmup: until dip_ref_weeks trailing Sundays exist, deploy any cash on
        Tuesday like B0 (so the warmup arm matches the control).
    """
    deposits = set(last_friday_deposit_dates(START, END))
    # weekly_px is Sunday-anchored. We index by normalized date for lookup,
    # and use .asof() semantics via searchsorted for "most recent Sunday <= d".
    weekly_idx = weekly_px.index  # DatetimeIndex (UTC, Sundays)

    cash = 0.0
    btc  = 0.0
    total_deposited = 0.0
    harvest_total   = 0.0
    fee_total       = 0.0
    rows, action_log = [], []

    for d in daterange(START, END):
        dnorm = d.normalize()
        action_today = ""

        # ---- deposit ----
        if dnorm in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"

        # ---- Tuesday decision ----
        if d.weekday() == 1:  # Tuesday
            px = price_on(daily_px, d)
            if px is None or pd.isna(px):
                pass
            else:
                # most-recent Sunday <= today (gives trailing weekly closes)
                pos = weekly_idx.searchsorted(dnorm, side="right") - 1
                trailing_n = pos + 1  # number of weekly closes available
                btc_value = btc * px
                total = btc_value + cash
                w = (btc_value / total) if total > 0 else 0.0

                if trailing_n < dip_ref_weeks:
                    # warmup: deploy all cash like B0
                    if cash > 0:
                        bought = (cash * (1 - FEE_RATE)) / px
                        fee_total += cash * FEE_RATE
                        spend = cash
                        btc  += bought
                        cash  = 0.0
                        action_log.append({
                            "date": d, "close": px, "btc_weight": round(w, 4),
                            "dip_pct": None, "sleeve_frac": None,
                            "action": "warmup_deploy", "trade_usd": round(spend, 4),
                            "cash_after": cash, "btc_after": btc,
                            "value_after": cash + btc * px, "phase": "warmup",
                        })
                        action_today = (action_today + "+warmup_deploy").lstrip("+")
                else:
                    lo = pos - dip_ref_weeks + 1
                    high = float(weekly_px.iloc[lo:pos + 1].max())
                    dip_pct = max(0.0, (high - px) / high) if high > 0 else 0.0
                    sleeve_frac = (cash / total) if total > 0 else 0.0

                    action_kind = "hold"
                    trade_usd   = 0.0

                    if w > target_w + upper_band and btc > 0:
                        # trim back to target_w
                        target_btc = (target_w * total) / px
                        sell_btc = btc - target_btc
                        proceeds_gross = sell_btc * px
                        fee = proceeds_gross * FEE_RATE
                        proceeds_net = proceeds_gross - fee
                        fee_total     += fee
                        harvest_total += proceeds_net
                        btc  -= sell_btc
                        cash += proceeds_net
                        action_kind = "trim"
                        trade_usd   = -proceeds_net

                    elif dip_pct >= dip_min and cash > 0:
                        size_frac = _dip_size_frac(dip_pct, curve)
                        deploy = size_frac * cash
                        if deploy > 0:
                            bought = (deploy * (1 - FEE_RATE)) / px
                            fee_total += deploy * FEE_RATE
                            btc  += bought
                            cash -= deploy
                            action_kind = "dip_buy"
                            trade_usd   = deploy

                    elif w < target_w - lower_band and cash > 0:
                        # move partway toward target_w
                        target_btc = (target_w * total) / px
                        buy_btc = max(0.0, target_btc - btc) * redeploy_frac
                        spend = buy_btc * px / (1 - FEE_RATE) if buy_btc > 0 else 0.0
                        spend = min(spend, cash)
                        if spend > 0:
                            bought = (spend * (1 - FEE_RATE)) / px
                            fee_total += spend * FEE_RATE
                            btc  += bought
                            cash -= spend
                            action_kind = "drift_redeploy"
                            trade_usd   = spend

                    action_log.append({
                        "date": d, "close": px,
                        "btc_weight": round(w, 4),
                        "dip_pct": round(dip_pct, 4),
                        "sleeve_frac": round(sleeve_frac, 4),
                        "action": action_kind,
                        "trade_usd": round(trade_usd, 4),
                        "cash_after": cash, "btc_after": btc,
                        "value_after": cash + btc * px,
                        "phase": "live",
                    })
                    action_today = (action_today + f"+{action_kind}").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px,
                     "value": cash + btc * px, "action": action_today})

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["harvest_total"]   = harvest_total
    df.attrs["fee_total"]       = fee_total
    return df, log


# ---------- v4 activity metrics ----------
def v4_activity_metrics(v4_df, action_log, b0_df):
    """Activity-focused scorecard (the actual goal per spec)."""
    live = action_log[action_log["phase"] == "live"]
    n_dec = len(live)
    n_active = int((live["action"] != "hold").sum()) if n_dec else 0
    active_pct = (n_active / n_dec * 100) if n_dec else float("nan")

    # weekly grid (Sunday-resampled) for divergence
    v4_w = v4_df.set_index("date")["value"].resample("W").last()
    b0_w = b0_df.set_index("date")["value"].resample("W").last()
    aligned = pd.concat([v4_w.rename("v4"), b0_w.rename("b0")], axis=1).dropna()
    mean_abs_value_gap = float((aligned["v4"] - aligned["b0"]).abs().mean()) \
        if len(aligned) else float("nan")

    # weight gap: B0 is ~100% BTC after first deploy. Compute weekly weights.
    def weekly_weight(df):
        s = df.set_index("date")
        tot = (s["cash"] + s["btc"] * s["price"]).resample("W").last()
        btc_val = (s["btc"] * s["price"]).resample("W").last()
        return (btc_val / tot.replace(0, np.nan))
    w_v4 = weekly_weight(v4_df)
    w_b0 = weekly_weight(b0_df)
    aligned_w = pd.concat([w_v4.rename("v4"), w_b0.rename("b0")], axis=1).dropna()
    mean_abs_weight_gap = float((aligned_w["v4"] - aligned_w["b0"]).abs().mean()) \
        if len(aligned_w) else float("nan")

    # avg sleeve fraction (live phase)
    avg_sleeve = float(live["sleeve_frac"].dropna().mean()) if n_dec else float("nan")

    counts = live["action"].value_counts().to_dict() if n_dec else {}
    return {
        "n_decisions_live":     n_dec,
        "n_active":             n_active,
        "active_weeks_%":       round(active_pct, 2),
        "mean_abs_value_gap_$": round(mean_abs_value_gap, 2),
        "mean_abs_weight_gap":  round(mean_abs_weight_gap, 4),
        "avg_sleeve_frac":      round(avg_sleeve, 4),
        "trim":                 counts.get("trim", 0),
        "dip_buy":              counts.get("dip_buy", 0),
        "drift_redeploy":       counts.get("drift_redeploy", 0),
        "hold":                 counts.get("hold", 0),
    }


def write_report(summary, activity, n_months, harvest_total, fee_total):
    md = [
        f"# Backtest report — strategy_v{VERSION} (Active Sleeve)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  sleeve_target: {SLEEVE_TARGET}",
        f"- upper_band: +{UPPER_BAND}  ·  lower_band: −{LOWER_BAND}",
        f"- dip_min: {DIP_MIN:.2%}  ·  dip_ref_weeks: {DIP_REF_WEEKS}  ·  curve: {CURVE_DEFAULT} (cap {DIP_CAP:.0%})",
        f"- Decision cadence: weekly Tuesday.  Deposit: $50 last Friday of month.",
        f"- Warmup: until {DIP_REF_WEEKS} trailing weekly closes; falls back to B0.",
        f"- Fee per trade: {FEE_RATE*100:.2f}%.  No cash yield.",
        "",
        "## Headline results (standard scoreboard)",
        "",
        df_to_md(summary),
        "",
        "## v4 activity metrics (the actual scoreboard per spec)",
        "",
        "Per strategy_v4.md, v4's job is visible weekly activity and divergence from B0,",
        "not return. Return drag is expected; treat any drawdown win as bonus.",
        "",
        df_to_md(pd.DataFrame([activity])),
        "",
        f"- Realized harvest from trims: ${harvest_total:,.2f}",
        f"- Cumulative fees paid:        ${fee_total:,.2f}",
        "",
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control). Per spec, the *only* comparison that matters here.",
        "  B3 is identical to B0 by construction and is dropped.",
        "",
        "## Honest caveats (echoed from strategy_v4.md)",
        "",
        "- This is a toy tuned to one mostly-up BTC cycle. Knobs are fit to this window.",
        "- The activity is the product, not the returns.",
        "- Dip-buying in a single bull cycle flatters itself; backtest can't show the failure mode where a dip keeps dipping.",
        "- The ~12% permanent sleeve is a standing tax on return.",
        "",
        "## Artifacts",
        "",
        f"- Equity curves: `output/equity_curves_v{VERSION}.png`",
        f"- Per-decision log: `output/action_log_v{VERSION}.csv`",
        f"- Postmortem: `results/postmortem_report_v{VERSION}.md`",
        "",
    ]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")


def plot_curves(arms):
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, df in arms.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.3)
    ax.set_title(f"strategy_v{VERSION} (Active Sleeve) vs B0 — BTC, {START.date()} to {END.date()}")
    ax.set_ylabel("Portfolio value (USD)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly = load_btc_hourly()
    daily  = daily_closes(hourly)
    # Need weekly Sundays going back DIP_REF_WEEKS before START for the warmup.
    weekly = weekly_closes(hourly)
    weekly = weekly[(weekly.index >= START - pd.Timedelta(weeks=DIP_REF_WEEKS + 4))
                    & (weekly.index <= END)]

    v4_df, action_log = simulate_v4(daily, weekly)
    b0_df             = simulate_control(daily)

    n_months  = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v4", v4_df), ("B0", b0_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival", b0_df, deposited),
        summarize_arm("v4 Active Sleeve",     v4_df, deposited,
                      action_log=action_log[action_log["phase"] == "live"]),
    ])
    print(summary.to_string(index=False))

    activity = v4_activity_metrics(v4_df, action_log, b0_df)
    print("v4 activity:", activity)

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0 deploy-on-arrival": b0_df,
                 "v4 Active Sleeve":     v4_df})
    write_report(summary, activity, n_months,
                 v4_df.attrs["harvest_total"], v4_df.attrs["fee_total"])


if __name__ == "__main__":
    main()
