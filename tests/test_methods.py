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


def _mbr_db():
    """Tiny warehouse: A and B on the shelf all year, C new this April, D dropped last year."""
    days = pd.date_range("2015-03-01", "2016-04-30", freq="D")
    rows = []
    for dt in days:
        this_year = dt >= pd.Timestamp("2016-01-30")
        rows.append(("S1", "CA", "A", "FOODS_1", "FOODS", dt, 12 if this_year else 10, 2.5 if this_year else 2.0))
        rows.append(("S1", "CA", "B", "HOBBIES_1", "HOBBIES", dt, 5, 4.0))
        if dt >= pd.Timestamp("2016-04-01"):
            rows.append(("S1", "CA", "C", "FOODS_1", "FOODS", dt, 3, 1.0))
        if dt <= pd.Timestamp("2015-06-30"):
            rows.append(("S1", "CA", "D", "FOODS_1", "FOODS", dt, 2, 1.0))
    sales = pd.DataFrame(rows, columns=["store_id", "state_id", "item_id", "dept_id", "cat_id", "date", "units", "sell_price"])
    sales["date"] = sales["date"].dt.date
    sales["revenue"] = sales["units"] * sales["sell_price"]
    cal = pd.DataFrame({"date": days.date, "fiscal_year": np.where(days >= pd.Timestamp("2016-01-30"), 2017, 2016)})
    oos = pd.DataFrame(
        {
            "store_id": ["S1"],
            "dept_id": ["FOODS_1"],
            "date": [pd.Timestamp("2016-04-10").date()],
            "lost_revenue": [25.0],
            "strict_flag": [True],
            "spell_class": ["Store stock-out"],
        }
    )
    con = duckdb.connect()
    con.register("sales_df", sales)
    con.register("cal_df", cal)
    con.register("oos_df", oos)
    con.execute("CREATE TABLE v_sales_daily_priced AS SELECT * FROM sales_df")
    con.execute("CREATE TABLE stg_calendar AS SELECT * FROM cal_df")
    con.execute("CREATE TABLE fct_oos_days AS SELECT * FROM oos_df")
    return con


def test_monthly_review_bridge_reconciles_to_known_answer():
    from retailrev import report

    con = _mbr_db()
    assert report.latest_complete_month(con) == "2016-04"
    r = report.build(con, "2016-04")
    p = r["parts"]
    # A: 300 units at $2 -> 360 at $2.50; B: 150 units at $4 both years (30 days each)
    assert p["comp_prior"] == pytest.approx(1200) and p["comp_current"] == pytest.approx(1500)
    assert p["price"] == pytest.approx(360 * 0.5)
    assert p["volume"] == pytest.approx(60 * 1200 / 450)
    assert p["volume"] + p["mix"] + p["price"] == pytest.approx(p["comp_current"] - p["comp_prior"])
    total_change = p["revenue_current"] - p["revenue_prior"]
    assert p["volume"] + p["mix"] + p["price"] + p["other"] == pytest.approx(total_change)
    assert p["other"] == pytest.approx(90 - 60)  # C new (+30 days x 3 x $1); D dropped (-30 days x 2 x $1)
    assert r["stockout"] == pytest.approx(25) and not r["stockout_complete"]
    assert "Monthly business review · April 2016" in report.render(r)
    with pytest.raises(ValueError):
        report.build(con, "2016-05")


