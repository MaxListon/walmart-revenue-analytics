"""Stock-out alerts: fire on the right day, adapt to each item's speed, and never use future sales."""

from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd
import pytest

from retailrev import stock_alerts as sa


def _daily(series: dict[tuple[str, str], list[int]], start=dt.date(2015, 1, 1)) -> pd.DataFrame:
    rows = []
    for (store, item), units in series.items():
        for i, u in enumerate(units):
            rows.append((store, item, item[:-4], item.split("_")[0], start + dt.timedelta(days=i), u, 2.0))
    return pd.DataFrame(rows, columns=["store_id", "item_id", "dept_id", "cat_id", "date", "units", "price"])


def _alerts(daily: pd.DataFrame, threshold=0.001, cap=None) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("daily_df", daily)
    con.execute("CREATE TEMP TABLE daily AS SELECT * FROM daily_df")
    con.execute(sa.RUNS_SQL)
    return sa.alerts(con, sa._alert_len_sql(threshold), "2015-01-01", "2015-12-31", cap=cap)


def test_alert_day_adapts_to_item_speed():
    assert sa.alert_day(0) == 3  # sells every day: (1/30)^3 < 0.1%
    assert sa.alert_day(20) == 20  # quiet 20 of the last 28 days: 0.7^20 < 0.1%
    assert sa.alert_day(0) < sa.alert_day(10) < sa.alert_day(20)


def test_fast_seller_alerts_on_day_three_slow_seller_does_not():
    fast = [3] * 40 + [0] * 10 + [3] * 30  # a 10-day gap after selling every day
    slow = ([1, 0, 0, 0] * 10) + [0] * 10 + [1, 0, 0, 0] * 8  # same gap, but it usually sells 1 day in 4
    a = _alerts(_daily({("S1", "FOODS_1_001"): fast, ("S1", "FOODS_1_002"): slow}))
    assert a.item_id.tolist() == ["FOODS_1_001"]
    row = a.iloc[0]
    assert row.alert_len == 3 and row.alert_date == pd.Timestamp("2015-02-12")  # day 3 of a gap starting 10 Feb
    assert row.risk_per_day == pytest.approx(3 * 2.0)


def test_alert_uses_no_future_sales():
    units = [2] * 40 + [0] * 12 + [5] * 40
    full = _alerts(_daily({("S1", "FOODS_1_001"): units}))
    cut = _alerts(_daily({("S1", "FOODS_1_001"): units[:43]}))  # data ends on the alert day
    assert full.alert_date.tolist() == cut.alert_date.tolist() == [pd.Timestamp("2015-02-12")]


def test_needs_a_full_month_of_history():
    a = _alerts(_daily({("S1", "FOODS_1_001"): [3] * 20 + [0] * 10}))  # only 20 days before the gap
    assert a.empty


def test_cap_keeps_the_highest_revenue_at_risk():
    series = {("S1", f"FOODS_1_{i:03d}"): [i] * 30 + [0] * 5 for i in range(1, 8)}
    a = _alerts(_daily(series), cap=3)
    assert sorted(a.item_id) == ["FOODS_1_005", "FOODS_1_006", "FOODS_1_007"]


def test_score_counts_precision_and_loss_after_alert():
    lab = pd.DataFrame(
        {
            "confirmed": [True, True, False, True],
            "spell_class": ["Store stock-out", "Seasonal gap", None, "Store stock-out"],
            "zero_days": [10, 40, 4, 6],
            "alert_len": [3, 5, 3, 3],
            "loss_per_day": [10.0, 5.0, None, 20.0],
        }
    )
    s = sa.score(lab, total_store_loss=200.0, store_days=2)
    assert s["alerts_per_store_day"] == 2
    assert s["real_gap_share"] == 0.75 and s["seasonal_gap_share"] == 0.25 and s["actionable_gap_share"] == 0.5
    assert s["loss_after_alert_share"] == pytest.approx((10 * 8 + 20 * 4) / 200)


def test_risk_uses_the_alert_days_price_not_later_prices():
    d = _daily({("S1", "FOODS_1_001"): [3] * 40 + [0] * 10 + [3] * 5})
    d.loc[d.date > dt.date(2015, 2, 12), "price"] = 99.0  # price changes after the alert
    assert _alerts(d).iloc[0].risk_per_day == pytest.approx(3 * 2.0)


def test_item_dark_in_four_other_stores_goes_to_merchandising():
    gap = {(f"S{i}", "FOODS_1_001"): [3] * 30 + [0] * 20 for i in range(1, 5)}
    late = {("S9", "FOODS_1_001"): [3] * 40 + [0] * 10}  # goes dark after four other stores already have
    a = _alerts(_daily({**gap, **late}))
    assert "S9" not in a.store_id.tolist() and len(a) == 4
