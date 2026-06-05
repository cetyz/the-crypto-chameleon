"""
analysis_v8.py — runs strategy_v8 ("Funded Basket") on cached BTC data.

Spec: analysis/strategies/strategy_v8.md
  - v8 is a funded BTC/cash basket held at a constant target weight by a
    *two-way* weekly rebalance. Each Tuesday: look at the whole portfolio
    (BTC + all cash, including any freshly-landed deposit) and rebalance BTC
    back to target_w — SELL when weight has drifted above target+band, BUY when
    it has drifted below target-band, HOLD inside the band. On a breach it
    corrects all the way to target (trigger on the band, correct to the centre).
  - One moving part: the rebalance. No drip, no FNG, no B0 spine. The cash side
    is a funded, standing, deliberate allocation — not a trim by-product.
  - New vs v6: v8 *buys dips* (deploys the cash sleeve as price falls). The
    permanent funded cash sleeve is a continuous drag (cash_yield = 0 here).

Per the "no code changes to prior-version scripts" discipline, v8 carries its
own simulate_v8. It is shorter than simulate_v6 (no drip queue, no held_cash,
no FNG). common.py is reused unchanged.

v8-base parameters (spec §Mechanics + param table):
  target_w = 0.90, band = 0.03 (static ±3% two-sided no-trade zone,
  rebalance-to-target on breach). The experiment-matrix headline row in the spec
  table labels "band 0" as the snap reference; the prose and param table pin the
  base band at 0.03, so 0.03 is the committed base here and band=0 is swept.

Outputs:
  - analysis/results/analysis_report_v8.md
  - analysis/output/equity_curves_v8.png
  - analysis/output/action_log_v8.csv
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
)


VERSION = 8
EQUITY_PNG     = os.path.join(OUTPUT_DIR, f"equity_curves_v{VERSION}.png")
ACTION_LOG_CSV = os.path.join(OUTPUT_DIR, f"action_log_v{VERSION}.csv")
REPORT_MD      = os.path.join(RESULTS_DIR, f"analysis_report_v{VERSION}.md")

# v8-base parameters (pinned).
TARGET_W = 0.90
BAND     = 0.03    # two-sided ±band no-trade zone; rebalance-to-target on breach


# ---- Realized-volatility band (variant) ----
# Spec §"The band: volatility-scaled variant":
#   band(t) = base_band * clamp(sigma_t / sigma_median, lo, hi)
# where sigma_t = stdev(log daily returns, trailing 30d). Use realized vol, not
# ATR — the loaders carry only a close series, so realized vol needs no new feed.
VOL_WINDOW   = 30
VOL_CLAMP_LO = 0.5
VOL_CLAMP_HI = 3.0


def realized_vol(daily_px, window=VOL_WINDOW):
    """Trailing `window`-day realized vol = stdev of log daily returns.

    Returns a Series indexed by the same daily dates as `daily_px`. The value at
    date d uses returns strictly up to and including d (no look-ahead). Early
    dates with < window observations are NaN; callers fall back to base_band.
    """
    logret = np.log(daily_px / daily_px.shift(1))
    return logret.rolling(window).std()


def band_series(daily_px, base_band, vol_scaled):
    """Per-day band width.

    - static (vol_scaled=False): constant `base_band` every day.
    - vol-scaled (vol_scaled=True): base_band * clamp(sigma_t / sigma_median,
      VOL_CLAMP_LO, VOL_CLAMP_HI). sigma_median is the full-sample median of the
      realized-vol series (an in-sample constant — flagged as such in the spec).
    """
    if not vol_scaled:
        return pd.Series(base_band, index=daily_px.index)
    sigma = realized_vol(daily_px)
    sigma_median = sigma.median()
    mult = (sigma / sigma_median).clip(lower=VOL_CLAMP_LO, upper=VOL_CLAMP_HI)
    band = base_band * mult
    return band.fillna(base_band)   # warmup days fall back to the static base


def simulate_v8(daily_px,
                target_w=TARGET_W, band=BAND,
                vol_scaled=False, cadence="weekly", two_way=True):
    """Strategy v8 'Funded Basket' — two-way band rebalance to a target weight.

    Decision loop:
      - deposit (last Friday of month): cash += 50. No deploy step; the next
        rebalance redistributes it.
      - rebalance day (Tuesday for cadence='weekly', else the first Tuesday of
        each month for cadence='monthly'):
            total        = btc*px + cash
            target_value = target_w * total
            drift        = btc*px - target_value
            if drift >  band*total:  SELL drift of BTC  (cash += drift_net)
            elif drift < -band*total and two_way:  BUY -drift of BTC (cash -= ...)
            else: HOLD
        On a breach the rebalance corrects all the way to target (centre), not to
        the band edge.

    Parameters:
      band         : the *base* band width. Static unless vol_scaled.
      vol_scaled   : if True, band width is volatility-scaled per band_series().
      cadence      : 'weekly' (every Tuesday) or 'monthly' (first Tuesday/month).
      two_way      : the v8-one-way ablation (criterion 4) when False.

    --- The one-way ablation (two_way=False) and why it is NOT a simple flag flip ---
    The spec's one-way row says "sell when over target, but never buy when under
    (cash just accrues)". Taken literally inside v8's architecture that is
    DEGENERATE: v8 is funded 100% by DCA deposits and has NO deposit-deploy step,
    so the position is bootstrapped entirely through the buy branch. A deposit
    arrives as cash -> weight drops below target -> the buy branch is the only
    thing that ever acquires BTC. Deposit-deployment and dip-buying are the *same*
    operation. Disable buying and the portfolio never holds any BTC at all (all
    cash forever) — which cannot be the meaningful contender the spec intends
    ("if one-way wins, drop the buy side").

    So the faithful, non-degenerate one-way — the spec's own "v6 with a funded
    sleeve and no drip" — must reintroduce the B0 deposit-deploy spine that v8
    proudly removed: deploy deposit cash unconditionally each rebalance, sell down
    to target on over-weight, and HOLD the proceeds in a `sleeve` that is counted
    in the weight denominator but never redeployed (so it never dip-buys). That
    makes one-way ~ v6-no-drip, and is exactly why this ablation reveals that
    "one rule" can only express the TWO-way basket — see the postmortem note. In
    two_way mode there is no `sleeve`; `cash` IS the fungible funded buffer.

    Fees: FEE_RATE per trade, charged on the traded notional. A SELL of `drift`
    dollars of BTC returns drift*(1-fee) to cash; a BUY of `-drift` dollars
    spends cash and adds drift*(1-fee)/px of BTC. cash_yield = 0 (cash idle).
    """
    band_by_day = band_series(daily_px, band, vol_scaled)

    deposits = set(last_friday_deposit_dates(START, END))
    cash = 0.0
    btc  = 0.0
    sleeve = 0.0       # one-way only: held trim proceeds, never redeployed
    total_deposited = 0.0
    buy_total  = 0.0   # gross USD bought into dips (the v6-impossible half)
    sell_total = 0.0   # gross USD sold down from over-weight
    fee_total  = 0.0
    rows, action_log = [], []

    for d in daterange(START, END):
        dnorm = d.normalize()
        action_today = ""

        # ---- deposit (Friday) — just becomes cash ----
        if dnorm in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"

        # ---- rebalance day ----
        is_rebalance_day = (d.weekday() == 1) and (
            cadence == "weekly" or _is_first_tuesday(dnorm)
        )
        if is_rebalance_day:
            px = price_on(daily_px, d)
            if px is not None and not pd.isna(px):
                b = float(band_by_day.get(dnorm, band))
                action_kind = "none"   # sentinel: summarize_arm counts non-"none" as trades
                trade_usd = 0.0

                if two_way:
                    # ---- TWO-WAY: the one rule. `cash` is the fungible buffer. ----
                    btc_value = btc * px
                    total = btc_value + cash
                    if total > 0:
                        target_value = target_w * total
                        drift = btc_value - target_value     # >0 over, <0 under
                        if drift > b * total and btc > 0:
                            # SELL down to target
                            sell_usd = min(drift, btc_value)
                            fee = sell_usd * FEE_RATE
                            btc  -= sell_usd / px
                            cash += sell_usd - fee
                            fee_total  += fee
                            sell_total += sell_usd
                            action_kind = "sell"
                            trade_usd   = -sell_usd
                        elif drift < -b * total and cash > 0:
                            # BUY up to target — deploy the cash buffer into the dip
                            buy_usd = min(-drift, cash)
                            fee = buy_usd * FEE_RATE
                            btc  += (buy_usd - fee) / px
                            cash -= buy_usd
                            fee_total += fee
                            buy_total += buy_usd
                            action_kind = "buy"
                            trade_usd   = buy_usd
                else:
                    # ---- ONE-WAY: B0 deposit-deploy spine + sell-only + held sleeve ----
                    # 1. deploy any free deposit cash (the reintroduced spine).
                    if cash > 0:
                        fee = cash * FEE_RATE
                        btc += (cash - fee) / px
                        fee_total += fee
                        buy_total += cash
                        action_kind = "buy"        # deposit-deploy, not a dip-buy
                        trade_usd   = cash
                        cash = 0.0
                    # 2. sell-only rebalance; sleeve is in the denominator, never redeployed.
                    btc_value = btc * px
                    total = btc_value + sleeve
                    if total > 0:
                        drift = btc_value - target_w * total
                        if drift > b * total and btc > 0:
                            sell_usd = min(drift, btc_value)
                            fee = sell_usd * FEE_RATE
                            btc    -= sell_usd / px
                            sleeve += sell_usd - fee
                            fee_total  += fee
                            sell_total += sell_usd
                            action_kind = "sell" if action_kind == "none" else "buy+sell"
                            trade_usd   = -sell_usd

                # weight after the rebalance, for the log/plots
                free = cash + sleeve
                w_after = (btc * px) / (btc * px + free) if (btc * px + free) > 0 else 0.0
                action_log.append({
                    "date": d, "close": px,
                    "band": round(b, 5),
                    "btc_weight_after": round(w_after, 5),
                    "action": action_kind,
                    "trade_usd": round(trade_usd, 4),
                    "cash_after": round(cash + sleeve, 4),
                    "btc_after": btc,
                    "value_after": round(cash + sleeve + btc * px, 4),
                })
                if action_kind != "none":
                    action_today = (action_today + f"+{action_kind}").lstrip("+")

        px = price_on(daily_px, d)
        rows.append({
            "date": d, "cash": cash + sleeve, "btc": btc, "price": px,
            "value": cash + sleeve + btc * px,
            "action": action_today,
        })

    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    df.attrs["total_deposited"] = total_deposited
    df.attrs["buy_total"]   = buy_total
    df.attrs["sell_total"]  = sell_total
    df.attrs["fee_total"]   = fee_total
    return df, log


def _is_first_tuesday(dnorm):
    """True if dnorm is the first Tuesday of its calendar month."""
    return dnorm.weekday() == 1 and dnorm.day <= 7


def rebalance_events(action_log):
    """One row per real trade (buy, sell, or the one-way compound buy+sell)."""
    if not len(action_log):
        return pd.DataFrame()
    trades = action_log[action_log["action"].isin(["buy", "sell", "buy+sell"])].copy()
    if not len(trades):
        return pd.DataFrame()
    return trades[["date", "close", "btc_weight_after", "action", "trade_usd"]]


def plot_curves(arms):
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, df in arms.items():
        ax.plot(df["date"].values, df["value"].values, label=name, linewidth=1.3)
    ax.set_title(f"strategy_v{VERSION} (Funded Basket) vs B0 — BTC, {START.date()} to {END.date()}")
    ax.set_ylabel("Portfolio value (USD)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


def write_report(summary, n_trades, n_buys, n_sells, n_months,
                 buy_total, sell_total, fee_total):
    md = [
        f"# Backtest report — strategy_v{VERSION} (Funded Basket)",
        "",
        f"_Window: {START.date()} → {END.date()} ({n_months} monthly deposits)_",
        "",
        "## Spec",
        "",
        f"- Source: `analysis/strategies/strategy_v{VERSION}.md`",
        f"- target_w: {TARGET_W}  ·  band: ±{BAND}  (two-sided no-trade zone, "
        f"weight in [{TARGET_W - BAND:.2f}, {TARGET_W + BAND:.2f}])",
        "- **Two-way** rebalance: SELL above target+band, BUY below target-band, "
        "HOLD inside. On a breach, correct **all the way to target**.",
        "- **No drip, no FNG, no B0 spine.** The cash side is a funded, standing, "
        "deliberate allocation — not a trim by-product.",
        f"- Decision cadence: weekly Tuesday.  Deposit: ${int(MONTHLY_DEPOSIT)} "
        "last Friday of month — lands as cash, the next rebalance redistributes it.",
        f"- Fee per trade: {FEE_RATE*100:.2f}%.  Cash yield: 0 "
        "(penalizes v8 hardest — the cash sleeve is now permanent).",
        "",
        "v8 is a **funded BTC/cash basket held at a constant target weight by a",
        "two-way weekly rebalance.** It makes no market prediction: buying a dip is",
        "the mechanical consequence of holding a constant weight, not a forecast that",
        "the dip recovers. It is a frontier choice judged on risk-adjusted edge, with",
        "two added burdens over v6 — a *permanent* funded cash drag, and the need to",
        "show the dip-buying earns its keep.",
        "",
        "## Headline results (standard scoreboard)",
        "",
        df_to_md(summary),
        "",
        "## v8 rebalance scorecard",
        "",
        "The ±3% base band suppresses most small weekly rebalances, so v8's trade",
        "count should sit well below v6's continuous trimming. The buy count is the",
        "half v6 never had — cash deployed into declines.",
        "",
        f"- Total trades:        **{n_trades}**  ({n_sells} sells, {n_buys} buys)",
        f"- Gross sold (over-weight trims):  ${sell_total:,.2f}",
        f"- Gross bought (dip-buys):         ${buy_total:,.2f}",
        f"- Cumulative fees paid:            ${fee_total:,.2f}",
        "",
        "## Benchmarks",
        "",
        "- **B0 — Deploy-on-arrival** (control). The headline comparison.",
        "- v6 (Band Rebalance) is the decisive cross-version comparison — see the postmortem.",
        "",
        "## Honest caveats (echoed from strategy_v8.md)",
        "",
        "- **Permanent funded cash drag is the central cost, and `cash_yield = 0`",
        "  makes it worst here.** v8 holds ~10% (more at lower `target_w`) in cash",
        "  continuously, earning nothing in this model. Real-world v8 — cash in",
        "  T-bills/stables at ~4–5% — is materially better than this backtest. Read",
        "  every v8 return number with that asterisk.",
        "- **Dip-buying's effect on drawdown is genuinely ambiguous.** The standing",
        "  cash buffer softens the *start* of a decline, but rebalancing *into* the",
        "  decline raises BTC exposure as price falls — at the trough v8 can hold more",
        "  BTC than it started with. Net max-DD vs B0 is an empirical question.",
        "- **The rebalancing bonus is regime-dependent.** Buy-low/sell-high adds",
        "  return mainly in choppy / mean-reverting markets. Over this single mostly-up",
        "  cycle, expect v8 to trail B0 on raw return.",
        "- **The band pools deposits as idle cash.** A $50 deposit can't breach ±3%",
        "  alone, so it sits until some larger move trips the band — a minor extra drag.",
        "- **Behaviorally, v8 demands discipline on three sides** — hold through bull",
        "  lag, keep buying into a 50–70% crash, and tolerate idle cash in between. The",
        "  backtest cannot test that.",
        "- **Single mostly-up, in-sample cycle (~120 weekly obs).** The dip-buying half",
        "  is exercised in essentially two declines (2020, 2022) — few events.",
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

    v8_df, action_log = simulate_v8(daily)
    b0_df             = simulate_control(daily)

    n_months  = len(last_friday_deposit_dates(START, END))
    deposited = n_months * MONTHLY_DEPOSIT
    for name, df in (("v8", v8_df), ("B0", b0_df)):
        got = df.attrs["total_deposited"]
        assert abs(got - deposited) < 1e-9, f"{name}: {got} != {deposited}"

    summary = pd.DataFrame([
        summarize_arm("B0 deploy-on-arrival", b0_df, deposited),
        summarize_arm("v8 Funded Basket",     v8_df, deposited,
                      action_log=action_log),
    ])
    print(summary.to_string(index=False))

    trades = rebalance_events(action_log)
    # substring so a one-way compound "buy+sell" row counts on both sides
    acts    = action_log["action"].astype(str) if len(action_log) else pd.Series(dtype=str)
    n_buys  = int(acts.str.contains("buy").sum())  if len(action_log) else 0
    n_sells = int(acts.str.contains("sell").sum()) if len(action_log) else 0
    print(f"Trades: {len(trades)} ({n_sells} sells, {n_buys} buys)  ·  "
          f"fees: ${v8_df.attrs['fee_total']:,.2f}")

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"Saved {ACTION_LOG_CSV} ({len(action_log)} rows)")

    plot_curves({"B0 deploy-on-arrival": b0_df,
                 "v8 Funded Basket":     v8_df})
    write_report(summary, len(trades), n_buys, n_sells, n_months,
                 v8_df.attrs["buy_total"], v8_df.attrs["sell_total"],
                 v8_df.attrs["fee_total"])


if __name__ == "__main__":
    main()
