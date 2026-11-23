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
    write_public_extracts()


def public_extracts() -> dict[str, pd.DataFrame]:
    """Four small, tidy tables for the one-page Tableau Public dashboard (docs/tableau_public_quickstart.md).

    Each is shaped so every sheet is a drag-and-drop build: no joins, blends or table calculations.
    Built only from outputs/*.csv, so it runs without the raw data.
    """
    annual = pd.read_csv(OUTPUTS / "annual_revenue.csv").set_index("fiscal_year")
    comp = pd.read_csv(OUTPUTS / "comp_sales.csv")
    boot = pd.read_csv(OUTPUTS / "bootstrap_ci.csv").set_index(["fiscal_year", "metric"])
    so = pd.read_csv(OUTPUTS / "stockout_summary.csv")
    seg = pd.read_csv(OUTPUTS / "segment_profile.csv")
    ol = pd.read_csv(OUTPUTS / "outlook_fy2017.csv")
    weekly = pd.read_csv(OUTPUTS / "outlook_weekly.csv")

    sel = ol[ol.selected].iloc[0]
    share = boot.loc[(2016, "Share of total growth from existing products")]
    comp16 = comp.set_index("fiscal_year").loc[2016]
    lost = so[(so.fiscal_year == 2016) & (so.spell_class == "Store stock-out")].lost_revenue.sum()
    kpis = pd.DataFrame(
        [
            (
                1,
                "FY2016 revenue",
                annual.loc[2016, "revenue_52wk"],
                f"${annual.loc[2016, 'revenue_52wk'] / 1e6:.1f}M",
                f"{annual.loc[2016, 'revenue_52wk'] / annual.loc[2012, 'revenue_52wk'] - 1:+.0%} since FY2012",
            ),
            (2, "FY2016 comparable sales", comp16.comp_growth, f"{comp16.comp_growth:+.1%}", "after three years of decline"),
            (
                3,
                "Growth from existing products",
                share.estimate,
                f"{share.estimate:.0%}",
                "of FY2016's increase; the rest is new products",
            ),
            (
                4,
                "Lost to store stock-outs",
                lost,
                f"${lost / 1e6:.2f}M",
                f"in FY2016 ({lost / annual.loc[2016, 'revenue_52wk']:.1%} of revenue)",
            ),
            (
                5,
                "FY2017 outlook",
                sel.fy2017_forecast,
                f"${sel.fy2017_forecast / 1e6:.1f}M",
                f"{sel.growth_vs_fy2016:+.1%} vs FY2016",
            ),
        ],
        columns=["order", "kpi", "value", "display", "note"],
    )

    growth = comp.melt(
        id_vars="fiscal_year", value_vars=["total_growth_52wk", "comp_growth"], var_name="measure", value_name="growth"
    )
    growth["measure"] = growth.measure.map({"total_growth_52wk": "Total growth", "comp_growth": "Comparable sales"})
    growth["color_key"] = growth.apply(
        lambda r: "Total" if r.measure == "Total growth" else ("Comp up" if r.growth >= 0 else "Comp down"), axis=1
    )
    growth["label"] = growth.growth.map(lambda v: f"{v:+.1%}".replace("-", "−"))

    seg = seg.assign(stockout_share=seg.stockout_lost / seg.stockout_lost.sum())
    segments = seg.melt(
        id_vars=["segment", "playbook"],
        value_vars=["product_share", "revenue_share", "stockout_share"],
        var_name="measure",
        value_name="share",
    )
    segments["measure"] = segments.measure.map(
        {"product_share": "Share of products", "revenue_share": "Share of revenue", "stockout_share": "Share of stock-out losses"}
    )
    order = {s: i + 1 for i, s in enumerate(seg.sort_values("revenue_share", ascending=False).segment)}
    segments.insert(0, "segment_order", segments.segment.map(order))

    outlook = weekly.assign(series="FY" + weekly.fiscal_year.astype(str) + " " + weekly.kind)[
        ["fiscal_year", "fiscal_week", "series", "revenue"]
    ]

    return {
        "kpis": kpis,
        "growth": growth.sort_values(["fiscal_year", "measure"], ascending=[True, False]),
        "segments": segments.sort_values(["segment_order", "measure"]),
        "outlook": outlook,
    }


def write_public_extracts() -> None:
    out = OUTPUTS / "tableau" / "public"
    out.mkdir(parents=True, exist_ok=True)
    for name, df in public_extracts().items():
        df.to_csv(out / f"{name}.csv", index=False)
    print("  wrote 4 Tableau Public extracts to outputs/tableau/public/")


if __name__ == "__main__":
    import sys

    write_public_extracts() if "--public" in sys.argv else main()
