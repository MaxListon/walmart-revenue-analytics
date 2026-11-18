-- =====================================================================
-- 03_stockouts.sql
-- Detect likely out-of-stock (OOS) spells from daily sales.
--
-- A run of L consecutive zero-sale days while the item is listed is a
-- likely stock-out when the item's own history makes that run very unlikely.
-- Real demand is lumpier than Poisson, so we use the item's *observed* share
-- of zero-sale days rather than a Poisson rate:
--
--     p0 = max(smoothed zero-day share in the 28 listed days before the run,
--              smoothed zero-day share in the 28 listed days after the run)
--          where smoothed share = (zero days + 1) / (28 + 2)
--     P(L zero days in a row) = p0 ^ L
--
-- Spells with p0^L < 1% are kept; the headline uses the stricter 0.1%
-- (column strict_flag), and 0.01% is reported as a sensitivity bound.
-- Taking the *higher* zero share and the *lower* selling rate of the two
-- windows is deliberately conservative: an item whose demand genuinely
-- collapsed is not called a stock-out. Runs with no 28-day window after
-- them (end of data or delisting) are never flagged. Christmas Day excluded.
--
-- Lost sales = min(avg daily units before, after) x L, at the run's shelf price.
-- =====================================================================

CREATE OR REPLACE TABLE fct_oos_spells AS
WITH daily AS (
    SELECT s.store_id, s.state_id, s.item_id, s.dept_id, s.cat_id, c.date, c.day_num,
           c.fiscal_year, s.units, p.sell_price
    FROM stg_sales_daily s
    JOIN stg_calendar c USING (day_num)
    JOIN stg_prices p
      ON p.store_id = s.store_id AND p.item_id = s.item_id AND p.wm_yr_wk = c.wm_yr_wk
    WHERE NOT (c.calendar_month = 12 AND extract(day FROM c.date) = 25)
),
seq AS (
    SELECT *,
           -- every positive-sales day starts a new block; zero days inherit it
           sum(CASE WHEN units > 0 THEN 1 ELSE 0 END)
               OVER (PARTITION BY store_id, item_id ORDER BY date) AS block,
           avg(units) OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS rate_before,
           count(*)   OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS n_before,
           avg(units) OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND 28 FOLLOWING) AS rate_after,
           count(*)   OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND 28 FOLLOWING) AS n_after,
           sum(CASE WHEN units = 0 THEN 1 ELSE 0 END) OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS zeros_before,
           sum(CASE WHEN units = 0 THEN 1 ELSE 0 END) OVER (PARTITION BY store_id, item_id ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND 28 FOLLOWING) AS zeros_after
    FROM daily
),
runs AS (
    SELECT store_id, any_value(state_id) AS state_id, item_id, any_value(dept_id) AS dept_id,
           any_value(cat_id) AS cat_id, block,
           min(date) AS start_date, max(date) AS end_date, count(*) AS zero_days,
           arg_min(rate_before, date) AS rate_before, arg_min(n_before, date) AS n_before,
           arg_max(rate_after, date)  AS rate_after,  arg_max(n_after, date)  AS n_after,
           arg_min(zeros_before, date) AS zeros_before, arg_max(zeros_after, date) AS zeros_after,
           avg(CAST(sell_price AS DOUBLE)) AS avg_price,
           list(DISTINCT fiscal_year) AS fiscal_years
    FROM seq
    WHERE units = 0
    GROUP BY store_id, item_id, block
)
SELECT * EXCLUDE (p_run), p_run AS p_value_run,
       p_run < 0.001  AS strict_flag,
       p_run < 0.0001 AS very_strict_flag
FROM (
    SELECT *,
           least(rate_before, rate_after)                        AS base_rate,
           least(rate_before, rate_after) * zero_days            AS expected_units,
           pow(greatest(zeros_before + 1, zeros_after + 1) / 30.0, zero_days) AS p_run
    FROM runs
    WHERE n_before = 28 AND n_after = 28
)
WHERE p_run < 0.01;

-- Classify each spell. Short gaps are classic store stock-outs (a
-- replenishment miss). Long gaps are usually not: if the same item has a gap
-- at the same time of year in another year it is seasonal ranging; if most
-- other stores have the item dark at the same time it is a chain-wide supply
-- or ranging decision. Only store stock-outs are counted as lost sales; the
-- rest are reported separately as availability gaps.
CREATE OR REPLACE TABLE fct_oos_spells AS
WITH long_spells AS (
    SELECT store_id, item_id, start_date, end_date, dayofyear(start_date) AS doy, year(start_date) AS yr
    FROM fct_oos_spells WHERE zero_days > 28
),
flags AS (
    SELECT a.store_id, a.item_id, a.start_date,
           bool_or(b.store_id = a.store_id AND b.yr <> a.yr
                   AND least(abs(b.doy - a.doy), 365 - abs(b.doy - a.doy)) <= 30) AS seasonal,
           count(DISTINCT b.store_id) FILTER (WHERE b.store_id <> a.store_id
                   AND b.start_date <= a.end_date AND b.end_date >= a.start_date) AS other_stores_dark
    FROM long_spells a
    JOIN long_spells b ON b.item_id = a.item_id
    GROUP BY ALL
)
SELECT o.*,
       CASE WHEN o.zero_days <= 28           THEN 'Store stock-out'
            WHEN f.seasonal                  THEN 'Seasonal gap'
            WHEN f.other_stores_dark >= 4    THEN 'Chain-wide gap'
            ELSE                                  'Store long gap' END AS spell_class,
       coalesce(f.other_stores_dark, 0) AS other_stores_dark
FROM fct_oos_spells o
LEFT JOIN flags f USING (store_id, item_id, start_date);

-- Day-level OOS flags, split by fiscal year (spells can cross year ends),
-- with lost units/revenue allocated evenly over the spell's days.
CREATE OR REPLACE TABLE fct_oos_days AS
SELECT o.store_id, o.state_id, o.item_id, o.dept_id, o.cat_id, c.date, c.fiscal_year, c.wm_yr_wk,
       o.base_rate                  AS lost_units,
       o.base_rate * o.avg_price    AS lost_revenue,
       o.strict_flag, o.very_strict_flag, o.spell_class, o.zero_days AS spell_length
FROM fct_oos_spells o
JOIN stg_calendar c ON c.date BETWEEN o.start_date AND o.end_date
WHERE NOT (c.calendar_month = 12 AND extract(day FROM c.date) = 25);
