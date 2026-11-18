-- Store performance scorecard for fiscal year {fy} vs {fy} - 1 (52-week basis).
WITH base AS (
    SELECT store_id, state_id, fiscal_year, cat_id, revenue, units, item_id
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year IN ({fy} - 1, {fy})
),
cur AS (
    SELECT store_id, any_value(state_id) AS state_id,
           sum(revenue) AS revenue,
           sum(units)   AS units,
           count(DISTINCT item_id) AS items_listed,
           sum(revenue) FILTER (WHERE cat_id = 'FOODS')     / sum(revenue) AS foods_share,
           sum(revenue) FILTER (WHERE cat_id = 'HOUSEHOLD') / sum(revenue) AS household_share,
           sum(revenue) FILTER (WHERE cat_id = 'HOBBIES')   / sum(revenue) AS hobbies_share
    FROM base WHERE fiscal_year = {fy} GROUP BY store_id
),
prev AS (
    SELECT store_id, sum(revenue) AS revenue_prior
    FROM base WHERE fiscal_year = {fy} - 1 GROUP BY store_id
)
SELECT
    c.store_id, c.state_id, c.revenue, p.revenue_prior,
    c.revenue / p.revenue_prior - 1                   AS yoy_growth,
    c.revenue / sum(c.revenue) OVER ()                AS share_of_chain,
    c.revenue / 52                                    AS avg_weekly_revenue,
    c.revenue / c.items_listed                        AS revenue_per_item,
    c.revenue / c.units                               AS avg_unit_price,
    c.items_listed, c.foods_share, c.household_share, c.hobbies_share,
    rank() OVER (ORDER BY c.revenue DESC)             AS revenue_rank
FROM cur c JOIN prev p USING (store_id)
ORDER BY c.revenue DESC;
