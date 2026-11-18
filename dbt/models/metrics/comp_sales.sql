-- Comparable sales: store-items listed all 52 weeks of both years.
with full_year as (
    select store_id, item_id, fiscal_year, sum(revenue) as revenue
    from {{ ref('fct_item_store_week') }}
    where fiscal_week <= 52 and days_observed = 7 and fiscal_year between 2012 and 2016
    group by all
    having count(*) = 52
)
select cur.fiscal_year,
       count(*)                                 as comp_store_items,
       sum(prev.revenue)                        as comp_revenue_prior,
       sum(cur.revenue)                         as comp_revenue_current,
       sum(cur.revenue) / sum(prev.revenue) - 1 as comp_growth
from full_year cur
join full_year prev
  on prev.store_id = cur.store_id and prev.item_id = cur.item_id
 and prev.fiscal_year = cur.fiscal_year - 1
group by cur.fiscal_year
