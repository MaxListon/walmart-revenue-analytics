"""Forecast accuracy benchmark using the M5 competition's own metric (WRMSSE).

The M5 competition scored 28-day daily unit forecasts with the Weighted Root Mean Squared
Scaled Error across 12 aggregation levels. This module forecasts the 70 store x department
series, adds them up to the 9 aggregate levels (154 series: total, state, store, category,
department, and their combinations), and scores each method with WRMSSE on those 9 levels.
The three product-level levels (10-12) are left out, so scores are comparable between the
methods here but not to the Kaggle leaderboard.

    RMSSE_i = sqrt( mean_h (y - yhat)^2 / mean_t (y_t - y_{t-1})^2 )   (scale: one-step naive error in training)
    WRMSSE  = sum over levels (1/9) sum_i w_i RMSSE_i,   w_i = series i's share of its level's dollar sales,
              last 28 training days

Methods (all forecast 28 days from the same origin):
    naive              repeat the last day
    seasonal naive     repeat the last week
    moving average     mean of the last 28 days
    weekday average    mean of the same weekday over the last 4 weeks
    exponential smoothing (ETS)  damped additive trend + weekly season, last 2 years
    calendar-aware     weekday average with SNAP-day and holiday-closure effects learned from the
                       previous year (the project's SNAP finding put to work)

Evaluated over six 28-day windows ending 22 May 2016, including the official M5 validation
(28 Mar - 24 Apr 2016) and evaluation (25 Apr - 22 May 2016) windows.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from retailrev.paths import connect

H = 28
N_WINDOWS = 6
LEVELS = {
    "Total": [],
    "State": ["state_id"],
    "Store": ["store_id"],
    "Category": ["cat_id"],
    "Department": ["dept_id"],
    "State x category": ["state_id", "cat_id"],
    "State x department": ["state_id", "dept_id"],
    "Store x category": ["store_id", "cat_id"],
    "Store x department": ["store_id", "dept_id"],
}

DAILY_SQL = """
SELECT v.store_id, v.state_id, v.cat_id, v.dept_id, v.date,
       sum(v.units) AS units, coalesce(sum(v.revenue), 0) AS revenue
FROM v_sales_daily_priced v
GROUP BY ALL
"""
CALENDAR_SQL = "SELECT date, snap_CA, snap_TX, snap_WI, event_name_1 FROM stg_calendar ORDER BY date"


def load(con=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (units, revenue, series attributes, calendar); units/revenue are date x series."""
    con = con or connect()
    d = con.execute(DAILY_SQL).df()
    d["series"] = d["store_id"] + "|" + d["dept_id"]
    units = d.pivot(index="date", columns="series", values="units").sort_index().fillna(0.0)
    revenue = d.pivot(index="date", columns="series", values="revenue").reindex_like(units).fillna(0.0)
    attrs = d.drop_duplicates("series").set_index("series")[["store_id", "state_id", "cat_id", "dept_id"]]
    attrs = attrs.loc[units.columns]
    cal = con.execute(CALENDAR_SQL).df().set_index("date").reindex(units.index)
    return units, revenue, attrs, cal


# ------------------------------------------------------------------ methods (bottom level)


def _naive(y: np.ndarray, **_) -> np.ndarray:
    return np.repeat(y[-1:], H, axis=0)


