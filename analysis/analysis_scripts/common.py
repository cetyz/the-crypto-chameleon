"""
Shared infrastructure for strategy_v{N} analysis / postmortem scripts.

Per research_process.md:
  - Specs live in analysis/strategies/strategy_vN.md
  - Per-version scripts live in analysis/analysis_scripts/{analysis,postmortem}_vN.py
  - Per-version reports land in analysis/results/{analysis,postmortem}_report_vN.md
  - Per-version artifacts land in analysis/output/*_vN.{png,csv}
  - Shared code lives in analysis/analysis_scripts/common.py (no suffix)
  - Shared data lives in analysis/data/ (no suffix)

This module contains every piece that is version-independent:
  - path helpers and per-version path builders
  - data loaders (BTC hourly + Binance perp funding)
  - signal functions (trend / funding) — used by v2 spec and by v3 postmortem regime split
  - metrics (max_drawdown, sharpe_sortino, bootstrap CI, forward returns)
  - the deposit calendar (last Friday of each month) — shared across all versions
  - the control / B0 simulator (deposit Fri, deploy 100% on the following Tue)
"""

import os
import time
import requests
import numpy as np
import pandas as pd


# ---------- Paths ----------
HERE        = os.path.dirname(os.path.abspath(__file__))
ANALYSIS    = os.path.dirname(HERE)
DATA_DIR    = os.path.join(ANALYSIS, "data")
OUTPUT_DIR  = os.path.join(ANALYSIS, "output")
RESULTS_DIR = os.path.join(ANALYSIS, "results")

BTC_HOURLY_CSV = os.path.join(DATA_DIR, "btc_hourly.csv")
FUNDING_CSV    = os.path.join(DATA_DIR, "btc_funding.csv")
FNG_CSV        = os.path.join(DATA_DIR, "fng_daily.csv")


def output_path(name, version):
    """e.g. output_path('equity_curves', 2) -> .../output/equity_curves_v2.png-or-csv."""
    return os.path.join(OUTPUT_DIR, f"{name}_v{version}")


def results_path(name, version):
    return os.path.join(RESULTS_DIR, f"{name}_v{version}.md")


# ---------- Window ----------
START             = pd.Timestamp("2020-03-01", tz="UTC")
END               = pd.Timestamp("2026-04-30 23:59:59", tz="UTC")
WARMUP_START      = pd.Timestamp("2019-09-08", tz="UTC")
FUNDING_FETCH_END = pd.Timestamp("2026-05-01", tz="UTC")

MONTHLY_DEPOSIT   = 50.0
FEE_RATE          = 0.001
SMA_WEEKS         = 20
FUNDING_WINDOW    = 26
FUNDING_HOT_PCT   = 80
FUNDING_COLD_PCT  = 20


# ---------- Data loaders ----------
def load_btc_hourly():
    df = pd.read_csv(BTC_HOURLY_CSV)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def weekly_closes(df_hourly):
    s = df_hourly.set_index("open_time")["close"]
    return s.resample("W").last().dropna()  # Sunday-anchored


def daily_closes(df_hourly):
    s = df_hourly.set_index("open_time")["close"]
    return s.resample("D").last().dropna()


def fetch_funding(symbol="BTCUSDT", start=WARMUP_START, end=FUNDING_FETCH_END):
    if os.path.exists(FUNDING_CSV):
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
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(FUNDING_CSV, index=False)
    return df


def weekly_funding_annpct(df_funding, week_index):
    fr = df_funding.set_index("fundingTime")["fundingRate"]
    out = {}
    for ts in week_index:
        window = fr[(fr.index > ts - pd.Timedelta(days=7)) & (fr.index <= ts)]
        out[ts] = window.mean() * 3 * 365 * 100 if len(window) else np.nan
    return pd.Series(out)


# ---------- Signals ----------
def funding_state(weekly_ann_pct, i):
    lo = max(0, i - FUNDING_WINDOW + 1)
    window = weekly_ann_pct.iloc[lo:i + 1].dropna()
    if len(window) < FUNDING_WINDOW:
        return None
    val = weekly_ann_pct.iloc[i]
    if pd.isna(val):
        return None
    hot = np.percentile(window, FUNDING_HOT_PCT)
    cold = np.percentile(window, FUNDING_COLD_PCT)
    if val >= hot:  return "Hot"
    if val <= cold: return "Cold"
    return "Neutral"


def trend_state(weekly_close, i):
    if i < SMA_WEEKS - 1:
        return None
    sma = weekly_close.iloc[i - SMA_WEEKS + 1:i + 1].mean()
    return "Up" if weekly_close.iloc[i] > sma else "Down"


def signals_ready(weekly_px, weekly_fund, i):
    return trend_state(weekly_px, i) is not None and funding_state(weekly_fund, i) is not None


# ---------- Deposit calendar ----------
def last_friday_deposit_dates(start=START, end=END):
    """Last Friday of each calendar month within [start, end]."""
    out = []
    cur = pd.Timestamp(start.year, start.month, 1, tz="UTC")
    end_norm = end.normalize()
    while cur <= end_norm:
        nxt = (cur + pd.offsets.MonthBegin(1)).tz_convert("UTC")
        last = nxt - pd.Timedelta(days=1)
        while last.weekday() != 4:
            last -= pd.Timedelta(days=1)
        if start.normalize() <= last <= end_norm:
            out.append(last.normalize())
        cur = nxt
    return out


