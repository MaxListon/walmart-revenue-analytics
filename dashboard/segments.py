"""Product segments: five k-means groups and their playbooks."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    AQUA,
    BLUE,
    GRAY,
    ORANGE,
    YELLOW,
    downloads,
    intro,
    load,
    show,
)


def render() -> None:
    intro("Which products behave alike, and what should each group get?")
    sp, si, sk = load("segment_profile"), load("product_segments"), load("segment_k_selection")
    seg_order = sp.segment.tolist()  # by revenue
    seg_color = dict(zip(seg_order, [BLUE, ORANGE, AQUA, YELLOW, GRAY]))
    sp["stockout_loss_share"] = sp.stockout_lost / sp.stockout_lost.sum()
    st.markdown("#### Five product segments, each with its own playbook")
    k = st.columns(len(sp))
    for col, r in zip(k, sp.itertuples()):
        col.metric(f"{r.segment} · {r.products:,} products", f"{r.revenue_share:.0%} of revenue")
    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        for c_, color, label in [
            ("product_share", GRAY, "Share of products"),
            ("revenue_share", BLUE, "Share of revenue"),
            ("stockout_loss_share", ORANGE, "Share of store stock-out losses"),
        ]:
            fig.add_bar(
                y=sp.segment,
                x=sp[c_],
                name=label,
                orientation="h",
                marker_color=color,
                hovertemplate="%{y}: %{x:.0%}<extra>" + label + "</extra>",
            )
        fig.update_layout(title="Products, revenue and stock-out losses by segment", barmode="group")
        fig.update_yaxes(autorange="reversed")
        show(fig, pct_x=True, height=460)
    with right:
        fig = go.Figure()
        for seg in seg_order:
            g = si[si.segment == seg]
            fig.add_scatter(
                x=g.velocity,
                y=g.snap_lift,
                mode="markers",
                name=seg,
                marker=dict(color=seg_color[seg], size=6, opacity=0.6),
                customdata=g[["item_id", "dept_id"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>%{x:.1f} units/store-week · SNAP %{y:+.0%}"
                "<extra>" + seg + "</extra>",
            )
        fig.update_xaxes(type="log", title="Units per store-week (log scale)")
        fig.update_layout(title="Every product: sales speed vs SNAP-day lift", yaxis_title="SNAP-day lift")
        show(fig, pct_y=True, height=460)
    st.markdown("**Segment profiles and playbooks**")
    st.dataframe(
        sp[
            [
                "segment",
                "products",
                "revenue_share",
                "stockout_loss_share",
                "median_velocity",
                "median_zero_share",
                "median_seasonality",
                "median_snap_lift",
                "median_growth",
                "food_share",
                "playbook",
            ]
        ].style.format(
            {
                "revenue_share": "{:.0%}",
                "stockout_loss_share": "{:.0%}",
                "median_velocity": "{:.1f}",
                "median_zero_share": "{:.0%}",
                "median_seasonality": "{:.2f}",
                "median_snap_lift": "{:+.0%}",
                "median_growth": "{:+.1%}",
                "food_share": "{:.0%}",
            }
        ),
        hide_index=True,
    )
    pick = st.selectbox("Top products in segment", seg_order)
    st.dataframe(
        si[si.segment == pick]
        .nlargest(15, "revenue")[["item_id", "dept_id", "revenue", "velocity", "snap_lift", "stockout_share", "growth"]]
        .style.format(
            {
                "revenue": "${:,.0f}",
                "velocity": "{:.1f}",
                "snap_lift": "{:+.0%}",
                "stockout_share": "{:.1%}",
                "growth": "{:+.1%}",
            }
        ),
        hide_index=True,
    )
    chosen = sk[sk.selected].iloc[0]
    st.caption(
        "k-means on five FY2016 behaviours per product: sales speed, share of weeks with no sales, seasonality, "
        f"SNAP-day lift and stock-out losses (standardised). Silhouette is flat across 4–6 segments "
        f"({sk.silhouette.min():.2f}–{sk.silhouette.max():.2f}), so 5 was chosen as the smallest number that separates "
        f"a stock-out-risk group. Stability across random starts: adjusted Rand {chosen.stability_ari:.2f}."
    )
    downloads("segments", "product_segments", "segment_profile", "segment_k_selection")
