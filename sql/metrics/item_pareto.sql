-- Item revenue concentration in fiscal year {fy} (chain-wide, all stores).
-- ABC class: A = items making the first 80% of revenue, B = next 15%,
-- C = last 5% (the long tail).
WITH items AS (
    SELECT item_id, any_value(cat_id) AS cat_id, any_value(dept_id) AS dept_id,
           sum(revenue) AS revenue, sum(units) AS units,
           count(DISTINCT store_id) AS stores_listed,
           sum(revenue) / nullif(sum(units), 0) AS avg_price
    FROM fct_item_store_week
    WHERE fiscal_year = {fy}
    GROUP BY item_id
),
ranked AS (
    SELECT *,
           row_number() OVER (ORDER BY revenue DESC, item_id) AS revenue_rank,
           sum(revenue) OVER (ORDER BY revenue DESC, item_id
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / sum(revenue) OVER () AS cum_share
    FROM items
)
SELECT *,
       revenue_rank / count(*) OVER () AS cum_item_share,
       CASE WHEN cum_share - revenue / sum(revenue) OVER () < 0.80 THEN 'A'
            WHEN cum_share - revenue / sum(revenue) OVER () < 0.95 THEN 'B'
            ELSE 'C' END AS abc_class
FROM ranked
ORDER BY revenue_rank;
