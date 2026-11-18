select store_id, item_id, wm_yr_wk, cast(sell_price as decimal(10, 2)) as sell_price
from read_csv('{{ var("raw_path") }}/sell_prices.csv', header = true)
