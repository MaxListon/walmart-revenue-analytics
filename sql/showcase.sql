-- SQL showcase: six business questions, each answered with one query on the warehouse.
-- Run against data/warehouse.duckdb (built by `python -m retailrev.pipeline`).
-- Each query is self-contained and starts with a `-- Q<n>:` line; the answer it returns is noted below it.
-- tests/test_sql_showcase.py checks every query compiles (in CI) and returns these answers (locally).
-- Fiscal years run February to January; growth uses 52 weeks because FY2014 had 53.


-- Q1: How fast did revenue grow each year?
-- Skills: aggregation with FILTER, LAG window function.
-- Answer: FY2016 revenue $42.8M, up 12.4% on FY2015 (52-week basis).
WITH yearly AS (
    SELECT fiscal_year,
           sum(revenue) FILTER (WHERE fiscal_week <= 52) AS revenue_52wk
    FROM fct_item_store_week
    WHERE fiscal_year BETWEEN 2012 AND 2016
    GROUP BY fiscal_year
)
SELECT fiscal_year,
       revenue_52wk,
       revenue_52wk / lag(revenue_52wk) OVER (ORDER BY fiscal_year) - 1 AS yoy_growth
FROM yearly
ORDER BY fiscal_year;


-- Q2: Which departments added the most revenue in FY2016?
-- Skills: conditional aggregation to pivot two years into columns, ranking.
-- Answer: HOUSEHOLD_1 added the most (+$1.61M, +19.0%), then HOBBIES_1 and FOODS_2.
--         FOODS_3, the largest department, slipped 1.0%.
WITH by_dept AS (
    SELECT dept_id,
           sum(revenue) FILTER (WHERE fiscal_year = 2015) AS revenue_fy2015,
           sum(revenue) FILTER (WHERE fiscal_year = 2016) AS revenue_fy2016
    FROM fct_item_store_week
    WHERE fiscal_year IN (2015, 2016) AND fiscal_week <= 52
    GROUP BY dept_id
)
SELECT dept_id,
       revenue_fy2016 - revenue_fy2015            AS revenue_added,
       revenue_fy2016 / revenue_fy2015 - 1        AS growth,
       rank() OVER (ORDER BY revenue_fy2016 - revenue_fy2015 DESC) AS rank_by_added
FROM by_dept
ORDER BY rank_by_added;


-- Q3: How does each store rank within its state, and what share of state revenue does it carry?
-- Skills: RANK and SUM as window functions partitioned by state.
-- Answer: CA_3 is the largest store in California, with 37% of the state's FY2016 revenue.
WITH stores AS (
    SELECT state_id, store_id, sum(revenue) AS revenue
    FROM fct_item_store_week
    WHERE fiscal_year = 2016
    GROUP BY state_id, store_id
)
SELECT state_id,
       store_id,
       revenue,
       rank() OVER (PARTITION BY state_id ORDER BY revenue DESC)   AS rank_in_state,
       revenue / sum(revenue) OVER (PARTITION BY state_id)          AS share_of_state
FROM stores
ORDER BY state_id, rank_in_state;


-- Q4: What is the best-selling product in each category?
-- Skills: ROW_NUMBER with QUALIFY to keep the top row per group.
-- Answer: HOBBIES_1_354 ($493K), FOODS_3_120 ($466K) and HOUSEHOLD_1_110 ($158K) lead their categories in FY2016.
SELECT cat_id,
       item_id,
       sum(revenue)                                   AS revenue,
       sum(revenue) / sum(units)                      AS avg_price
FROM fct_item_store_week
WHERE fiscal_year = 2016
GROUP BY cat_id, item_id
QUALIFY row_number() OVER (PARTITION BY cat_id ORDER BY sum(revenue) DESC) = 1
ORDER BY revenue DESC;


-- Q5: How concentrated is revenue? How many products make up 80% of it?
-- Skills: running total with SUM OVER (ORDER BY ...), Pareto analysis.
-- Answer: 1,310 of 3,049 products (43%) make up 80% of FY2016 revenue.
WITH items AS (
    SELECT item_id, sum(revenue) AS revenue
    FROM fct_item_store_week
    WHERE fiscal_year = 2016
    GROUP BY item_id
),
ranked AS (
    SELECT item_id,
           revenue,
           sum(revenue) OVER (ORDER BY revenue DESC, item_id) / sum(revenue) OVER () AS cum_share,
           row_number() OVER (ORDER BY revenue DESC, item_id)                        AS item_rank,
           count(*) OVER ()                                                           AS items
    FROM items
)
SELECT min(item_rank)          AS items_for_80pct,
       any_value(items)        AS items,
       min(item_rank) / any_value(items) AS share_of_items
FROM ranked
WHERE cum_share >= 0.8;


-- Q6: Which stores spent the most weeks below the same week a year earlier?
-- Skills: self-join on the prior year's matching week, FILTER to count by year.
-- Answer: WI_3 was below last year in 45 of 52 weeks of FY2014 (its April 2013 step down).
--         By FY2016, six of the ten stores had no such weeks.
WITH store_week AS (
    SELECT store_id, fiscal_year, fiscal_week, sum(revenue) AS revenue
    FROM fct_item_store_week
    WHERE fiscal_week <= 52
    GROUP BY store_id, fiscal_year, fiscal_week
)
SELECT cur.store_id,
       count(*) FILTER (WHERE cur.fiscal_year = 2014 AND cur.revenue < prev.revenue) AS weeks_down_fy2014,
       count(*) FILTER (WHERE cur.fiscal_year = 2016 AND cur.revenue < prev.revenue) AS weeks_down_fy2016
FROM store_week cur
JOIN store_week prev
  ON prev.store_id = cur.store_id
 AND prev.fiscal_week = cur.fiscal_week
 AND prev.fiscal_year = cur.fiscal_year - 1
GROUP BY cur.store_id
ORDER BY weeks_down_fy2014 DESC, cur.store_id;
