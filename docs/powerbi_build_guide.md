# Power BI build guide

This rebuilds the core of the dashboard in **Power BI Desktop** from the extracts in `outputs/tableau/` (the same CSVs feed Tableau and Power BI). It takes about 60–90 minutes and shows the skills Power BI job postings ask for: Power Query, a star schema, relationships and DAX.

> **Mac note:** Power BI Desktop runs on Windows only. On a Mac, use a Windows lab machine (most universities have them), a Windows virtual machine, or a cloud PC. The finished `.pbix` can be published to the free Power BI service and shared as a link.

## 0. Load the data
**Home → Get data → Text/CSV**, then load each file from `outputs/tableau/`:

| Table | Grain | Role |
|---|---|---|
| `item_store_year` | fiscal year × store × product | main fact table (revenue, units, weeks listed) |
| `weekly_store_category` | week × store × category | trend fact table |
| `product_segments` | product | product dimension with segment |
| `segment_profile` | segment | segment playbooks and shares |
| `stockout_summary` | fiscal year × category × gap type | stock-out losses |
| `comp_sales`, `revenue_bridge_long` | fiscal year (× level × segment) | **checkpoints** to verify your DAX |

In Power Query, set `fiscal_year` to **Whole number**, `revenue` and `units` to **Decimal number**, and `week_start` to **Date**.

## 1. Build the star schema (Power Query)
Create small dimension tables so slicers filter every fact table the same way:

1. **DimStore:** right-click `item_store_year` → *Reference* → keep `store_id`, `state_id` → *Remove duplicates*.
2. **DimYear:** *Reference* `item_store_year` → keep `fiscal_year` → *Remove duplicates*.
3. **DimProduct:** use `product_segments` (item_id, dept_id, cat_id, segment). Three products have no FY2016 sales and no segment; that's expected.

**Model view → relationships** (all many-to-one, single direction, dimension → fact):

| From (many) | To (one) |
|---|---|
| `item_store_year[store_id]` | `DimStore[store_id]` |
| `item_store_year[fiscal_year]` | `DimYear[fiscal_year]` |
| `item_store_year[item_id]` | `DimProduct[item_id]` |
| `weekly_store_category[store_id]` | `DimStore[store_id]` |
| `weekly_store_category[fiscal_year]` | `DimYear[fiscal_year]` |

## 2. Comparable sales (calculated columns on `item_store_year`)
A store-product is "comparable" in year Y if it was listed all 52 weeks of Y **and** Y−1. Each row carries the flag and last year's revenue:

```DAX
Is Comp =
VAR s = item_store_year[store_id]
VAR i = item_store_year[item_id]
VAR y = item_store_year[fiscal_year]
VAR prior_weeks =
    LOOKUPVALUE ( item_store_year[weeks_listed],
        item_store_year[store_id], s, item_store_year[item_id], i, item_store_year[fiscal_year], y - 1 )
RETURN item_store_year[weeks_listed] = 52 && prior_weeks = 52

Comp Revenue Prior Row =
IF ( item_store_year[Is Comp],
    LOOKUPVALUE ( item_store_year[revenue],
        item_store_year[store_id], item_store_year[store_id],
        item_store_year[item_id], item_store_year[item_id],
        item_store_year[fiscal_year], item_store_year[fiscal_year] - 1 ) )
```

## 3. Measures
```DAX
Revenue = SUM ( item_store_year[revenue] )
Units = SUM ( item_store_year[units] )
Avg Unit Price = DIVIDE ( [Revenue], [Units] )

Revenue PY = CALCULATE ( [Revenue], DimYear[fiscal_year] = MAX ( DimYear[fiscal_year] ) - 1 )
Total Growth = DIVIDE ( [Revenue], [Revenue PY] ) - 1

Comp Revenue = CALCULATE ( [Revenue], item_store_year[Is Comp] = TRUE () )
Comp Revenue PY = SUM ( item_store_year[Comp Revenue Prior Row] )
Comp Growth = DIVIDE ( [Comp Revenue], [Comp Revenue PY] ) - 1
Growth From New Products = [Total Growth] - [Comp Growth]

Share of Revenue = DIVIDE ( [Revenue], CALCULATE ( [Revenue], ALL ( DimProduct ) ) )
Store Stock-out Loss =
    CALCULATE ( SUM ( stockout_summary[lost_revenue] ), stockout_summary[spell_class] = "Store stock-out" )
```

**Check your DAX against the Python pipeline** (a card with `Comp Growth`, sliced by `DimYear[fiscal_year]`):

| Fiscal year | Comp Growth must show |
|---|---|
| 2013 | −3.5% |
| 2014 | −9.2% |
| 2015 | −5.9% |
| 2016 | +5.6% |

FY2016 `Revenue` should be **$42.8M** and `Store Stock-out Loss` for FY2016 **$0.79M**. If a number is off, the most common cause is a relationship pointing the wrong way.

## 4. Pages to build
1. **Overview:** cards for Revenue, Total Growth, Comp Growth (FY2016); a clustered column chart of Total Growth vs Comp Growth by fiscal year; a line chart of weekly revenue from `weekly_store_category`.
2. **Revenue bridge:** a **Waterfall** visual on `revenue_bridge_long` filtered to `level = "Total"` and one fiscal year; Category = `step`, Y = `amount`, Breakdown = `group`.
3. **Product segments:** a clustered bar of Share of Revenue by `DimProduct[segment]`; a table of `segment_profile` with the playbook column; a scatter of products (X = `product_segments[velocity]` on a log axis, Y = `snap_lift`, legend = segment).
4. **Availability:** stacked columns of `stockout_summary[lost_revenue]` by fiscal year and `spell_class`.

Add slicers for `DimStore[state_id]`, `DimStore[store_id]` and `DimProduct[cat_id]`, and use **Sync slicers** so they apply on every page.

## 5. Publish
**Home → Publish** to *My workspace* in the free Power BI service, then **File → Embed report → Publish to web** for a public link (only use public data like this). Add the link to the README next to the Streamlit dashboard.
