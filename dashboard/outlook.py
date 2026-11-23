"""FY2017 outlook: forecast methods, backtest and the selected projection."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GRAY,
    INK2,
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
    ol = d.ol
    intro("Where will FY2017 land, and how sure can we be?")
    w, bt = load("outlook_weekly"), load("outlook_backtest")
    sel = ol[ol.selected].iloc[0]
    naive = ol[ol.method == "Chain run-rate"].iloc[0]
    k = st.columns(3)
    k[0].metric("FY2017 full-year forecast", money(sel.fy2017_forecast), f"{sel.growth_vs_fy2016:+.1%} vs FY2016")
    k[1].metric("Range (worst backtest miss)", f"{money(sel.range_low)} – {money(sel.range_high)}")
    k[2].metric(
        "Naive run-rate would say",
        money(naive.fy2017_forecast),
        f"{money(naive.fy2017_forecast - sel.fy2017_forecast)} likely too high",
        delta_color="off",
        delta_arrow="off",
    )
    # cumulative view: where the year lands, with the naive run-rate drawn for comparison
    last = w[w.fiscal_year == 2016].set_index("fiscal_week").revenue
    act = w[(w.fiscal_year == 2017) & (w.kind == "actual")].set_index("fiscal_week").revenue
    fc = w[(w.fiscal_year == 2017) & (w.kind == "forecast")].set_index("fiscal_week").revenue
    cut = act.index.max()
    naive_path = act.sum() + (last.loc[cut + 1 :] * act.sum() / last.loc[:cut].sum()).cumsum()
    fc_path = act.sum() + fc.cumsum()
    fig = go.Figure()
    for name, x, y, color, dash in [
        ("FY2016 actual", last.index, last.cumsum(), GRAY, "solid"),
        ("FY2017 actual", act.index, act.cumsum(), BLUE, "solid"),
        ("FY2017 forecast", [cut, *fc_path.index], [act.sum(), *fc_path], ORANGE, "dash"),
        ("Naive run-rate", [cut, *naive_path.index], [act.sum(), *naive_path], INK2, "dot"),
    ]:
        fig.add_scatter(
            x=x,
            y=y,
            name=name,
            mode="lines",
            line=dict(color=color, dash=dash, width=2.5),
            hovertemplate=name + " through wk %{x}: %{y:$,.0f}<extra></extra>",
        )
    fig.add_scatter(
        x=[53, 53],
        y=[sel.range_low, sel.range_high],
        mode="lines",
        name="Forecast range",
        line=dict(color=ORANGE, width=6),
        hovertemplate="Range: %{y:$,.0f}<extra></extra>",
    )
    fig.update_layout(
        title="Cumulative revenue: FY2017 actual + forecast vs FY2016 and a naive run-rate",
        xaxis_title="Fiscal week",
        hovermode="x unified",
    )
    show(fig, money_y=True, height=420)
    with st.expander("Weekly view"):
        fig = go.Figure()
        for name, s_, color, dash in [
            ("FY2016 actual", last, GRAY, "solid"),
            ("FY2017 actual", act, BLUE, "solid"),
            ("FY2017 forecast", fc, ORANGE, "dash"),
        ]:
            fig.add_scatter(
                x=s_.index,
                y=s_.values,
                name=name,
                mode="lines",
                line=dict(color=color, dash=dash, width=2),
                hovertemplate=name + " wk %{x}: %{y:$,.0f}<extra></extra>",
            )
        fig.update_layout(title="Weekly chain revenue", xaxis_title="Fiscal week", hovermode="x unified")
        show(fig, money_y=True, height=360)
    left, right = st.columns(2)
    with left:
        st.markdown("**Method comparison (backtests from week 16 of FY2014–FY2016)**")
        st.dataframe(
            ol[["method", "selected", "fy2017_forecast", "mean_abs_full_year_error", "worst_full_year_error"]].style.format(
                {"fy2017_forecast": "${:,.0f}", "mean_abs_full_year_error": "{:.1%}", "worst_full_year_error": "{:.1%}"}
            ),
            hide_index=True,
        )
    with right:
        st.markdown("**Backtest detail: full-year error by year**")
        st.dataframe(bt.pivot(index="method", columns="fiscal_year", values="full_year_error").style.format("{:+.1%}"))
    st.caption(
        "The winning method projects each store from its own year-to-date trend, but stops a store's step change "
        "(CA_2, June 2015) from compounding once it reaches its one-year anniversary."
    )
    st.markdown("#### How accurate is the forecasting? A benchmark on the M5 competition's own metric")
    fbs = load("forecast_benchmark_summary").sort_values("mean_wrmsse")
    fbr = load("forecast_benchmark")
    left, right = st.columns([1.2, 1])
    with left:
        fig = go.Figure()
        for m_ in fbs.method:
            g = fbr[fbr.method == m_]
            fig.add_scatter(
                x=g.window_start,
                y=g.wrmsse,
                mode="lines+markers",
                name=m_,
                line=dict(width=3 if m_.startswith("Calendar") else 1.5),
                hovertemplate=m_ + "<br>window from %{x|%d %b %Y}: %{y:.2f}<extra></extra>",
            )
        fig.update_layout(title="WRMSSE by 28-day window (lower is better)", xaxis_title="Window start")
        show(fig, height=380)
    with right:
        st.dataframe(
            fbs[["method", "mean_wrmsse", "windows_won", "m5_evaluation_window", "vs_seasonal_naive"]]
            .rename(
                columns={
                    "method": "Method",
                    "mean_wrmsse": "Mean WRMSSE",
                    "windows_won": "Windows won",
                    "m5_evaluation_window": "M5 evaluation window",
                    "vs_seasonal_naive": "vs seasonal naive",
                }
            )
            .style.format({"Mean WRMSSE": "{:.3f}", "M5 evaluation window": "{:.3f}", "vs seasonal naive": "{:+.0%}"}),
            hide_index=True,
            width="stretch",
        )
    st.caption(
        "28-day daily unit forecasts for the 70 store × department series, added up and scored on the 9 aggregate "
        "levels of the M5 metric (the 3 product-level levels are left out, so scores can't be compared with the Kaggle "
        "leaderboard). Six windows ending 22 May 2016 include the official M5 validation and evaluation periods. "
        "The calendar-aware method adds the SNAP-day effects found in this project to a weekday average."
    )
    downloads(
        "outlook", "outlook_fy2017", "outlook_weekly", "outlook_backtest", "forecast_benchmark", "forecast_benchmark_summary"
    )