def _bench_frames(days=420, lift=1.3):
    from retailrev import forecast_benchmark as fb

    idx = pd.date_range("2015-01-01", periods=days, freq="D")
    attrs = pd.DataFrame(
        {
            "store_id": ["CA_1", "CA_1", "TX_1", "TX_1"],
            "state_id": ["CA", "CA", "TX", "TX"],
            "cat_id": ["FOODS", "HOBBIES", "FOODS", "HOBBIES"],
            "dept_id": ["FOODS_1", "HOBBIES_1", "FOODS_1", "HOBBIES_1"],
        },
        index=["CA_1|FOODS_1", "CA_1|HOBBIES_1", "TX_1|FOODS_1", "TX_1|HOBBIES_1"],
    )
    weekly = np.array([10, 12, 9, 11, 15, 20, 18], dtype=float)
    base = np.tile(weekly, days // 7 + 1)[:days]
    snap = np.asarray(idx.day <= 10)
    units = pd.DataFrame({c: base * (i + 1) for i, c in enumerate(attrs.index)}, index=idx)
    units_snap = units.copy()
    units_snap.loc[snap, ["CA_1|FOODS_1", "TX_1|FOODS_1"]] *= lift
    return fb, attrs, units, units_snap, snap


def test_wrmsse_is_zero_for_perfect_and_seasonal_forecasts():
    fb, attrs, units, _, _ = _bench_frames()
    train, actual = units.iloc[:-28], units.iloc[-28:]
    revenue = train * 2.0
    assert fb.wrmsse(actual, actual, train, revenue, attrs)["wrmsse"] == pytest.approx(0)
    sn = pd.DataFrame(fb._seasonal_naive(train.to_numpy()), index=actual.index, columns=units.columns)
    assert fb.wrmsse(actual, sn, train, revenue, attrs)["wrmsse"] == pytest.approx(0, abs=1e-12)
    naive = pd.DataFrame(fb._naive(train.to_numpy()), index=actual.index, columns=units.columns)
    assert fb.wrmsse(actual, naive, train, revenue, attrs)["wrmsse"] > 0.5


def test_calendar_aware_forecast_learns_planted_snap_lift():
    fb, attrs, _, units, snap = _bench_frames(lift=1.3)
    y = units.to_numpy()
    closed = np.zeros(len(y), dtype=bool)
    snap2d = np.column_stack([snap] * 4)
    m = fb.calendar_multipliers(y[:-28], snap2d[:-28], closed[:-28])
    assert m[0] == pytest.approx(1.3, rel=0.03) and m[1] == pytest.approx(1.0, rel=0.03)
    f = fb._calendar_aware(y[:-28], snap2d[:-28], closed[:-28], snap2d[-28:], closed[-28:])
    plain = fb._weekday_average(y[:-28])
    err_cal, err_plain = np.abs(f - y[-28:]).mean(), np.abs(plain - y[-28:]).mean()
    assert err_cal < 0.5 * err_plain


def test_auc_matches_known_orderings():
    from retailrev.launch_model import auc

    y = np.array([0, 0, 1, 1])
    assert auc(y, np.array([1, 2, 3, 4])) == 1.0
    assert auc(y, np.array([4, 3, 2, 1])) == 0.0
    assert auc(y, np.array([1, 3, 2, 4])) == 0.75


def test_launch_model_finds_planted_signal():
    from retailrev import launch_model as lm

    rng = np.random.default_rng(3)
    n = 800
    vel = np.exp(rng.normal(1.4, 1.0, n))
    price = np.exp(rng.normal(1.0, 0.5, n))
    d = pd.DataFrame(
        {
            "item_id": [f"I{i:04d}" for i in range(n)],
            "dept_id": "D",
            "cat_id": rng.choice(["FOODS", "HOBBIES", "HOUSEHOLD"], n),
            "launch_week": pd.Timestamp("2012-01-07") + pd.to_timedelta(rng.integers(0, 150, n), unit="W"),
            "units_4wk": vel * 30,
            "revenue_4wk": vel * 30 * price,
            "store_weeks_4wk": 30,
            "zero_weeks_4wk": rng.integers(0, 10, n),
            "stores_by_week4": rng.integers(3, 11, n),
            "velocity_week1": vel,
            "velocity_week4": vel,
            "price_4wk": price,
            # later revenue rate follows early revenue rate, with noise
            "revenue_later": vel * price * np.exp(rng.normal(0, 0.4, n)) * 400,
            "store_weeks_later": 400,
        }
    )
    r = lm.fit_and_evaluate(lm.add_features(d), n_boot=50)
    s = r["scores"].set_index("model")["auc"]
    assert s.min() > 0.8
    assert r["calibration"]["actual"].iloc[-1] > r["calibration"]["actual"].iloc[0]


def _sim_data(days=500, seed=0, noisy=True):
    from retailrev import stock_sim as ss

    rng = np.random.default_rng(seed)
    dates = pd.date_range(ss.FY_START - pd.Timedelta(days=200), periods=days, freq="D")
    n = 40
    rate = rng.uniform(2, 8, n)
    demand = rng.poisson(rate, (days, n)).astype(float) if noisy else np.tile(rate.round(), (days, 1))
    attrs = pd.DataFrame(
        {
            "state_id": "CA",
            "dept_id": "FOODS_3",
            "item_id": [f"I{i}" for i in range(n)],
            "segment": ["SNAP-driven staples"] * (n // 2) + ["Availability risk"] * (n - n // 2),
        }
    )
    return ss, {
        "demand": demand,
        "price": np.full((days, n), 2.0),
        "snap": np.zeros((days, n), dtype=bool),
        "dates": dates,
        "attrs": attrs,
        "measured_loss": 0.0,
    }


def test_stock_sim_constant_demand_never_stocks_out():
    ss, data = _sim_data(noisy=False)
    r = ss.simulate(data, z=0.0)
    assert r["lost_revenue"] == pytest.approx(0)
    assert r["fill_rate"] == pytest.approx(1)


def test_stock_sim_more_safety_stock_cuts_losses_and_costs_inventory():
    ss, data = _sim_data()
    low, high = ss.simulate(data, z=0.0), ss.simulate(data, z=2.0)
    assert high["lost_revenue"] < low["lost_revenue"]
    assert high["avg_inventory_value"] > low["avg_inventory_value"]


def test_snap_multipliers_recover_planted_lift():
    from retailrev.stock_sim import snap_multipliers

    rng = np.random.default_rng(1)
    days, n = 400, 6
    snap = np.zeros((days, n), dtype=bool)
    snap[np.arange(days) % 30 < 10] = True
    demand = rng.poisson(10, (days, n)) * np.where(snap, 1.4, 1.0)
    attrs = pd.DataFrame({"state_id": "TX", "dept_id": ["FOODS_1"] * 3 + ["HOBBIES_1"] * 3})
    m = snap_multipliers(demand, np.ones_like(snap), snap, attrs)
    assert m == pytest.approx(np.full(n, 1.4), rel=0.03)


def test_price_test_readout_recovers_planted_elasticity():
    from retailrev import price_test as pt

    rng = np.random.default_rng(5)
    stores, items, weeks = [f"S{i}" for i in range(10)], [f"H{i:03d}" for i in range(120)], 20
    rows = []
    for it in items:
        base = rng.uniform(3, 12)
        for st in stores:
            level = base * rng.uniform(0.7, 1.3)
            for w in range(weeks):
                rows.append((st, it, w, float(rng.poisson(level * (1 + 0.1 * np.sin(w))))))
    d = pd.DataFrame(rows, columns=["store_id", "item_id", "w", "units"])
    g = pt.window(d)
    pays, flat = pt.run(g, -0.4, seed=1), pt.run(g, -1.0, seed=1)
    assert pays["estimated_elasticity"] == pytest.approx(-0.4, abs=0.35)
    assert flat["estimated_elasticity"] == pytest.approx(-1.0, abs=0.35)
    assert pays["decision"] == "Roll out" and flat["decision"] == "Don't roll out"


def test_excel_workbook_is_formula_driven(tmp_path, monkeypatch):
    from openpyxl import load_workbook

    from retailrev import excel

    monkeypatch.setattr(excel, "OUT", tmp_path / "model.xlsx")
    excel.build()
    wb = load_workbook(tmp_path / "model.xlsx")
    assert wb.sheetnames == [
        "Read me",
        "Store explorer",
        "Price test ROI",
        "Segments",
        "Comparable sales",
        "Data - store x category",
    ]
    ex = wb["Store explorer"]
    # the store picker is a dropdown, and the summary is lookups on the data sheet, not pasted numbers
    assert any("B4" in str(dv.sqref) for dv in ex.data_validations.dataValidation)
    assert str(ex["B5"].value).startswith("=INDEX(") and "MATCH($B$4" in str(ex["B5"].value)
    assert all(str(ex[f"C{r}"].value).startswith("=SUMIFS(") for r in (12, 13, 14))
    roi = wb["Price test ROI"]
    # results must be live formulas built on the input cells (B5-B8), not pasted numbers
    for ref in ["B11", "B12", "B13", "B14", "B16"]:
        f = str(roi[ref].value)
        assert f.startswith("=") and any(cell in f for cell in ["B5", "B6", "B7", "B8", "B12"])
    formulas = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row if str(c.value).startswith("="))
    assert formulas > 100
