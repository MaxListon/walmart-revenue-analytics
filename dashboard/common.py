"""Shared pieces for every dashboard tab: palette, data loading, chart styling and small widgets."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

OUT = Path(__file__).resolve().parents[1] / "outputs"
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


def core() -> SimpleNamespace:
    """The frames several tabs share: annual revenue, comp sales, the bridge, bootstrap CIs and the outlook."""
    annual, comp, bridge = load("annual_revenue"), load("comp_sales"), load("revenue_bridge")
    boot, ol = load("bootstrap_ci"), load("outlook_fy2017")
    return SimpleNamespace(
        annual=annual,
        comp=comp,
        bridge=bridge,
        boot=boot,
        ol=ol,
        b16=bridge[(bridge.fiscal_year == 2016) & (bridge.level == "Total")].iloc[0],
        ci=boot.set_index(["fiscal_year", "metric"]),
    )
