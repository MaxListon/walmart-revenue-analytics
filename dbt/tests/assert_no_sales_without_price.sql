-- Revenue = units x price is only complete if no unit sold lacks a shelf price.
select s.store_id, s.item_id, c.wm_yr_wk, sum(s.units) as units
from {{ ref('stg_sales_daily') }} s
join {{ ref('stg_calendar') }} c using (day_num)
left join {{ ref('stg_prices') }} p
  on p.store_id = s.store_id and p.item_id = s.item_id and p.wm_yr_wk = c.wm_yr_wk
where p.sell_price is null
group by all
having sum(s.units) > 0
