"""Products & launches: launch cohorts and early signals of top sellers."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    CAT,
    ORANGE,
    core,
    downloads,
    intro,
    load,
    money,
    show,
)


def render() -> None:
    d = core()
    b16 = d.b16
    intro("Which products drive revenue, and how fast do new launches ramp up?")
    par, grow = load("item_pareto_fy2016"), load("item_growth_fy2016")
    a = par.groupby("abc_class").agg(items=("item_id", "count"))
    top2 = grow.head(2).revenue_change.sum()
    k = st.columns(3)
    k[0].metric(
        "Items making 80% of revenue (A)",
        f"{a.loc['A', 'items']:,}",
        f"{a.loc['A', 'items'] / len(par):.0%} of items",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Long-tail items (C, last 5% of revenue)",
        f"{a.loc['C', 'items']:,}",
        f"{a.loc['C', 'items'] / len(par):.0%} of items",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "Revenue added by the top 2 breakout items",
        money(top2),
        f"{top2 / (b16.revenue_current - b16.revenue_prior):.0%} of FY2016 growth",
        delta_color="off",
        delta_arrow="off",
    )
    left, right = st.columns(2)
    with left:
        fig = go.Figure(
            go.Scatter(
                x=par.cum_item_share,
                y=par.cum_share,
                mode="lines",
                line=dict(color=BLUE, width=2),
                hovertemplate="Top %{x:.0%} of items → %{y:.0%} of revenue<extra></extra>",
            )
        )
        fig.update_layout(title="Revenue concentration, FY2016", xaxis_title="Share of items, ranked by revenue")
        show(fig, pct_y=True, pct_x=True)
    with right:
        r = load("launch_ramp_curve")
        fig = go.Figure()
        for cat, g in r.groupby("cat_id"):
            fig.add_scatter(
                x=g.months_since_launch,
                y=g.index_vs_steady_state,
                name=cat.title(),
                mode="lines",
                line=dict(color=CAT[cat], width=2),
                hovertemplate=cat.title() + " month %{x}: %{y:.2f}<extra></extra>",
            )
        fig.add_hline(y=1, line_color="#c3c2b7")
        fig.update_layout(title="New products' sales rate vs their steady state", xaxis_title="Months since launch in a store")
        show(fig)
        st.caption("Food launches sell at full speed from month 1; Hobbies take ~3 months to ramp.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Rollout speed by launch year**")
        ro = load("launch_rollout")
        st.dataframe(
            ro[ro.launch_fy <= 2015].style.format(
                {
                    "median_weeks_to_all_stores": "{:.0f}",
                    "share_full_rollout_within_4_weeks": "{:.0%}",
                    "avg_stores_in_first_4_weeks": "{:.1f}",
                }
            ),
            hide_index=True,
            height=300,
        )
    with c2:
        st.markdown("**FY2016 productivity: launches vs established products**")
        lo = load("launch_outcomes_fy2016")
        st.dataframe(
            lo[lo["items"] > 5][["cohort", "cat_id", "items", "revenue_per_store_item", "share_class_A"]].style.format(
                {"revenue_per_store_item": "${:,.0f}", "share_class_A": "{:.0%}"}
            ),
            hide_index=True,
            height=300,
        )
    cat = st.multiselect("Category", ["FOODS", "HOUSEHOLD", "HOBBIES"], default=["FOODS", "HOUSEHOLD", "HOBBIES"])
    fmt = {
        "revenue": "${:,.0f}",
        "revenue_change": "${:+,.0f}",
        "revenue_growth": "{:+.0%}",
        "avg_price": "${:.2f}",
        "avg_price_change": "{:+.1%}",
        "units": "{:,.0f}",
    }
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Top 15 best sellers, FY2016**")
        st.dataframe(
            par[par.cat_id.isin(cat)].head(15)[["item_id", "revenue", "units", "avg_price"]].style.format(fmt), hide_index=True
        )
    with c2:
        st.markdown("**Biggest gainers vs FY2015**")
        st.dataframe(
            grow[grow.cat_id.isin(cat)].head(15)[["item_id", "revenue_change", "revenue_growth"]].style.format(fmt),
            hide_index=True,
        )
    with c3:
        st.markdown("**Biggest decliners vs FY2015**")
        st.dataframe(
            grow[grow.cat_id.isin(cat)].tail(15).iloc[::-1][["item_id", "revenue_change", "revenue_growth"]].style.format(fmt),
            hide_index=True,
        )
    st.markdown("#### Can we tell a future top seller by week 4?")
    lsc = load("launch_model_scores")
    lcal = load("launch_model_calibration")
    rule, mdl = lsc.iloc[0], lsc.iloc[1]
    k = st.columns(3)
    k[0].metric(
        "Top-20% picks that became top sellers",
        f"{rule.precision_top20:.0%}",
        f"vs {rule.base_rate:.0%} at random",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Ranking accuracy (AUC), one-number rule",
        f"{rule.auc:.2f}",
        "0.5 = coin flip, 1 = perfect",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "Ranking accuracy (AUC), full model", f"{mdl.auc:.2f}", "no better than the rule", delta_color="off", delta_arrow="off"
    )
    fig = go.Figure()
    fig.add_bar(x=lcal.decile, y=lcal.actual, name="Actual top-seller rate", marker_color=BLUE)
    fig.add_scatter(
        x=lcal.decile, y=lcal.predicted, name="Model's predicted rate", mode="lines+markers", line=dict(color=ORANGE, width=2.5)
    )
    fig.update_layout(title="Launches grouped by predicted chance (10 = most likely top seller)", xaxis_title="Decile")
    show(fig, pct_y=True, height=360)
    st.caption(
        f"Test set: the latest {int(rule.test_launches)} launches (from {rule.test_from}); the model learned from the earlier "
        f"{int(rule.train_launches)}. Top seller = top quarter by revenue per store-week in weeks 13–52. The simple rule "
        "(first-month revenue per store-week) ranks as well as the full model, which is also overconfident at the top. "
        "M5 only includes products still sold in 2016, so launches that were withdrawn can't be predicted."
    )
    downloads(
        "products",
        "item_pareto_fy2016",
        "item_growth_fy2016",
        "launch_outcomes_fy2016",
        "launch_ramp_curve",
        "launch_rollout",
        "launch_model_scores",
        "launch_model_calibration",
        "launch_model_coefficients",
    )
