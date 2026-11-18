"""Walmart Revenue Performance Review: interactive dashboard.

Reads only outputs/*.csv (committed), so it runs without the raw data:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

OUT = Path(__file__).parent / "outputs"
BLUE, ORANGE, AQUA, YELLOW, RED, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#a8a69f"
INK2, GRID = "#52514e", "#e1e0d9"
CAT = {"FOODS": BLUE, "HOUSEHOLD": ORANGE, "HOBBIES": AQUA}
STATE = {"CA": BLUE, "TX": ORANGE, "WI": AQUA}
STORE_COLORS = dict(
    zip(
        ["CA_1", "CA_2", "CA_3", "CA_4", "TX_1", "TX_2", "TX_3", "WI_1", "WI_2", "WI_3"],
        [BLUE, "#86b6ef", "#1c5cab", "#5598e7", ORANGE, "#f2a07f", "#b84a1d", AQUA, "#7fd3b4", "#0f7a54"],
    )
)

st.set_page_config(page_title="Walmart Revenue Review", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")


@st.cache_data
def _read(name: str, mtime: float, **kw) -> pd.DataFrame:
    return pd.read_csv(OUT / f"{name}.csv", **kw)


def load(name: str, **kw) -> pd.DataFrame:
    # file modification time is part of the cache key, so re-running the pipeline refreshes the app
    return _read(name, (OUT / f"{name}.csv").stat().st_mtime, **kw)


def style(fig: go.Figure, height: int = 380, pct_y: bool = False, money_y: bool = False, pct_x: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=96, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        title=dict(y=0.98, yanchor="top", x=0.01, xanchor="left"),
        font=dict(size=13, family="Inter, sans-serif", color="#14213d"),
        title_font=dict(family="Space Grotesk, Inter, sans-serif", size=16),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#c3c2b7")
    if pct_y:
        fig.update_yaxes(tickformat=".0%")
    if pct_x:
        fig.update_xaxes(tickformat=".0%")
    if money_y:
        fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def money(v: float) -> str:
    return f"${v / 1e6:,.1f}M" if abs(v) >= 1e6 else f"${v / 1e3:,.0f}K"


def show(fig: go.Figure, **kw) -> None:
    st.plotly_chart(style(fig, **kw), width="stretch")


GLOSSARY = {
    "Fiscal year (FY)": "Walmart's year runs February to January and is named by the year it ends: FY2016 is "
    "Feb 2015 – Jan 2016. Growth is compared over 52 weeks because FY2014 had 53.",
    "Comparable (comp) sales": "Sales of the same products in the same stores, counting only store-products on the "
    "shelf all 52 weeks of both years. It strips out growth that comes from adding products.",
    "Revenue bridge": "Splits the change in revenue into pieces that add back to the total exactly: volume, mix and "
    "price for existing products, plus launches reaching a full year, new listings and lost listings.",
    "Volume, mix, price": "Volume: more or fewer units at last year's prices. Mix: shoppers shifting toward pricier or "
    "cheaper products. Price: the same products selling at different prices.",
    "95% confidence interval (CI)": "A range that would contain the true value 95% of the time. Here it comes from "
    "resampling products 2,000 times (a bootstrap).",
    "Store stock-out": "A run of zero-sale days (28 or fewer) that the product's own sales history makes less than "
    "0.1% likely. Lost revenue = the normal daily sales rate × the days dark.",
    "Chain-wide gap": "A product dark in most stores at once: usually a supply or range decision, not a store problem.",
    "Price elasticity": "The % change in units for a 1% change in price. At −0.4, a 5% price rise loses about 2% of "
    "units, so revenue rises; below −1, a price rise loses revenue.",
    "SNAP days": "The days each state issues food-assistance (SNAP) benefits. California, Texas and Wisconsin each "
    "use a different calendar.",
    "A/A test": "A fake experiment on real history where nothing actually changed. How much its results vary shows how "
    "noisy a real test would be.",
    "Statistical power": "The chance a test detects an effect that is really there. 80% is the usual target.",
    "Synthetic control": "A weighted 'twin' built from stores without a change, showing what a store would have done "
    "had nothing happened.",
    "Backtest": "Running a forecasting method from the same point in past years and checking it against what actually happened.",
    "Product segment": "A group of products that sell alike (speed, gaps, seasonality, SNAP lift, stock-outs), found "
    "by k-means clustering. Each segment gets its own playbook.",
}


def intro(question: str) -> None:
    st.markdown(f"**The question:** {question}")


def downloads(section: str, *names: str) -> None:
    with st.expander("Download the data behind this tab"):
        cols = st.columns(4)
        for i, name in enumerate(names):
            cols[i % 4].download_button(
                f"{name}.csv",
                data=(OUT / f"{name}.csv").read_bytes(),
                file_name=f"{name}.csv",
                mime="text/csv",
                key=f"dl_{section}_{name}",
                width="stretch",
            )


with st.sidebar:
    st.markdown("### Glossary")
    st.caption("Plain-English definitions of the terms used in this dashboard.")
    for term, definition in GLOSSARY.items():
        with st.expander(term):
            st.write(definition)


annual, comp, bridge = load("annual_revenue"), load("comp_sales"), load("revenue_bridge")
boot, ol = load("bootstrap_ci"), load("outlook_fy2017")
b16 = bridge[(bridge.fiscal_year == 2016) & (bridge.level == "Total")].iloc[0]
ci = boot.set_index(["fiscal_year", "metric"])

st.title("Walmart Revenue Performance Review")
st.caption(
    "Real Walmart unit sales × weekly shelf prices · 3,049 products · 10 stores in CA, TX, WI · "
    "fiscal 2012 to fiscal 2017 YTD (Jan 2011 to May 2016) · Source: M5 competition data"
)

tabs = st.tabs(
    [
        "Start here",
        "Overview",
        "Why comp fell",
        "Availability",
        "Products & launches",
        "Stores",
        "Pricing",
        "Calendar & SNAP",
        "FY2017 outlook",
        "Product segments",
        "Data & method",
    ]
)

# ======================================================================== start here
with tabs[0]:
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
        "conversation with replenishment."
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
                ["3", "Cut store stock-outs, starting with SNAP-driven staples", "Store operations", "30-day pilot"],
                ["4", "Review chain-wide gaps with merchandising", "Merchandising", "Next range review"],
                ["5", "Plan food stock and labor to the SNAP calendar", "Supply chain", "Next quarter"],
            ],
            columns=["#", "Action", "Suggested owner", "Timing"],
        ),
        hide_index=True,
        width="stretch",
    )

# ======================================================================== overview
with tabs[1]:
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

# ======================================================================== why comp fell
with tabs[2]:
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

# ======================================================================== availability
with tabs[3]:
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
    downloads("availability", "stockout_summary", "stockout_by_store_dept_fy2016", "stockout_top_items_fy2016")

# ======================================================================== products & launches
with tabs[4]:
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
    downloads(
        "products", "item_pareto_fy2016", "item_growth_fy2016", "launch_outcomes_fy2016", "launch_ramp_curve", "launch_rollout"
    )

# ======================================================================== stores
with tabs[5]:
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

# ======================================================================== pricing
with tabs[6]:
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
    downloads(
        "pricing",
        "price_elasticity",
        "price_event_elasticity",
        "price_event_dynamics",
        "promo_effects",
        "promo_cost",
        "price_dip_screen",
        "price_test_power",
    )

# ======================================================================== calendar
with tabs[7]:
    intro("What do SNAP benefit days and holidays do to sales?")
    snap, timing, ev = load("snap_lift"), load("snap_timing"), load("event_lift")
    left, right = st.columns(2)
    with left:
        s = snap[snap.state_id != "ALL"]
        fig = go.Figure()
        for c_ in ["FOODS", "HOUSEHOLD", "HOBBIES"]:
            d = s[s.cat_id == c_]
            fig.add_bar(
                x=d.state_id,
                y=d.snap_lift,
                name=c_.title(),
                marker_color=CAT[c_],
                error_y=dict(
                    type="data", symmetric=False, array=d.ci_high - d.snap_lift, arrayminus=d.snap_lift - d.ci_low, color=INK2
                ),
                hovertemplate=c_.title() + " · %{x}: %{y:+.1%}<extra></extra>",
            )
        fig.update_layout(title="Revenue lift on SNAP benefit days", barmode="group")
        show(fig, pct_y=True, height=400)
    with right:
        state = st.radio("State", ["CA", "TX", "WI"], horizontal=True, index=2)
        d = timing[timing.state_id == state]
        fig = go.Figure(
            go.Bar(
                x=d.day_of_month,
                y=d.foods_vs_household,
                marker_color=[STATE[state] if x else GRAY for x in d.snap_day],
                hovertemplate="Day %{x}: %{y:+.1%}<extra></extra>",
            )
        )
        fig.update_layout(title="Food vs household spending by day of month (color = SNAP day)", xaxis_title="Day of month")
        show(fig, pct_y=True, height=400)
    st.caption(
        "Food spending follows each state's SNAP calendar day by day, then sags toward month-end. Because every "
        "month has the same SNAP schedule, this shows when SNAP spending happens, not whether it's net new."
    )
    e = ev[ev.event_name != "Christmas"].sort_values("median_lift")
    fig = go.Figure()
    fig.add_bar(
        y=e.event_name,
        x=e.median_lift_day_before,
        name="Day before",
        orientation="h",
        marker_color=GRAY,
        hovertemplate="%{y} day before: %{x:+.1%}<extra></extra>",
    )
    fig.add_bar(
        y=e.event_name,
        x=e.median_lift,
        name="Event day",
        orientation="h",
        marker_color=[BLUE if v >= 0 else RED for v in e.median_lift],
        hovertemplate="%{y}: %{x:+.1%}<extra></extra>",
    )
    fig.update_layout(title="Event-day revenue vs the same weekday ±4 weeks", barmode="group")
    show(fig, pct_x=True, height=820)
    downloads("calendar", "snap_lift", "snap_timing", "event_lift")

# ======================================================================== outlook
with tabs[8]:
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
    downloads("outlook", "outlook_fy2017", "outlook_weekly", "outlook_backtest")

# ======================================================================== segments
with tabs[9]:
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

# ======================================================================== method
with tabs[10]:
    intro("Where does the data come from, and how was each number built?")
    st.markdown("""
