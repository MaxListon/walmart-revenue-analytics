"""Tests for the v2 methods, each against simulated data with a known answer."""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest

from retailrev import outlook, price_events, store_events
from retailrev.paths import OUTPUTS, SQL_DIR


# --------------------------------------------------------------- stock-out detection
def _daily_con(units_by_item: dict[str, list[int]]) -> duckdb.DuckDBPyConnection:
    """Minimal warehouse with the tables 03_stockouts.sql reads."""
    n = len(next(iter(units_by_item.values())))
    dates = pd.date_range("2013-01-07", periods=n, freq="D")  # avoids Christmas
    cal = pd.DataFrame(
        {
            "date": dates,
            "day_num": range(1, n + 1),
            "wm_yr_wk": [11301 + i // 7 for i in range(n)],
            "fiscal_year": 2013,
            "calendar_month": dates.month,
        }
    )
    sales, prices = [], []
    for item, units in units_by_item.items():
        sales += [
            dict(store_id="S", state_id="CA", item_id=item, dept_id="D", cat_id="C", day_num=i + 1, units=u)
            for i, u in enumerate(units)
        ]
        prices += [dict(store_id="S", item_id=item, wm_yr_wk=w, sell_price=2.0) for w in cal.wm_yr_wk.unique()]
    con = duckdb.connect()
    for name, df in [("stg_calendar", cal), ("stg_sales_daily", pd.DataFrame(sales)), ("stg_prices", pd.DataFrame(prices))]:
        con.register("tmp", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.execute((SQL_DIR / "03_stockouts.sql").read_text())
    return con


def test_stockout_flags_gap_in_steady_seller_but_not_slow_seller():
    rng = np.random.default_rng(1)
    steady = list(rng.poisson(5, 40)) + [0] * 10 + list(rng.poisson(5, 40))  # 10 dark days at ~5/day
    slow = [1 if i % 4 == 0 else 0 for i in range(90)]  # sells every 4th day
    con = _daily_con({"STEADY": [max(u, 1) for u in steady[:40]] + [0] * 10 + [max(u, 1) for u in steady[50:]], "SLOW": slow})
    spells = con.execute("SELECT item_id, zero_days, strict_flag, spell_class FROM fct_oos_spells").df()
    steady_spells = spells[spells.item_id == "STEADY"]
    assert len(steady_spells) == 1 and steady_spells.zero_days.iloc[0] == 10
    assert bool(steady_spells.strict_flag.iloc[0]) and steady_spells.spell_class.iloc[0] == "Store stock-out"
    assert not spells[spells.item_id == "SLOW"].strict_flag.any()  # 3-day gaps are normal for it


def test_stockout_not_flagged_when_demand_never_returns():
    units = [4] * 40 + [0] * 10 + [0] * 40  # no recovery: a real demand collapse / delisting
    con = _daily_con({"GONE": units})
    assert con.execute("SELECT count(*) FROM fct_oos_spells").fetchone()[0] == 0


# --------------------------------------------------------------- price events
def test_event_study_recovers_known_elasticity():
    rng = np.random.default_rng(3)
    rows = []
    true_e = -1.2
    for item in range(120):
        base = rng.uniform(3, 12)
        change_w = rng.integers(15, 40)
        for s in range(5):
            for w in range(60):
                price = 2.0
                if s == 0 and w >= change_w:
                    price = 2.0 * np.exp(0.15)  # +15% permanent increase in store 0 only
                mu = base * np.exp(0.2 * np.sin(w / 5)) * (price / 2.0) ** true_e
                rows.append(
                    dict(
                        store_id=f"S{s}",
                        item_id=f"I{item}",
                        dept_id="D",
                        cat_id="C",
                        wm_yr_wk=11300 + w,
                        w=w,
                        units=float(rng.poisson(mu)),
                        price=price,
                    )
                )
    ev = price_events.build_events(pd.DataFrame(rows))
    assert ev[ev.kind == "permanent"].event_id.nunique() == 120
    est = price_events.permanent_elasticities(ev)
    overall = est[(est.segment == "All departments") & (est.direction == "all")].iloc[0]
    assert overall.elasticity == pytest.approx(true_e, abs=0.2)
    assert overall.ci_low < true_e < overall.ci_high


# --------------------------------------------------------------- synthetic control
def test_synthetic_control_recovers_known_step():
    rng = np.random.default_rng(5)
    weeks = pd.date_range("2012-01-07", periods=200, freq="7D")
    season = 1 + 0.15 * np.sin(np.arange(200) * 2 * np.pi / 52)
    rows = []
    for s, level in [("A", 100), ("B", 120), ("C", 80), ("D", 95), ("E", 110), ("T", 105)]:
        y = level * season * np.exp(rng.normal(0, 0.02, 200))
        if s == "T":
            y = y * np.where(np.arange(200) >= 100, 1.40, 1.0)  # +40% step at week 100
        rows += [dict(week_start=w, store_id=s, cat_id="FOODS", revenue=v) for w, v in zip(weeks, y)]
    d = pd.DataFrame(rows)
    breaks = store_events.detect_breaks(d)
    top = breaks.iloc[0]
    assert top.store_id == "T" and abs((top.break_week - weeks[100]).days) <= 7
    summary, _ = store_events.synthetic_controls(d, {"T": weeks[100]})
    assert summary.effect_vs_synthetic.iloc[0] == pytest.approx(0.40, abs=0.05)
    assert summary.placebo_p_value.iloc[0] == pytest.approx(1 / 6)  # beats all 5 placebos


# --------------------------------------------------------------- outlook
def test_step_adjusted_run_rate_stops_inflated_growth_at_anniversary():
    rows = []
    start = pd.Timestamp("2014-02-01")
    for fy in (2015, 2016):
        for wk in range(1, 53):
            date = start + pd.Timedelta(weeks=(fy - 2015) * 52 + wk - 1)
            for s in ("A", "B"):
                rev = 100.0
                if s == "B" and date >= pd.Timestamp("2014-12-06"):  # B doubles late in FY2015, then stays flat
                    rev = 200.0
                rows.append(dict(store_id=s, fiscal_year=fy, fiscal_week=wk, week_start=date, revenue=rev))
    d = pd.DataFrame(rows)
    b = {"B": pd.Timestamp("2014-12-06")}
    naive = outlook._run_rate(d, 2016, by_store=True)
    adj = outlook._run_rate(d, 2016, by_store=True, breaks=b)
    # flat business: correct rest-of-year total is 36 weeks x (100 + 200)
    assert adj.sum() == pytest.approx(36 * 300)
    assert naive.sum() > adj.sum()


# --------------------------------------------------------------- output integrity
def test_availability_decomposition_reconciles():
    d = pd.read_csv(OUTPUTS / "availability_decomposition.csv")
    gap = d.revenue_prior + d.availability_effect + d.rate_of_sale_effect - d.revenue_current
    assert gap.abs().max() < 0.01


def test_bootstrap_intervals_contain_point_estimates():
    b = pd.read_csv(OUTPUTS / "bootstrap_ci.csv")
    assert ((b.ci_low <= b.estimate) & (b.estimate <= b.ci_high)).all()


def test_selected_outlook_method_has_lowest_backtest_error():
    f = pd.read_csv(OUTPUTS / "outlook_fy2017.csv")
    assert f.loc[f.selected, "mean_abs_full_year_error"].iloc[0] == f.mean_abs_full_year_error.min()


# --------------------------------------------------------------- inflation & test design
def test_cpi_fiscal_year_runs_february_to_january():
    from retailrev import inflation

    d = inflation.load_cpi()
    assert d.loc[(d.year == 2015) & (d.month == 1), "fiscal_year"].unique().tolist() == [2015]
    assert d.loc[(d.year == 2015) & (d.month == 2), "fiscal_year"].unique().tolist() == [2016]
    fy = inflation.fiscal_cpi()
    assert (fy["months"] == 12).all()


def test_real_growth_deflates_nominal_growth():
    g = pd.read_csv(OUTPUTS / "inflation_adjusted_growth.csv").dropna(subset=["nominal_growth"])
    assert np.allclose(1 + g.real_growth, (1 + g.nominal_growth) / (1 + g.cpi_inflation))


def test_power_table_matches_normal_approximation():
    from scipy.stats import norm

    from retailrev.experiment_design import power_table

    rng = np.random.default_rng(0)
    aa = pd.DataFrame(
        {
            "design": "d",
            "test_weeks": 8,
            "estimate": rng.normal(0, 0.01, 4000),
            "std_error": 0.01,
            "p_value": rng.uniform(0, 1, 4000),
            "items": 1000,
        }
    )
    row = power_table(aa, price_changes=(0.05,)).iloc[0]
    expected = norm.cdf(np.log(1.05) * 0.6 / 0.01 - norm.ppf(0.95))
    assert row["power_detect_-0.4_vs_-1"] == pytest.approx(expected, abs=0.01)


def test_price_test_designs_are_calibrated():
    p = pd.read_csv(OUTPUTS / "price_test_power.csv")
    # A/A tests: false positives near the 5% nominal rate (50 simulations each, so allow noise)
    assert p.aa_false_positive_rate.between(0, 0.14).all()
    best = p[(p.price_change == 0.05) & (p.test_weeks == 12)].set_index("design")["power_detect_-0.4_vs_-1"]
    assert best.max() > 0.8 and best.min() < 0.5


def test_event_panel_does_not_depend_on_input_row_order():
    """Regression test: row order from the database is not guaranteed, so the
    event panel (and every estimate built on it) must not depend on it."""
    rng = np.random.default_rng(9)
    rows = []
    for item in range(30):
        change_w = rng.integers(12, 30)
        for s in range(6):
            for w in range(50):
                price = 3.0 * (1.1 if (s < 2 and w >= change_w) else 1.0)
                rows.append(
                    dict(
                        store_id=f"S{s}",
                        item_id=f"I{item}",
                        dept_id="D",
                        cat_id="C",
                        wm_yr_wk=11300 + w,
                        w=w,
                        units=float(rng.poisson(4)),
                        price=price,
                    )
                )
    df = pd.DataFrame(rows)
    a = price_events.build_events(df)
    b = price_events.build_events(df.sample(frac=1, random_state=3))
    assert len(a) > 0 and a.equals(b)


def test_promo_cost_values_a_known_cut():
    # one 2-week cut from $10 to $7, 10 units a week, measured lift +25%
    ev = pd.DataFrame(
        {
            "kind": "temporary",
            "event_id": "e1",
            "treated": 1,
            "rel_week": [-1, 0, 1, 2],
            "w": [0, 1, 2, 3],
            "price": [10.0, 7.0, 7.0, 10.0],
            "units": [8.0, 10.0, 10.0, 8.0],
            "promo_weeks": 2,
        }
    )
    panel = pd.DataFrame({"w": [0, 1, 2, 3], "wm_yr_wk": [11601, 11602, 11603, 11604]})
    promo = pd.DataFrame(
        {"effect": ["Units during temporary cut"], "pct_effect": [0.25], "ci_low_pct": [0.0], "ci_high_pct": [0.5]}
    )
    row = price_events.promo_cost(ev, panel, promo).iloc[0]
    assert row.fiscal_year == 2017
    assert row.discount_given == pytest.approx(2 * 10 * 3)  # units x (10 - 7)
    # revenue 2 x 70 vs counterfactual 2 x (10 / 1.25) x 10
    assert row.net_revenue_effect == pytest.approx(140 - 160)
    assert row.net_if_lift_low < row.net_revenue_effect < row.net_if_lift_high


def test_price_dip_screen_counts_only_dips_that_come_back():
    prices = [10, 10, 10, 10, 7, 10, 10, 10, 10, 8, 8, 8, 8, 8, 8]  # one dip, then a permanent cut
    panel = pd.DataFrame(
        {
            "item_id": "i",
            "store_id": "s",
            "w": range(len(prices)),
            "wm_yr_wk": [11601 + k for k in range(len(prices))],
            "price": [float(p) for p in prices],
            "units": 5.0,
        }
    )
    row = price_events.price_dip_screen(panel).iloc[0]
    assert row.dip_weeks == 1
    assert row.discount_given == pytest.approx(5 * 3)


def test_bootstrap_does_not_depend_on_input_row_order():
    from retailrev.robustness import bootstrap_from_pairs

    rng = np.random.default_rng(0)
    d = pd.DataFrame(
        {
            "item_id": [f"i{k}" for k in range(300)] * 2,
            "fiscal_year": [2015] * 300 + [2016] * 300,
            "comp_r0": rng.uniform(50, 150, 600),
            "comp_r1": rng.uniform(50, 150, 600),
            "total_change": rng.uniform(-20, 60, 600),
        }
    )
    a = bootstrap_from_pairs(d, n_boot=200, seed=3)
    b = bootstrap_from_pairs(d.sample(frac=1, random_state=9), n_boot=200, seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_segmentation_recovers_and_names_planted_groups():
    from retailrev import segments

    rng = np.random.default_rng(1)
    # velocity, zero share, seasonality CV, SNAP lift, stock-out share
    planted = {
        "Core fast movers": (15, 0.02, 0.12, 0.05, 0.004),
        "SNAP-driven staples": (10, 0.05, 0.20, 0.35, 0.030),
        "Availability risk": (4, 0.20, 0.20, 0.03, 0.050),
        "Seasonal": (3, 0.45, 0.90, 0.10, 0.002),
        "Long tail": (1, 0.45, 0.25, 0.00, 0.000),
    }
    rows = []
    for name, (vel, zero, seas, snap, so) in planted.items():
        for i in range(120):
            v = vel * np.exp(rng.normal(0, 0.15))
            revenue = v * 520 * 3.0
            share = max(so * np.exp(rng.normal(0, 0.2)), 0)
            rows.append(
                {
                    "item_id": f"{name[:4]}_{i:03d}",
                    "dept_id": "D",
                    "cat_id": "FOODS",
                    "truth": name,
                    "listed_store_weeks": 520,
                    "units": v * 520,
                    "revenue": revenue,
                    "zero_weeks": round(520 * min(max(zero + rng.normal(0, 0.03), 0), 1)),
                    "seasonality_cv": seas * np.exp(rng.normal(0, 0.15)),
                    "snap_lift_raw": snap + rng.normal(0, 0.03),
                    "stockout_lost": revenue * share / (1 - share),
                    "revenue_prior": revenue / 1.05,
                }
            )
    d = segments.add_derived(pd.DataFrame(rows))
    items, prof, k_table = segments.segment_products(d)
    got = items.merge(d[["item_id", "truth"]], on="item_id")
    assert (got["segment"] == got["truth"]).mean() > 0.95
    assert prof["revenue_share"].sum() == pytest.approx(1)
    # same answer whatever order the rows arrive in
    again, _, _ = segments.segment_products(d.sample(frac=1, random_state=2))
    pd.testing.assert_frame_equal(items, again)
