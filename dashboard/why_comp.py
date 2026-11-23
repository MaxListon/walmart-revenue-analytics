"""Why comp fell: each explanation for the comparable-sales decline, tested."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    AQUA,
    BLUE,
    CAT,
    GRAY,
    ORANGE,
    YELLOW,
    downloads,
    intro,
    load,
    show,
)


def render() -> None:
    intro("Why did existing products sell less in FY2013–FY2015?")
    st.markdown("#### Three explanations tested for the FY2013–FY2015 decline in existing-product sales")
    av = load("availability_decomposition")
    left, right = st.columns([1.2, 1])
    with left:
        d = av[av.level == "Total"]
        fig = go.Figure()
        fig.add_bar(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.availability_pts,
            name="Availability (days on shelf)",
            marker_color=ORANGE,
            hovertemplate="%{x}<br>Availability %{y:+.1%}<extra></extra>",
        )
        fig.add_bar(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.rate_of_sale_pts,
            name="Sales per available day",
            marker_color=BLUE,
            hovertemplate="%{x}<br>Rate of sale %{y:+.1%}<extra></extra>",
        )
        fig.add_scatter(
            x=[f"FY{y}" for y in d.fiscal_year],
            y=d.comp_growth,
            mode="markers+text",
            name="Comp growth",
            text=[f"{v:+.1%}" for v in d.comp_growth],
            textposition="middle right",
            marker=dict(color="#0b0b0b", size=10),
            hovertemplate="%{x}<br>Comp %{y:+.1%}<extra></extra>",
        )
        fig.update_layout(title="Comp growth = availability + sales per available day", barmode="group")
        show(fig, pct_y=True)
    with right:
        st.markdown("**1. Cannibalization? No.**")
        cm = load("cannibalization_models")
        st.dataframe(
            cm[["model", "term", "estimate", "ci_low", "ci_high", "p_value"]].style.format(
                {"estimate": "{:+.3f}", "ci_low": "{:+.3f}", "ci_high": "{:+.3f}", "p_value": "{:.3f}"}
            ),
            hide_index=True,
            height=250,
        )
        st.caption(
            "Store-departments that added more new products saw comp sales hold up *better*, not worse "
            "(cannibalization would make these negative). 280 store × dept × year observations."
        )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**2. Product lifecycle? No: every launch cohort fell together**")
        co = load("comp_by_cohort")
        fig = go.Figure()
        palette = [GRAY, BLUE, ORANGE, AQUA, YELLOW]
        for i, (name, g) in enumerate(co.groupby("cohort")):
            if g.revenue_prior.sum() < 5e5:
                continue
            fig.add_scatter(
                x=[f"FY{y}" for y in g.fiscal_year],
                y=g.comp_growth,
                name=name,
                mode="lines+markers",
                line=dict(color=palette[i % 5]),
                hovertemplate=name + "<br>%{x}: %{y:+.1%}<extra></extra>",
            )
        show(fig, pct_y=True, height=340)
    with c2:
        st.markdown("**3. Timing: same-item revenue vs a year earlier, by month**")
        m = load("monthly_same_item_yoy", parse_dates=["month"])
        fig = go.Figure()
        for cat, g in m.groupby("cat_id"):
            fig.add_scatter(
                x=g.month,
                y=g.revenue_yoy,
                name=cat.title(),
                mode="lines",
                line=dict(color=CAT[cat], width=1.8),
                hovertemplate=cat.title() + " %{x|%b %Y}: %{y:+.1%}<extra></extra>",
            )
        fig.add_hline(y=0, line_color="#c3c2b7")
        show(fig, pct_y=True, height=340)
        st.caption("FOODS turned negative in Oct 2012 and recovered in Apr 2014, matching Walmart's weak FY2014.")
    st.markdown("**Is the decline robust to how 'existing products' is defined?**")
    sens = load("comp_sensitivity").pivot(index="definition", columns="fiscal_year", values="comp_growth")
    st.dataframe(sens.style.format("{:+.1%}").background_gradient(cmap="RdBu", vmin=-0.12, vmax=0.12, axis=None))
    st.caption(
        "FY2014–15 declines hold for every full- or near-full-year definition. The loosest rule (sold once in "
        "both years) includes launches ramping up, which masks them. FY2013 is fragile."
    )

    st.markdown(
        "**Was it pricing? No: Walmart held food prices below market inflation (BLS CPI) while volume fell, "
        "and priced above it in FY2016 as sales recovered**"
    )
    sp = load("shelf_price_vs_cpi")
    sp = sp[sp.segment != "Total"]
    fig = go.Figure()
    for cat in ["FOODS", "HOUSEHOLD", "HOBBIES"]:
        g = sp[sp.segment == cat]
        fig.add_bar(
            x=[f"FY{y}" for y in g.fiscal_year],
            y=g.gap_vs_cpi_pts,
            name=cat.title(),
            marker_color=CAT[cat],
            customdata=g[["shelf_price_change", "cpi_inflation"]],
            hovertemplate=cat.title() + " %{x}<br>Walmart %{customdata[0]:+.1%} vs CPI %{customdata[1]:+.1%}"
            "<br>Gap %{y:+.1%}<extra></extra>",
        )
    fig.update_layout(title="Walmart same-item price change minus category inflation", barmode="group")
    show(fig, pct_y=True, height=340)
    ig = load("inflation_adjusted_growth")
    t = ig[ig.segment == "Total"].dropna(subset=["nominal_growth"])
    st.caption(
        "Below zero = Walmart priced under market inflation. Inflation was low, so most growth is real: "
        + ", ".join(f"FY{r.fiscal_year} {r.nominal_growth:+.1%} nominal / {r.real_growth:+.1%} real" for r in t.itertuples())
        + "."
    )
    downloads(
        "why",
        "availability_decomposition",
        "cannibalization_models",
        "comp_by_cohort",
        "comp_sensitivity",
        "monthly_same_item_yoy",
        "shelf_price_vs_cpi",
        "inflation_adjusted_growth",
    )
