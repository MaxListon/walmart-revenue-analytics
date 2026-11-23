"""Data & method: sources, definitions and data-quality checks."""

from __future__ import annotations

import streamlit as st

from dashboard.common import (
    downloads,
    intro,
    load,
)


def render() -> None:
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
