"""
analysis_v2.py — runs strategy_v2 ("Tilt") on cached BTC data.

Spec: analysis/strategies/strategy_v2.md
  - Always deploy, never sell. Deployment fraction f per (trend, funding) cell.
  - F_MIN floor, RESERVE_CAP ceiling on cash-reserve as % of portfolio.
  - Warmup period mirrors B0 (deposit Fri, deploy 100% next Tue close).

Benchmarks (per spec §Benchmarks):
  - B0 = deploy-on-arrival = the control account = the real bar.
  - B2 = v1 strategy re-simulated on the SAME deposit calendar
         (spec §Implementation notes 1 — apples-to-apples capital timing).
  - (No B1 — weekly flat DCA is dropped from the project.)

Outputs:
  - analysis/results/analysis_report_v2.md
  - analysis/output/equity_curves_v2.png
  - analysis/output/action_log_v2.csv
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
    trend_state, funding_state, signals_ready,
    last_friday_deposit_dates, next_tuesday, daterange, price_on,
    simulate_control, max_drawdown, sharpe_sortino, summarize_arm, df_to_md,
)


def df_to_md_safe(df):
    return df_to_md(df) if df is not None and len(df) else "_empty_"

VERSION = 2

EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# ---------- Spec constants ----------
F_MIN        = 0.40
RESERVE_CAP  = 0.25  # cash reserve ceiling as fraction of portfolio_value

# Full 6-cell table (encoded directly because Down+Hot is -0.10, not -0.15).
FINAL_F = {
    ("Up",   "Cold"):    1.00,
    ("Up",   "Neutral"): 0.85,
    ("Up",   "Hot"):     0.70,
    ("Down", "Cold"):    0.65,
    ("Down", "Neutral"): 0.50,
    ("Down", "Hot"):     0.40,
}

# v1 POLICY for B2 (inlined; v1's analysis.py is left untouched).
V1_POLICY = {
    ("Up",   "Cold"):    "Buy100",
    ("Up",   "Neutral"): "Buy50",
    ("Up",   "Hot"):     "Hold",
    ("Down", "Cold"):    "Buy50",
    ("Down", "Neutral"): "Hold",
    ("Down", "Hot"):     "Sell50",
}
V1_PATIENCE_LIMIT = 4


# ---------- v2 simulator ----------
def simulate_v2(daily_px, weekly_px, weekly_fund,
                final_f_table=None, f_min=F_MIN, reserve_cap=RESERVE_CAP):
    """Strategy v2 'Tilt'. Deposits last Friday of each month; weekly Sunday-close decisions.

    During warmup (until both signals are available), mirror B0: deploy 100% on
    the next-Tuesday close after each deposit (spec §Implementation notes 3).
    """
    if final_f_table is None:
        final_f_table = FINAL_F

    deposits     = set(last_friday_deposit_dates(START, END))
    week_idx_by_date = {ts.normalize(): i for i, ts in enumerate(weekly_px.index)}

    # Pre-compute, for each deposit, which Sunday it first becomes spendable.
    # During warmup we will instead deploy that deposit on the next Tuesday.
    tue_buys = {}  # date -> usd (only used in warmup)
    for d in deposits:
        t = next_tuesday(d)
        if t <= END.normalize():
            tue_buys[t] = tue_buys.get(t, 0.0) + MONTHLY_DEPOSIT

    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    rows, action_log = [], []
    warmup_active = True

    # Track when we first see signals ready -> end warmup.
    for d in daterange(START, END):
        action_today = ""
        # 1. Deposit
        if d.normalize() in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"

        # 2. Sunday weekly decision
        i = week_idx_by_date.get(d.normalize())
        if i is not None:
            ready = signals_ready(weekly_px, weekly_fund, i)
            if ready:
                warmup_active = False
                t = trend_state(weekly_px, i)
                f_state = funding_state(weekly_fund, i)
                f = final_f_table[(t, f_state)]
                f = max(f_min, min(1.0, f))

                px = weekly_px.iloc[i]
                deploy = f * cash
                if deploy > 0:
                    btc += (deploy * (1 - FEE_RATE)) / px
                    cash -= deploy

                # Force-deploy any reserve above RESERVE_CAP * portfolio_value.
                portfolio_value = cash + btc * px
                if portfolio_value > 0 and cash > reserve_cap * portfolio_value:
                    excess = cash - reserve_cap * portfolio_value
                    btc += (excess * (1 - FEE_RATE)) / px
                    cash -= excess
                    forced = excess
                else:
                    forced = 0.0

                action_log.append({
                    "date": d, "close": px, "trend": t, "funding": f_state, "f": f,
                    "deploy_usd": round(deploy, 4), "forced_usd": round(forced, 4),
                    "cash_after": cash, "btc_after": btc,
                    "value_after": cash + btc * px,
                    "phase": "live",
                })
                action_today = (action_today + "+v2").lstrip("+")

        # 3. Warmup: deploy-on-arrival (Tuesday following each deposit)
        if warmup_active:
            spend = tue_buys.get(d.normalize(), 0.0)
            if spend > 0 and cash > 0:
                actual = min(spend, cash)
                px = price_on(daily_px, d)
                btc += (actual * (1 - FEE_RATE)) / px
                cash -= actual
                action_log.append({
                    "date": d, "close": px, "trend": None, "funding": None, "f": 1.0,
                    "deploy_usd": round(actual, 4), "forced_usd": 0.0,
                    "cash_after": cash, "btc_after": btc,
                    "value_after": cash + btc * price_on(daily_px, d),
                    "phase": "warmup",
                })
                action_today = (action_today + "+warmup_buy").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px,
                     "value": cash + btc * px, "action": action_today})

    df  = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    return df, log


# ---------- B2: v1 strategy on the new deposit calendar ----------
def simulate_v1_on_new_calendar(daily_px, weekly_px, weekly_fund):
    deposits = set(last_friday_deposit_dates(START, END))
    week_idx_by_date = {ts.normalize(): i for i, ts in enumerate(weekly_px.index)}

    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    holds = 0
    rows = []
    for d in daterange(START, END):
        if d.normalize() in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
        i = week_idx_by_date.get(d.normalize())
        if i is not None:
            t = trend_state(weekly_px, i)
            f = funding_state(weekly_fund, i)
            if t is not None and f is not None:
                natural = V1_POLICY[(t, f)]
                if natural == "Hold" and holds >= V1_PATIENCE_LIMIT:
                    action, holds = "Buy50", 0
                elif natural == "Hold":
                    action, holds = "Hold", holds + 1
                else:
                    action, holds = natural, 0
                px = weekly_px.iloc[i]
                if action == "Buy100" and cash > 0:
                    btc += (cash * (1 - FEE_RATE)) / px
                    cash = 0.0
                elif action == "Buy50" and cash > 0:
                    s = cash * 0.5
                    btc += (s * (1 - FEE_RATE)) / px
                    cash -= s
                elif action == "Sell50" and btc > 0:
                    sell = btc * 0.5
                    cash += sell * px * (1 - FEE_RATE)
                    btc -= sell
        px = price_on(daily_px, d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px,
                     "value": cash + btc * px})
    df = pd.DataFrame(rows)
    df.attrs["total_deposited"] = total_deposited
    return df


# ---------- Report ----------
def write_report(summary_df, arms, action_log, n_months):
    cell_counts = (action_log[action_log["phase"] == "live"]
                   .groupby(["trend", "funding"]).size()
                   .reset_index(name="n"))
    if len(cell_counts):
        cell_counts["f"] = cell_counts.apply(
            lambda r: FINAL_F[(r["trend"], r["funding"])], axis=1)

    live = action_log[action_log["phase"] == "live"].copy()
    avg_reserve_frac = (live["cash_after"] / live["value_after"]).mean() if len(live) else float("nan")

    md = [
        f"# Backtest report — strategy_v{VERSION} (Tilt)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- Action space: continuous f in [{F_MIN}, 1.0]; never sells.",
        f"- RESERVE_CAP: {RESERVE_CAP} of portfolio_value.",
        f"- Deposit cadence: $50 on the last Friday of each calendar month.",
        f"- Warmup: SMA{SMA_WEEKS}w + funding{FUNDING_WINDOW}w; mirrors B0 (deploy on next Tue).",
        f"- Fee per trade: {FEE_RATE*100:.2f}%",
        "",
        "## Headline results",
        "",
        summary_df.pipe(df_to_md_safe),
        "",
        "## Action stats (live-phase only)",
        "",
        f"- Live weekly decisions: {len(live)}",
        f"- Avg cash-reserve fraction: {avg_reserve_frac:.1%}",
        f"- Forced-deploy events (reserve > cap): {int((live['forced_usd'] > 0).sum())}",
        "",
        "By (trend, funding) cell:",
        "",
        cell_counts.pipe(df_to_md_safe) if len(cell_counts) else "_no live cells_",
        "",
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (the control account, the real bar).",
        "- **B2 — v1 strategy** re-simulated on the monthly-last-Friday calendar.",
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
    ax.set_title(f"strategy_v{VERSION} (Tilt) vs benchmarks — BTC, {START.date()} to {END.date()}")
    ax.set_ylabel("Portfolio value (USD)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


# ---------- Main ----------
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

    v2_df, action_log = simulate_v2(daily, weekly, weekly_fund)
    b0_df             = simulate_control(daily)
    b2_df             = simulate_v1_on_new_calendar(daily, weekly, weekly_fund)

    n_months = len(last_friday_deposit_dates(START, END))
    expected = n_months * MONTHLY_DEPOSIT
    for name, df in (("v2", v2_df), ("B0", b0_df), ("B2", b2_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - expected) < 1e-9, f"{name}: deposited {got} != expected {expected}"

    deposited = expected
    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival", b0_df, deposited),
        summarize_arm("B2 v1 (new cadence)",  b2_df, deposited),
        summarize_arm("v2 Tilt",              v2_df, deposited,
                      action_log=action_log[action_log["phase"] == "live"]),
    ])
    print(summary.to_string(index=False))

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0 deploy-on-arrival": b0_df, "B2 v1": b2_df, "v2 Tilt": v2_df})
    write_report(summary,
                 {"B0": b0_df, "B2": b2_df, "v2": v2_df},
                 action_log, n_months)


if __name__ == "__main__":
    main()
