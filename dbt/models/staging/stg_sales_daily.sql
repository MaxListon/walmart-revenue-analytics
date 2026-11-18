-- The raw file is wide (one column per day): unpivot to item x store x day.
with wide as (
    select * from read_csv('{{ var("raw_path") }}/sales_train_evaluation.csv', header = true)
)
select item_id, dept_id, cat_id, store_id, state_id,
       cast(substr(d, 3) as integer) as day_num,
       cast(units as integer)        as units
from (unpivot wide on columns('^d_[0-9]+$') into name d value units)
