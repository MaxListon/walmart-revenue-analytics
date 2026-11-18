-- Comparable ("comp") sales growth, the like-for-like metric retailers
-- report to investors. A store-item is in the comp base for year Y only
-- if it was listed (had a shelf price) in all 52 fiscal weeks of both
-- Y-1 and Y. Growth from newly added products is therefore excluded.
WITH weekly AS (
    SELECT store_id, item_id, fiscal_year, revenue
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND days_observed = 7 AND fiscal_year BETWEEN 2012 AND 2016
),
full_year AS (          -- store-items listed every week of a fiscal year
    SELECT store_id, item_id, fiscal_year, sum(revenue) AS revenue
    FROM weekly
    GROUP BY ALL
    HAVING count(*) = 52
),
pairs AS (
    SELECT cur.fiscal_year,
           sum(prev.revenue) AS comp_revenue_prior,
           sum(cur.revenue)  AS comp_revenue_current,
           count(*)          AS comp_store_items
    FROM full_year cur
    JOIN full_year prev
      ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id
     AND prev.fiscal_year = cur.fiscal_year - 1
    GROUP BY cur.fiscal_year
),
totals AS (
    SELECT fiscal_year, sum(revenue) AS total_revenue_52wk
    FROM fct_item_store_week
    WHERE fiscal_week <= 52
    GROUP BY fiscal_year
)
SELECT
    p.fiscal_year,
    p.comp_store_items,
    p.comp_revenue_prior,
    p.comp_revenue_current,
    p.comp_revenue_current / p.comp_revenue_prior - 1  AS comp_growth,
    t.total_revenue_52wk / tp.total_revenue_52wk - 1   AS total_growth_52wk,
    p.comp_revenue_current / t.total_revenue_52wk      AS comp_share_of_revenue
FROM pairs p
JOIN totals t  ON t.fiscal_year  = p.fiscal_year
JOIN totals tp ON tp.fiscal_year = p.fiscal_year - 1
ORDER BY p.fiscal_year;
