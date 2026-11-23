"""Availability: revenue lost to stock-outs and gaps."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GRAY,
    ORANGE,
    RED,
    YELLOW,
    core,
    downloads,
    intro,
    load,
    money,
    show,
)


def render() -> None:
    d = core()
    annual = d.annual
    intro("How much revenue is lost while listed products sit at zero sales?")
    s = load("stockout_summary")
    t = s.groupby(["fiscal_year", "spell_class"])["lost_revenue"].sum().unstack()
    so16 = t.loc[2016, "Store stock-out"]
    k = st.columns(3)
    k[0].metric(
        "FY2016 revenue lost to store stock-outs",
        money(so16),
        f"{so16 / annual.set_index('fiscal_year').loc[2016, 'revenue_52wk']:.1%} of revenue",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric("Chain-wide gaps (supply / ranging)", money(t.loc[2016, "Chain-wide gap"]))
    k[2].metric("Seasonal gaps (intentional)", money(t.loc[2016, "Seasonal gap"]))
    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        for cls, col in [
            ("Store stock-out", RED),
            ("Store long gap", ORANGE),
            ("Chain-wide gap", YELLOW),
            ("Seasonal gap", GRAY),
        ]:
            fig.add_bar(
                x=[f"FY{y}" for y in t.index],
                y=t[cls],
                name=cls,
                marker_color=col,
                hovertemplate=cls + "<br>%{x}: %{y:$,.0f}<extra></extra>",
            )
        fig.update_layout(barmode="stack", title="Revenue while listed products sat at zero sales")
        show(fig, money_y=True)
        st.caption(
            "Flagged when a zero-sale run had <0.1% chance given the item's own history in the 28 days before and "
            "after. Store stock-out = ≤28 days. Longer gaps: seasonal if they recur each year; chain-wide if ≥4 other "
            "stores are dark at the same time."
        )
    with right:
        bs = load("stockout_by_store_dept_fy2016")
        g = bs[bs.spell_class == "Store stock-out"].groupby("store_id").lost_revenue.sum().sort_values()
        fig = go.Figure(
            go.Bar(x=g.values, y=g.index, orientation="h", marker_color=RED, hovertemplate="%{y}: %{x:$,.0f}<extra></extra>")
        )
        fig.update_layout(title="FY2016 store stock-out losses by store")
        fig.update_xaxes(tickprefix="$", tickformat="~s")
        show(fig)
    st.markdown("**Top products by FY2016 stock-out losses**")
    ti = load("stockout_top_items_fy2016")
    st.dataframe(ti.style.format({"lost_revenue": "${:,.0f}"}), hide_index=True, height=300)
    st.markdown("#### How much of the stock-out loss is realistically recoverable?")
    sim = load("stockout_policy_simulation")
    allp = sim[sim.segment == "All"]
    flat = allp[allp.policy == "Flat forecast (current)"].set_index("z_increase")
    staples = sim[(sim.segment == "SNAP-driven staples") & (sim.policy == "SNAP-aware for staples")]
    k = st.columns(3)
    k[0].metric(
        "Loss recovered with a moderate safety-stock rise (+0.5 SD)",
        f"{flat.loc[0.5, 'share_of_loss_recovered']:.0%}",
        f"{money(flat.loc[0.5, 'revenue_recovered'])} a year",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Extra inventory it takes",
        money(flat.loc[0.5, "extra_inventory_value"]),
        "average stock on hand, at shelf price",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "SNAP-aware ordering, staples",
        f"{money(staples.saving_vs_flat_at_same_inventory.dropna().median())} a year",
        "less lost at the same inventory",
        delta_color="off",
        delta_arrow="off",
    )
    left, right = st.columns(2)
    for col, seg, title in [
        (left, "All", "All simulated products"),
        (right, "SNAP-driven staples", "SNAP-driven staples"),
    ]:
        with col:
            g = sim[sim.segment == seg]
            fig = go.Figure()
            for pol, color in [("Flat forecast (current)", GRAY), ("SNAP-aware for staples", BLUE)]:
                h = g[g.policy == pol].sort_values("avg_inventory_value")
                fig.add_scatter(
                    x=h.avg_inventory_value,
                    y=h.lost_revenue,
                    mode="lines+markers",
                    name=pol,
                    line=dict(color=color, width=2.5),
                    customdata=h.z_increase,
                    hovertemplate=pol + "<br>safety stock +%{customdata} SD<br>inventory %{x:$,.0f}"
                    "<br>lost %{y:$,.0f}<extra></extra>",
                )
            fig.update_layout(title=f"{title}: revenue lost vs inventory held", xaxis_title="Average inventory")
            fig.update_xaxes(tickprefix="$", tickformat="~s")
            show(fig, money_y=True, height=380)
    st.caption(
        "Simulation, not measurement: every store-product in the SNAP-driven staples and availability-risk segments, "
        "FY2016 demand (actual sales plus estimated lost sales), weekly orders with a 3-day lead time, safety stock "
        "calibrated so today's policy loses what the detector measured. Holding more stock always cuts losses, so "
        "policies are compared at equal inventory. Scaled to all store stock-outs, about $0.2M a year is realistically "
        "recoverable, not the full $0.79M."
    )
    downloads(
        "availability",
        "stockout_summary",
        "stockout_by_store_dept_fy2016",
        "stockout_top_items_fy2016",
        "stockout_policy_simulation",
    )
