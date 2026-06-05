"""
analysis_v6.py — runs strategy_v6 ("Band Rebalance") on cached BTC data.

Spec: analysis/strategies/strategy_v6.md
  - v6 is v5 with the Fear & Greed gate REMOVED. Trim on weight alone:
    whenever BTC's portfolio weight drifts above target_w + band, sell back
    to target_w. No sentiment signal, no euphoria gate, no directional call.
  - This is a continuous rebalancer to a target weight, not an event-driven
    harvester — it fires nearly every Tuesday by design.
  - v6-base IS the v5 `no-fng` ablation code path, so it must reproduce those
    exact numbers (return 117.41%, max DD -57.91%, Sortino 3.354, Sharpe 1.544,
    ~318 trims). That row is the regression target.

Per the "no code changes to prior-version scripts" discipline, v6 carries its
own simulate_v6 (a copy of simulate_v5 with the gate physically removed and the
FNG argument gone) rather than calling simulate_v5(..., disable_fng_gate=True).
common.py is reused unchanged; load_fng_daily/fng_state are simply not called.

Outputs:
  - analysis/results/analysis_report_v6.md
  - analysis/output/equity_curves_v6.png
  - analysis/output/action_log_v6.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, FEE_RATE,
    load_btc_hourly, daily_closes,
    last_friday_deposit_dates, next_tuesday, daterange, price_on,
    simulate_control, summarize_arm, df_to_md,
)


VERSION = 6
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# v6-base parameters (pinned). Inherited from v5 unchanged; no FNG threshold.
TARGET_W   = 0.92
BAND       = 0.05   # trim when w > target_w + band  (= 0.97)
DRIP_WEEKS = 4      # re-entry slices; may be an int or the sentinel "hold"


def simulate_v6(daily_px,
                target_w=TARGET_W, band=BAND, drip_weeks=DRIP_WEEKS,
                disable_trim=False):
    """Strategy v6 'Band Rebalance'.

    Tuesday loop, in spec order:
      0. drip — if a slice is due today, deploy it first
      1. deploy any remaining free cash like B0
      2. compute w AFTER the deploy step
      3. if w > target+band -> sell down to target_w  (NO sentiment gate)
      4. else hold

    `drip_weeks` controls what happens to trim proceeds:
      - int N: split into N equal slices on the next N Tuesdays (the v5 drip).
        Drip-pending sits OUT of the weight denominator (matches v5 exactly), so
        it re-inflates weight when it lands — the churn the matrix interrogates.
      - "hold": proceeds go to a held_cash bucket that is NEVER redeployed by the
        B0 step and IS counted in the weight denominator, so the position
        genuinely stays at the lower weight (the drip=hold variant).
    """
    hold_mode = (drip_weeks == "hold")

    deposits = set(last_friday_deposit_dates(START, END))
    cash = 0.0
    btc  = 0.0
    held_cash = 0.0        # only used in hold_mode; never redeployed
    drip_schedule = {}     # normalized Tuesday date -> usd to deploy
    total_deposited = 0.0
    harvest_total   = 0.0
    fee_total       = 0.0
    rows, action_log = [], []

    for d in daterange(START, END):
        dnorm = d.normalize()
        action_today = ""

        # ---- deposit (Friday) ----
        if dnorm in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"

        # ---- Tuesday decision ----
        if d.weekday() == 1:
            px = price_on(daily_px, d)
            if px is not None and not pd.isna(px):
                action_kind = "hold"
                trade_usd   = 0.0

                # 0. drip slice due today
                drip_due = drip_schedule.pop(dnorm, 0.0)
                if drip_due > 0:
                    bought = (drip_due * (1 - FEE_RATE)) / px
                    fee_total += drip_due * FEE_RATE
                    btc += bought
                    action_kind = "drip_buy"
                    trade_usd   = drip_due

                # 1. deploy any free cash (B0-style). held_cash is untouched.
                if cash > 0:
                    spend = cash
                    bought = (spend * (1 - FEE_RATE)) / px
                    fee_total += spend * FEE_RATE
                    btc  += bought
                    cash  = 0.0
                    action_kind = "deploy" if action_kind == "hold" else "drip+deploy"
                    trade_usd  += spend

                # 2. weight after deploy. held_cash is part of the denominator
                #    (hold genuinely lowers the weight); drip-pending is not.
                btc_value = btc * px
                total = btc_value + cash + held_cash
                w = (btc_value / total) if total > 0 else 0.0

                # 3. band-gated rebalance (no sentiment gate)
                if (not disable_trim) and w > target_w + band and btc > 0:
                    target_btc = (target_w * total) / px
                    sell_btc = btc - target_btc
                    if sell_btc > 0:
                        proceeds_gross = sell_btc * px
                        fee = proceeds_gross * FEE_RATE
                        proceeds_net = proceeds_gross - fee
                        fee_total     += fee
                        harvest_total += proceeds_net
                        btc -= sell_btc
                        if proceeds_net > 0:
                            if hold_mode:
                                held_cash += proceeds_net
                            elif drip_weeks and drip_weeks > 0:
                                slice_usd = proceeds_net / drip_weeks
                                tnext = dnorm
                                for _ in range(drip_weeks):
                                    tnext = next_tuesday(tnext)
                                    drip_schedule[tnext] = drip_schedule.get(tnext, 0.0) + slice_usd
                        action_kind = "trim"
                        trade_usd   = -proceeds_net

                action_log.append({
                    "date": d, "close": px,
                    "btc_weight": round(w, 4),
                    "drip_pending": round(sum(drip_schedule.values()), 4),
                    "held_cash": round(held_cash, 4),
                    "action": action_kind,
                    "trade_usd": round(trade_usd, 4),
                    "cash_after": round(cash, 4),
                    "btc_after": btc,
                    "value_after": cash + held_cash + btc * px,
                })
                action_today = (action_today + f"+{action_kind}").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({
            "date": d, "cash": cash, "btc": btc, "price": px,
            "value": cash + held_cash + btc * px + sum(drip_schedule.values()),
            "drip_pending": sum(drip_schedule.values()),
            "held_cash": held_cash,
            "action": action_today,
        })

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["harvest_total"]   = harvest_total
    df.attrs["fee_total"]       = fee_total
    return df, log


def trim_events(action_log):
    """One row per trim. No FNG column — v6 trims on weight alone."""
    if not len(action_log):
        return pd.DataFrame()
    trims = action_log[action_log["action"] == "trim"].copy()
    if not len(trims):
        return pd.DataFrame()
    return trims[["date", "close", "btc_weight", "trade_usd"]].rename(
        columns={"trade_usd": "usd_trimmed"}
    )


def plot_curves(arms):
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, df in arms.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.3)
    ax.set_title(f"strategy_v{VERSION} (Band Rebalance) vs B0 — BTC, {START.date()} to {END.date()}")
    ax.set_ylabel("Portfolio value (USD)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


def write_report(summary, trims_df, n_months, harvest_total, fee_total):
    n_trims = len(trims_df)
    md = [
        f"# Backtest report — strategy_v{VERSION} (Band Rebalance)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  band: +{BAND}  (trim threshold w > {TARGET_W + BAND:.2f})",
        f"- drip_weeks: {DRIP_WEEKS}  ·  **no Fear & Greed gate** — trim on weight alone.",
        f"- Decision cadence: weekly Tuesday.  Deposit: ${int(MONTHLY_DEPOSIT)} last Friday of month.",
        f"- Fee per trade: {FEE_RATE*100:.2f}%.  No cash yield.",
        "",
        "v6 is a **continuous rebalancer to a target weight**, not an event-driven",
        "harvester. With deposits deploying weekly and BTC mostly rising, the band",
        "trigger fires nearly every Tuesday. v6 deliberately accepts giving up return",
        "in exchange for a shallower drawdown and a better risk-adjusted profile — it",
        "is a frontier choice, **not** an attempt to match B0's return.",
        "",
        "## Headline results (standard scoreboard)",
        "",
        df_to_md(summary),
        "",
        "## v6 rebalance scorecard",
        "",
        "There is **no trim-count target** — v6 trims continuously by construction,",
        "so counting trims is meaningless. Fee drag is the relevant frequency check.",
        "",
        f"- Distinct trim events:    **{n_trims}**  (continuous by design — informational)",
        f"- Realized harvest:        ${harvest_total:,.2f}",
        f"- Cumulative fees paid:    ${fee_total:,.2f}  (larger than v5's $8.17 — already baked into the headline)",
        "",
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control). The headline comparison.",
        "",
        "## Honest caveats (echoed from strategy_v6.md)",
        "",
        "- **Single mostly-up BTC cycle.** v6's drawdown advantage is earned almost",
        "  entirely in the 2022 decline and the chop; its return cost is paid in the",
        "  up-legs. ~120 weekly observations is one cycle — point estimates are wide.",
        "- **The return give-up is real and front-loaded.** v6 lags B0 during bull",
        "  runs, persistently and visibly, because every rebalance sells into a rising",
        "  market — psychologically the hardest time to hold it.",
        "- **The drip may be working against the goal.** Under near-weekly trimming the",
        "  4-week drip re-inflates weight back toward 1.0, partially undoing the cushion.",
        "  drip=4 was inherited for reproducibility, not chosen — the postmortem's",
        "  drip=hold variant tests whether removing the churn deepens the cushion.",
        "- **Cash yield = 0 specifically penalizes v6.** It holds more cash-in-transit;",
        "  real cash earns ~4–5%, so real-world v6 is somewhat better than this backtest.",
        "- **Tax is not modeled, and v6 is the strategy most exposed to it.** ~300+ trims",
        "  means ~300+ realized-gain events; in a taxable account this drag could erase",
        "  much of the edge. The single biggest check before treating v6 as live-viable.",
        "- **v6 only helps if you hold it through both directions** — through the",
        "  drawdown *and* through the bull-market lag. That is a behavioral assumption",
        "  the backtest cannot test.",
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


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    hourly = load_btc_hourly()
    daily  = daily_closes(hourly)

    v6_df, action_log = simulate_v6(daily)
    b0_df             = simulate_control(daily)

    n_months  = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v6", v6_df), ("B0", b0_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival", b0_df, deposited),
        summarize_arm("v6 Band Rebalance",    v6_df, deposited,
                      action_log=action_log),
    ])
    print(summary.to_string(index=False))

    trims_df = trim_events(action_log)
    print(f"Trims: {len(trims_df)}  ·  fees: ${v6_df.attrs['fee_total']:,.2f}")

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0 deploy-on-arrival": b0_df,
                 "v6 Band Rebalance":    v6_df})
    write_report(summary, trims_df, n_months,
                 v6_df.attrs["harvest_total"], v6_df.attrs["fee_total"])


if __name__ == "__main__":
    main()
