select store_id, item_id, wm_yr_wk, count(*) as n
from {{ ref('fct_item_store_week') }}
group by all
having count(*) > 1
