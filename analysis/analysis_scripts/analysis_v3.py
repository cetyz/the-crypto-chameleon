"""
analysis_v3.py — runs strategy_v3 ("Allocation Rebalancer") on cached BTC data.

Spec: analysis/strategies/strategy_v3.md
  - target_w, band. No directional signals; sells only as rebalance.
  - Sunday weekly decision; deposits flow to underweight side by default.
  - Warmup mirrors B0 for the same window as v2 (SMA20w + funding 26w) so the
    v2 / v3 reports are comparable.

Benchmarks (per spec §Benchmarks):
  - B0 — Deploy-on-arrival (control account).
  - B2 — v1 strategy on the new calendar.
  - B3 — Buy-and-hold of v3's deposits (apples-to-apples "never rebalance").
        v3 is meant to lose less than B3 in drawdowns; raw return likely lower.

Outputs:
  - analysis/results/analysis_report_v3.md
  - analysis/output/equity_curves_v3.png
  - analysis/output/action_log_v3.csv
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
from analysis_v2 import simulate_v1_on_new_calendar


VERSION = 3
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

TARGET_W = 0.75
BAND     = 0.10


def _df_to_md_safe(df):
    return df_to_md(df) if df is not None and len(df) else "_empty_"


# ---------- v3 simulator ----------
def simulate_v3(daily_px, weekly_px, weekly_fund,
                target_w=TARGET_W, band=BAND, deposit_steer=True):
    """Strategy v3 'Allocation Rebalancer'.

    deposit_steer=True (default): deposits flow toward the underweight side via
      the normal rebalance band logic. False: deposits go 100% to BTC always
      (the v3-no-deposit-steer variant from the experiment matrix).
    """
    deposits = set(last_friday_deposit_dates(START, END))
    week_idx_by_date = {ts.normalize(): i for i, ts in enumerate(weekly_px.index)}
    tue_buys = {}
    for d in deposits:
        t = next_tuesday(d)
        if t <= END.normalize():
            tue_buys[t] = tue_buys.get(t, 0.0) + MONTHLY_DEPOSIT

    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    harvest_total = 0.0
    fee_total = 0.0
    rows, action_log = [], []
    warmup_active = True

    for d in daterange(START, END):
        action_today = ""
        if d.normalize() in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"

        i = week_idx_by_date.get(d.normalize())
        if i is not None:
            ready = signals_ready(weekly_px, weekly_fund, i)
            if ready:
                warmup_active = False
                px = weekly_px.iloc[i]
                portfolio_value = cash + btc * px
                w = (btc * px) / portfolio_value if portfolio_value > 0 else 0.0

                action_kind = "none"
                trade_usd = 0.0
                if w > target_w + band and btc > 0:
                    # trim back to target
                    target_btc = (target_w * portfolio_value) / px
                    sell_btc = btc - target_btc
                    proceeds = sell_btc * px * (1 - FEE_RATE)
                    fee_total += sell_btc * px * FEE_RATE
                    harvest_total += proceeds
                    btc  -= sell_btc
                    cash += proceeds
                    action_kind = "trim"
                    trade_usd = -proceeds
                elif w < target_w - band and cash > 0:
                    target_btc = (target_w * portfolio_value) / px
                    buy_btc = target_btc - btc
                    spend = buy_btc * px / (1 - FEE_RATE) if buy_btc > 0 else 0.0
                    spend = min(spend, cash)
                    bought = (spend * (1 - FEE_RATE)) / px
                    fee_total += spend * FEE_RATE
                    btc  += bought
                    cash -= spend
                    action_kind = "redeploy"
                    trade_usd = spend
                else:
                    # in-band: deploy this week's pending deposit toward target (if steering)
                    if deposit_steer and cash > 0:
                        # nudge weight toward target by deploying enough to hit target if possible
                        target_btc = (target_w * portfolio_value) / px
                        buy_btc = max(0.0, target_btc - btc)
                        spend_for_target = buy_btc * px / (1 - FEE_RATE)
                        spend = min(spend_for_target, cash)
                        if spend > 0:
                            bought = (spend * (1 - FEE_RATE)) / px
                            fee_total += spend * FEE_RATE
                            btc  += bought
                            cash -= spend
                            action_kind = "deposit_buy"
                            trade_usd = spend
                    elif not deposit_steer and cash > 0:
                        # variant: all deposits go to BTC, ignore band
                        bought = (cash * (1 - FEE_RATE)) / px
                        fee_total += cash * FEE_RATE
                        btc += bought
                        trade_usd = cash
                        cash = 0.0
                        action_kind = "deposit_buy"

                action_log.append({
                    "date": d, "close": px, "btc_weight": round(w, 4),
                    "action": action_kind, "trade_usd": round(trade_usd, 4),
                    "cash_after": cash, "btc_after": btc,
                    "value_after": cash + btc * px,
                    "phase": "live",
                })
                action_today = (action_today + f"+{action_kind}").lstrip("+")

        if warmup_active:
            spend = tue_buys.get(d.normalize(), 0.0)
            if spend > 0 and cash > 0:
                actual = min(spend, cash)
                px = price_on(daily_px, d)
                bought = (actual * (1 - FEE_RATE)) / px
                fee_total += actual * FEE_RATE
                btc += bought
                cash -= actual
                action_log.append({
                    "date": d, "close": px, "btc_weight": None,
                    "action": "warmup_buy", "trade_usd": round(actual, 4),
                    "cash_after": cash, "btc_after": btc,
                    "value_after": cash + btc * px,
                    "phase": "warmup",
                })
                action_today = (action_today + "+warmup_buy").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px,
                     "value": cash + btc * px, "action": action_today})

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["harvest_total"]   = harvest_total
    df.attrs["fee_total"]       = fee_total
    return df, log


# ---------- B3: buy-and-hold of v3's deposits ----------
def simulate_b3(daily_px):
    """Every deposit is immediately deployed; held forever. Same as B0 here
    because the control already deploys 100% — so B3 == B0 for our window.
    Kept as a separate function for clarity in the report."""
    return simulate_control(daily_px)


# ---------- Report ----------
def write_report(summary, action_log, n_months, harvest_total, fee_total):
    live = action_log[action_log["phase"] == "live"]
    by_action = live["action"].value_counts().rename_axis("action").reset_index(name="n")
    live_deployed = live[live["btc_weight"] > 0]
    avg_weight = live_deployed["btc_weight"].mean() if len(live_deployed) else float("nan")

    md = [
        f"# Backtest report — strategy_v{VERSION} (Allocation Rebalancer)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  band: ±{BAND}",
        f"- Rebalance-only sells (no directional sells).",
        f"- Deposit cadence: $50 on the last Friday of each calendar month.",
        f"- Warmup: SMA{SMA_WEEKS}w + funding{FUNDING_WINDOW}w; mirrors B0 (deploy on next Tue).",
        f"- Fee per trade: {FEE_RATE*100:.2f}%",
        "",
        "## Headline results",
        "",
        df_to_md(summary),
        "",
        "## Rebalance activity (live phase)",
        "",
        f"- Live weekly decisions: {len(live)}",
        f"- Avg BTC weight: {avg_weight:.2%}",
        f"- Cumulative realized harvest (cash banked from trims): ${harvest_total:,.2f}",
        f"- Cumulative fees paid: ${fee_total:,.2f}",
        "",
        "By action:",
        "",
        _df_to_md_safe(by_action),
        "",
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control).",
        "- **B2 — v1 strategy** on the new calendar.",
        "- **B3 — Buy-and-hold of v3's deposits** (the headline comparison; see spec §Benchmarks).",
        "  Note: with monthly deposits fully deployed on arrival, B3 == B0 by construction.",
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
    ax.set_title(f"strategy_v{VERSION} (Rebalancer) vs benchmarks — BTC, {START.date()} to {END.date()}")
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

    hourly  = load_btc_hourly()
    daily   = daily_closes(hourly)
    weekly  = weekly_closes(hourly)
    weekly  = weekly[(weekly.index >= START - pd.Timedelta(weeks=SMA_WEEKS + FUNDING_WINDOW + 4))
                     & (weekly.index <= END)]
    funding = fetch_funding()
    weekly_fund = weekly_funding_annpct(funding, weekly.index)

    v3_df, action_log = simulate_v3(daily, weekly, weekly_fund)
    b0_df             = simulate_control(daily)
    b2_df             = simulate_v1_on_new_calendar(daily, weekly, weekly_fund)
    b3_df             = simulate_b3(daily)  # == B0 with this deposit structure

    n_months = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v3", v3_df), ("B0", b0_df), ("B2", b2_df), ("B3", b3_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival", b0_df, deposited),
        summarize_arm("B2 v1 (new cadence)",  b2_df, deposited),
        summarize_arm("B3 buy-and-hold",      b3_df, deposited),
        summarize_arm("v3 Rebalancer",        v3_df, deposited,
                      action_log=action_log[action_log["phase"] == "live"]),
    ])
    print(summary.to_string(index=False))

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0/B3 deploy-on-arrival": b0_df,
                 "B2 v1": b2_df,
                 "v3 Rebalancer": v3_df})
    write_report(summary, action_log, n_months,
                 v3_df.attrs["harvest_total"], v3_df.attrs["fee_total"])


if __name__ == "__main__":
    main()