def next_tuesday(d):
    days_ahead = (1 - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (d + pd.Timedelta(days=days_ahead)).normalize()


def daterange(start=START, end=END):
    return pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")


def price_on(daily_px, d):
    return daily_px.loc[d] if d in daily_px.index else daily_px.asof(d)


# ---------- Control / B0 simulator ----------
def simulate_control(daily_px, start=START, end=END):
    """Control = $50 on last Friday of month, deploy 100% on the FOLLOWING Tuesday close.

    Same simulator backs:
      - the live "control" account's behavior on the dashboard
      - the B0 "Deploy-on-arrival" benchmark in v2 / v3 reports
    """
    deposits = set(last_friday_deposit_dates(start, end))
    buys_by_date = {}  # tuesday -> usd_to_spend
    for d in deposits:
        t = next_tuesday(d)
        if t <= end.normalize():
            buys_by_date[t] = buys_by_date.get(t, 0.0) + MONTHLY_DEPOSIT

    cash, btc = 0.0, 0.0
    total_deposited = 0.0
    rows = []
    for d in daterange(start, end):
        action = ""
        if d.normalize() in deposits:
            cash += MONTHLY_DEPOSIT
            total_deposited += MONTHLY_DEPOSIT
            action = "deposit"
        spend = buys_by_date.get(d.normalize(), 0.0)
        if spend > 0 and cash > 0:
            actual = min(spend, cash)
            px = price_on(daily_px, d)
            btc += (actual * (1 - FEE_RATE)) / px
            cash -= actual
            action = (action + "+buy").lstrip("+")
        px = price_on(daily_px, d)
        rows.append({"date": d, "cash": cash, "btc": btc, "price": px,
                     "value": cash + btc * px, "action": action})
    df = pd.DataFrame(rows)
    df.attrs["total_deposited"] = total_deposited
    return df


# ---------- Metrics ----------
def max_drawdown(value):
    peak = value.cummax()
    dd = (value - peak) / peak
    return float(dd.min())


def sharpe_sortino(df):
    s = df.set_index("date")["value"]
    weekly = s.resample("W").last().pct_change()
    weekly = weekly.replace([np.inf, -np.inf], np.nan).dropna()
    if len(weekly) < 2 or weekly.std() == 0:
        return float("nan"), float("nan")
    sharpe = weekly.mean() / weekly.std() * np.sqrt(52)
    downside = weekly[weekly < 0]
    sortino = (weekly.mean() / downside.std() * np.sqrt(52)) \
              if len(downside) > 1 and downside.std() > 0 else float("nan")
    return float(sharpe), float(sortino)


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


def df_to_md(df):
    """Tiny GitHub-flavored markdown table writer — avoids the tabulate dep."""
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep  = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, r in df.iterrows():
        rows.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join([head, sep] + rows)


def fwd_return(weekly_px, ts, horizon_weeks):
    idx = weekly_px.index
    if ts not in idx:
        return np.nan
    i = idx.get_loc(ts)
    j = i + horizon_weeks
    if j >= len(idx):
        return np.nan
    return weekly_px.iloc[j] / weekly_px.iloc[i] - 1


# ---------- Fear & Greed Index (v5+) ----------
def load_fng_daily():
    """Daily Fear & Greed Index (0..100). Cached to FNG_CSV; fetched from
    alternative.me if absent. Returns Series indexed by normalized UTC date.
    History goes back to 2018-02-01."""
    if os.path.exists(FNG_CSV):
        df = pd.read_csv(FNG_CSV)
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.normalize()
        return df.set_index("date")["value"].astype(int).sort_index()
    print("Fetching Fear & Greed Index history from alternative.me ...")
    r = requests.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=30)
    r.raise_for_status()
    raw = r.json().get("data", [])
    rows = []
    for d in raw:
        ts = pd.to_datetime(int(d["timestamp"]), unit="s", utc=True).normalize()
        rows.append({"date": ts, "value": int(d["value"]),
                     "classification": d.get("value_classification", "")})
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(FNG_CSV, index=False)
    return df.set_index("date")["value"].astype(int)


def fng_state(daily_fng, d, threshold=90):
    """Returns the FNG int at date `d`, forward-filled to the most recent
    available prior date if `d` itself is missing (the API has occasional
    holes). Returns None if no prior value exists. `threshold` is unused
    in the lookup itself; kept in the signature so callers can pass it
    through for legibility."""
    dn = pd.Timestamp(d).normalize()
    if dn.tzinfo is None:
        dn = dn.tz_localize("UTC")
    if dn in daily_fng.index:
        return int(daily_fng.loc[dn])
    prior = daily_fng.loc[:dn]
    if len(prior) == 0:
        return None
    return int(prior.iloc[-1])


def summarize_arm(name, df, deposited, action_log=None, extra=None):
    final = df["value"].iloc[-1]
    out = {
        "arm": name,
        "deposited": round(deposited, 2),
        "final_value": round(final, 2),
        "total_return_%": round((final / deposited - 1) * 100, 2),
        "max_drawdown_%": round(max_drawdown(df["value"]) * 100, 2),
    }
    sharpe, sortino = sharpe_sortino(df)
    out["sharpe"]  = round(sharpe, 3)
    out["sortino"] = round(sortino, 3)
    if action_log is not None and len(action_log):
        in_market_days = (df["btc"] > 0).sum()
        if "action" in action_log.columns:
            real = action_log[~action_log["action"].isin(["none", ""])]
        elif "deploy_usd" in action_log.columns:
            forced = action_log["forced_usd"] if "forced_usd" in action_log.columns else 0
            real = action_log[(action_log["deploy_usd"] > 0) | (forced > 0)]
        else:
            real = action_log
        out["n_trades"]    = int(len(real))
        out["n_decisions"] = int(len(action_log))
        out["time_in_market_%"] = round(100 * in_market_days / len(df), 2)
    if extra:
        out.update(extra)
    return out
