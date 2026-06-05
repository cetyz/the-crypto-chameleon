"""
DCA vs Signal-Strategy Backtest — BTC, 2020-03-01 to 2026-04-30
================================================================
Arm A (DCA):       $50 deposited on the 1st of each month, $10 spent every
                   Tuesday at that day's UTC close. Leftover cash rolls over.
Arm B (Strategy):  $50 deposited on the 1st of each month. Decisions made at
                   Sunday weekly close per placeholder_strat.md:
                     trend  = weekly close vs 20-week SMA
                     funding= 7d trailing mean of 8h Binance perp funding,
                              annualized, classified by rolling-26w 20/80
                              percentile cutoffs
                   Policy table + 4-week patience override. 0.1% fee per trade.

Outputs: console summary, equity_curves.png, action_log.csv.
Funding rate is fetched once from fapi.binance.com and cached to btc_funding.csv.
"""

import os
import time
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---------- Config ----------
HERE              = os.path.dirname(os.path.abspath(__file__))
BTC_HOURLY_CSV    = os.path.join(HERE, "btc_hourly.csv")
FUNDING_CSV       = os.path.join(HERE, "btc_funding.csv")
EQUITY_PNG        = os.path.join(HERE, "equity_curves.png")
ACTION_LOG_CSV    = os.path.join(HERE, "action_log.csv")
REPORT_MD         = os.path.join(HERE, "analysis_report.md")
POSTMORTEM_MD     = os.path.join(HERE, "postmortem_report.md")

START             = pd.Timestamp("2020-03-01", tz="UTC")
END               = pd.Timestamp("2026-04-30 23:59:59", tz="UTC")
N_MONTHS          = 74        # 2020-03 through 2026-04 inclusive
WARMUP_START      = pd.Timestamp("2019-09-08", tz="UTC")
FUNDING_FETCH_END = pd.Timestamp("2026-05-01", tz="UTC")

MONTHLY_DEPOSIT   = 50.0
DCA_TUESDAY_SPEND = 10.0
FEE_RATE          = 0.001     # 0.10% per trade
SMA_WEEKS         = 20
FUNDING_WINDOW    = 26        # rolling weeks for percentile thresholds
FUNDING_HOT_PCT   = 80
FUNDING_COLD_PCT  = 20
PATIENCE_LIMIT    = 4

POLICY = {
    ("Up",   "Cold"):    "Buy100",
    ("Up",   "Neutral"): "Buy50",
    ("Up",   "Hot"):     "Hold",
    ("Down", "Cold"):    "Buy50",
    ("Down", "Neutral"): "Hold",
    ("Down", "Hot"):     "Sell50",
}


# ---------- Data loaders ----------
def load_btc_hourly():
    df = pd.read_csv(BTC_HOURLY_CSV)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def weekly_closes(df_hourly):
    """Sunday-anchored weekly close (UTC). Resample 'W' = Mon-Sun, label=right."""
    s = df_hourly.set_index("open_time")["close"]
    return s.resample("W").last().dropna()  # index = Sunday 00:00 UTC


def daily_closes(df_hourly):
    s = df_hourly.set_index("open_time")["close"]
    return s.resample("D").last().dropna()