def _seasonal_naive(y: np.ndarray, **_) -> np.ndarray:
    return np.tile(y[-7:], (H // 7, 1))


def _moving_average(y: np.ndarray, **_) -> np.ndarray:
    return np.repeat(y[-28:].mean(axis=0, keepdims=True), H, axis=0)


def _weekday_average(y: np.ndarray, **_) -> np.ndarray:
    week = np.stack([y[-7 * k - 7 : len(y) - 7 * k] for k in range(4)]).mean(axis=0)  # last 4 weeks, by weekday
    return np.tile(week, (H // 7, 1))


def _ets(y: np.ndarray, **_) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    hist = y[-730:]
    out = np.empty((H, y.shape[1]))
    for j in range(y.shape[1]):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(hist[:, j], trend="add", damped_trend=True, seasonal="add", seasonal_periods=7).fit()
        out[:, j] = fit.forecast(H)
    return np.clip(out, 0, None)


def calendar_multipliers(y: np.ndarray, snap: np.ndarray, closed: np.ndarray) -> np.ndarray:
    """Per-series SNAP-day multiplier, learned from the last 364 days (relative to non-SNAP days)."""
    yy, ss, cc = y[-364:], snap[-364:], closed[-364:]
    open_ = ~cc[:, None]
    on = (yy * (ss & open_)).sum(0) / np.maximum((ss & open_).sum(0), 1)
    off = (yy * (~ss & open_)).sum(0) / np.maximum((~ss & open_).sum(0), 1)
    return np.where(off > 0, on / np.where(off > 0, off, 1), 1.0)


def _calendar_aware(y: np.ndarray, snap: np.ndarray, closed: np.ndarray, snap_f: np.ndarray, closed_f: np.ndarray, **_):
    m = calendar_multipliers(y, snap, closed)
    adj = np.where(snap, m, 1.0)  # history adjustment factor per day x series
    adj = np.where(closed[:, None], np.nan, adj)
    base = y / adj  # demand as if a non-SNAP open day
    week = np.nanmean(np.stack([base[-7 * k - 7 : len(base) - 7 * k] for k in range(4)]), axis=0)
    week = np.nan_to_num(week)
    f = np.tile(week, (H // 7, 1)) * np.where(snap_f, m, 1.0)
    return np.where(closed_f[:, None], 0.0, f)


METHODS = {
    "Naive (last day)": _naive,
    "Seasonal naive (last week)": _seasonal_naive,
    "Moving average (28 days)": _moving_average,
    "Weekday average (4 weeks)": _weekday_average,
    "Exponential smoothing (ETS)": _ets,
    "Calendar-aware weekday average": _calendar_aware,
}


# ------------------------------------------------------------------ scoring


def aggregate(frame: pd.DataFrame, attrs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Sum date x bottom-series frame up to every level (date x series of that level)."""
    out = {}
    for level, keys in LEVELS.items():
        if not keys:
            out[level] = frame.sum(axis=1).to_frame("Total")
        else:
            grp = attrs[keys].astype(str).agg("|".join, axis=1)
            out[level] = frame.T.groupby(grp.values).sum().T
    return out


def wrmsse(actual: pd.DataFrame, forecast: pd.DataFrame, train: pd.DataFrame, train_rev: pd.DataFrame, attrs) -> dict:
    """WRMSSE over the 9 levels; returns the total and each level's contribution."""
    a, f, t, r = (aggregate(x, attrs) for x in (actual, forecast, train, train_rev))
    per_level = {}
    for level in LEVELS:
        tr = t[level].to_numpy()
        scale = np.empty(tr.shape[1])
        for j in range(tr.shape[1]):
            s = tr[:, j]
            start = np.argmax(s > 0)  # M5: scale from the first non-zero sale
            scale[j] = np.mean(np.diff(s[start:]) ** 2)
        mse = ((a[level].to_numpy() - f[level].to_numpy()) ** 2).mean(axis=0)
        rmsse = np.sqrt(mse / scale)
        w = r[level].iloc[-28:].sum().to_numpy()
        per_level[level] = float((w / w.sum() * rmsse).sum())
    return {"wrmsse": float(np.mean(list(per_level.values()))), **per_level}


def benchmark(units, revenue, attrs, cal, n_windows: int = N_WINDOWS) -> pd.DataFrame:
    dates = units.index
    snap_cols = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
    snap = np.column_stack([cal[snap_cols[s]].to_numpy() == 1 for s in attrs["state_id"]])
    closed = (cal["event_name_1"] == "Christmas").to_numpy()
    rows = []
    for k in range(n_windows):
        end = len(dates) - k * H  # exclusive
        origin = end - H
        train, actual = units.iloc[:origin], units.iloc[origin:end]
        y = train.to_numpy()
        for name, fn in METHODS.items():
            fc = fn(
                y,
                snap=snap[:origin],
                closed=closed[:origin],
                snap_f=snap[origin:end],
                closed_f=closed[origin:end],
            )
            fc = pd.DataFrame(fc, index=actual.index, columns=units.columns)
            score = wrmsse(actual, fc, train, revenue.iloc[:origin], attrs)
            rows.append(
                {
                    "method": name,
                    "window_start": dates[origin],
                    "window_end": dates[end - 1],
                    "m5_window": {0: "M5 evaluation", 1: "M5 validation"}.get(k, ""),
                    **score,
                }
            )
    return pd.DataFrame(rows)


def summary(b: pd.DataFrame) -> pd.DataFrame:
    s = (
        b.groupby("method")
        .agg(mean_wrmsse=("wrmsse", "mean"), worst_window=("wrmsse", "max"), best_window=("wrmsse", "min"))
        .reset_index()
    )
    wins = b.loc[b.groupby("window_start")["wrmsse"].idxmin(), "method"].value_counts()
    s["windows_won"] = s["method"].map(wins).fillna(0).astype(int)
    m5 = b[b["m5_window"] == "M5 evaluation"].set_index("method")["wrmsse"]
    s["m5_evaluation_window"] = s["method"].map(m5)
    base = s.set_index("method").loc["Seasonal naive (last week)", "mean_wrmsse"]
    s["vs_seasonal_naive"] = s["mean_wrmsse"] / base - 1
    return s.sort_values("mean_wrmsse").reset_index(drop=True)
