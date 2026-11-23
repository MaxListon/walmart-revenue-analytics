"""Calendar & SNAP: SNAP benefit-day and holiday effects on sales."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    CAT,
    GRAY,
    INK2,
    RED,
    STATE,
    downloads,
    intro,
    load,
    show,
)


def render() -> None:
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
