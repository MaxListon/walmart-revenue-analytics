-- Weekly revenue by store and category: feeds trend charts and Tableau.
-- Excludes the final partial week (fewer than 7 days of data).
SELECT
    wm_yr_wk, any_value(fiscal_year) AS fiscal_year, any_value(fiscal_week) AS fiscal_week,
    min(week_start) AS week_start,
    store_id, any_value(state_id) AS state_id, cat_id,
    sum(revenue) AS revenue, sum(units) AS units,
    count(*) AS store_items_listed
FROM fct_item_store_week
WHERE days_observed = 7
GROUP BY wm_yr_wk, store_id, cat_id
ORDER BY wm_yr_wk, store_id, cat_id;
