-- One row per day. Walmart weeks run Saturday-Friday; wm_yr_wk encodes the
-- fiscal year, named (Walmart convention) by the calendar year it ends in.
select
    cast(date as date)                    as date,
    cast(substr(d, 3) as integer)         as day_num,
    wm_yr_wk,
    2000 + (wm_yr_wk // 100) - 100 + 1    as fiscal_year,
    wm_yr_wk % 100                        as fiscal_week,
    weekday,
    month                                 as calendar_month,
    event_name_1, event_type_1,
    snap_CA, snap_TX, snap_WI
from read_csv('{{ var("raw_path") }}/calendar.csv', header = true)
where cast(substr(d, 3) as integer) <= 1941
