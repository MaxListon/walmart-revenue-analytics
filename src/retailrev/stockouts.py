"""Stock-outs, availability gaps, and how much they explain the comp decline.

Detection lives in sql/03_stockouts.sql. This module summarizes it and runs
the availability decomposition of comparable sales:

    revenue = available days x revenue per available day

    change = (A1 - A0) x (R0 / A0)            availability effect
           + A1 x (R1 / A1 - R0 / A0)         rate-of-sale (demand) effect

where unavailable days are flagged spells (strict threshold) other than
seasonal gaps, for comp store-items (listed all 52 weeks of both years).
"""

from __future__ import annotations

import pandas as pd

from retailrev.paths import connect

SUMMARY_SQL = """
WITH listed AS (
    SELECT fiscal_year, cat_id, count(*) AS listed_days, sum(revenue) AS revenue
    FROM v_sales_daily_priced
    WHERE sell_price IS NOT NULL AND fiscal_year BETWEEN 2012 AND 2016
    GROUP BY ALL
)
SELECT o.fiscal_year, o.cat_id, o.spell_class,
       count(*)            AS dark_days,
       sum(o.lost_units)   AS lost_units,
       sum(o.lost_revenue) AS lost_revenue,
       any_value(l.listed_days) AS listed_days,
       any_value(l.revenue)     AS revenue
FROM fct_oos_days o
JOIN listed l USING (fiscal_year, cat_id)
WHERE o.strict_flag AND o.fiscal_year BETWEEN 2012 AND 2016
GROUP BY ALL
ORDER BY 1, 2, 3
"""

BY_STORE_SQL = """
SELECT o.store_id, o.dept_id, o.spell_class,
       count(*) AS dark_days, sum(o.lost_revenue) AS lost_revenue
FROM fct_oos_days o
WHERE o.strict_flag AND o.fiscal_year = {fy}
GROUP BY ALL ORDER BY lost_revenue DESC
"""

TOP_ITEMS_SQL = """
SELECT item_id, any_value(dept_id) AS dept_id,
       count(*) AS dark_days, count(DISTINCT store_id) AS stores_affected,
       sum(lost_revenue) AS lost_revenue
FROM fct_oos_days
WHERE strict_flag AND fiscal_year = {fy} AND spell_class = '{cls}'
GROUP BY item_id ORDER BY lost_revenue DESC LIMIT 25
"""

DECOMP_SQL = """
WITH cal AS (SELECT date, fiscal_year, fiscal_week FROM stg_calendar WHERE fiscal_week <= 52),
listed AS (   -- comp store-items: listed every week of both years
    SELECT store_id, item_id, fiscal_year FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
    GROUP BY ALL HAVING count(*) = 52
),
dark AS (
    SELECT o.store_id, o.item_id, c.fiscal_year, count(*) AS dark_days
    FROM fct_oos_days o JOIN cal c USING (date)
    WHERE o.strict_flag AND o.spell_class <> 'Seasonal gap'
    GROUP BY ALL
),
rev AS (
    SELECT store_id, item_id, cat_id, fiscal_year, sum(revenue) AS revenue,
           sum(days_observed) AS days
    FROM fct_item_store_week WHERE fiscal_week <= 52 GROUP BY ALL
),
yr AS (
    SELECT r.store_id, r.item_id, r.cat_id, r.fiscal_year, r.revenue,
           r.days - coalesce(d.dark_days, 0) AS available_days
    FROM rev r
    JOIN listed l USING (store_id, item_id, fiscal_year)
    LEFT JOIN dark d USING (store_id, item_id, fiscal_year)
)
SELECT cur.fiscal_year, {group_col} AS segment,
       sum(prev.revenue) AS revenue_prior, sum(cur.revenue) AS revenue_current,
       sum(prev.available_days) AS available_days_prior, sum(cur.available_days) AS available_days_current,
       sum((cur.available_days - prev.available_days) * prev.revenue / nullif(prev.available_days, 0)) AS availability_effect,
       sum(cur.available_days * (cur.revenue / nullif(cur.available_days, 0)
                                - prev.revenue / nullif(prev.available_days, 0)))                  AS rate_of_sale_effect
FROM yr cur
JOIN yr prev ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id
            AND prev.fiscal_year = cur.fiscal_year - 1
WHERE cur.available_days > 0 AND prev.available_days > 0
GROUP BY ALL ORDER BY 1, 2
"""


def summary() -> pd.DataFrame:
    return connect().execute(SUMMARY_SQL).df()


def by_store(fy: int = 2016) -> pd.DataFrame:
    return connect().execute(BY_STORE_SQL.format(fy=fy)).df()


def top_items(fy: int = 2016, cls: str = "Store stock-out") -> pd.DataFrame:
    return connect().execute(TOP_ITEMS_SQL.format(fy=fy, cls=cls)).df()


def availability_decomposition() -> pd.DataFrame:
    con = connect()
    parts = []
    for level, col in [("Total", "'Total'"), ("Category", "cur.cat_id")]:
        d = con.execute(DECOMP_SQL.format(group_col=col)).df()
        d.insert(1, "level", level)
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d["comp_change"] = d["revenue_current"] - d["revenue_prior"]
    d["comp_growth"] = d["comp_change"] / d["revenue_prior"]
    d["availability_pts"] = d["availability_effect"] / d["revenue_prior"]
    d["rate_of_sale_pts"] = d["rate_of_sale_effect"] / d["revenue_prior"]
    return d
