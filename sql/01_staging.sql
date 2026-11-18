-- =====================================================================
-- 01_staging.sql
-- Load the three raw M5 files into typed staging tables.
-- {raw} is replaced with the raw-data folder by build.py.
-- =====================================================================

-- Calendar: one row per day. Walmart weeks run Saturday-Friday and
-- wm_yr_wk encodes the fiscal year (1YYww), e.g. 11101 = first week of
-- the fiscal year that starts 2011-01-29 and ends January 2012.
CREATE OR REPLACE TABLE stg_calendar AS
SELECT
    CAST(date AS DATE)                         AS date,
    CAST(substr(d, 3) AS INTEGER)              AS day_num,
    d,
    wm_yr_wk,
    -- Walmart names a fiscal year by the calendar year it ends in
    2000 + (wm_yr_wk // 100) - 100 + 1         AS fiscal_year,
    wm_yr_wk % 100                             AS fiscal_week,
    weekday,
    year                                       AS calendar_year,
    month                                      AS calendar_month,
    event_name_1, event_type_1,
    event_name_2, event_type_2,
    snap_CA, snap_TX, snap_WI
FROM read_csv('{raw}/calendar.csv', header = true)
WHERE CAST(substr(d, 3) AS INTEGER) <= 1941;   -- last day with actual sales

-- Prices: one row per store x item x week the item was on the shelf.
CREATE OR REPLACE TABLE stg_prices AS
SELECT store_id, item_id, wm_yr_wk, CAST(sell_price AS DECIMAL(10, 2)) AS sell_price
FROM read_csv('{raw}/sell_prices.csv', header = true);

-- Sales: the raw file is wide (one column per day). Unpivot to long.
CREATE OR REPLACE TABLE stg_sales_daily AS
WITH wide AS (
    SELECT * FROM read_csv('{raw}/sales_train_evaluation.csv', header = true)
)
SELECT
    item_id, dept_id, cat_id, store_id, state_id,
    CAST(substr(d, 3) AS INTEGER) AS day_num,
    CAST(units AS INTEGER)        AS units
FROM (
    UNPIVOT wide
    ON COLUMNS('^d_[0-9]+$')
    INTO NAME d VALUE units
);
