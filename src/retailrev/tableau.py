"""Write Tableau-ready extracts to outputs/tableau/ (flat, tidy, one grain each).

Usage:  python -m retailrev.tableau
"""

from __future__ import annotations

import pandas as pd

from retailrev.paths import OUTPUTS, connect

ITEM_STORE_YEAR_SQL = """
WITH y AS (
    SELECT fiscal_year, store_id, state_id, item_id, dept_id, cat_id,
           sum(revenue) AS revenue, sum(units) AS units, count(*) AS weeks_listed
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
    GROUP BY ALL
)
SELECT *, revenue / nullif(units, 0) AS avg_unit_price
FROM y ORDER BY fiscal_year, store_id, item_id
"""


def main() -> None:
    out = OUTPUTS / "tableau"
    out.mkdir(parents=True, exist_ok=True)

    con = connect()
    iy = con.execute(ITEM_STORE_YEAR_SQL).df()
    con.close()
    abc = pd.read_csv(OUTPUTS / "item_pareto_fy2016.csv")[["item_id", "abc_class"]]
    iy = iy.merge(abc.rename(columns={"abc_class": "abc_class_fy2016"}), on="item_id", how="left")
    iy.to_csv(out / "item_store_year.csv", index=False)

    weekly = pd.read_csv(OUTPUTS / "weekly_revenue_store_category.csv")
    weekly.to_csv(out / "weekly_store_category.csv", index=False)

    # Bridge in long format: one row per component, ready for a waterfall.
    b = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    comps = {
        "revenue_prior": ("0 Prior year", "Total"),
        "volume_effect": ("1 Volume", "Comp"),
        "mix_effect": ("2 Mix", "Comp"),
        "price_effect": ("3 Price", "Comp"),
        "launch_annualization_effect": ("4 Launches annualizing", "Assortment"),
        "new_listings_effect": ("5 New listings", "Assortment"),
        "lost_listings_effect": ("6 Lost listings", "Assortment"),
        "revenue_current": ("7 Current year", "Total"),
    }
    long = b.melt(id_vars=["fiscal_year", "level", "segment"], value_vars=list(comps), var_name="component", value_name="amount")
    long["step"] = long["component"].map(lambda c: comps[c][0])
    long["group"] = long["component"].map(lambda c: comps[c][1])
    long.sort_values(["fiscal_year", "level", "segment", "step"]).to_csv(out / "revenue_bridge_long.csv", index=False)

    for name in (
        "store_scorecard_fy2016",
        "event_lift",
        "snap_lift",
        "price_elasticity",
        "comp_sales",
        "annual_revenue",
        "availability_decomposition",
        "stockout_summary",
        "snap_timing",
        "store_synthetic_paths",
        "outlook_weekly",
        "outlook_fy2017",
        "price_event_dynamics",
        "bootstrap_ci",
        "monthly_same_item_yoy",
        "shelf_price_vs_cpi",
        "inflation_adjusted_growth",
        "price_test_power",
        "product_segments",
        "segment_profile",
        "promo_cost",
    ):
        pd.read_csv(OUTPUTS / f"{name}.csv").to_csv(out / f"{name}.csv", index=False)
    print(f"  wrote {len(list(out.glob('*.csv')))} extracts to outputs/tableau/ (item_store_year: {len(iy):,} rows)")


if __name__ == "__main__":
    main()
