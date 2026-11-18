"""Tests for metric logic and pipeline integrity.

Two kinds:
* Unit tests run the real metric SQL against a tiny hand-built warehouse
  where the right answer is known by hand. These always run.
* Integration tests check the real warehouse and outputs. They are skipped
  if the warehouse hasn't been built (no raw data).
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest

from retailrev.paths import OUTPUTS, WAREHOUSE
from retailrev.sqlrun import run_metric
from retailrev.stats import demean, fe_ols

COMPONENTS = [
    "volume_effect",
    "mix_effect",
    "price_effect",
    "launch_annualization_effect",
    "new_listings_effect",
    "lost_listings_effect",
]


# --------------------------------------------------------------- toy warehouse
def _toy() -> duckdb.DuckDBPyConnection:
    """Two years x 52 weeks. Items:
    A: comp. 10 units/wk @ $2 -> 12 units/wk @ $2.50   (volume + price)
    B: comp. 5 units/wk @ $10 both years               (flat)
    C: new in year 2, 3 units/wk @ $4
    D: lost: year 1 only, 1 unit/wk @ $1
    E: listed weeks 27-52 of year 1, all of year 2, 2 units/wk @ $5 (annualization)
    """
    rows = []
    for fy, base in [(2015, 11401), (2016, 11501)]:
        for wk in range(1, 53):
            w = base + wk - 1

            def add(item, units, price, w=w, fy=fy, wk=wk):
                rows.append(
                    dict(
                        store_id="S1",
                        state_id="CA",
                        item_id=item,
                        dept_id="D",
                        cat_id="C",
                        wm_yr_wk=w,
                        fiscal_year=fy,
                        fiscal_week=wk,
                        days_observed=7,
                        units=units,
                        sell_price=price,
                        revenue=units * price,
                    )
                )

            add("A", 10 if fy == 2015 else 12, 2.0 if fy == 2015 else 2.5)
            add("B", 5, 10.0)
            if fy == 2016:
                add("C", 3, 4.0)
            if fy == 2015:
                add("D", 1, 1.0)
            if fy == 2016 or wk > 26:
                add("E", 2, 5.0)
    con = duckdb.connect()
    con.register("df", pd.DataFrame(rows))
    con.execute("CREATE TABLE fct_item_store_week AS SELECT * FROM df")
    return con


def test_bridge_reconciles_exactly_on_toy_data():
    b = run_metric(_toy(), "pvm_bridge", y0=2015, y1=2016, group_col="'Total'").iloc[0]
    assert b.revenue_prior + sum(b[c] for c in COMPONENTS) == pytest.approx(b.revenue_current, abs=1e-6)


def test_bridge_components_match_hand_calculation():
    b = run_metric(_toy(), "pvm_bridge", y0=2015, y1=2016, group_col="'Total'").iloc[0]
    # comp items A and B: Q0 = 52*15 = 780, R0 = 52*(20+50) = 3640, P0avg = 4.6667
    # Q1 = 52*17 = 884; sum(q1*p0) = 52*(12*2 + 5*10) = 3848
    p0avg = 3640 / 780
    assert b.volume_effect == pytest.approx((884 - 780) * p0avg)
    assert b.mix_effect == pytest.approx(3848 - 884 * p0avg)
    assert b.price_effect == pytest.approx(52 * 12 * 0.5)  # A sold 624 units at +$0.50
    assert b.new_listings_effect == pytest.approx(52 * 3 * 4)  # C
    assert b.lost_listings_effect == pytest.approx(-52 * 1 * 1)  # D
    assert b.launch_annualization_effect == pytest.approx(52 * 10 - 26 * 10)  # E


def test_comp_growth_matches_bridge_and_excludes_new_items():
    con = _toy()
    c = run_metric(con, "comp_sales").iloc[0]
    b = run_metric(con, "pvm_bridge", y0=2015, y1=2016, group_col="'Total'").iloc[0]
    expected = (52 * (12 * 2.5 + 50)) / (52 * (20 + 50)) - 1  # only A and B
    assert c.comp_growth == pytest.approx(expected)
    assert b.comp_growth == pytest.approx(expected)
    assert c.comp_store_items == 2


def test_pareto_classes_cover_revenue_in_order():
    p = run_metric(_toy(), "item_pareto", fy=2016)
    assert p.cum_share.is_monotonic_increasing
    assert p.cum_share.iloc[-1] == pytest.approx(1.0)
    assert p.abc_class.iloc[0] == "A"  # best seller is always class A


# --------------------------------------------------------------- statistics
def test_fixed_effects_recover_known_elasticity():
    rng = np.random.default_rng(7)
    n_items, n_weeks, true_b = 60, 80, -0.7
    item = np.repeat(np.arange(n_items), n_weeks)
    week = np.tile(np.arange(n_weeks), n_items)
    item_fe = rng.normal(2, 1, n_items)[item]
    week_fe = np.sin(week / 6)[...]
    log_p = rng.normal(0, 0.2, item.size) + 0.3 * item_fe  # price correlated with popularity
    y = true_b * log_p + item_fe + week_fe + rng.normal(0, 0.1, item.size)
    df = pd.DataFrame(dict(y=y, log_price=log_p, item=item, week=week))
    res = fe_ols(df, "y", ["log_price"], ["item", "week"], cluster="item")
    assert res.params[0] == pytest.approx(true_b, abs=0.03)


def test_demean_removes_group_means():
    df = pd.DataFrame(dict(v=[1.0, 3.0, 10.0, 14.0], g=["a", "a", "b", "b"], h=["x", "y", "x", "y"]))
    d = demean(df, ["v"], ["g", "h"])
    assert d.groupby(df.g)["v"].mean().abs().max() < 1e-9
    assert d.groupby(df.h)["v"].mean().abs().max() < 1e-9


# --------------------------------------------------------------- integration
needs_warehouse = pytest.mark.skipif(not WAREHOUSE.exists(), reason="warehouse not built (raw data absent)")


@needs_warehouse
def test_all_hard_quality_checks_pass():
    from retailrev.quality import run_checks

    q = run_checks()
    assert q[q.type == "hard"].passed.all(), q[~q.passed]


@needs_warehouse
def test_real_bridge_reconciles_for_every_year_and_segment():
    b = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    gap = b.revenue_prior + b[COMPONENTS].sum(axis=1) - b.revenue_current
    assert gap.abs().max() < 0.01


def test_segment_bridges_sum_to_total():
    b = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    for (fy, level), g in b[b.level != "Total"].groupby(["fiscal_year", "level"]):
        total = b[(b.fiscal_year == fy) & (b.level == "Total")].iloc[0]
        for col in ["revenue_prior", "revenue_current", "new_listings_effect", "launch_annualization_effect"]:
            assert g[col].sum() == pytest.approx(total[col], rel=1e-9), (fy, level, col)


def test_outputs_are_consistent():
    a = pd.read_csv(OUTPUTS / "annual_revenue.csv").set_index("fiscal_year")
    c = pd.read_csv(OUTPUTS / "comp_sales.csv").set_index("fiscal_year")
    assert a.loc[2014, "fiscal_weeks"] == 53
    assert a.loc[2014, "revenue_reported"] > a.loc[2014, "revenue_52wk"]
    assert (c.comp_revenue_current <= a.loc[c.index, "revenue_52wk"]).all()
    s = pd.read_csv(OUTPUTS / "store_scorecard_fy2016.csv")
    assert s.revenue.sum() == pytest.approx(a.loc[2016, "revenue_52wk"], rel=1e-9)
    assert s.share_of_chain.sum() == pytest.approx(1.0)
