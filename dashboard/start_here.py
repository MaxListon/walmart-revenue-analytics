"""Start here: the story in six steps."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GLOSSARY,
    GRAY,
    RED,
    core,
    load,
    money,
    show,
)


def render() -> None:
    d = core()
    annual, comp, ol, b16, ci = d.annual, d.comp, d.ol, d.b16, d.ci
    seg_p = load("segment_profile")
    so_all = load("stockout_summary")
    av = load("availability_decomposition")
    el_all = load("price_elasticity")
    pw = load("price_test_power")
    sn = load("snap_lift")
    dips = load("price_dip_screen")
    fy16_ = annual[annual.fiscal_year == 2016].iloc[0]
    fy12_ = annual[annual.fiscal_year == 2012].iloc[0]
    c16 = ci.loc[(2016, "Comparable sales growth")]
    sh16 = ci.loc[(2016, "Share of total growth from existing products")]
    sel_ = ol[ol.selected].iloc[0]
    naive_ = ol[ol.method == "Chain run-rate"].iloc[0]
    so16 = so_all[so_all.fiscal_year == 2016].groupby("spell_class").lost_revenue.sum()
    av14 = av[(av.level == "Total") & (av.fiscal_year == 2014)].iloc[0]
    hh = el_all[(el_all.spec == "Poisson, all item-stores") & el_all.dept_id.str.startswith("HOUSEHOLD")]
    food_snap = sn[(sn.cat_id == "FOODS") & (sn.state_id != "ALL")].snap_lift
    best = pw[(pw.price_change == 0.05) & (pw.test_weeks == 12)].set_index("design")
    p_pairs = best.loc[best.index.str.startswith("Product-stores"), "power_detect_-0.4_vs_-1"].iloc[0]
    p_prod = best.loc[best.index.str.startswith("Products"), "power_detect_-0.4_vs_-1"].iloc[0]
    snap_seg = seg_p.set_index("segment").loc["SNAP-driven staples"]
    snap_loss_share = snap_seg.stockout_lost / seg_p.stockout_lost.sum()
    comp_part = b16.volume_effect + b16.mix_effect + b16.price_effect
    total_change = b16.revenue_current - b16.revenue_prior

    st.markdown("### The short version")
    st.markdown(
        f"Revenue across these 10 Walmart stores grew **{fy16_.revenue_52wk / fy12_.revenue_52wk - 1:.0%}** in four "
        f"years. But the same products in the same stores sold **less** for three of those years: growth came from "
        f"adding products. Existing products recovered in FY2016 (**{c16.estimate:+.1%}**). The money now is in "
        f"stock-outs, SNAP-day timing and a carefully designed price test. This page tells the story in six steps; "
        f"the other tabs hold the detail."
    )
    st.caption("New to a term? Open the glossary with the arrow at the top left.")

    def chapter(n: int, headline: str, explore: str) -> None:
        st.divider()
        st.markdown(f"#### {n}. {headline}")
        st.caption(f"Detail: the **{explore}** tab")

    chapter(1, "Revenue grew every year, but existing products shrank for three of them", "Overview")
    left, right = st.columns([1, 1.4])
    with left:
        st.metric("Revenue, FY2012 → FY2016", f"{money(fy12_.revenue_52wk)} → {money(fy16_.revenue_52wk)}")
        st.metric(
            "Comparable sales, FY2016",
            f"{c16.estimate:+.1%}",
            f"after {comp[comp.fiscal_year < 2016].comp_growth.min():+.1%} at the FY2014 low",
            delta_color="off",
            delta_arrow="off",
            help=GLOSSARY["Comparable (comp) sales"],
        )
        st.write(
            "Total growth (gray) looked healthy every year. Comparable sales (red and blue) strip out new products: "
            "they fell in FY2013, FY2014 and FY2015."
        )
    with right:
        d = annual.merge(comp[["fiscal_year", "comp_growth"]], on="fiscal_year").dropna(subset=["yoy_52wk"])
        fig = go.Figure()
        fig.add_bar(x=[f"FY{y}" for y in d.fiscal_year], y=d.yoy_52wk, name="Total growth", marker_color=GRAY)
        fig.add_bar(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.comp_growth,
            name="Comparable growth (red = down)",
            marker_color=[BLUE if v >= 0 else RED for v in d.comp_growth],
        )
        fig.update_traces(hovertemplate="%{x}: %{y:+.1%}<extra>%{fullData.name}</extra>")
        show(fig, pct_y=True, height=300)

    chapter(2, f"Only {sh16.estimate:.0%} of FY2016's growth came from products already on the shelf", "Overview")
    left, right = st.columns([1, 1.4])
    with left:
        st.metric(
            "Share of FY2016 growth from existing products",
            f"{sh16.estimate:.0%}",
            f"95% CI {sh16.ci_low:.0%}–{sh16.ci_high:.0%}",
            delta_color="off",
            delta_arrow="off",
            help=GLOSSARY["Revenue bridge"],
        )
        st.write(
            f"Of the {money(total_change)} increase, existing products added {money(comp_part)}. Last year's "
            f"launches reaching a full year added {money(b16.launch_annualization_effect)} on their own."
        )
    with right:
        parts = pd.DataFrame(
            {
                "piece": ["Existing products", "Launches reaching a full year", "New listings", "Lost listings"],
                "amount": [
                    comp_part,
                    b16.launch_annualization_effect,
                    b16.new_listings_effect,
                    b16.lost_listings_effect,
                ],
            }
        )
        fig = go.Figure(
            go.Bar(
                y=parts.piece,
                x=parts.amount,
                orientation="h",
                marker_color=[BLUE, GRAY, GRAY, RED],
                text=[money(v) for v in parts.amount],
                textposition="outside",
                hovertemplate="%{y}: %{x:$,.0f}<extra></extra>",
            )
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(title="Where FY2016's growth came from")
        show(fig, height=300)

    chapter(3, "Existing products shrank because of weaker demand, not cannibalization or pricing", "Why comp fell")
    v = st.columns(4)
    v[0].markdown("**Cannibalization: ruled out.** Departments that added more products held up *better*.")
    v[1].markdown("**Product ageing: ruled out.** Old and new products fell together, then recovered together.")
    v[2].markdown(
        f"**Availability: partial.** Fewer days on the shelf explain {abs(av14.availability_pts) * 100:.1f} of "
        f"FY2014's {abs(av14.comp_growth) * 100:.1f}-point drop."
    )
    v[3].markdown(
        "**Pricing: ruled out.** Food prices sat below food inflation while volume fell. **Most of it was weaker "
        "demand**, timed with Walmart's weakest reported year."
    )

    chapter(4, "The money: stock-outs, chain-wide gaps and SNAP timing", "Availability and Product segments")
    k = st.columns(4)
    k[0].metric(
        "Store stock-outs, FY2016",
        money(so16.get("Store stock-out", 0)),
        "revenue lost",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["Store stock-out"],
    )
    k[1].metric(
        "Chain-wide gaps, FY2016",
        money(so16.get("Chain-wide gap", 0)),
        "a supply or range question",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["Chain-wide gap"],
    )
    k[2].metric(
        "Food lift on SNAP days",
        f"+{food_snap.min():.0%} to +{food_snap.max():.0%}",
        "by state",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["SNAP days"],
    )
    k[3].metric(
        "Stock-out losses in SNAP-driven staples",
        f"{snap_loss_share:.0%}",
        f"from {snap_seg.product_share:.0%} of products",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["Product segment"],
    )
    st.write(
        "SNAP-driven food staples sell out around SNAP benefit days, so stock-outs and SNAP timing are one "
        "conversation with replenishment. Not all of the loss can be won back: an ordering simulation calibrated to "
        "these losses says about a quarter (≈$0.2M a year) is realistic for a modest rise in safety stock."
    )

    chapter(5, "Pricing: Household is the place to test a price rise, carefully", "Pricing")
    k = st.columns(3)
    k[0].metric(
        "Household price elasticity (main model)",
        f"{hh.elasticity.mean():.1f}",
        "checks are noisier",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["Price elasticity"],
    )
    k[1].metric(
        "Power of the recommended test",
        f"{p_pairs:.0%}",
        f"vs {p_prod:.0%} for the obvious design",
        delta_color="off",
        delta_arrow="off",
        help=GLOSSARY["Statistical power"],
    )
    k[2].metric(
        "Temporary price-cut discounts, FY2016",
        money(dips.set_index("fiscal_year").loc[2016, "discount_given"]),
        "rare under everyday low pricing",
        delta_color="off",
        delta_arrow="off",
    )
    st.write(
        "A 5% Household increase on a random half of product-store pairs for 12 weeks can tell a revenue-raising "
        "price rise from a revenue-neutral one. Randomizing whole products cannot."
    )

    chapter(6, f"FY2017 is tracking to {money(sel_.fy2017_forecast)}", "FY2017 outlook")
    k = st.columns(3)
    k[0].metric(
        "FY2017 forecast",
        money(sel_.fy2017_forecast),
        f"{sel_.growth_vs_fy2016:+.1%} vs FY2016",
        help=GLOSSARY["Backtest"],
    )
    k[1].metric("Forecast range", f"{money(sel_.range_low)} – {money(sel_.range_high)}")
    k[2].metric(
        "Naive run-rate would say",
        money(naive_.fy2017_forecast),
        f"{money(naive_.fy2017_forecast - sel_.fy2017_forecast)} likely too high",
        delta_color="off",
        delta_arrow="off",
    )

    st.divider()
    st.markdown("#### What to do")
    st.dataframe(
        pd.DataFrame(
            [
                ["1", "Report comparable sales next to total growth", "Finance", "Next monthly review"],
                ["2", "Test a 5% Household price increase", "Pricing", "12-week test"],
                [
                    "3",
                    "Cut store stock-outs, starting with SNAP-driven staples (≈$0.2M/yr recoverable)",
                    "Store operations",
                    "30-day pilot",
                ],
                ["4", "Review chain-wide gaps with merchandising", "Merchandising", "Next range review"],
                ["5", "Plan food stock and labor to the SNAP calendar", "Supply chain", "Next quarter"],
            ],
            columns=["#", "Action", "Suggested owner", "Timing"],
        ),
        hide_index=True,
        width="stretch",
    )
