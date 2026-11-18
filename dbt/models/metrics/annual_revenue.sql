-- Annual revenue, reported and on a 52-week basis (FY2014 has 53 weeks).
with yearly as (
    select fiscal_year,
           count(distinct wm_yr_wk)                      as fiscal_weeks,
           sum(revenue)                                  as revenue_reported,
           sum(revenue) filter (where fiscal_week <= 52) as revenue_52wk,
           sum(units)   filter (where fiscal_week <= 52) as units_52wk
    from {{ ref('fct_item_store_week') }}
    where fiscal_year between 2012 and 2016
    group by fiscal_year
)
select *,
       revenue_52wk / lag(revenue_52wk) over (order by fiscal_year) - 1 as yoy_52wk
from yearly
