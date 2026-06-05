"""
analysis_v7.py — runs strategy_v7 ("Fear-Gated Warchest") on cached BTC data.

Spec: analysis/strategies/strategy_v7.md
  - v7 is v6 with the trim proceeds REROUTED. The band-gated trim is untouched
    from v6 (sell BTC back to target_w whenever w > target_w + band). What
    changes is where the proceeds go: instead of v6's unconditional 4-week drip
    back into BTC, proceeds accumulate in a segregated **warchest** (cash) that
    only deploys when the Fear & Greed Index reads extreme fear (FNG <= 25).
  - On a fear Tuesday with no active run, a run *arms* on the current warchest
    balance: slice_size = warchest / drip_weeks, slices_remaining = drip_weeks.
    Each subsequent fear Tuesday pays out one slice. Any non-fear Tuesday
    CANCELS the run (slices_remaining -> 0); the undeployed balance waits and a
    fresh run re-slices the then-current balance when fear returns.
  - BASE: the warchest is EXCLUDED from the weight denominator (target_w is a
    target on *invested* capital). The "included" treatment is a tested variant
    living in postmortem_v7.py.

v7 reintroduces the FNG signal v6 removed — but on the BUY side. It resurrects
load_fng_daily / fng_state from common.py (dead code in v6). Per the "no code
changes to prior-version scripts" discipline, v7 carries its own simulate_v7
rather than re-flagging simulate_v5/simulate_v6. common.py is reused unchanged.

The headline expectation is *skeptical*: v5's postmortem found the sentiment
gate added nothing on the sell side, so the burden of proof is on v7 to beat
v6 and a no-signal null. This script just runs v7-base honestly; the
"does the gate earn its keep" tests live in postmortem_v7.py.

Outputs:
  - analysis/results/analysis_report_v7.md
  - analysis/output/equity_curves_v7.png
  - analysis/output/action_log_v7.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common import (
    OUTPUT_DIR, RESULTS_DIR, START, END,
    MONTHLY_DEPOSIT, FEE_RATE,
    load_btc_hourly, daily_closes,
    last_friday_deposit_dates, daterange, price_on,
    simulate_control, summarize_arm, df_to_md,
    load_fng_daily, fng_state,
)


VERSION = 7
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# v7-base parameters (pinned). Trim half inherited from v6 unchanged.
TARGET_W       = 0.92
BAND           = 0.05   # trim when w > target_w + band  (= 0.97)
FNG_BUY_THR    = 25     # deploy warchest only when daily FNG <= this (extreme fear)
DRIP_WEEKS     = 4      # how many weekly slices a TRIGGERED warchest run spreads over


def simulate_v7(daily_px, daily_fng,
                target_w=TARGET_W, band=BAND,
                fng_buy_threshold=FNG_BUY_THR, drip_weeks=DRIP_WEEKS,
                include_warchest_in_w=False,
                null_no_signal=False, null_drip_weeks=12,
                backstop_k=None,
                disable_trim=False):
    """Strategy v7 'Fear-Gated Warchest'.

    Tuesday loop, in spec order (Mechanics §):
      1. deploy any free DEPOSIT cash like B0 (the warchest is NOT touched here)
      2. compute weight. BASE: w = btc_value / (btc_value + cash)  [warchest excluded].
         `include_warchest_in_w=True` uses btc_value + cash + warchest instead.
      3. band-gated trim (unchanged from v6): if w > target_w + band, sell BTC
         down to target_w; proceeds go to the WARCHEST (not a drip).
      4. fear-gated warchest deployment (computed AFTER the trim, so a fear-day
         warchest buy cannot trigger a same-Tuesday trim of itself):
           fear = (FNG_today <= fng_buy_threshold)
           if not fear:                      slices_remaining = 0   # cancel any run
           if fear and slices==0 and wc>0:   arm a fresh run on the current balance
           if fear and slices>0  and wc>0:   pay out one slice

    Variant switches (all default to base behavior):
      - include_warchest_in_w: the "warchest-in-denominator" matrix variant.
        Self-damps trims (chest grows -> w reads lower -> fewer trims).
      - null_no_signal: the KEY null. Warchest deploys on a fixed `null_drip_weeks`
        drip with NO FNG gate and NO cancellation. Tests whether the fear-gate
        beats a dumb slow clock (mirror of v5's failed criterion, on the buy side).
      - backstop_k: anti-idle floor. If the warchest has sat undeployed for
        > K weeks, force one slice regardless of FNG. None = no backstop.
      - disable_trim: ablation; with no trims the warchest never fills (-> B0).
    """
    deposits = set(last_friday_deposit_dates(START, END))
    cash = 0.0
    btc  = 0.0
    warchest = 0.0          # segregated trim proceeds; only deploys on fear (or null clock)
    slices_remaining = 0
    slice_size = 0.0
    weeks_idle = 0          # weeks the (non-empty) warchest has gone undeployed (backstop)
    total_deposited = 0.0
    harvest_total   = 0.0   # gross-of-redeploy realized trim proceeds (net of fee)
    fee_total       = 0.0
    rows, action_log = [], []

    def buy(usd, px):
        """Spend `usd` of cash-like money on BTC; returns btc bought. Mutates fee_total."""
        nonlocal btc, fee_total
        bought = (usd * (1 - FEE_RATE)) / px
        fee_total += usd * FEE_RATE
        btc += bought
        return bought

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
                tags = []
                trade_usd = 0.0
                fng_today = None

                # 1. deploy free DEPOSIT cash (B0-style). Warchest untouched.
                if cash > 0:
                    spend = cash
                    buy(spend, px)
                    cash = 0.0
                    tags.append("deploy")
                    trade_usd += spend

                # 2. weight after the deposit deploy
                btc_value = btc * px
                if include_warchest_in_w:
                    total = btc_value + cash + warchest
                else:
                    total = btc_value + cash      # base: warchest excluded
                w = (btc_value / total) if total > 0 else 0.0

                # 3. band-gated trim (unchanged from v6) -> proceeds to WARCHEST
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
                            warchest += proceeds_net
                        tags.append("trim")
                        trade_usd -= proceeds_net

                # 4. warchest deployment
                deployed = 0.0
                if null_no_signal:
                    # fixed slow drip, no FNG, no cancellation
                    if slices_remaining == 0 and warchest > 0:
                        slice_size = warchest / null_drip_weeks
                        slices_remaining = null_drip_weeks
                    if slices_remaining > 0 and warchest > 0:
                        amount = min(slice_size, warchest)
                        buy(amount, px)
                        warchest -= amount
                        slices_remaining -= 1
                        deployed = amount
                else:
                    fng_today = fng_state(daily_fng, dnorm, threshold=fng_buy_threshold)
                    fear = (fng_today is not None) and (fng_today <= fng_buy_threshold)

                    if not fear:
                        slices_remaining = 0          # cancel any active run
                    if fear and slices_remaining == 0 and warchest > 0:
                        slice_size = warchest / drip_weeks
                        slices_remaining = drip_weeks
                    if fear and slices_remaining > 0 and warchest > 0:
                        amount = min(slice_size, warchest)
                        buy(amount, px)
                        warchest -= amount
                        slices_remaining -= 1
                        deployed = amount

                    # anti-idle backstop: force a slice if the chest has sat too long
                    if backstop_k is not None:
                        if deployed > 0:
                            weeks_idle = 0
                        elif warchest > 0:
                            weeks_idle += 1
                            if weeks_idle > backstop_k:
                                amount = min(warchest / drip_weeks, warchest)
                                buy(amount, px)
                                warchest -= amount
                                deployed = amount
                                weeks_idle = 0
                                tags.append("backstop")

                if deployed > 0:
                    tags.append("warchest_buy")
                    trade_usd += deployed

                action_kind = "+".join(tags) if tags else "hold"
                action_log.append({
                    "date": d, "close": px,
                    "btc_weight": round(w, 4),
                    "fng": fng_today if fng_today is not None else "",
                    "warchest": round(warchest, 4),
                    "slices_remaining": slices_remaining,
                    "action": action_kind,
                    "trade_usd": round(trade_usd, 4),
                    "deployed_usd": round(deployed, 4),
                    "cash_after": round(cash, 4),
                    "btc_after": btc,
                    "value_after": cash + warchest + btc * px,
                })
                action_today = (action_today + f"+{action_kind}").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({
            "date": d, "cash": cash, "btc": btc, "price": px,
            "value": cash + warchest + btc * px,
            "warchest": warchest,
            "action": action_today,
        })

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["harvest_total"]   = harvest_total
    df.attrs["fee_total"]       = fee_total
    return df, log


def warchest_buy_events(action_log):
    """One row per warchest deployment, with the FNG that triggered it."""
    if not len(action_log):
        return pd.DataFrame()
    buys = action_log[action_log["action"].str.contains("warchest_buy", na=False)].copy()
    if not len(buys):
        return pd.DataFrame()
    return buys[["date", "close", "fng", "warchest", "deployed_usd"]].rename(
        columns={"deployed_usd": "usd_deployed"}
    )


def trim_events(action_log):
    """One row per trim. No FNG gate on the sell side — v7's trim is v6's trim."""
    if not len(action_log):
        return pd.DataFrame()
    trims = action_log[action_log["action"].str.contains("trim", na=False)].copy()
    if not len(trims):
        return pd.DataFrame()
    return trims[["date", "close", "btc_weight", "trade_usd"]].rename(
        columns={"trade_usd": "usd_trimmed"}
    )


def plot_curves(arms, warchest_series=None):
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
    for name, df in arms.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.3)
    ax.set_title(f"strategy_v{VERSION} (Fear-Gated Warchest) vs B0 — BTC, {START.date()} to {END.date()}")
    ax.set_ylabel("Portfolio value (USD)")
    ax.legend(); ax.grid(alpha=0.3)
    if warchest_series is not None:
        ax2.fill_between(warchest_series.index.values, warchest_series.values,
                         color="tab:orange", alpha=0.5)
        ax2.set_ylabel("Warchest (USD)")
        ax2.set_title("Idle warchest balance — grows during bulls, drains into fear windows")
        ax2.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


def write_report(summary, trims_df, buys_df, n_months,
                 harvest_total, fee_total, warchest_end, max_warchest):
    n_trims = len(trims_df)
    n_buys  = len(buys_df)
    md = [
        f"# Backtest report — strategy_v{VERSION} (Fear-Gated Warchest)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  band: +{BAND}  (trim threshold w > {TARGET_W + BAND:.2f})  — **unchanged from v6**",
        f"- fng_buy_threshold: {FNG_BUY_THR}  (deploy warchest only on FNG ≤ {FNG_BUY_THR})  ·  drip_weeks: {DRIP_WEEKS}",
        f"- Warchest accounting: **excluded** from the weight denominator (base).",
        f"- Decision cadence: weekly Tuesday.  Deposit: ${int(MONTHLY_DEPOSIT)} last Friday of month.",
        f"- Fee per trade: {FEE_RATE*100:.2f}%.  No cash yield (penalizes the idle warchest — see caveats).",
        "",
        "v7 keeps v6's band-gated trim **exactly**, but reroutes the proceeds: instead",
        "of v6's unconditional 4-week drip back into BTC, the cash accumulates in a",
        "segregated warchest that only deploys when the Fear & Greed Index reads extreme",
        "fear (≤ 25). It is a directional bet — *fear is a better-than-random time to",
        "buy* — and it should be judged on whether that bet beats (a) a no-signal slow",
        "drip and (b) just dripping straight back in (v6). See `postmortem_report_v7.md`.",
        "",
        "## Headline results (standard scoreboard)",
        "",
        df_to_md(summary),
        "",
        "## v7 warchest scorecard",
        "",
        f"- Distinct trim events:        **{n_trims}**  (continuous by design — same machine as v6)",
        f"- Distinct warchest deploys:   **{n_buys}**  (only fire inside FNG ≤ {FNG_BUY_THR} windows)",
        f"- Realized harvest (to chest): ${harvest_total:,.2f}",
        f"- Warchest balance at window end: ${warchest_end:,.2f}  (idle cash never redeployed)",
        f"- Peak warchest balance:       ${max_warchest:,.2f}",
        f"- Cumulative fees paid:        ${fee_total:,.2f}",
        "",
    ]
    if n_buys:
        md += ["Warchest deployments (date + FNG at firing; `warchest` is the balance",
               "*after* the slice was paid out):", "",
               df_to_md(buys_df.assign(
                   usd_deployed=buys_df["usd_deployed"].round(2),
                   warchest=buys_df["warchest"].round(2))), ""]
    else:
        md += ["_No warchest deployment fired in this window — FNG never reached the",
               "threshold while the chest held cash. The chest sat idle; v7 underperforms",
               "v6 by exactly the opportunity cost of that idle cash._", ""]
    md += [
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control). The headline comparison.",
        "- The decisive comparisons (vs v6, and vs a no-signal slow drip) live in the",
        "  postmortem — v7's whole justification is whether the fear-gate earns its keep.",
        "",
        "## Honest caveats (echoed from strategy_v7.md)",
        "",
        "- **Almost nothing to calibrate the buy-gate against.** The trim harvests across",
        "  the whole cycle, but the *buy* half only acts in extreme-fear windows — over",
        "  2020→2026 there are essentially two (2020 COVID, 2022 bear). The threshold is",
        "  fit to ~2 events; treat any in-sample-optimal value with heavy suspicion.",
        "- **v7 reintroduces a directional call after v6 worked to remove one.** The prior",
        "  from v5 is unfavourable: the sentiment gate did not earn its keep on the sell",
        "  side. v7 must overcome that with evidence, not assume the buy side is different.",
        "- **FNG ≤ 25 is largely a proxy for 'price already fell a lot.'** The buy-gate may",
        "  be little more than a drawdown-from-high trigger with an extra data dependency.",
        "- **Idle-cash drag is worse than v6's, and cash yield = 0 punishes it harder.** The",
        "  warchest can sit for months between fear episodes; at 0% that is pure opportunity",
        "  cost. Real-world v7 (warchest in T-bills/stables at ~4–5%) is meaningfully better",
        "  than this backtest shows.",
        "- **Excluding the warchest from the denominator is not free.** target_w = 0.92 is a",
        "  target on *invested* capital; a growing chest does NOT damp future trims, so",
        "  trims and warchest growth mildly reinforce each other. The included-denominator",
        "  variant in the postmortem shows how much this choice distorts the metrics.",
        "- **The conservative re-arm rule won't catch sharp V-bottoms.** Cancelling a run",
        "  the moment FNG recovers under-deploys into fast recoveries by design.",
        "- **Single mostly-up cycle, in-sample, ~120 weekly observations** — doubly binding",
        "  here because the buy-gate only acts in the rarest part of the sample.",
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

    v7_df, action_log = simulate_v7(daily, fng)
    b0_df             = simulate_control(daily)

    n_months  = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v7", v7_df), ("B0", b0_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival",       b0_df, deposited),
        summarize_arm("v7 Fear-Gated Warchest",     v7_df, deposited,
                      action_log=action_log),
    ])
    print(summary.to_string(index=False))

    trims_df = trim_events(action_log)
    buys_df  = warchest_buy_events(action_log)
    warchest_end = float(v7_df["warchest"].iloc[-1])
    max_warchest = float(v7_df["warchest"].max())
    print(f"Trims: {len(trims_df)}  ·  warchest deploys: {len(buys_df)}  ·  "
          f"warchest end: ${warchest_end:,.2f}  ·  peak: ${max_warchest:,.2f}  ·  "
          f"fees: ${v7_df.attrs['fee_total']:,.2f}")
    if len(buys_df):
        print(buys_df.to_string(index=False))

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    warchest_series = v7_df.set_index("date")["warchest"]
    plot_curves({"B0 deploy-on-arrival": b0_df,
                 "v7 Fear-Gated Warchest": v7_df},
                warchest_series=warchest_series)
    write_report(summary, trims_df, buys_df, n_months,
                 v7_df.attrs["harvest_total"], v7_df.attrs["fee_total"],
                 warchest_end, max_warchest)


if __name__ == "__main__":
    main()
