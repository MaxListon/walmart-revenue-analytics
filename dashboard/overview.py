"""Overview: total vs comparable growth and the revenue bridge."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GRAY,
    GRID,
    INK2,
    RED,
    core,
    downloads,
    intro,
    load,
    money,
    show,
)


def render() -> None:
    d = core()
    annual, comp, bridge, ol, ci = d.annual, d.comp, d.bridge, d.ol, d.ci
    intro("How fast is revenue growing, and how much of that growth is real?")
    fy16 = annual[annual.fiscal_year == 2016].iloc[0]
    c = ci.loc[(2016, "Comparable sales growth")]
    sh = ci.loc[(2016, "Share of total growth from existing products")]
    sel = ol[ol.selected].iloc[0]
    k = st.columns(4)
    k[0].metric("FY2016 revenue", money(fy16.revenue_52wk), f"{fy16.yoy_52wk:+.1%} vs FY2015")
    k[1].metric(
        "FY2016 comparable sales",
        f"{c.estimate:+.1%}",
        f"95% CI {c.ci_low:+.1%} to {c.ci_high:+.1%}",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "Growth from existing products",
        f"{sh.estimate:.0%}",
        f"95% CI {sh.ci_low:.0%}–{sh.ci_high:.0%}",
        delta_color="off",
        delta_arrow="off",
    )
    k[3].metric(
        "FY2017 outlook",
        money(sel.fy2017_forecast),
        f"{sel.growth_vs_fy2016:+.1%} (range {money(sel.range_low)}–{money(sel.range_high)})",
    )

    left, right = st.columns(2)
    with left:
        d = annual.merge(comp[["fiscal_year", "comp_growth"]], on="fiscal_year").dropna(subset=["yoy_52wk"])
        fig = go.Figure()
        fig.add_bar(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.yoy_52wk,
            name="Total revenue growth",
            marker_color=GRAY,
            hovertemplate="%{x}<br>Total growth %{y:+.1%}<extra></extra>",
        )
        err = ci.xs("Comparable sales growth", level=1).reindex(d.fiscal_year)
        fig.add_bar(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.comp_growth,
            name="Comparable sales growth (95% CI)",
            marker_color=[BLUE if v >= 0 else RED for v in d.comp_growth],
            error_y=dict(
                type="data",
                symmetric=False,
                array=(err.ci_high - err.estimate).to_numpy(),
                arrayminus=(err.estimate - err.ci_low).to_numpy(),
                color=INK2,
            ),
            hovertemplate="%{x}<br>Comp growth %{y:+.1%}<extra></extra>",
        )
        fig.update_layout(title="Total vs comparable growth (52-week basis)", barmode="group", bargap=0.3)
        show(fig, pct_y=True)
        st.caption(
            "Comparable = store-items on the shelf all 52 weeks of both years. Existing products shrank for three "
            "straight years while new listings carried total growth. CIs: item bootstrap, 2,000 draws."
        )
    with right:
        c1, c2, c3 = st.columns(3)
        year = c1.selectbox("Fiscal year", [2016, 2015, 2014, 2013])
        level = c2.selectbox("View by", ["Total", "Category", "State", "Store", "Department"])
        segs = bridge[(bridge.fiscal_year == year) & (bridge.level == level)].segment.tolist()
        seg = c3.selectbox("Segment", segs, disabled=level == "Total")
        b = bridge[(bridge.fiscal_year == year) & (bridge.level == level) & (bridge.segment == seg)].iloc[0]
        steps = [
            ("Volume", b.volume_effect),
            ("Mix", b.mix_effect),
            ("Price", b.price_effect),
            ("Launches annualizing", b.launch_annualization_effect),
            ("New listings", b.new_listings_effect),
            ("Lost listings", b.lost_listings_effect),
        ]
        fig = go.Figure(
            go.Waterfall(
                x=[f"FY{year - 1}"] + [s[0] for s in steps] + [f"FY{year}"],
                measure=["absolute"] + ["relative"] * len(steps) + ["total"],
                y=[b.revenue_prior] + [s[1] for s in steps] + [b.revenue_current],
                increasing=dict(marker_color=BLUE),
                decreasing=dict(marker_color=RED),
                totals=dict(marker_color=GRAY),
                connector=dict(line=dict(color=GRID)),
                hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
            )
        )
        fig.update_layout(title=f"Revenue bridge, FY{year} vs FY{year - 1}" + ("" if level == "Total" else f": {seg}"))
        fig.update_yaxes(range=[min(b.revenue_prior, b.revenue_current) * 0.8, max(b.revenue_prior, b.revenue_current) * 1.05])
        show(fig, money_y=True)
        st.caption(
            f"Comp growth for this segment: {b.comp_growth:+.1%}. Volume + mix + price = existing products "
            "(ties exactly to comp); the rest is assortment change. Y-axis truncated."
        )

    st.markdown("**External sanity check: Walmart U.S. reported comparable sales**")
    ext = load("external_benchmark")
    st.dataframe(
        ext[["fiscal_year", "walmart_us_comp_sales", "comp_growth", "total_growth_52wk"]]
        .rename(
            columns={
                "fiscal_year": "Fiscal year",
                "walmart_us_comp_sales": "Walmart U.S. comps (10-K)",
                "comp_growth": "This sample: same-item comp",
                "total_growth_52wk": "This sample: total growth",
            }
        )
        .style.format(
            {
                "Walmart U.S. comps (10-K)": "{:+.1%}",
                "This sample: same-item comp": "{:+.1%}",
                "This sample: total growth": "{:+.1%}",
            }
        ),
        hide_index=True,
    )
    st.caption(
        "FY2014 is the weakest year in both. Levels differ by design: store comps include newly added products and "
        "e-commerce; this sample's comp tracks the same products only. Source: Walmart FY2016 annual report."
    )
    downloads("overview", "annual_revenue", "comp_sales", "revenue_bridge", "bootstrap_ci", "external_benchmark")
