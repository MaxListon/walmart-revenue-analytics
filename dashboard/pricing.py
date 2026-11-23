"""Pricing: elasticities, price events and the price-test design."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GRAY,
    INK2,
    ORANGE,
    downloads,
    intro,
    load,
    money,
    show,
)


def render() -> None:
    intro("How price-sensitive are shoppers, and how should a price change be tested?")
    el, pev, dyn, promo = (
        load("price_elasticity"),
        load("price_event_elasticity"),
        load("price_event_dynamics"),
        load("promo_effects"),
    )
    seg = "All departments (excl. week before change)"
    inc = pev[(pev.segment == seg) & (pev.direction == "increase")].iloc[0]
    dec = pev[(pev.segment == seg) & (pev.direction == "decrease")].iloc[0]
    pr = promo.set_index("effect").loc["Units during temporary cut"]
    k = st.columns(3)
    k[0].metric(
        "Elasticity of permanent price increases",
        f"{inc.elasticity:.2f}",
        f"CI {inc.ci_low:.2f} to {inc.ci_high:.2f}",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Elasticity of permanent price cuts",
        f"{dec.elasticity:.2f}",
        f"CI {dec.ci_low:.2f} to {dec.ci_high:.2f}",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        f"Unit lift from temporary cuts (median {pr.median_price_cut:.0%})",
        f"{pr.pct_effect:+.1%}",
        f"CI {pr.ci_low_pct:+.1%} to {pr.ci_high_pct:+.1%} (not significant)",
        delta_color="off",
        delta_arrow="off",
    )
    pc = load("promo_cost").set_index("fiscal_year").loc[2016]
    dips = load("price_dip_screen").set_index("fiscal_year").loc[2016]
    st.caption(
        f"Temporary cuts are rare under everyday low pricing: in FY2016 the {pc.events:,.0f} cleanly identified cuts "
        f"gave away {money(pc.discount_given)} of discount, and a broad screen of every short price dip finds "
        f"{money(dips.discount_given)} ({dips.discount_share_of_revenue:.2%} of revenue). Household's −0.4 comes from "
        "the main panel model; the robustness checks are noisier, which is why the next step is a test."
    )
    left, right = st.columns(2)
    with left:
        specs = sorted(el.spec.unique())
        spec = st.radio("Model", specs, index=specs.index("Poisson, all item-stores"))
        d = el[el.spec == spec].sort_values("dept_id", ascending=False)
        fig = go.Figure(
            go.Scatter(
                x=d.elasticity,
                y=d.dept_id,
                mode="markers",
                marker=dict(color=BLUE, size=10),
                error_x=dict(
                    type="data", symmetric=False, array=d.ci_high - d.elasticity, arrayminus=d.elasticity - d.ci_low, color=BLUE
                ),
                hovertemplate="%{y}: %{x:.2f}<extra></extra>",
            )
        )
        fig.add_vline(x=-1, line_color=INK2, annotation_text="unit-elastic (−1)", annotation_position="bottom left")
        fig.update_layout(title="Department elasticity (95% CI)", xaxis_title="% change in units per 1% price change")
        show(fig, height=400)
    with right:
        d = dyn[dyn.kind == "permanent"].sort_values("rel_week")
        base = d.loc[d.rel_week.between(-8, -2), "estimate"].mean()
        fig = go.Figure()
        fig.add_scatter(x=d.rel_week, y=d.ci_high - base, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(
            x=d.rel_week,
            y=d.ci_low - base,
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(42,120,214,0.15)",
            showlegend=False,
            hoverinfo="skip",
        )
        fig.add_scatter(
            x=d.rel_week,
            y=d.estimate - base,
            mode="lines+markers",
            line=dict(color=BLUE, width=2),
            name="Effect",
            showlegend=False,
            hovertemplate="Week %{x}: %{y:.2f}<extra></extra>",
        )
        fig.add_vline(x=-0.5, line_color=INK2)
        fig.update_layout(
            title="Event study: units around a permanent price change",
            xaxis_title="Weeks relative to change",
            yaxis_title="Effect per unit of log price change",
        )
        show(fig, height=400)
    st.caption(
        "Event study compares a store that changed an item's price with stores selling the same item whose price "
        "didn't change (15,246 events; Poisson, clustered SEs). Treated stores dip in the week before a change, so "
        "headline numbers drop that week. Price cuts likely include 'Rollback' signage not in the data, which "
        "inflates their effect."
    )

    st.markdown("#### Designing the Household price test")
    pw = load("price_test_power")
    names = {
        "Products: half of products treated in all stores": "Randomize products",
        "Product-stores: each product treated in a random half of stores": "Randomize product-store pairs",
    }
    best = pw[(pw.design.str.startswith("Product-stores")) & (pw.price_change == 0.05) & (pw.test_weeks == 12)].iloc[0]
    k = st.columns(3)
    k[0].metric("Recommended design", "+5% on half of product-store pairs", "12 weeks", delta_color="off", delta_arrow="off")
    k[1].metric(
        "Power to tell −0.4 from −1",
        f"{best['power_detect_-0.4_vs_-1']:.0%}",
        f"A/A false-positive rate {best.aa_false_positive_rate:.0%}",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "Expected revenue lift on tested items if −0.4",
        f"{best['expected_revenue_lift_if_-0.4']:+.1%}",
        delta_color="off",
        delta_arrow="off",
    )
    fig = go.Figure()
    for (design, p_), g in pw.groupby(["design", "price_change"]):
        g = g.sort_values("test_weeks")
        fig.add_scatter(
            x=g.test_weeks,
            y=g["power_detect_-0.4_vs_-1"],
            mode="lines+markers",
            name=f"{names[design]}, +{p_:.0%}",
            line=dict(
                color={0.02: GRAY, 0.03: ORANGE, 0.05: BLUE}[p_], dash="solid" if design.startswith("Product-stores") else "dot"
            ),
            hovertemplate=names[design] + f", +{p_:.0%}<br>%{{x}} weeks: %{{y:.0%}}<extra></extra>",
        )
    fig.add_hline(y=0.8, line_color=INK2, annotation_text="80% target")
    fig.update_layout(
        title="Power by design, price change and test length (solid = product-store pairs)", xaxis_title="Test length (weeks)"
    )
    show(fig, pct_y=True, height=420)
    st.caption(
        "Power measured by simulation on real FY2015–16 Household sales: 200 'A/A tests' per design, where no "
        "price changed, give the true noise of the estimate. Randomizing whole products leaves product-to-product "
        "differences in the noise; randomizing product-store pairs compares each product with itself."
    )
    st.markdown("#### The experiment brief, and a readout on a simulated result")
    ro, rr = load("price_test_readout"), load("price_test_readout_repeats")
    show_ro = ro[["true_elasticity", "estimated_elasticity", "ci_low", "ci_high", "p_value_vs_unit_elastic", "decision"]]
    st.dataframe(
        show_ro.rename(
            columns={
                "true_elasticity": "Planted elasticity",
                "estimated_elasticity": "Estimated",
                "ci_low": "95% CI low",
                "ci_high": "95% CI high",
                "p_value_vs_unit_elastic": "p (vs −1)",
                "decision": "Decision",
            }
        ).style.format(
            {
                "Planted elasticity": "{:.2f}",
                "Estimated": "{:.2f}",
                "95% CI low": "{:.2f}",
                "95% CI high": "{:.2f}",
                "p (vs −1)": "{:.3f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    pays = rr[rr.true_elasticity == -0.4]
    flat_ = rr[rr.true_elasticity == -1.0]
    st.caption(
        "The test hasn't run, so a known demand response was planted into real FY2016 Household sales and the "
        "pre-registered analysis (docs/price_test_brief.md) was run on it. Repeated with "
        f"{len(pays)} random assignments per case: when the rise truly pays, the rule said roll out "
        f"{(pays.decision == 'Roll out').mean():.0%} of the time; when it doesn't, "
        f"{(flat_.decision == 'Roll out').mean():.0%}."
    )
    downloads(
        "pricing",
        "price_test_readout",
        "price_test_readout_repeats",
        "price_elasticity",
        "price_event_elasticity",
        "price_event_dynamics",
        "promo_effects",
        "promo_cost",
        "price_dip_screen",
        "price_test_power",
    )
