"""Pricing analysis: how often prices move, and how strongly units respond.

Panel elasticity (per department), store x item x week grain, using every
price movement of items whose price changed at least once:

    main:        units ~ Poisson(exp(b * log(price) + item-store FE + store-week FE))
    comparison:  log(1 + units) = b * log(price) + same FEs     (OLS, v1 of this project)

Item-store effects remove baseline popularity; store-week effects remove
seasonality, holidays and store-wide shocks. Standard errors are clustered by
item. Poisson handles zero-sale weeks directly; the log(1+units) version
compresses responses for slow sellers and biases b toward zero.

These pool permanent changes with temporary cuts. price_events.py separates
them with an event study.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyfixest as pf

from retailrev.paths import connect

ELASTICITY_SQL = """
WITH movers AS (   -- item-stores whose price changed at least once
    SELECT store_id, item_id
    FROM fct_item_store_week
    WHERE days_observed = 7 AND sell_price > 0.05
    GROUP BY ALL
    HAVING min(sell_price) <> max(sell_price) AND avg(units) >= ?
)
SELECT f.store_id, f.item_id, f.dept_id, f.wm_yr_wk,
       CAST(f.units AS DOUBLE) AS units, ln(CAST(f.sell_price AS DOUBLE)) AS log_price
FROM fct_item_store_week f
JOIN movers USING (store_id, item_id)
WHERE f.days_observed = 7 AND f.sell_price > 0.05 AND f.dept_id = ?
"""

PRICE_MOVES_SQL = """
WITH p AS (
    SELECT store_id, item_id, dept_id, fiscal_year, sell_price,
           lag(sell_price) OVER (PARTITION BY store_id, item_id ORDER BY wm_yr_wk) AS prev_price
    FROM fct_item_store_week
    WHERE sell_price > 0.05
)
SELECT dept_id, fiscal_year,
       count(*) FILTER (WHERE sell_price > prev_price) AS price_increases,
       count(*) FILTER (WHERE sell_price < prev_price) AS price_decreases,
       count(*) FILTER (WHERE prev_price IS NOT NULL) AS listed_weeks,
       avg(sell_price / prev_price - 1) FILTER (WHERE sell_price > prev_price) AS avg_increase_pct,
       avg(sell_price / prev_price - 1) FILTER (WHERE sell_price < prev_price) AS avg_decrease_pct
FROM p
WHERE fiscal_year BETWEEN 2012 AND 2016
GROUP BY ALL
ORDER BY dept_id, fiscal_year
"""

SPECS = [
    # (label, model, min avg weekly units)
    ("Poisson, all item-stores", "poisson", 0),
    ("Poisson, fast movers (>=5 units/week)", "poisson", 5),
    ("OLS log(1+units), all item-stores", "ols", 0),
    ("OLS log(1+units), fast movers (>=5 units/week)", "ols", 5),
]


def department_elasticities() -> pd.DataFrame:
    con = connect()
    depts = [r[0] for r in con.execute("SELECT DISTINCT dept_id FROM dim_item ORDER BY 1").fetchall()]
    rows = []
    for label, model, min_units in SPECS:
        for dept in depts:
            df = con.execute(ELASTICITY_SQL, [min_units, dept]).df()
            df["item_store"] = df["store_id"] + "|" + df["item_id"]
            df["store_week"] = df["store_id"] + "|" + df["wm_yr_wk"].astype(str)
            if model == "poisson":
                m = pf.fepois("units ~ log_price | item_store + store_week", data=df, vcov={"CRV1": "item_id"})
            else:
                df["y"] = np.log1p(df["units"])
                m = pf.feols("y ~ log_price | item_store + store_week", data=df, vcov={"CRV1": "item_id"})
            t = m.tidy().loc["log_price"]
            rows.append(
                {
                    "dept_id": dept,
                    "spec": label,
                    "model": model,
                    "sample": "all item-stores" if min_units == 0 else "fast movers",
                    "elasticity": t["Estimate"],
                    "ci_low": t["2.5%"],
                    "ci_high": t["97.5%"],
                    "std_error": t["Std. Error"],
                    "observations": m._N,
                    "items_with_price_changes": df["item_id"].nunique(),
                }
            )
    con.close()
    return pd.DataFrame(rows)


def price_moves() -> pd.DataFrame:
    con = connect()
    df = con.execute(PRICE_MOVES_SQL).df()
    con.close()
    df["increase_rate"] = df["price_increases"] / df["listed_weeks"]
    df["decrease_rate"] = df["price_decreases"] / df["listed_weeks"]
    return df
