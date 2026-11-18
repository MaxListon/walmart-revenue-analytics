-- Every unit in the raw daily data must land in the weekly fact exactly once.
select raw_units, fact_units
from (select sum(units) as raw_units from {{ ref('stg_sales_daily') }})
cross join (select sum(units) as fact_units from {{ ref('fct_item_store_week') }})
where raw_units <> fact_units
