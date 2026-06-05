"""
analysis_v5.py — runs strategy_v5 ("Greed-Gated Trim") on cached BTC data.

Spec: analysis/strategies/strategy_v5.md
  - B0-style deploy-on-arrival as the spine.
  - Rare trim gated by BOTH band-exceedance AND Fear & Greed Index >= 90.
  - Trim proceeds drip back into BTC over `drip_weeks` Tuesdays
    (separate bucket from `cash`, so they don't get immediately re-deployed).

Outputs:
  - analysis/results/analysis_report_v5.md
  - analysis/output/equity_curves_v5.png
  - analysis/output/action_log_v5.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, FEE_RATE,
    load_btc_hourly, daily_closes, weekly_closes,
    last_friday_deposit_dates, next_tuesday, daterange, price_on,
    simulate_control, summarize_arm, df_to_md,
    load_fng_daily, fng_state,
)


VERSION = 5
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# v5-base parameters (pinned)
TARGET_W       = 0.92
BAND           = 0.05   # trim when w > target_w + band
FNG_TRIM_THR   = 90     # AND daily FNG >= this
DRIP_WEEKS     = 4      # re-entry slices


def simulate_v5(daily_px, daily_fng,
                target_w=TARGET_W, band=BAND,
                fng_trim_threshold=FNG_TRIM_THR, drip_weeks=DRIP_WEEKS,
                disable_fng_gate=False, disable_trim=False):
    """Strategy v5 'Greed-Gated Trim'.

    Tuesday loop, in spec order:
      0. drip — if a slice is due today, deploy it first
      1. deploy any remaining free cash like B0
      2. compute w AFTER the deploy step
      3. if w > target+band AND fng >= threshold -> sell down to target_w,
         split proceeds into drip_weeks equal slices on subsequent Tuesdays
      4. else hold
    """
    deposits = set(last_friday_deposit_dates(START, END))
    cash = 0.0
    btc  = 0.0
    drip_schedule = {}   # normalized Tuesday date -> usd to deploy
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

                # 1. deploy any free cash (B0-style)
                if cash > 0:
                    spend = cash
                    bought = (spend * (1 - FEE_RATE)) / px
                    fee_total += spend * FEE_RATE
                    btc  += bought
                    cash  = 0.0
                    # combine action label if we already dripped
                    action_kind = "deploy" if action_kind == "hold" else "drip+deploy"
                    trade_usd  += spend

                # 2. weight after deploy
                btc_value = btc * px
                total = btc_value + cash
                w = (btc_value / total) if total > 0 else 0.0
                fng_today = fng_state(daily_fng, dnorm, threshold=fng_trim_threshold)

                # 3. signal-gated trim
                fng_ok = disable_fng_gate or (fng_today is not None
                                              and fng_today >= fng_trim_threshold)
                if (not disable_trim) and w > target_w + band and fng_ok and btc > 0:
                    target_btc = (target_w * total) / px
                    sell_btc = btc - target_btc
                    if sell_btc > 0:
                        proceeds_gross = sell_btc * px
                        fee = proceeds_gross * FEE_RATE
                        proceeds_net = proceeds_gross - fee
                        fee_total     += fee
                        harvest_total += proceeds_net
                        btc -= sell_btc
                        # split into drip_weeks slices on subsequent Tuesdays
                        if drip_weeks > 0 and proceeds_net > 0:
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
                    "fng": fng_today if fng_today is not None else "",
                    "drip_pending": round(sum(drip_schedule.values()), 4),
                    "action": action_kind,
                    "trade_usd": round(trade_usd, 4),
                    "cash_after": round(cash, 4),
                    "btc_after": btc,
                    "value_after": cash + btc * px,
                })
                action_today = (action_today + f"+{action_kind}").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({
            "date": d, "cash": cash, "btc": btc, "price": px,
            "value": cash + btc * px + sum(drip_schedule.values()),
            "drip_pending": sum(drip_schedule.values()),
            "action": action_today,
        })

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["harvest_total"]   = harvest_total
    df.attrs["fee_total"]       = fee_total
    return df, log


def trim_events(action_log):
    """Spec-mandated disclosure: one row per distinct trim with FNG at firing."""
    if not len(action_log):
        return pd.DataFrame()
    trims = action_log[action_log["action"] == "trim"].copy()
    if not len(trims):
        return pd.DataFrame()
    return trims[["date", "close", "btc_weight", "fng", "trade_usd"]].rename(
        columns={"trade_usd": "usd_trimmed"}
    )


def plot_curves(arms):
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, df in arms.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.3)
    ax.set_title(f"strategy_v{VERSION} (Greed-Gated Trim) vs B0 — BTC, {START.date()} to {END.date()}")
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
        f"# Backtest report — strategy_v{VERSION} (Greed-Gated Trim)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  band: +{BAND}  (trim threshold w > {TARGET_W + BAND:.2f})",
        f"- fng_trim_threshold: {FNG_TRIM_THR}  ·  drip_weeks: {DRIP_WEEKS}",
        f"- Decision cadence: weekly Tuesday.  Deposit: ${int(MONTHLY_DEPOSIT)} last Friday of month.",
        f"- Fee per trade: {FEE_RATE*100:.2f}%.  No cash yield.",
        "",
        "## Headline results (standard scoreboard)",
        "",
        df_to_md(summary),
        "",
        "## v5 trim scorecard",
        "",
        f"- Distinct trim events:    **{n_trims}**  (spec target: 2–8)",
        f"- Realized harvest:        ${harvest_total:,.2f}",
        f"- Cumulative fees paid:    ${fee_total:,.2f}",
        "",
    ]
    if n_trims:
        md += ["Trim events (spec-mandated disclosure — date + FNG at firing):", "",
               df_to_md(trims_df), ""]
    else:
        md += ["_No trim events fired in this window. v5 == B0 by construction here._", ""]
    md += [
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control). The headline comparison.",
        "",
        "## Honest caveats (echoed from strategy_v5.md)",
        "",
        "- Single mostly-up BTC cycle. FNG≥90 days may cluster around late-2021;",
        "  v5's story can collapse to 'one well-timed trim'.",
        "- FNG is composite, not orthogonal to signals we already had. Chosen for legibility.",
        "- Drip is unconditional — gives some harvest back in regimes where the trim coincides with the top.",
        "- If FNG≥90 never occurs in a cycle, v5 == B0. Feature, not bug, but worth saying.",
        "- One cycle of in-sample tuning. The matrix is the only honest defense.",
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
    fng    = load_fng_daily()

    v5_df, action_log = simulate_v5(daily, fng)
    b0_df             = simulate_control(daily)

    n_months  = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v5", v5_df), ("B0", b0_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival",      b0_df, deposited),
        summarize_arm("v5 Greed-Gated Trim",       v5_df, deposited,
                      action_log=action_log),
    ])
    print(summary.to_string(index=False))

    trims_df = trim_events(action_log)
    print(f"Trims: {len(trims_df)}")
    if len(trims_df):
        print(trims_df.to_string(index=False))

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0 deploy-on-arrival": b0_df,
                 "v5 Greed-Gated Trim":  v5_df})
    write_report(summary, trims_df, n_months,
                 v5_df.attrs["harvest_total"], v5_df.attrs["fee_total"])


if __name__ == "__main__":
    main()
