-- Revenue bridge between fiscal year {y0} and {y1} (52-week basis),
-- computed at store x item grain and rolled up by {group_col}.
--
--   R1 - R0 = volume + mix + price          (comp store-items)
--           + launch_annualization          (listed part of {y0}, all/part of {y1})
--           + new_listings - lost_listings  (listed in only one of the two years)
--
-- Comp store-items are listed in all 52 weeks of both years, so
-- volume + mix + price ties exactly to comp_sales.sql.
--
--   volume = (Q1 - Q0) * P0avg            more units at last year's average price
--   mix    = sum(q1 * p0) - Q1 * P0avg    shift toward higher/lower priced items
--   price  = sum(q1 * (p1 - p0))          same items sold at different prices
WITH yr AS (
    SELECT store_id, item_id, cat_id, dept_id, state_id, fiscal_year,
           count(*)     AS weeks_listed,
           sum(units)   AS q,
           sum(revenue) AS r
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year IN ({y0}, {y1})
    GROUP BY ALL
),
j AS (
    SELECT coalesce(a.store_id, b.store_id) AS store_id,
           coalesce(a.state_id, b.state_id) AS state_id,
           coalesce(a.item_id, b.item_id)   AS item_id,
           coalesce(a.cat_id, b.cat_id)     AS cat_id,
           coalesce(a.dept_id, b.dept_id)   AS dept_id,
           coalesce(a.q, 0) AS q0, coalesce(a.r, 0) AS r0,
           coalesce(b.q, 0) AS q1, coalesce(b.r, 0) AS r1,
           CASE
               WHEN a.weeks_listed = 52 AND b.weeks_listed = 52 THEN 'comp'
               WHEN a.item_id IS NULL OR a.q = 0               THEN 'new'
               WHEN b.item_id IS NULL OR b.q = 0               THEN 'lost'
               ELSE 'annualization'
           END AS bucket
    FROM (SELECT * FROM yr WHERE fiscal_year = {y0}) a
    FULL OUTER JOIN (SELECT * FROM yr WHERE fiscal_year = {y1}) b
      ON a.store_id = b.store_id AND a.item_id = b.item_id
),
comp AS (
    SELECT {group_col} AS grp,
           sum(q0) AS Q0, sum(q1) AS Q1, sum(r0) AS R0c, sum(r1) AS R1c,
           -- an item with no prior-year units has no prior price: value it
           -- at its current price so it adds volume, not price.
           sum(q1 * CASE WHEN q0 > 0 THEN r0 / q0 WHEN q1 > 0 THEN r1 / q1 ELSE 0 END) AS q1p0
    FROM j WHERE bucket = 'comp'
    GROUP BY grp
),
other AS (
    SELECT {group_col} AS grp,
           sum(r1 - r0) FILTER (WHERE bucket = 'annualization') AS annualization,
           sum(r1)      FILTER (WHERE bucket = 'new')           AS new_listings,
           sum(r0)      FILTER (WHERE bucket = 'lost')          AS lost_listings,
           sum(r0) AS R0, sum(r1) AS R1
    FROM j GROUP BY grp
)
SELECT
    o.grp                                           AS segment,
    o.R0                                            AS revenue_prior,
    (c.Q1 - c.Q0) * (c.R0c / c.Q0)                  AS volume_effect,
    c.q1p0 - c.Q1 * (c.R0c / c.Q0)                  AS mix_effect,
    c.R1c - c.q1p0                                  AS price_effect,
    coalesce(o.annualization, 0)                    AS launch_annualization_effect,
    coalesce(o.new_listings, 0)                     AS new_listings_effect,
    -coalesce(o.lost_listings, 0)                   AS lost_listings_effect,
    o.R1                                            AS revenue_current,
    c.R1c / c.R0c - 1                               AS comp_growth
FROM other o JOIN comp c USING (grp)
ORDER BY o.R1 DESC;
