"""
BTC Weekly-Low Seasonality Analysis
====================================
Question: is there a particular day-of-week and hour-of-day at which BTC
systematically reaches its weekly minimum? Designed to inform DCA timing.

Approach:
  1. Pull hourly BTCUSDT closes from Binance (free, no API key).
  2. For each Mon00:00 -> Sun23:59 UTC week, find the bar with the lowest close.
     (Using the argmin of close within a week is invariant to price level and
      to any additive/multiplicative drift -- so we don't need to detrend.)
  3. Build a 7x24 frequency grid of (day-of-week, hour-of-day) of weekly lows.
  4. Test for non-uniformity:
        - chi-square goodness-of-fit on the full 168-cell grid
        - chi-square on the day and hour marginals (more power per cell)
        - permutation test on the top cell (handles multiple-testing honestly)
  5. Secondary view: mean hourly log return by (dow, hour). Stationarity-safe.
  6. Robustness: rerun on pre-2020, 2020-2023, and post-ETF (2024+) regimes.
     If the "winning" cell flips between regimes, treat it as noise.

Usage:
    pip install requests pandas numpy scipy matplotlib seaborn
    python btc_weekly_low.py

Outputs:
    btc_hourly.csv                 (data cache)
    heatmap_<label>.png            (weekly-low count by dow x hour)
    returns_<label>.png            (mean hourly log return by dow x hour)
    Printed summary in the terminal, including the recommended day/hour.

Notes:
    - All timestamps are UTC. If you prefer Singapore time, add 8 hours
      to the printed hour (no DST in SGT).
    - If Binance is unreachable from your network, swap fetch_binance_klines()
      for ccxt or download the monthly archives from data.binance.vision.
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns

# ---------- Config ----------
SYMBOL          = "BTCUSDT"
INTERVAL        = "1h"
START_DATE      = "2018-01-01"   # Binance hourly history is reliable from here
CACHE_FILE      = "btc_hourly.csv"
OUTPUT_DIR      = "."
N_PERMUTATIONS  = 10_000
DAY_NAMES       = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]


# ---------- 1. Data ----------
def fetch_binance_klines(symbol, interval, start_ms, end_ms=None):
    """Paginate Binance /api/v3/klines (max 1000 bars per call)."""
    url = "https://api.binance.com/api/v3/klines"
    out, cursor = [], start_ms
    while True:
        params = {"symbol": symbol, "interval": interval,
                  "startTime": cursor, "limit": 1000}
        if end_ms:
            params["endTime"] = end_ms
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 1000:
            break
        cursor = batch[-1][0] + 1
        time.sleep(0.2)  # be polite
    cols = ["open_time","open","high","low","close","volume",
            "close_time","quote_volume","trades",
            "taker_buy_base","taker_buy_quote","ignore"]
    df = pd.DataFrame(out, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df[["open_time","open","high","low","close","volume"]]


def get_data():
    if os.path.exists(CACHE_FILE):
        print(f"Loading cached {CACHE_FILE}")
        df = pd.read_csv(CACHE_FILE)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        return df
    print(f"Fetching {SYMBOL} {INTERVAL} from Binance...")
    start_ms = int(pd.Timestamp(START_DATE, tz="UTC").timestamp() * 1000)
    df = fetch_binance_klines(SYMBOL, INTERVAL, start_ms)
    df.to_csv(CACHE_FILE, index=False)
    print(f"Saved {len(df):,} bars to {CACHE_FILE}")
    return df


# ---------- 2. Weekly lows ----------
def weekly_lows(df):
    """For each Mon00:00 UTC -> Sun23:59 UTC week, return the bar with min close."""
    df = df.copy()
    df["week_start"] = (df["open_time"]
                        # - pd.to_timedelta(df["open_time"].dt.dayofweek, unit="d")
                        - pd.to_timedelta((df["open_time"].dt.dayofweek - 3) % 7, unit="D")
                       ).dt.floor("D")
    # require near-complete weeks (>= 6 days of bars) so a partial week doesn't bias dow
    counts = df.groupby("week_start").size()
    full = counts[counts >= 24 * 6].index
    df = df[df["week_start"].isin(full)]
    idx = df.groupby("week_start")["close"].idxmin()
    lows = df.loc[idx].copy()
    lows["dow"]  = lows["open_time"].dt.dayofweek
    lows["hour"] = lows["open_time"].dt.hour
    return lows


# ---------- 3. Tests ----------
def frequency_grid(lows):
    grid = np.zeros((7, 24), dtype=int)
    for _, r in lows.iterrows():
        grid[int(r["dow"]), int(r["hour"])] += 1
    return grid


def chi_square_full(grid):
    obs = grid.flatten()
    n = obs.sum()
    chi2, p = stats.chisquare(obs, np.full(168, n / 168))
    return chi2, p


def chi_square_marginals(grid):
    dow = grid.sum(axis=1)
    hr  = grid.sum(axis=0)
    n = dow.sum()
    chi2_d, p_d = stats.chisquare(dow, np.full(7,  n / 7))
    chi2_h, p_h = stats.chisquare(hr,  np.full(24, n / 24))
    return (chi2_d, p_d, dow), (chi2_h, p_h, hr)


def permutation_top_cell(grid, n_perm=10_000, seed=42):
    """Null: weekly-low times are i.i.d. uniform over the 168 cells.
    Stat: max cell count. p = P(null_max >= observed_max)."""
    rng = np.random.default_rng(seed)
    n = int(grid.sum())
    observed_max = int(grid.max())
    null_maxes = np.empty(n_perm, dtype=int)
    for i in range(n_perm):
        sample = rng.integers(0, 168, size=n)
        null_maxes[i] = np.bincount(sample, minlength=168).max()
    return observed_max, float((null_maxes >= observed_max).mean())


def avg_return_grid(df):
    """Mean hourly log return by (dow, hour). Works in returns -> stationarity-safe."""
    df = df.copy()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["dow"]  = df["open_time"].dt.dayofweek
    df["hour"] = df["open_time"].dt.hour
    return (df.groupby(["dow", "hour"])["log_ret"]
              .mean().unstack().reindex(index=range(7), columns=range(24)).values)


def rolling_rank_analysis(df, label):
    """Drift- and boundary-invariant DCA analysis.

    For each hourly bar, compute its percentile rank within a CENTERED
    168-hour (7-day) window. Mean rank per (dow, hour) cell tells us
    whether that hour systematically sits below (good for DCA) or above
    its local 7-day average.

    - Drift-invariant: rank is relative, within-window only.
    - Boundary-invariant: no fixed week start, so no argmin bias to a wall.
    - Independence: cells one week apart use non-overlapping windows, so
      the ~n_weeks observations per cell are approximately independent
      and a one-sample t-test against 0.5 is valid.
    """
    print(f"\n--- [{label}] rolling-rank (drift-invariant) ---")
    df = df.copy().sort_values("open_time").reset_index(drop=True)
    win = 24 * 7
    df["pct_rank"] = (df["close"]
                      .rolling(win, center=True, min_periods=win)
                      .rank(pct=True))
    df["dow"]  = df["open_time"].dt.dayofweek
    df["hour"] = df["open_time"].dt.hour
    df = df.dropna(subset=["pct_rank"])

    # 7x24 grid of mean percentile rank
    grid = (df.groupby(["dow","hour"])["pct_rank"].mean()
              .unstack().reindex(index=range(7), columns=range(24)).values)

    # Per-cell t-test vs null of 0.5 (no seasonality)
    rows = []
    for d in range(7):
        for h in range(24):
            x = df.loc[(df["dow"]==d) & (df["hour"]==h), "pct_rank"].values
            if len(x) < 20:
                continue
            t, p = stats.ttest_1samp(x, 0.5)
            rows.append({"dow": d, "hour": h, "n": len(x),
                         "mean_rank": float(np.mean(x)), "t": float(t), "p": float(p)})
    res = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)

    # Benjamini-Hochberg FDR across 168 cells
    m = len(res)
    raw = res["p"].values * m / (res.index.values + 1)
    res["p_bh"] = np.clip(np.minimum.accumulate(raw[::-1])[::-1], 0, 1)

    # Day-of-week summary (the part you actually care about)
    dow_means = df.groupby("dow")["pct_rank"].mean()
    print("Mean percentile rank by day (0.5 = neutral; <0.5 = below local avg = better for DCA):")
    for d in range(7):
        n_d = (df["dow"]==d).sum()
        t_d, p_d = stats.ttest_1samp(df.loc[df["dow"]==d, "pct_rank"], 0.5)
        tag = ""
        if d == dow_means.idxmin(): tag = "  <- lowest"
        if d == dow_means.idxmax(): tag = "  <- highest"
        print(f"  {DAY_NAMES[d]}: mean_rank={dow_means[d]:.4f}  t={t_d:+.2f}  p={p_d:.4f}{tag}")

    # Top 5 cells (most below local average) after BH correction
    best = res.sort_values("mean_rank").head(5)
    print("Top 5 cells with lowest mean rank (best DCA candidates):")
    for _, r in best.iterrows():
        sgt = (int(r["hour"]) + 8) % 24
        print(f"  {DAY_NAMES[int(r['dow'])]} {int(r['hour']):02d}:00 UTC "
              f"({sgt:02d}:00 SGT)  mean_rank={r['mean_rank']:.4f}  "
              f"p={r['p']:.4f}  p_BH={r['p_bh']:.4f}")

    plot_heatmap(grid, f"{label}: mean percentile rank in centered 7d window",
                 f"rank_{label}.png", fmt=".3f", cmap="RdYlGn_r", center=0.5)

# ---------- 4. Plots ----------
def plot_heatmap(grid, title, fname, fmt="d", cmap="YlOrRd", center=None):
    fig, ax = plt.subplots(figsize=(14, 4))
    sns.heatmap(grid, annot=True, fmt=fmt, cmap=cmap, center=center,
                xticklabels=range(24), yticklabels=DAY_NAMES, ax=ax,
                cbar_kws={"label": ""})
    ax.set_xlabel("Hour (UTC)")
    ax.set_ylabel("Day of week")
    ax.set_title(title)
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, fname)
    plt.savefig(path, dpi=120)
    plt.close()
    print(f"  saved {path}")


# ---------- 5. Driver ----------
def run_analysis(df, label):
    print(f"\n=== {label} ===")
    print(f"Bars: {len(df):,}   Range: {df['open_time'].min()} -> {df['open_time'].max()}")
    lows = weekly_lows(df)
    n_weeks = len(lows)
    if n_weeks < 20:
        print("  Too few full weeks; skipping.")
        return
    print(f"Full weeks analyzed: {n_weeks}")

    grid = frequency_grid(lows)
    chi2_f, p_f = chi_square_full(grid)
    (cd, pd_, dow), (ch, ph, hr) = chi_square_marginals(grid)

    print(f"Chi-square, full 168 cells: chi2={chi2_f:.1f}, p={p_f:.4f}  "
          f"(df=167; needs to beat noise from many cells)")
    print(f"Chi-square, day-of-week (7 cells):  chi2={cd:.2f}, p={pd_:.4f}")
    print(f"Chi-square, hour-of-day (24 cells): chi2={ch:.2f}, p={ph:.4f}")

    print(f"Day counts: " + ", ".join(f"{DAY_NAMES[i]}={dow[i]}" for i in range(7))
          + f"  (uniform baseline = {n_weeks/7:.1f})")
    bd, wd = int(np.argmax(dow)), int(np.argmin(dow))
    print(f"  Most frequent day : {DAY_NAMES[bd]}  "
          f"({dow[bd]}/{n_weeks} = {dow[bd]/n_weeks:.1%}, baseline 14.3%)")
    print(f"  Least frequent day: {DAY_NAMES[wd]}  "
          f"({dow[wd]}/{n_weeks} = {dow[wd]/n_weeks:.1%})")
    bh = int(np.argmax(hr))
    print(f"  Most frequent hour: {bh:02d}:00 UTC  "
          f"({hr[bh]}/{n_weeks} = {hr[bh]/n_weeks:.1%}, baseline 4.2%)")

    obs_max, p_perm = permutation_top_cell(grid, n_perm=N_PERMUTATIONS)
    top = np.unravel_index(np.argmax(grid), grid.shape)
    sgt_hour = (top[1] + 8) % 24
    print(f"  Top (dow, hour) cell: {DAY_NAMES[top[0]]} {top[1]:02d}:00 UTC "
          f"(= {sgt_hour:02d}:00 SGT) with {obs_max}/{n_weeks} = {obs_max/n_weeks:.1%}")
    print(f"  Permutation p-value for top cell vs uniform null: p={p_perm:.4f}")

    plot_heatmap(grid,
                 f"{label}: weekly-low frequency (n={n_weeks} weeks)",
                 f"heatmap_{label}.png")
    ret_grid_bps = avg_return_grid(df) * 10_000  # bps
    plot_heatmap(ret_grid_bps,
                 f"{label}: mean hourly log return (bps)",
                 f"returns_{label}.png",
                 fmt=".1f", cmap="RdYlGn", center=0)
    rolling_rank_analysis(df, label)


def main():
    df = get_data()
    print(f"\nTotal bars loaded: {len(df):,}")

    # Full sample
    run_analysis(df, "full_sample")

    # Regime splits -- BTC market structure has changed materially over time
    splits = [
        ("pre_2020",       "2018-01-01", "2020-01-01"),
        ("2020_2023",      "2020-01-01", "2024-01-01"),
        ("post_etf_2024+", "2024-01-01", "2099-01-01"),
    ]
    for label, s, e in splits:
        sub = df[(df["open_time"] >= pd.Timestamp(s, tz="UTC")) &
                 (df["open_time"] <  pd.Timestamp(e, tz="UTC"))]
        run_analysis(sub, label)

    print("\n" + "="*72)
    print("How to read this:")
    print(" - p < 0.05 on the day-of-week or hour-of-day marginal is the first")
    print("   filter. The full 168-cell chi-square is noisy and rarely meaningful.")
    print(" - The permutation p-value on the top cell is the honest test: it")
    print("   accounts for the fact that with 168 bins one will look big by chance.")
    print(" - Cross-check the regime splits. If the 'best' day/hour flips between")
    print("   pre-2020, 2020-2023, and 2024+, the pattern is not stable and you")
    print("   should DCA whenever is convenient.")
    print(" - SGT = UTC + 8 (no DST).")


if __name__ == "__main__":
    main()