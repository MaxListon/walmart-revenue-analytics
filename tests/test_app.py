"""The dashboard renders every tab without errors, and its headline numbers match the outputs.

Uses Streamlit's own test harness (no browser), so it runs in CI on the committed outputs/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
OUT = Path(__file__).resolve().parents[1] / "outputs"
TABS = [
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


@pytest.fixture(scope="module")
def app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=120).run()


def test_every_tab_renders_without_errors(app):
    assert not app.exception, [e.value for e in app.exception]
    assert [t.label for t in app.tabs] == TABS
    assert len(app.metric) >= 40
    assert len(app.sidebar.expander) >= 10  # glossary


def test_headline_numbers_match_the_outputs(app):
    metrics = {m.label: m.value for m in app.metric}
    comp = pd.read_csv(OUT / "comp_sales.csv").set_index("fiscal_year")
    assert metrics["Comparable sales, FY2016"] == f"{comp.loc[2016, 'comp_growth']:+.1%}"
    boot = pd.read_csv(OUT / "bootstrap_ci.csv")
    share = boot[(boot.fiscal_year == 2016) & boot.metric.str.startswith("Share")].estimate.iloc[0]
    assert metrics["Share of FY2016 growth from existing products"] == f"{share:.0%}"
    sel = pd.read_csv(OUT / "outlook_fy2017.csv").query("selected").iloc[0]
    assert metrics["FY2017 forecast"] == f"${sel.fy2017_forecast / 1e6:,.1f}M"


def test_every_dropdown_option_renders():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    for i in range(len(at.selectbox)):
        for option in at.selectbox[i].options:
            at.selectbox[i].select(option).run()
            assert not at.exception, (at.selectbox[i].label, option, [e.value for e in at.exception])


def test_every_filter_renders_with_a_single_choice():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    for i in range(len(at.multiselect)):
        for option in at.multiselect[i].options:
            at.multiselect[i].set_value([option]).run()
            assert not at.exception, (at.multiselect[i].label, option, [e.value for e in at.exception])
        at.multiselect[i].set_value(at.multiselect[i].options).run()