def fetch_funding(symbol="BTCUSDT", start=WARMUP_START, end=FUNDING_FETCH_END):
    """Paginated fetch of Binance USDT-perp funding rate (8h cadence)."""
    if os.path.exists(FUNDING_CSV):
        print(f"Loading cached {FUNDING_CSV}")
        df = pd.read_csv(FUNDING_CSV)
        df["fundingTime"] = pd.to_datetime(df["fundingTime"], utc=True, format="ISO8601")
        return df
    print(f"Fetching funding rate from Binance fapi {start.date()} -> {end.date()}...")
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    out = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while True:
        r = requests.get(url, params={
            "symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000
        }, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 1000:
            break
        cursor = batch[-1]["fundingTime"] + 1
        time.sleep(0.2)
    df = pd.DataFrame(out)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = df["fundingRate"].astype(float)
    df = df[["fundingTime", "fundingRate"]].sort_values("fundingTime").reset_index(drop=True)
    df.to_csv(FUNDING_CSV, index=False)
    print(f"Saved {len(df):,} funding rows to {FUNDING_CSV}")
    return df


def weekly_funding_annpct(df_funding, week_index):
    """For each weekly-close timestamp, trailing-7-day mean 8h funding, annualized %.

    annualized = mean_8h_rate * 3 * 365 * 100
    """
    fr = df_funding.set_index("fundingTime")["fundingRate"]
    out = {}
    for ts in week_index:
        window = fr[(fr.index > ts - pd.Timedelta(days=7)) & (fr.index <= ts)]
        if len(window) == 0:
            out[ts] = np.nan
        else:
            out[ts] = window.mean() * 3 * 365 * 100
    return pd.Series(out)


# ---------- Signals ----------
def funding_state(weekly_ann_pct, i):
    """Classify week i using only the trailing FUNDING_WINDOW weeks (incl. i).
    Returns 'Hot'/'Neutral'/'Cold' or None if not enough history."""
    lo = max(0, i - FUNDING_WINDOW + 1)
    window = weekly_ann_pct.iloc[lo:i + 1].dropna()
    if len(window) < FUNDING_WINDOW:
        return None
    val = weekly_ann_pct.iloc[i]
    if pd.isna(val):
        return None
    hot_thr  = np.percentile(window, FUNDING_HOT_PCT)
    cold_thr = np.percentile(window, FUNDING_COLD_PCT)
    if val >= hot_thr:
        return "Hot"
    if val <= cold_thr:
        return "Cold"
    return "Neutral"


def trend_state(weekly_close, i):
    """Up if close > trailing 20w SMA (excluding current to avoid trivial self-bias?
    Spec says 'close vs 20-week SMA' -- inclusive is standard.)"""
    if i < SMA_WEEKS - 1:
        return None
    sma = weekly_close.iloc[i - SMA_WEEKS + 1:i + 1].mean()
    return "Up" if weekly_close.iloc[i] > sma else "Down"


def decide(trend, funding, consecutive_holds):
    """Returns (final_action, new_counter, patience_fire, natural_action)."""
    natural = POLICY[(trend, funding)]
    if natural == "Hold" and consecutive_holds >= PATIENCE_LIMIT:
        return "Buy50", 0, True, natural
    if natural == "Hold":
        return "Hold", consecutive_holds + 1, False, natural
    return natural, 0, False, natural


# ---------- Simulators ----------
def daterange(start, end):
    return pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")


def simulate_dca(daily_px):
    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    rows = []
    for d in daterange(START, END):
        action = ""
        if d.day == 1:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action = "deposit"
        if d.dayofweek == 1:  # Tuesday
            spend = min(DCA_TUESDAY_SPEND, cash)
            if spend > 0 and d in daily_px.index:
                px = daily_px.loc[d]
                btc_bought = (spend * (1 - FEE_RATE)) / px
                cash -= spend
                btc  += btc_bought
                action = (action + "+buy").lstrip("+")
        px = daily_px.loc[d] if d in daily_px.index else daily_px.asof(d)
        rows.append({
            "date": d, "cash": cash, "btc": btc, "price": px,
            "value": cash + btc * px, "action": action,
        })
    df = pd.DataFrame(rows)
    assert abs(total_deposited - N_MONTHS * MONTHLY_DEPOSIT) < 1e-9, total_deposited
    return df


def simulate_strategy(daily_px, weekly_px, weekly_funding):
    """weekly_px and weekly_funding share the same Sunday-anchored index."""
    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    consecutive_holds = 0
    week_idx_by_date = {ts.normalize(): i for i, ts in enumerate(weekly_px.index)}
    rows, action_log = [], []
    for d in daterange(START, END):
        action_today = ""
        if d.day == 1:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action_today = "deposit"
        # Weekly decision on Sunday (matches resample 'W' anchor).
        if d.normalize() in week_idx_by_date:
            i = week_idx_by_date[d.normalize()]
            t = trend_state(weekly_px, i)
            f = funding_state(weekly_funding, i)
            if t is not None and f is not None:
                final, consecutive_holds, patience, natural = decide(t, f, consecutive_holds)
                px = weekly_px.iloc[i]
                trade_usd = 0.0
                trade_btc = 0.0
                if final == "Buy100":
                    trade_usd = cash
                elif final == "Buy50":
                    trade_usd = cash * 0.5
                elif final == "Sell50":
                    trade_btc = btc * 0.5
                if trade_usd > 0:
                    btc_bought = (trade_usd * (1 - FEE_RATE)) / px
                    cash -= trade_usd
                    btc  += btc_bought
                if trade_btc > 0:
                    usd_received = trade_btc * px * (1 - FEE_RATE)
                    btc  -= trade_btc
                    cash += usd_received
                action_log.append({
                    "date": d, "close": px, "trend": t, "funding": f,
                    "natural": natural, "final": final, "patience_fire": patience,
                    "cash_after": cash, "btc_after": btc,
                    "value_after": cash + btc * px,
                })
                action_today = (action_today + "+" + final).lstrip("+")
        px = daily_px.loc[d] if d in daily_px.index else daily_px.asof(d)
        rows.append({
            "date": d, "cash": cash, "btc": btc, "price": px,
            "value": cash + btc * px, "action": action_today,
        })
    df = pd.DataFrame(rows)
    log = pd.DataFrame(action_log)
    assert abs(total_deposited - N_MONTHS * MONTHLY_DEPOSIT) < 1e-9, total_deposited
    return df, log


# ---------- Metrics ----------
def max_drawdown(value):
    peak = value.cummax()
    dd = (value - peak) / peak
    return dd.min()


def sharpe_sortino(value):
    """Weekly returns from daily value series, annualized."""
    s = value.set_index("date")["value"]
    weekly = s.resample("W").last().pct_change().dropna()
    if len(weekly) < 2 or weekly.std() == 0:
        return float("nan"), float("nan")
    sharpe = weekly.mean() / weekly.std() * np.sqrt(52)
    downside = weekly[weekly < 0]
    sortino = (weekly.mean() / downside.std() * np.sqrt(52)) if len(downside) > 1 and downside.std() > 0 else float("nan")
    return float(sharpe), float(sortino)


def summarize(name, df, action_log=None):
    final = df["value"].iloc[-1]
    deposited = N_MONTHS * MONTHLY_DEPOSIT
    ret = final / deposited - 1
    mdd = max_drawdown(df["value"])
    sharpe, sortino = sharpe_sortino(df)
    out = {
        "arm": name,
        "deposited": deposited,
        "final_value": round(final, 2),
        "total_return_%": round(ret * 100, 2),
        "max_drawdown_%": round(mdd * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
    }
    if action_log is not None and len(action_log):
        traded = action_log[action_log["final"] != "Hold"]
        in_market_days = (df["btc"] > 0).sum()
        out["n_trades"] = int(len(traded))
        out["time_in_market_%"] = round(100 * in_market_days / len(df), 2)
        out["patience_fires"] = int(action_log["patience_fire"].sum())
    return out


# ---------- Plot ----------
def plot_equity(dca_df, strat_df, action_log):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dca_df["date"],  dca_df["value"],  label="DCA ($10/Tue)",      linewidth=1.5)
    ax.plot(strat_df["date"], strat_df["value"], label="Strategy (signal)", linewidth=1.5)
    fires = action_log[action_log["patience_fire"]]
    if len(fires):
        # mark on strat curve at those dates
        merged = fires.merge(strat_df[["date", "value"]], on="date", how="left")
        ax.scatter(merged["date"], merged["value"], marker="^", s=60,
                   color="orange", zorder=5, label="Patience fire")
    ax.set_title("DCA vs Signal Strategy — BTC, 2020-03-01 to 2026-04-30")
    ax.set_ylabel("Portfolio value (USD, cash + BTC marked-to-market)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(EQUITY_PNG, dpi=120)
    plt.close()
    print(f"Saved {EQUITY_PNG}")


# ---------- Report ----------
def sample_week_lines(weekly_px, weekly_fund, n=6):
    """Return formatted lines for the first n in-window weeks with both signals."""
    lines, shown = [], 0
    for i, ts in enumerate(weekly_px.index):
        if ts < START:
            continue
        t = trend_state(weekly_px, i)
        f = funding_state(weekly_fund, i)
        if t is None or f is None:
            continue
        natural = POLICY[(t, f)]
        sma = weekly_px.iloc[i - SMA_WEEKS + 1:i + 1].mean()
        lines.append(
            f"  {ts.date()}  close={weekly_px.iloc[i]:>10.2f}  sma20={sma:>10.2f}  "
            f"funding_ann={weekly_fund.iloc[i]:+6.2f}%  trend={t:<4}  funding={f:<7}  "
            f"natural={natural}"
        )
        shown += 1
        if shown >= n:
            break
    return lines


def write_analysis_report(summary, action_log, sample_lines):
    """Persist headline backtest results to analysis_report.md."""
    cell_counts = (action_log.groupby(["trend", "funding"]).size()
                   .reset_index(name="n"))
    cell_counts["natural"] = cell_counts.apply(
        lambda r: POLICY[(r["trend"], r["funding"])], axis=1)
    action_counts = (action_log["final"].value_counts()
                     .rename_axis("action").reset_index(name="n"))

    md = [
        "# Backtest report",
        "",
        f"_Window: {START.date()} → {END.date()} ({N_MONTHS} months of deposits)_",
        "",
        "## Run parameters",
        "",
        f"- Monthly deposit: ${MONTHLY_DEPOSIT:.0f}  ·  DCA Tuesday spend: ${DCA_TUESDAY_SPEND:.0f}",
        f"- Fee per trade: {FEE_RATE * 100:.2f}%",
        f"- Trend SMA: {SMA_WEEKS} weeks",
        f"- Funding window: {FUNDING_WINDOW} weeks  ·  hot/cold percentiles: "
        f"{FUNDING_HOT_PCT}/{FUNDING_COLD_PCT}",
        f"- Patience override threshold: {PATIENCE_LIMIT} consecutive holds",
        "",
        "## Headline results",
        "",
        summary.to_markdown(index=False),
        "",
        "## Action distribution",
        "",
        "By executed action:",
        "",
        action_counts.to_markdown(index=False),
        "",
        "By (trend, funding) cell:",
        "",
        cell_counts.to_markdown(index=False),
        "",
        "## Sample weeks (first 6 in-window with both signals available)",
        "",
        "```",
        *sample_lines,
        "```",
        "",
        "## Artifacts",
        "",
        f"- Equity curves: `{os.path.basename(EQUITY_PNG)}`",
        f"- Per-decision log: `{os.path.basename(ACTION_LOG_CSV)}`",
    ]
    if os.path.exists(POSTMORTEM_MD):
        md.append(f"- Postmortem: `{os.path.basename(POSTMORTEM_MD)}`")
    md.append("")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Saved {REPORT_MD}")


# ---------- Main ----------
def main():
    hourly = load_btc_hourly()
    daily_px = daily_closes(hourly)
    weekly_px = weekly_closes(hourly)
    weekly_px = weekly_px[(weekly_px.index >= WARMUP_START) & (weekly_px.index <= END)]

    funding = fetch_funding()
    weekly_fund = weekly_funding_annpct(funding, weekly_px.index)

    # Sanity: no trade fires before warmup is complete.
    # By construction trend_state/funding_state return None until enough history.

    sample_lines = sample_week_lines(weekly_px, weekly_fund, n=6)
    print("\n--- Sample weeks (first 6 in-window with both signals available) ---")
    for ln in sample_lines:
        print(ln)

    dca_df = simulate_dca(daily_px)
    strat_df, action_log = simulate_strategy(daily_px, weekly_px, weekly_fund)

    print("\n--- Results ---")
    summary = pd.DataFrame([
        summarize("DCA", dca_df),
        summarize("Strategy", strat_df, action_log),
    ])
    print(summary.to_string(index=False))

    action_log.to_csv(ACTION_LOG_CSV, index=False)
    print(f"\nSaved {ACTION_LOG_CSV}  ({len(action_log)} weekly decisions)")
    plot_equity(dca_df, strat_df, action_log)
    write_analysis_report(summary, action_log, sample_lines)


if __name__ == "__main__":
    main()
