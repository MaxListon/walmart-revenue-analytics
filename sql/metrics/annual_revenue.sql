-- Annual revenue, reported vs. 52-week basis.
-- FY2014 has 53 weeks in the Walmart calendar; the 52-week basis drops
-- fiscal week 53 so year-over-year growth compares like periods.
-- FY2017 is a partial year (16 full weeks) and is excluded here.
WITH yearly AS (
    SELECT
        fiscal_year,
        count(DISTINCT wm_yr_wk)                              AS fiscal_weeks,
        sum(revenue)                                          AS revenue_reported,
        sum(revenue) FILTER (WHERE fiscal_week <= 52)         AS revenue_52wk,
        sum(units)   FILTER (WHERE fiscal_week <= 52)         AS units_52wk,
        count(DISTINCT store_id || item_id)                   AS store_items_listed,
        count(DISTINCT item_id)                               AS items_listed
    FROM fct_item_store_week
    WHERE fiscal_year BETWEEN 2012 AND 2016
    GROUP BY fiscal_year
)
SELECT
    fiscal_year,
    fiscal_weeks,
    revenue_reported,
    revenue_52wk,
    units_52wk,
    revenue_52wk / units_52wk                                         AS avg_unit_price,
    store_items_listed,
    items_listed,
    revenue_reported / lag(revenue_reported) OVER (ORDER BY fiscal_year) - 1 AS yoy_reported,
    revenue_52wk     / lag(revenue_52wk)     OVER (ORDER BY fiscal_year) - 1 AS yoy_52wk
FROM yearly
ORDER BY fiscal_year;
