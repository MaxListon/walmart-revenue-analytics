"""Calendar effects on revenue: holidays/events, SNAP days, weekday rhythm.

Event lift compares each event day with a baseline built from the same
store, same category and same weekday in the 4 weeks before and after,
skipping other event days. That controls for store size, weekly rhythm and
season, so the lift is the effect of the event itself.

SNAP lift is estimated with a fixed-effects regression on daily store x
category revenue:

    log(revenue) = b * snap_day + store-month FE + store-weekday FE + e

SNAP (food-assistance benefit) days differ by state; FOODS should respond
and non-food categories serve as a check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retailrev.paths import connect
from retailrev.stats import fe_ols

DAILY_SQL = """
SELECT d.store_id, d.state_id, d.cat_id, d.date, sum(d.revenue) AS revenue,
       any_value(c.weekday) AS weekday,
       any_value(c.event_name_1) AS event_name,
       any_value(c.event_type_1) AS event_type,
       any_value(CASE d.state_id WHEN 'CA' THEN c.snap_CA WHEN 'TX' THEN c.snap_TX ELSE c.snap_WI END) AS snap
FROM fct_store_dept_day d
JOIN stg_calendar c USING (date)
GROUP BY d.store_id, d.state_id, d.cat_id, d.date
ORDER BY d.store_id, d.cat_id, d.date
"""


def load_daily() -> pd.DataFrame:
    con = connect()
    df = con.execute(DAILY_SQL).df()
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = df["revenue"].astype(float)
    return df


def event_lift(daily: pd.DataFrame, offset_days: int = 0) -> pd.DataFrame:
    """Lift per event occurrence and category vs same-weekday baseline.

    offset_days=-1 measures the day *before* each event, which shows whether
    holiday shopping is lost or just pulled forward.
    """
    d = daily.copy()
    d["is_event"] = d["event_name"].notna()
    rows = []
    events = d.loc[d["is_event"], ["date", "event_name", "event_type"]].drop_duplicates()
    events["date"] = events["date"] + pd.Timedelta(days=offset_days)
    events = events[events["date"].isin(d["date"])]
    for _, ev in events.iterrows():
        offsets = [pd.Timedelta(weeks=w) for w in (-4, -3, -2, -1, 1, 2, 3, 4)]
        base_dates = [ev["date"] + o for o in offsets]
        base = d[d["date"].isin(base_dates) & ~d["is_event"]]
        base = base.groupby("cat_id")["revenue"].sum() / base.groupby("cat_id")["date"].nunique()
        day = d[d["date"] == ev["date"]].groupby("cat_id")["revenue"].sum()
        for cat in day.index:
            if cat in base.index and base[cat] > 0:
                rows.append(
                    {
                        "event_name": ev["event_name"],
                        "event_type": ev["event_type"],
                        "date": ev["date"],
                        "cat_id": cat,
                        "event_revenue": day[cat],
                        "baseline_revenue": base[cat],
                    }
                )
    out = pd.DataFrame(rows)
    out["lift"] = out["event_revenue"] / out["baseline_revenue"] - 1
    return out


def summarize_event_lift(lift: pd.DataFrame) -> pd.DataFrame:
    total = lift.groupby(["event_name", "event_type", "date"], as_index=False)[["event_revenue", "baseline_revenue"]].sum()
    total["lift"] = total["event_revenue"] / total["baseline_revenue"] - 1
    total["revenue_impact"] = total["event_revenue"] - total["baseline_revenue"]
    s = (
        total.groupby(["event_name", "event_type"])
        .agg(
            occurrences=("lift", "size"),
            median_lift=("lift", "median"),
            min_lift=("lift", "min"),
            max_lift=("lift", "max"),
            avg_revenue_impact=("revenue_impact", "mean"),
        )
        .reset_index()
        .sort_values("median_lift")
    )
    by_cat = lift.groupby(["event_name", "cat_id"])["lift"].median().unstack().add_prefix("median_lift_").reset_index()
    return s.merge(by_cat, on="event_name")


def snap_lift(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily[(daily["revenue"] > 0) & daily["event_name"].isna()].copy()
    d["y"] = np.log(d["revenue"])
    d["snap"] = d["snap"].astype(float)
    d["store_month"] = d["store_id"] + "|" + d["date"].dt.to_period("M").astype(str)
    d["store_weekday"] = d["store_id"] + "|" + d["weekday"]
    rows = []
    for (cat, state), g in list(d.groupby(["cat_id", "state_id"])) + [((c, "ALL"), g) for c, g in d.groupby("cat_id")]:
        res = fe_ols(g, "y", ["snap"], ["store_month", "store_weekday"], cluster="store_month")
        b, se = float(res.params[0]), float(res.bse[0])
        rows.append(
            {
                "cat_id": cat,
                "state_id": state,
                "snap_lift": np.expm1(b),
                "ci_low": np.expm1(b - 1.96 * se),
                "ci_high": np.expm1(b + 1.96 * se),
                "days": len(g),
            }
        )
    return pd.DataFrame(rows).sort_values(["cat_id", "state_id"])


def weekday_profile(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily[daily["revenue"] > 0]
    w = d.groupby(["cat_id", "weekday"])["revenue"].mean().unstack(0)
    w = w / w.mean()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return w.loc[order].reset_index()


def snap_timing(daily: pd.DataFrame) -> pd.DataFrame:
    """Day-of-month profile of FOODS revenue relative to HOUSEHOLD, by state.

    Using the FOODS/HOUSEHOLD ratio in the same store and day removes payday
    timing and store traffic that affect both categories, isolating the
    food-specific (SNAP) part. Store-month and store-weekday fixed effects
    absorb level and weekly rhythm. Day 1-31 coefficients are relative to
    the average day.

    Note: every month has the same SNAP schedule within a state, so this
    shows *when* SNAP spending happens, not whether it is net new.
    """
    import pyfixest as pf

    d = daily[daily["event_name"].isna() & (daily["revenue"] > 0)]
    w = (
        d.pivot_table(index=["store_id", "state_id", "date", "weekday", "snap"], columns="cat_id", values="revenue")
        .reset_index()
        .dropna(subset=["FOODS", "HOUSEHOLD"])
    )
    w["y"] = np.log(w["FOODS"] / w["HOUSEHOLD"])
    w["dom"] = w["date"].dt.day
    w["store_month"] = w["store_id"] + "|" + w["date"].dt.to_period("M").astype(str)
    w["store_weekday"] = w["store_id"] + "|" + w["weekday"]
    rows = []
    for state, g in w.groupby("state_id"):
        g = g.copy()
        g["y"] = g["y"] - g.groupby("store_month")["y"].transform("mean")  # relative to the store-month
        m = pf.feols("y ~ C(dom) | store_month + store_weekday", data=g, vcov={"CRV1": "store_month"})
        t = m.tidy()
        coefs = {1: 0.0}
        lo, hi = {1: 0.0}, {1: 0.0}
        for name, r in t.iterrows():
            day = int(name.split("[")[-1].rstrip("]").replace("T.", ""))
            coefs[day], lo[day], hi[day] = r["Estimate"], r["2.5%"], r["97.5%"]
        snap_days = g.groupby("dom")["snap"].max()
        prof = pd.DataFrame({"day_of_month": list(coefs)}).sort_values("day_of_month")
        prof["coef"] = prof["day_of_month"].map(coefs)
        center = prof["coef"].mean()  # re-center on the average day
        prof["foods_vs_household"] = np.expm1(prof["coef"] - center)
        prof["ci_low"] = np.expm1(prof["day_of_month"].map(lo) - center)
        prof["ci_high"] = np.expm1(prof["day_of_month"].map(hi) - center)
        prof["snap_day"] = prof["day_of_month"].map(snap_days).fillna(0).astype(int)
        prof["state_id"] = state
        rows.append(prof.drop(columns="coef"))
    return pd.concat(rows, ignore_index=True)