**Data.** Real Walmart daily unit sales (59M item-store-days) and weekly shelf prices from the M5 forecasting
competition. Product names are anonymized; categories, departments, stores and states are real.
Revenue = units × that week's shelf price. M5 includes only items still sold in 2016 (survivorship);
comparable sales are robust to that.

**Comparable sales & bridge.** Store-items listed all 52 weeks of both years (FY2014 has 53 weeks; 52-week basis).
Bridge splits comp change into volume, mix and price; the remainder is launches annualizing, new and lost listings.
Ties to the cent. Bootstrap CIs resample items (2,000 draws).

**Stock-outs.** Zero-sale runs while listed, flagged when the item's observed zero-day rate in the 28 days before and
after makes the run <0.1% likely; valued at the lower of the before/after selling rates. Classified as store
stock-out, store long gap, chain-wide gap or seasonal gap.

**Causal-style models.** Cannibalization: store × dept × year panel with store-year and dept-year FE plus a placebo.
Elasticity: Poisson with item-store and store-week FE; stacked difference-in-differences around 15,246 permanent price
changes. SNAP: store-month and store-weekday FE; FOODS/HOUSEHOLD ratio for timing. Store changes: changepoint
detection + synthetic control with placebo inference. Outlook: four methods backtested from the same point in three years.

**Inflation.** BLS CPI-U (food at home, household furnishings & operations, recreation, all items), fiscal-year averages;
Walmart's same-item price change is a Paasche index on comparable store-items.

**Price-test design.** 200 A/A simulations per design on real FY2015–16 Household sales give the true noise of the
estimate; power is the chance of telling an elasticity of −0.4 from −1 at a 5% one-sided level.

**Product segments.** k-means (20 k-means++ starts) on five standardised FY2016 behaviours per product: log sales
speed, share of weeks with no sales, seasonality, SNAP-day lift and stock-out loss share. Silhouette is flat across
4–6 groups, so 5 is the smallest number that isolates a stock-out-risk group; names come from rules on the centroids.

**Reproducibility.** Every random step sorts its input first, so results don't depend on database row order; the full
pipeline was re-run and diffed against the previous outputs.
""")
    st.markdown("**Automated data-quality checks**")
    q = load("data_quality_checks")
    st.dataframe(q[["check", "type", "value", "expectation", "passed", "meaning"]], hide_index=True)
    downloads("method", "data_quality_checks")
