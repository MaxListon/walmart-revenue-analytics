"""Stores: store-level growth and synthetic-control step changes."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    GRAY,
    INK2,
    STATE,
    STORE_COLORS,
    core,
    downloads,
    intro,
    load,
    show,
)


def render() -> None:
    d = core()
    bridge = d.bridge
    intro("Which stores grew, and which ones changed step for good?")
    sc = load("store_scorecard_fy2016")
    sb = bridge[(bridge.fiscal_year == 2016) & (bridge.level == "Store")].set_index("segment")
    sc["comp_growth"] = sc.store_id.map(sb.comp_growth)
    syn, paths = load("store_synthetic_control"), load("store_synthetic_paths")
    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        for stt, g in sc.groupby("state_id"):
            fig.add_scatter(
                x=g.revenue,
                y=g.comp_growth,
                mode="markers+text",
                text=g.store_id,
                textposition="top center",
                name=stt,
                marker=dict(color=STATE[stt], size=12, line=dict(color="white", width=2)),
                customdata=g[["yoy_growth"]],
                hovertemplate="%{text}<br>Revenue %{x:$,.0f}<br>Comp %{y:+.1%}<br>Total %{customdata[0]:+.1%}<extra></extra>",
            )
        fig.update_layout(title="FY2016 store size vs comparable growth", xaxis_title="FY2016 revenue")
        fig.update_xaxes(tickprefix="$", tickformat="~s")
        show(fig, pct_y=True, height=420)
    with right:
        store = st.selectbox("Store step change", syn.store_id.tolist())
        p = paths[paths.store_id == store]
        r = syn.set_index("store_id").loc[store]
        fig = go.Figure()
        fig.add_scatter(x=p.weeks_from_break, y=p.synthetic_index, name="Synthetic twin", line=dict(color=GRAY))
        fig.add_scatter(x=p.weeks_from_break, y=p.actual_index, name=store, line=dict(color=STORE_COLORS[store]))
        fig.add_vline(x=0, line_color=INK2)
        fig.update_layout(
            title=f"{store} vs its synthetic twin: {r.effect_vs_synthetic:+.0%} after {r.break_week}",
            xaxis_title="Weeks from break",
        )
        show(fig, height=420)
        st.caption(
            f"Twin = {r.top_donors}. Larger than all {int(r.placebo_stores)} placebo stores (p = {r.placebo_p_value:.2f}, "
            f"the minimum possible). Cause not in the data; step-ups were food-led."
        )
    wk = load("weekly_revenue_store_category", parse_dates=["week_start"])
    stores = st.multiselect("Stores", sorted(wk.store_id.unique()), default=["CA_3", "CA_2", "WI_2"])
    f = wk[wk.store_id.isin(stores)].groupby(["week_start", "store_id"], as_index=False).revenue.sum()
    fig = go.Figure()
    for s_ in sorted(stores):
        g = f[f.store_id == s_]
        fig.add_scatter(
            x=g.week_start,
            y=g.revenue,
            name=s_,
            mode="lines",
            line=dict(color=STORE_COLORS[s_], width=1.6),
            hovertemplate=s_ + " %{x|%b %d, %Y}: %{y:$,.0f}<extra></extra>",
        )
    fig.update_layout(title="Weekly revenue", hovermode="x unified")
    show(fig, money_y=True)
    downloads(
        "stores", "store_scorecard_fy2016", "store_synthetic_control", "store_synthetic_paths", "weekly_revenue_store_category"
    )
