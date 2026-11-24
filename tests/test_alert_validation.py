"""Planted stock-outs: the alert is scored against a truth that is known by construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retailrev import alert_validation as av


def test_planted_gap_fires_on_the_right_day():
    daily = np.full(60, 3.0)  # sells every day: the item-aware rule fires on day 3
    assert av.plant(daily, 40, 7, "Item-aware", 0.001) == 3
    assert av.plant(daily, 40, 2, "Item-aware", 0.001) is None  # gap too short
    assert av.plant(daily, 40, 7, "Fixed days", 5) == 5


def test_quiet_days_before_the_gap_count_toward_the_run():
    u = np.full(60, 3.0)
    u[38:40] = 0  # two quiet days right before the planted gap
    assert av.plant(u, 40, 7, "Fixed days", 5) == 3
    assert av.plant(u, 40, 7, "Fixed days", 2) == 0  # already alerted before the gap


def test_true_loss_and_what_is_left_after_the_alert():
    u, p = np.full((1, 60), 3.0), np.full((1, 60), 2.0)
    det, already, loss, ahead = av.outcomes(u, p, [(0, 40)], 7)[("Item-aware", 0.001)][0]
    assert (det, already, loss, ahead) == (1, 0, 7 * 6, 4 * 6)  # alert on day 3, so days 4-7 are still ahead


def test_volume_counts_only_alerts_inside_the_window():
    u = np.full((1, 80), 2.0)
    u[0, 50:60] = 0
    assert av.volume(u, 40, 70, 1)[("Fixed days", 5)] == pytest.approx(1 / 31)
    assert av.volume(u, 60, 70, 1)[("Fixed days", 5)] == 0


def test_pilot_power_is_about_the_false_positive_rate_with_no_effect():
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"alert_date": np.repeat(pd.date_range("2015-02-01", periods=60), 40)})
    d["alert_len"], d["zero_days"] = 3, 3 + rng.geometric(0.2, len(d))
    pw = av.pilot_power(d, reps=200)
    assert pw[pw.cut == 0].power.max() < 0.08  # one-sided 2.5%, plus simulation noise
    assert pw[(pw.cut == 0.5) & (pw.weeks == 12)].power.min() > 0.8
