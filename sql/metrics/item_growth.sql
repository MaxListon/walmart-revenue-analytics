-- Item-level revenue change FY{y0} -> FY{y1} (52-week basis, all stores),
-- for items sold in both years. Used for top gainers / decliners.
WITH y AS (
    SELECT item_id, any_value(cat_id) AS cat_id, any_value(dept_id) AS dept_id,
           sum(revenue) FILTER (WHERE fiscal_year = {y0}) AS revenue_prior,
           sum(revenue) FILTER (WHERE fiscal_year = {y1}) AS revenue_current,
           sum(units)   FILTER (WHERE fiscal_year = {y0}) AS units_prior,
           sum(units)   FILTER (WHERE fiscal_year = {y1}) AS units_current
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year IN ({y0}, {y1})
    GROUP BY item_id
)
SELECT *,
       revenue_current - revenue_prior                AS revenue_change,
       revenue_current / revenue_prior - 1            AS revenue_growth,
       (revenue_current / units_current) / (revenue_prior / units_prior) - 1 AS avg_price_change
FROM y
WHERE revenue_prior > 0 AND revenue_current > 0
ORDER BY revenue_change DESC, item_id;  -- item_id breaks ties so the order is stable
