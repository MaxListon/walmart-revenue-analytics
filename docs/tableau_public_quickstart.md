# Tableau Public quickstart: a one-page dashboard in about an hour

A one-page version of the story for Tableau Public, built from four small files in `outputs/tableau/public/`. Each file is shaped so every sheet is drag-and-drop: no joins, blends or table calculations. For the full two-page build, see the [full Tableau guide](tableau_build_guide.md).

Regenerate the files any time with `python -m retailrev.tableau --public` (it reads only `outputs/*.csv`).

| File | One row per | Feeds |
|---|---|---|
| `kpis.csv` | headline number (5) | KPI tiles |
| `growth.csv` | fiscal year × measure | Total vs comparable growth |
| `segments.csv` | segment × measure | Segments: products vs revenue vs stock-outs |
| `outlook.csv` | fiscal week × series | FY2017 outlook line |

## 0. Setup (5 min)
1. Install **Tableau Public Desktop** (free, Mac and Windows) from public.tableau.com, then sign in with a free Tableau Public account.
2. **Connect → Text file →** `outputs/tableau/public/kpis.csv`.
3. **Data → New Data Source** for each of the other three files. Keep them separate. Don't join them.
4. In `growth`, `outlook` and `segments`, right-click `fiscal_year`, `fiscal_week` and `segment_order` → **Convert to Dimension**, then **Convert to Discrete**.

## 1. Sheet "KPIs" (10 min) · `kpis`
1. Drag `kpi` to **Columns**, then sort it by `order` (right-click `kpi` → *Sort* → *Field* → `order`, Minimum, Ascending).
2. Drag `display` to **Text** on the Marks card, then `note` to **Text** as well.
3. Drag `kpi` to **Text** too. Click **Text** and lay out the label as three lines: `<kpi>` (size 9, `#52514e`), `<display>` (size 22, bold, `#14213d`) and `<note>` (size 9, `#52514e`).
4. Right-click the column header → uncheck *Show Header*, since the label now carries the name.

## 2. Sheet "Growth" (10 min) · `growth`
1. `fiscal_year` to **Columns**, then `measure` to **Columns** to the right of it, so the bars sit side by side.
2. `growth` to **Rows**. Right-click the axis → *Format* → *Numbers* → *Percentage*, 0 decimals.
3. `color_key` to **Color**, then *Edit Colors*: **Total** `#c3c2b7`, **Comp up** `#2a78d6`, **Comp down** `#e34948`.
4. `label` to **Label**.
5. Hide the `measure` header and use the title as the legend: *"Revenue grew every year (gray), but the same products sold less for three years (red)"*.

## 3. Sheet "Segments" (10 min) · `segments`
1. `segment_order` then `segment` to **Rows**. Right-click `segment_order` → uncheck *Show Header*.
2. `measure` to **Rows** after `segment`, so each segment gets three bars, and `measure` to **Color** as well.
3. `share` to **Columns**. Format the axis as a percentage, 0 decimals.
4. Colors: **Share of products** `#c3c2b7`, **Share of revenue** `#2a78d6`, **Share of stock-out losses** `#e34948`.
5. `playbook` to **Tooltip**.
6. Title: *"SNAP-driven staples: 14% of products, 41% of stock-out losses"*.

## 4. Sheet "Outlook" (10 min) · `outlook`
1. `fiscal_week` to **Columns** (keep it discrete or make it continuous), `revenue` to **Rows**.
2. `series` to **Color**: **FY2016 actual** `#c3c2b7`, **FY2017 actual** `#2a78d6`, **FY2017 forecast** `#2a78d6`.
3. `series` to **Path** or **Detail**, then click the line on the Marks card and pick a dashed pattern for the forecast. (Tableau 2023.2+ lets you set the line pattern per series. In older versions, use a lighter blue `#86b6ef` instead.)
4. Format the axis as currency (`$`, 0 decimals, display units: thousands).
5. Title: *"FY2017 is tracking to $48.7M (+13.8%)"*.

## 5. Dashboard (10 min)
**Size:** Fixed, 1200 × 820. Background `#f7f6f2`.

```
┌──────────────────────────────────────────────────────────────┐
│ Walmart Revenue Performance Review                            │
│ Revenue grew 65%, but the same products sold less for 3 years │
├──────────────────────────────────────────────────────────────┤
│ KPIs (5 tiles)                                                │
├──────────────────────────────┬───────────────────────────────┤
│ Growth                       │ Segments                      │
├──────────────────────────────┴───────────────────────────────┤
│ Outlook                                                       │
├──────────────────────────────────────────────────────────────┤
│ Source: M5 competition data · code: github.com/MaxListon/...  │
└──────────────────────────────────────────────────────────────┘
```

1. Drag in a **Text** object for the title and subtitle, then the four sheets in the layout above.
2. Turn off the legends that the titles already explain. Keep the Segments legend.
3. Add a **Text** footer with the data source and the GitHub link.

## 6. Publish (5 min)
1. **File → Save to Tableau Public As…** → title it **Walmart Revenue Performance Review**.
2. On the published page, edit the description: one line on the finding, plus the GitHub link.
3. Copy the URL and add it to the README's link row (next to the dashboard link) and to your resume.

## Check before publishing
- The KPI tiles read **$42.8M · +5.6% · 43% · $0.79M · $48.7M**: the same numbers as the executive summary.
- No chart uses two y-axes.
- Colors match the dashboard and deck: blue up, red down, gray for totals and context.
