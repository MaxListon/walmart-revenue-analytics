"""FY2017 full-year revenue outlook, chosen by backtest.

The data ends after fiscal week 16 of FY2017. Finance teams typically
project the rest of the year from year-to-date trends. Four methods are
backtested from the same point (end of week 16) in FY2014, FY2015 and
FY2016, on a 52-week basis:

  1. Chain run-rate:   rest of last year x chain YTD growth
  2. Store run-rate:   same, store by store
  3. Store run-rate, step-change adjusted: a store whose sales stepped up or
     down within the 52 weeks before the forecast point stops getting its
     inflated YTD growth once the step reaches its anniversary; it gets the
     other stores' median growth instead. (CA_2 jumped in June 2015 and
     annualizes in June 2016 - its +80% YTD growth won't continue.)
  4. Holt-Winters exponential smoothing (damped trend, 52-week seasonality)
     on chain weekly revenue.

The method with the lowest average full-year error is used for FY2017, with
a range set by its worst backtest miss.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from retailrev.paths import connect

ORIGIN_WEEK = 16
SQL = """
SELECT store_id, fiscal_year, fiscal_week, min(week_start) AS week_start, sum(revenue) AS revenue
FROM fct_item_store_week
WHERE days_observed = 7 AND fiscal_week <= 52
GROUP BY ALL ORDER BY fiscal_year, fiscal_week, store_id
"""


def load() -> pd.DataFrame:
    d = connect().execute(SQL).df()
    d["week_start"] = pd.to_datetime(d["week_start"])
    return d


def _run_rate(d: pd.DataFrame, fy: int, by_store: bool, breaks: dict[str, pd.Timestamp] | None = None) -> pd.Series:
    """Forecast weekly revenue for weeks 17-52 of fy. Returns chain total by fiscal_week."""
    cur, prev = d[d.fiscal_year == fy], d[d.fiscal_year == fy - 1]
    ytd = lambda x: x[x.fiscal_week <= ORIGIN_WEEK].groupby("store_id")["revenue"].sum()
    g_store = ytd(cur) / ytd(prev)
    g_chain = ytd(cur).sum() / ytd(prev).sum()
    rest = prev[prev.fiscal_week > ORIGIN_WEEK].copy()
    if not by_store:
        rest["fcst"] = rest["revenue"] * g_chain
    else:
        rest["fcst"] = rest["revenue"] * rest["store_id"].map(g_store)
        if breaks:
            origin_date = cur.loc[cur.fiscal_week == ORIGIN_WEEK, "week_start"].iloc[0]
            normal = g_store.drop([s for s in breaks if s in g_store.index]).median()
            for s, bw in breaks.items():
                # step happened within the year before the forecast point -> annualizes during the forecast
                if origin_date - pd.Timedelta(weeks=52) < bw <= origin_date:
                    anniversary = bw + pd.Timedelta(weeks=52)
                    mask = (rest.store_id == s) & (rest.week_start + pd.Timedelta(weeks=52) >= anniversary)
                    rest.loc[mask, "fcst"] = rest.loc[mask, "revenue"] * normal
    return rest.groupby("fiscal_week")["fcst"].sum()


def _holt_winters(d: pd.DataFrame, fy: int) -> pd.Series:
    chain = d.groupby(["fiscal_year", "fiscal_week"])["revenue"].sum()
    hist = chain[
        (chain.index.get_level_values(0) < fy)
        | ((chain.index.get_level_values(0) == fy) & (chain.index.get_level_values(1) <= ORIGIN_WEEK))
    ]
    y = np.log(hist.to_numpy())
    model = ExponentialSmoothing(
        y, trend="add", damped_trend=True, seasonal="add", seasonal_periods=52, initialization_method="estimated"
    ).fit()
    f = np.exp(model.forecast(52 - ORIGIN_WEEK))
    return pd.Series(f, index=range(ORIGIN_WEEK + 1, 53))


METHODS = {
    "Chain run-rate": lambda d, fy, b: _run_rate(d, fy, by_store=False),
    "Store run-rate": lambda d, fy, b: _run_rate(d, fy, by_store=True),
    "Store run-rate, step-change adjusted": lambda d, fy, b: _run_rate(d, fy, by_store=True, breaks=b),
    "Holt-Winters (chain)": lambda d, fy, b: _holt_winters(d, fy),
}


def backtest(d: pd.DataFrame, breaks: dict[str, pd.Timestamp]) -> pd.DataFrame:
    rows = []
    for fy in (2014, 2015, 2016):
        chain = d[d.fiscal_year == fy].groupby("fiscal_week")["revenue"].sum()
        actual_rest = chain[chain.index > ORIGIN_WEEK]
        ytd = chain[chain.index <= ORIGIN_WEEK].sum()
        for name, f in METHODS.items():
            fc = f(d, fy, breaks).reindex(actual_rest.index)
            rows.append(
                {
                    "fiscal_year": fy,
                    "method": name,
                    "forecast_full_year": ytd + fc.sum(),
                    "actual_full_year": ytd + actual_rest.sum(),
                    "full_year_error": (ytd + fc.sum()) / (ytd + actual_rest.sum()) - 1,
                    "weekly_mape": (abs(fc - actual_rest) / actual_rest).mean(),
                }
            )
    return pd.DataFrame(rows)


def forecast_fy2017(d: pd.DataFrame, breaks: dict[str, pd.Timestamp], bt: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    score = (
        bt.groupby("method")
        .agg(
            mean_abs_full_year_error=("full_year_error", lambda e: e.abs().mean()),
            worst_full_year_error=("full_year_error", lambda e: e.abs().max()),
            mean_weekly_mape=("weekly_mape", "mean"),
        )
        .sort_values("mean_abs_full_year_error")
    )
    best = score.index[0]
    ytd = d[(d.fiscal_year == 2017) & (d.fiscal_week <= ORIGIN_WEEK)].groupby("fiscal_week")["revenue"].sum()
    rows = []
    for name, f in METHODS.items():
        fc = f(d, 2017, breaks)
        full = ytd.sum() + fc.sum()
        err = score.loc[name, "worst_full_year_error"]
        rows.append(
            {
                "method": name,
                "selected": name == best,
                "ytd_actual_weeks_1_16": ytd.sum(),
                "forecast_weeks_17_52": fc.sum(),
                "fy2017_forecast": full,
                "range_low": full * (1 - err),
                "range_high": full * (1 + err),
                "growth_vs_fy2016": full / d[d.fiscal_year == 2016]["revenue"].sum() - 1,
            }
        )
    weekly = pd.concat(
        [
            d[d.fiscal_year.isin([2016, 2017])]
            .groupby(["fiscal_year", "fiscal_week"])["revenue"]
            .sum()
            .rename("revenue")
            .reset_index()
            .assign(kind="actual"),
            METHODS[best](d, 2017, breaks)
            .rename("revenue")
            .rename_axis("fiscal_week")
            .reset_index()
            .assign(fiscal_year=2017, kind="forecast"),
        ],
        ignore_index=True,
    )
    return pd.DataFrame(rows).merge(score.reset_index(), on="method"), weekly
