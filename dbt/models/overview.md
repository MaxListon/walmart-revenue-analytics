{% docs __overview__ %}
# Walmart Revenue Performance Review: data model

This site documents the dbt version of the project's warehouse, built from the
[M5 forecasting competition](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data) data:
real Walmart daily unit sales and weekly shelf prices for 3,049 products in 10 stores (CA, TX, WI), Jan 2011 – May 2016.

**Code and findings:** [github.com/MaxListon/walmart-revenue-analytics](https://github.com/MaxListon/walmart-revenue-analytics)

## Layers
| Layer | Models | What it does |
|---|---|---|
| **Staging** | `stg_calendar`, `stg_prices`, `stg_sales_daily` | Reads the raw CSVs, unpivots daily sales (59M rows), adds the Walmart fiscal calendar |
| **Marts** | `dim_store`, `dim_item`, `fct_item_store_week` | A star schema: one fact row per store × item × listed week, with revenue = units × shelf price |
| **Metrics** | `annual_revenue`, `comp_sales`, `revenue_bridge_total` | The headline business metrics, as views |

## How to explore
- Click **the blue button at the bottom right** to open the lineage graph: raw files → staging → marts → metrics.
- Every model and column has a description; tests are listed on each model's page.

## Tests (34)
Generic tests (unique, not null, accepted values, relationships) plus five custom ones:
the revenue bridge reconciles to the cent, units reconcile between daily and weekly tables,
every unit sold has a price, the fact table has one row per store × item × week, and dbt's numbers match the
project's Python pipeline.
{% enddocs %}
