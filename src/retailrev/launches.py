"""New-product launches: rollout speed, ramp-up, and whether launches pay off.

Launch cohort = fiscal year an item was first listed in any store. Items on
the shelf in the first week of data (Jan 2011) are "established": their true
launch date is unknown. M5 only contains items still sold in 2016, so every
launch here "survived"; this measures how good launches were, not how
many failed.
"""

from __future__ import annotations

import pandas as pd

from retailrev.paths import connect

WEEK_INDEX = "dense_rank() OVER (ORDER BY wm_yr_wk) - 1"

ROLLOUT_SQL = f"""
WITH wk AS (SELECT DISTINCT wm_yr_wk, {WEEK_INDEX} AS w FROM fct_item_store_week),
first_store AS (
    SELECT f.item_id, any_value(f.cat_id) AS cat_id, f.store_id, min(wk.w) AS w0, min(f.fiscal_year) AS fy0
    FROM fct_item_store_week f JOIN wk USING (wm_yr_wk) GROUP BY f.item_id, f.store_id
),
item AS (
    SELECT item_id, any_value(cat_id) AS cat_id, min(w0) AS first_w, max(w0) AS last_w,
           arg_min(fy0, w0) AS launch_fy, count(*) AS stores,
           count(*) FILTER (WHERE w0 <= (SELECT min(w0) FROM first_store fs WHERE fs.item_id = first_store.item_id) + 4) AS stores_in_4_weeks
    FROM first_store GROUP BY item_id
)
SELECT launch_fy, cat_id, count(*) AS items_launched,
       median(last_w - first_w) AS median_weeks_to_all_stores,
       avg(CAST((last_w - first_w) <= 4 AS INTEGER)) AS share_full_rollout_within_4_weeks,
       avg(stores_in_4_weeks) AS avg_stores_in_first_4_weeks
FROM item
WHERE first_w > 0
GROUP BY ALL ORDER BY 1, 2
"""

RAMP_SQL = """
WITH f AS (   -- store-level launches after the first 10 weeks of data
    SELECT store_id, item_id FROM fct_item_store_week GROUP BY ALL HAVING min(wm_yr_wk) > 11110
),
w AS (
    SELECT s.cat_id, s.units,
           dense_rank() OVER (PARTITION BY s.store_id, s.item_id ORDER BY s.wm_yr_wk) - 1 AS age_weeks
    FROM fct_item_store_week s JOIN f USING (store_id, item_id)
    WHERE s.days_observed = 7
)
SELECT cat_id, age_weeks // 4 AS months_since_launch,
       avg(units) AS avg_weekly_units, count(*) AS store_item_weeks
FROM w WHERE age_weeks < 104
GROUP BY ALL ORDER BY 1, 2
"""

OUTCOME_SQL = """
WITH chain_launch AS (
    SELECT item_id, CASE WHEN min(wm_yr_wk) = 11101 THEN 'Established (on shelf Jan 2011)'
                         ELSE 'Launched FY' || min(fiscal_year) END AS cohort
    FROM fct_item_store_week GROUP BY item_id
),
fy16 AS (
    SELECT item_id, any_value(cat_id) AS cat_id, sum(revenue) AS revenue,
           count(DISTINCT store_id) AS stores
    FROM fct_item_store_week WHERE fiscal_year = 2016 GROUP BY item_id
)
SELECT c.cohort, f.cat_id, count(*) AS items, sum(f.revenue) AS revenue_fy2016,
       sum(f.revenue) / sum(f.stores) AS revenue_per_store_item
FROM fy16 f JOIN chain_launch c USING (item_id)
GROUP BY ALL ORDER BY 1, 2
"""


def rollout() -> pd.DataFrame:
    return connect().execute(ROLLOUT_SQL).df()


def ramp_curve() -> pd.DataFrame:
    d = connect().execute(RAMP_SQL).df()
    # index each category to its months 6-12 average (steady state)
    base = d[d["months_since_launch"].between(6, 12)].groupby("cat_id")["avg_weekly_units"].mean()
    d["index_vs_steady_state"] = d["avg_weekly_units"] / d["cat_id"].map(base)
    return d


def outcomes(pareto: pd.DataFrame) -> pd.DataFrame:
    d = connect().execute(OUTCOME_SQL).df()
    abc = (
        connect()
        .execute("""
        SELECT item_id, CASE WHEN min(wm_yr_wk) = 11101 THEN 'Established (on shelf Jan 2011)'
                             ELSE 'Launched FY' || min(fiscal_year) END AS cohort
        FROM fct_item_store_week GROUP BY item_id""")
        .df()
        .merge(pareto[["item_id", "cat_id", "abc_class"]], on="item_id")
    )
    mix = (
        abc.groupby(["cohort", "cat_id"])["abc_class"]
        .value_counts(normalize=True)
        .unstack(fill_value=0)
        .add_prefix("share_class_")
        .reset_index()
    )
    return d.merge(mix, on=["cohort", "cat_id"], how="left")
