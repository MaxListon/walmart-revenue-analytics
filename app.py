"""Walmart Revenue Performance Review: interactive dashboard.

Reads only outputs/*.csv (committed), so it runs without the raw data:
    streamlit run app.py

Each tab lives in its own module under dashboard/ with a render() function;
shared palette, loaders and widgets are in dashboard/common.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `dashboard` imports under any launcher

st.set_page_config(page_title="Walmart Revenue Review", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

from dashboard import (  # noqa: E402  (page config must run first)
    availability,
    calendar_snap,
    method,
    outlook,
    overview,
    pricing,
    products,
    segments,
    start_here,
    stores,
    why_comp,
)
from dashboard.common import GLOSSARY  # noqa: E402

with st.sidebar:
    st.markdown("### Glossary")
    st.caption("Plain-English definitions of the terms used in this dashboard.")
    for term, definition in GLOSSARY.items():
        with st.expander(term):
            st.write(definition)

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

PAGES = [start_here, overview, why_comp, availability, products, stores, pricing, calendar_snap, outlook, segments, method]
for tab, page in zip(tabs, PAGES, strict=True):
    with tab:
        page.render()
