-- Panel for the cannibalization analysis: one row per store x department x
-- fiscal year (FY2013-FY2016), with the revenue bridge split into existing
-- (comp) products and products added to the shelf.
--
--   comp_change      revenue change of store-items listed all 52 weeks of both years
--   added_revenue    current-year revenue from store-items that were NOT on the
--                    shelf all of last year (new listings + prior-year launches)
--   other_dept_added same, for the store's other departments (placebo)
WITH yr AS (
    SELECT store_id, state_id, dept_id, cat_id, item_id, fiscal_year,
           count(*) AS weeks_listed, sum(revenue) AS r, sum(units) AS q
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
    GROUP BY ALL
),
pairs AS (
    SELECT cur.store_id, cur.state_id, cur.dept_id, cur.cat_id, cur.item_id, cur.fiscal_year,
           cur.r AS r1, prev.r AS r0,
           (cur.weeks_listed = 52 AND prev.weeks_listed = 52) AS is_comp
    FROM yr cur
    LEFT JOIN yr prev
      ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id
     AND prev.fiscal_year = cur.fiscal_year - 1
    WHERE cur.fiscal_year >= 2013
),
sd AS (
    SELECT store_id, any_value(state_id) AS state_id, dept_id, any_value(cat_id) AS cat_id, fiscal_year,
           sum(r0) FILTER (WHERE is_comp)                       AS comp_revenue_prior,
           sum(r1) FILTER (WHERE is_comp)                       AS comp_revenue_current,
           count(*) FILTER (WHERE is_comp)                      AS comp_items,
           coalesce(sum(r1) FILTER (WHERE NOT is_comp OR is_comp IS NULL), 0) AS added_revenue,
           count(*) FILTER (WHERE r0 IS NULL)                   AS new_items,
           sum(r1)                                              AS total_revenue
    FROM pairs
    GROUP BY store_id, dept_id, fiscal_year
)
SELECT *,
       comp_revenue_current - comp_revenue_prior                     AS comp_change,
       comp_revenue_current / comp_revenue_prior - 1                 AS comp_growth,
       added_revenue / comp_revenue_prior                            AS added_intensity,
       sum(added_revenue) OVER (PARTITION BY store_id, fiscal_year) - added_revenue AS other_dept_added,
       (sum(added_revenue) OVER (PARTITION BY store_id, fiscal_year) - added_revenue)
         / (sum(comp_revenue_prior) OVER (PARTITION BY store_id, fiscal_year) - comp_revenue_prior)
                                                                     AS other_dept_added_intensity
FROM sd
ORDER BY store_id, dept_id, fiscal_year;
