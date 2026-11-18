-- =====================================================================
-- 02_marts.sql
-- Analysis-ready tables. Revenue = units sold x that week's shelf price.
-- =====================================================================

CREATE OR REPLACE TABLE dim_store AS
SELECT DISTINCT store_id, state_id FROM stg_sales_daily ORDER BY store_id;

CREATE OR REPLACE TABLE dim_item AS
SELECT DISTINCT item_id, dept_id, cat_id FROM stg_sales_daily ORDER BY item_id;

-- Daily sales with calendar attributes and the week's price attached.
-- Kept as a view: 59M rows is cheap to scan in DuckDB and we never need
-- to store it.
CREATE OR REPLACE VIEW v_sales_daily_priced AS
SELECT
    s.item_id, s.dept_id, s.cat_id, s.store_id, s.state_id,
    c.date, c.wm_yr_wk, c.fiscal_year, c.fiscal_week,
    s.units,
    p.sell_price,
    s.units * p.sell_price AS revenue
FROM stg_sales_daily s
JOIN stg_calendar c USING (day_num)
LEFT JOIN stg_prices p
    ON p.store_id = s.store_id AND p.item_id = s.item_id AND p.wm_yr_wk = c.wm_yr_wk;

-- Core fact table: one row per store x item x week the item was listed
-- (had a shelf price). This is the grain used by every revenue metric.
CREATE OR REPLACE TABLE fct_item_store_week AS
SELECT
    store_id, state_id, item_id, dept_id, cat_id,
    wm_yr_wk,
    any_value(fiscal_year)            AS fiscal_year,
    any_value(fiscal_week)            AS fiscal_week,
    min(date)                         AS week_start,
    count(*)                          AS days_observed,
    sum(units)                        AS units,
    any_value(sell_price)             AS sell_price,
    sum(revenue)                      AS revenue,
    count(*) FILTER (WHERE units = 0) AS zero_sale_days
FROM v_sales_daily_priced
WHERE sell_price IS NOT NULL
GROUP BY ALL;

-- Daily store x department totals: used for events, SNAP and seasonality.
CREATE OR REPLACE TABLE fct_store_dept_day AS
SELECT
    store_id, state_id, dept_id, cat_id, date, wm_yr_wk, fiscal_year,
    sum(units)                    AS units,
    sum(coalesce(revenue, 0))     AS revenue,
    count(*) FILTER (WHERE sell_price IS NOT NULL) AS items_listed
FROM v_sales_daily_priced
GROUP BY ALL;
