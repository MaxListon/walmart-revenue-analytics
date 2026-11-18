-- Grain: store x item x week the item was listed (had a shelf price).
-- Revenue = units x that week's shelf price.
with priced as (
    select s.store_id, s.state_id, s.item_id, s.dept_id, s.cat_id,
           c.date, c.wm_yr_wk, c.fiscal_year, c.fiscal_week,
           s.units, p.sell_price, s.units * p.sell_price as revenue
    from {{ ref('stg_sales_daily') }} s
    join {{ ref('stg_calendar') }} c using (day_num)
    join {{ ref('stg_prices') }} p
      on p.store_id = s.store_id and p.item_id = s.item_id and p.wm_yr_wk = c.wm_yr_wk
)
select store_id, state_id, item_id, dept_id, cat_id, wm_yr_wk,
       any_value(fiscal_year) as fiscal_year, any_value(fiscal_week) as fiscal_week,
       min(date) as week_start, count(*) as days_observed,
       sum(units) as units, any_value(sell_price) as sell_price, sum(revenue) as revenue,
       count(*) filter (where units = 0) as zero_sale_days
from priced
group by all
