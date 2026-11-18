"""Why did comparable sales shrink in FY2013-FY2015?

Tests three explanations in turn:

1. Cannibalization: did newly added products take sales from existing ones?
   Panel of store x department x year. Regress the change in existing-product
   revenue on revenue from newly added products, with store-year and
   department-year fixed effects (absorbing store traffic and chain-wide
   category trends). A placebo uses products added in the store's *other*
   departments. Cannibalization predicts a negative coefficient.
2. Product lifecycle: do older products fade? Comp growth by launch cohort.
3. Concentration: is the decline broad-based, or driven by a few products?
"""

from __future__ import annotations

import pandas as pd
import pyfixest as pf

from retailrev.paths import connect
from retailrev.sqlrun import run_metric

MODELS = {
    "Dollars, store-year + dept-year FE": "comp_change ~ added_revenue | store_year + dept_year",
    "Dollars, store-dept + year FE, with other-dept placebo": "comp_change ~ added_revenue + other_dept_added | store_dept + fiscal_year",
    "Growth rate, store-year + dept-year FE": "comp_growth ~ added_intensity | store_year + dept_year",
    "Growth rate, store-dept + year FE, with other-dept placebo": "comp_growth ~ added_intensity + other_dept_added_intensity | store_dept + fiscal_year",
}

COHORT_SQL = """
WITH first_listed AS (
    SELECT store_id, item_id, min(wm_yr_wk) AS first_wk, min(fiscal_year) AS first_fy
    FROM fct_item_store_week GROUP BY ALL
),
yr AS (
    SELECT store_id, item_id, fiscal_year, count(*) AS weeks_listed, sum(revenue) AS r, sum(units) AS q
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016 GROUP BY ALL
)
SELECT cur.fiscal_year,
       CASE WHEN f.first_wk = 11101 THEN 'On shelf at data start' ELSE 'Launched FY' || f.first_fy END AS cohort,
       count(*) AS comp_store_items,
       sum(prev.r) AS revenue_prior, sum(cur.r) AS revenue_current,
       sum(cur.r) / sum(prev.r) - 1 AS comp_growth,
       sum(cur.q) / sum(prev.q) - 1 AS comp_unit_growth
FROM yr cur
JOIN yr prev ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id AND prev.fiscal_year = cur.fiscal_year - 1
JOIN first_listed f ON f.store_id = cur.store_id AND f.item_id = cur.item_id
WHERE cur.weeks_listed = 52 AND prev.weeks_listed = 52
GROUP BY ALL ORDER BY 1, 2
"""

ITEM_CHANGE_SQL = """
WITH yr AS (
    SELECT store_id, item_id, cat_id, dept_id, fiscal_year, count(*) AS weeks_listed,
           sum(revenue) AS r, count(*) FILTER (WHERE units = 0) AS zero_weeks
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016 GROUP BY ALL
)
SELECT cur.fiscal_year, cur.item_id, any_value(cur.cat_id) AS cat_id, any_value(cur.dept_id) AS dept_id,
       sum(prev.r) AS revenue_prior, sum(cur.r) AS revenue_current, sum(cur.r - prev.r) AS revenue_change,
       sum(prev.zero_weeks) AS zero_weeks_prior, sum(cur.zero_weeks) AS zero_weeks_current,
       count(*) AS stores
FROM yr cur
JOIN yr prev ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id AND prev.fiscal_year = cur.fiscal_year - 1
WHERE cur.weeks_listed = 52 AND prev.weeks_listed = 52
GROUP BY cur.fiscal_year, cur.item_id
"""


MONTHLY_YOY_SQL = """
-- Same-item monthly year-over-year: store-items listed every day of both the
-- month and the same month a year earlier.
WITH mo AS (
    SELECT store_id, item_id, cat_id, date_trunc('month', date) AS month,
           sum(units) AS u, sum(revenue) AS r,
           count(*) FILTER (WHERE sell_price IS NOT NULL) AS listed_days, count(*) AS n_days
    FROM v_sales_daily_priced GROUP BY ALL
),
fm AS (SELECT * FROM mo WHERE listed_days = n_days)
SELECT a.cat_id, a.month,
       sum(a.r) / sum(b.r) - 1 AS revenue_yoy, sum(a.u) / sum(b.u) - 1 AS unit_yoy, count(*) AS store_items
FROM fm a JOIN fm b ON b.store_id = a.store_id AND b.item_id = a.item_id AND b.month = a.month - INTERVAL 1 YEAR
GROUP BY ALL ORDER BY 1, 2
"""


def monthly_same_item_yoy() -> pd.DataFrame:
    return connect().execute(MONTHLY_YOY_SQL).df()


def panel() -> pd.DataFrame:
    d = run_metric(connect(), "store_dept_bridge_panel")
    d["store_dept"] = d["store_id"] + "|" + d["dept_id"]
    d["store_year"] = d["store_id"] + "|" + d["fiscal_year"].astype(str)
    d["dept_year"] = d["dept_id"] + "|" + d["fiscal_year"].astype(str)
    return d


def cannibalization_models(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, fml in MODELS.items():
        m = pf.feols(fml, data=d, vcov={"CRV1": "store_dept"})
        t = m.tidy().reset_index()
        for _, r in t.iterrows():
            rows.append(
                {
                    "model": name,
                    "term": r["Coefficient"],
                    "estimate": r["Estimate"],
                    "std_error": r["Std. Error"],
                    "ci_low": r["2.5%"],
                    "ci_high": r["97.5%"],
                    "p_value": r["Pr(>|t|)"],
                    "observations": m._N,
                }
            )
    return pd.DataFrame(rows)


def comp_by_cohort() -> pd.DataFrame:
    return connect().execute(COHORT_SQL).df()


def decline_concentration() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per year and category: share of the comp decline explained by the
    top-N declining products, plus the item-level detail."""
    items = connect().execute(ITEM_CHANGE_SQL).df()
    rows = []
    for (fy, cat), g in items.groupby(["fiscal_year", "cat_id"]):
        g = g.sort_values("revenue_change")
        total = g["revenue_change"].sum()
        row = {
            "fiscal_year": fy,
            "cat_id": cat,
            "items": len(g),
            "comp_change": total,
            "share_items_declining": (g["revenue_change"] < 0).mean(),
        }
        for k in (10, 50, 100):
            row[f"top{k}_decliners_change"] = g["revenue_change"].head(k).sum()
        top = g.head(20)
        row["top20_zero_weeks_prior"] = top["zero_weeks_prior"].sum()
        row["top20_zero_weeks_current"] = top["zero_weeks_current"].sum()
        rows.append(row)
    return pd.DataFrame(rows), items
