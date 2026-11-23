# Tableau Public build guide

> Short on time? The [one-hour quickstart](tableau_public_quickstart.md) builds a one-page version from four ready-shaped files.

This guide rebuilds the executive dashboard in **Tableau Public** (free, and it runs on Mac) from the extracts in `outputs/tableau/`. It takes about 60–90 minutes. Publishing it gives you a public link for your resume next to the GitHub repo.

## 0. Setup
1. Install Tableau Public Desktop: <https://public.tableau.com/app/discover> → *Create* → *Download the App*.
2. **Connect → Text file** → `outputs/tableau/item_store_year.csv`.
3. On the Data Source page, use **Add** to bring in each other CSV as its own data source. Don't join them; each one has its own grain.

| Extract | Grain | Use it for |
|---|---|---|
| `item_store_year.csv` | fiscal year × store × item | category/store/item revenue, ABC class, price |
| `weekly_store_category.csv` | week × store × category | trend lines |
| `revenue_bridge_long.csv` | year × level × segment × bridge step | waterfall |
| `comp_sales.csv`, `annual_revenue.csv` | fiscal year | KPI tiles, total vs comp chart |
| `store_scorecard_fy2016.csv` | store | scorecard table |
| `event_lift.csv`, `snap_lift.csv`, `price_elasticity.csv` | event / state × category / dept | calendar & pricing sheets |

Set `fiscal_year`, `wm_yr_wk` and `fiscal_week` to **Dimension (discrete)**, and `week_start` to **Date**.

## 1. Calculated fields (item_store_year)
```
// Revenue FY2016
IF [Fiscal Year] = 2016 THEN [Revenue] END

// Revenue FY2015
IF [Fiscal Year] = 2015 THEN [Revenue] END

// YoY Growth
SUM([Revenue FY2016]) / SUM([Revenue FY2015]) - 1

// Avg Unit Price
SUM([Revenue]) / SUM([Units])

// Revenue Rank (table calc, compute using item_id)
RANK(SUM([Revenue]))

// Cumulative Revenue Share (table calc, compute using item_id, sorted by revenue desc)
RUNNING_SUM(SUM([Revenue])) / TOTAL(SUM([Revenue]))
```

## 2. Sheets
1. **KPI tiles** (`annual_revenue`, `comp_sales`): four text sheets for FY2016 revenue, YoY, comp growth, and the share of growth from existing products (from `revenue_bridge_long`: Comp group ÷ total change).
2. **Total vs comp growth**: `fiscal_year` on Columns, Measure Values (`yoy_52wk`, `comp_growth`) on Rows, side-by-side bars. Color: gray for total; comp blue `#2a78d6` if ≥ 0, red `#e34948` if < 0.
3. **Revenue bridge (waterfall)** (`revenue_bridge_long`): `step` on Columns, `SUM(amount)` on Rows as a **Gantt bar**. Create `Running = RUNNING_SUM(SUM([amount]))` and size `-SUM([amount])` for the classic waterfall. Filters: `fiscal_year`, `level`, `segment` (show as single-value dropdowns).
4. **Weekly trend** (`weekly_store_category`): `week_start` (continuous week) on Columns, `SUM(revenue)` on Rows, `state_id` on Color. Filters: store, category.
5. **Pareto** (`item_store_year`, filter FY2016): `item_id` on Columns sorted by revenue descending, `Cumulative Revenue Share` on Rows as a line. Add reference lines at 0.8 and 0.95.
6. **Top 15 best sellers**: a table filtered to the top 15 by revenue for FY2016, with category as a quick filter.
7. **Store scorecard** (`store_scorecard_fy2016`): highlight table of revenue, YoY, revenue per item, and foods share.
8. **SNAP lift** (`snap_lift`, state ≠ ALL): `state_id` on Columns, `snap_lift` on Rows, `cat_id` on Color. Error bars: a dual axis to `ci_low`/`ci_high` as a range is optional.
9. **Elasticity** (`price_elasticity`): `elasticity` on Columns, `dept_id` on Rows, `sample` on Color (circles), with a reference line at −1.

## 3. Dashboard layout (1200 × 900)
```
┌──────────────────────────────────────────────────────────────┐
│ Title + 1-line takeaway                                       │
│ [FY16 revenue] [YoY] [Comp growth] [Share from existing items]│
├──────────────────────────────┬───────────────────────────────┤
│ Total vs comp growth         │ Revenue bridge (filters)      │
├──────────────────────────────┴───────────────────────────────┤
│ Weekly revenue by state (store / category filters)            │
├──────────────────────────────┬───────────────────────────────┤
│ Pareto + top sellers         │ Store scorecard               │
└──────────────────────────────┴───────────────────────────────┘
```
Make a second dashboard tab for **Pricing & calendar** (SNAP, events, elasticity).

## 4. Colors (use these exactly)
| Use | Hex |
|---|---|
| FOODS / CA / up | `#2a78d6` |
| HOUSEHOLD / TX | `#eb6834` |
| HOBBIES / WI | `#1baf7a` |
| Down / negative | `#e34948` |
| Totals / context | `#a8a69f` |

## 5. Publish
*File → Save to Tableau Public*. Title: **Walmart Revenue Performance Review**. Add the GitHub link in the description, and put the Tableau Public URL in the repo README and on your resume.

## 6. Page 2: "Why comp fell & what to do" (v2 extracts)
| Sheet | Extract | Build |
|---|---|---|
| Comp decomposition | `availability_decomposition` (level = Total) | `fiscal_year` on Columns; `availability_pts` and `rate_of_sale_pts` as side-by-side bars; `comp_growth` as a circle on a synchronized axis. That's the same measure family, so it's not a dual-scale chart |
| Lost revenue by gap type | `stockout_summary` | stacked bars of `lost_revenue` by `fiscal_year`, colored by `spell_class` (Store stock-out red `#e34948`, Seasonal gray) |
| SNAP day-of-month | `snap_timing` | `day_of_month` on Columns, `foods_vs_household` bars, `snap_day` on Color, `state_id` as a page filter |
| Store synthetic control | `store_synthetic_paths` | `weeks_from_break` on Columns, `actual_index` and `synthetic_index` as lines, `store_id` filter |
| FY2017 outlook | `outlook_weekly` | `fiscal_week` on Columns, `revenue` lines colored by `fiscal_year` + `kind` (forecast dashed) |
