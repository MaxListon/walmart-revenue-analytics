"""Availability: revenue lost to stock-outs and gaps."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.common import (
    BLUE,
    GRAY,
    ORANGE,
    RED,
    YELLOW,
    core,
    downloads,
    intro,
    load,
    money,
    show,
)

LABELS = {"detected": "gaps caught", "revenue_ahead": "lost revenue still ahead"}


def render() -> None:
    d = core()
    annual = d.annual
    intro("How much revenue is lost while listed products sit at zero sales?")
    s = load("stockout_summary")
    t = s.groupby(["fiscal_year", "spell_class"])["lost_revenue"].sum().unstack()
    so16 = t.loc[2016, "Store stock-out"]
    k = st.columns(3)
    k[0].metric(
        "FY2016 revenue lost to store stock-outs",
        money(so16),
        f"{so16 / annual.set_index('fiscal_year').loc[2016, 'revenue_52wk']:.1%} of revenue",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric("Chain-wide gaps (supply / ranging)", money(t.loc[2016, "Chain-wide gap"]))
    k[2].metric("Seasonal gaps (intentional)", money(t.loc[2016, "Seasonal gap"]))
    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        for cls, col in [
            ("Store stock-out", RED),
            ("Store long gap", ORANGE),
            ("Chain-wide gap", YELLOW),
            ("Seasonal gap", GRAY),
        ]:
            fig.add_bar(
                x=[f"FY{y}" for y in t.index],
                y=t[cls],
                name=cls,
                marker_color=col,
                hovertemplate=cls + "<br>%{x}: %{y:$,.0f}<extra></extra>",
            )
        fig.update_layout(barmode="stack", title="Revenue while listed products sat at zero sales")
        show(fig, money_y=True)
        st.caption(
            "Flagged when a zero-sale run had <0.1% chance given the item's own history in the 28 days before and "
            "after. Store stock-out = ≤28 days. Longer gaps: seasonal if they recur each year; chain-wide if ≥4 other "
            "stores are dark at the same time."
        )
    with right:
        bs = load("stockout_by_store_dept_fy2016")
        g = bs[bs.spell_class == "Store stock-out"].groupby("store_id").lost_revenue.sum().sort_values()
        fig = go.Figure(
            go.Bar(x=g.values, y=g.index, orientation="h", marker_color=RED, hovertemplate="%{y}: %{x:$,.0f}<extra></extra>")
        )
        fig.update_layout(title="FY2016 store stock-out losses by store")
        fig.update_xaxes(tickprefix="$", tickformat="~s")
        show(fig)
    st.markdown("**Top products by FY2016 stock-out losses**")
    ti = load("stockout_top_items_fy2016")
    st.dataframe(ti.style.format({"lost_revenue": "${:,.0f}"}), hide_index=True, height=300)
    st.markdown("#### How much of the stock-out loss is realistically recoverable?")
    sim = load("stockout_policy_simulation")
    allp = sim[sim.segment == "All"]
    flat = allp[allp.policy == "Flat forecast (current)"].set_index("z_increase")
    staples = sim[(sim.segment == "SNAP-driven staples") & (sim.policy == "SNAP-aware for staples")]
    k = st.columns(3)
    k[0].metric(
        "Loss recovered with a moderate safety-stock rise (+0.5 SD)",
        f"{flat.loc[0.5, 'share_of_loss_recovered']:.0%}",
        f"{money(flat.loc[0.5, 'revenue_recovered'])} a year",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Extra inventory it takes",
        money(flat.loc[0.5, "extra_inventory_value"]),
        "average stock on hand, at shelf price",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "SNAP-aware ordering, staples",
        f"{money(staples.saving_vs_flat_at_same_inventory.dropna().median())} a year",
        "less lost at the same inventory",
        delta_color="off",
        delta_arrow="off",
    )
    left, right = st.columns(2)
    for col, seg, title in [
        (left, "All", "All simulated products"),
        (right, "SNAP-driven staples", "SNAP-driven staples"),
    ]:
        with col:
            g = sim[sim.segment == seg]
            fig = go.Figure()
            for pol, color in [("Flat forecast (current)", GRAY), ("SNAP-aware for staples", BLUE)]:
                h = g[g.policy == pol].sort_values("avg_inventory_value")
                fig.add_scatter(
                    x=h.avg_inventory_value,
                    y=h.lost_revenue,
                    mode="lines+markers",
                    name=pol,
                    line=dict(color=color, width=2.5),
                    customdata=h.z_increase,
                    hovertemplate=pol + "<br>safety stock +%{customdata} SD<br>inventory %{x:$,.0f}"
                    "<br>lost %{y:$,.0f}<extra></extra>",
                )
            fig.update_layout(title=f"{title}: revenue lost vs inventory held", xaxis_title="Average inventory")
            fig.update_xaxes(tickprefix="$", tickformat="~s")
            show(fig, money_y=True, height=380)
    st.caption(
        "Simulation, not measurement: every store-product in the SNAP-driven staples and availability-risk segments, "
        "FY2016 demand (actual sales plus estimated lost sales), weekly orders with a 3-day lead time, safety stock "
        "calibrated so today's policy loses what the detector measured. Holding more stock always cuts losses, so "
        "policies are compared at equal inventory. Scaled to all store stock-outs, about $0.2M a year is realistically "
        "recoverable, not the full $0.79M."
    )
    alerts_section()
    downloads(
        "availability",
        "stockout_summary",
        "stockout_by_store_dept_fy2016",
        "stockout_top_items_fy2016",
        "stockout_policy_simulation",
        "stockout_alert_backtest",
        "stockout_alerts_latest_store",
        "stockout_alerts_latest_merchandising",
        "alert_validation",
        "alert_validation_matched",
        "alert_pilot_power",
    )


def alerts_section() -> None:
    st.markdown("#### Daily stock-out alerts: a prototype, checked against the full detector")
    bt = load("stockout_alert_backtest")
    ch = bt[bt.chosen].iloc[0]
    fx = bt[bt.setting == "5 days without a sale"].iloc[0]
    k = st.columns(3)
    k[0].metric(
        "Alerts later confirmed as gaps",
        f"{ch.real_gap_share:.0%}",
        f"{ch.store_stockout_share:.0%} were store stock-outs",
        delta_color="off",
        delta_arrow="off",
    )
    k[1].metric(
        "Store stock-out loss still ahead when the alert fired",
        f"{ch.loss_after_alert_share:.0%}",
        f"vs {fx.loss_after_alert_share:.0%} for 'no sale in 5 days'",
        delta_color="off",
        delta_arrow="off",
    )
    k[2].metric(
        "Workload",
        f"{ch.alerts_per_store_day:.1f} alerts",
        "per store per day, highest revenue at risk first",
        delta_color="off",
        delta_arrow="off",
    )
    left, right = st.columns([1, 1.2])
    with left:
        fig = go.Figure()
        for rule, color in [("Fixed days", GRAY), ("Item-aware", BLUE)]:
            g = bt[bt.rule == rule]
            fig.add_scatter(
                x=g.loss_after_alert_share,
                y=g.real_gap_share,
                mode="markers+text",
                name=rule,
                text=[t.replace(" without a sale", "") + (" (used)" if c else "") for t, c in zip(g.setting, g.chosen)],
                textposition="middle right" if rule == "Item-aware" else "middle left",
                marker=dict(color=color, size=11, line=dict(color="white", width=2)),
                hovertemplate="%{text}<br>confirmed %{y:.0%}<br>loss still ahead %{x:.0%}<extra></extra>",
            )
        fig.update_layout(
            title="Each rule, at most 5 alerts per store per day (FY2016)",
            xaxis_title="Store stock-out loss still ahead when the alert fired",
            yaxis_title="Alerts later confirmed",
        )
        fig.update_xaxes(range=[0, 0.62])
        fig.update_yaxes(range=[0.1, 0.9])
        show(fig, pct_y=True, pct_x=True, height=420)
    with right:
        store_list = load("stockout_alerts_latest_store")
        merch = load("stockout_alerts_latest_merchandising")
        store = st.selectbox("Alert list for store", sorted(store_list.store_id.unique()), key="alert_store")
        s = store_list[store_list.store_id == store].copy()
        s["chance"] = s.chance_if_selling_normally.map(lambda p: f"1 in {1 / p:,.0f}" if p > 1e-6 else "under 1 in a million")
        st.caption(f"Morning of {s.as_of.iloc[0]}: top {len(s)} by revenue at risk")
        st.dataframe(
            s[["item_id", "days_without_sale", "revenue_at_risk_per_day", "chance"]].rename(
                columns={
                    "item_id": "Product",
                    "days_without_sale": "Days without a sale",
                    "revenue_at_risk_per_day": "At risk per day",
                    "chance": "Chance if selling normally",
                }
            ),
            hide_index=True,
            column_config={"At risk per day": st.column_config.NumberColumn(format="$%.2f")},
        )
        st.caption(
            f"Sent to merchandising instead: {len(merch)} products dark in 4+ other stores or for over 28 days "
            f"(top: {', '.join(merch.item_id.head(3))})."
        )
    st.caption(
        "An alert fires when a product's run without a sale would happen less than 0.1% of the time given its own last "
        "28 days: the 3rd quiet day for a daily seller, weeks for a slow one. It uses only what was known that morning. "
        "'Confirmed' means the full detector, which also sees the next 28 days, agreed. That detector uses nearly the "
        "same test, so this strongly favors the item-aware rule and is agreement, not accuracy: there are no inventory "
        "records to check against. Loss still ahead is not the same as preventable. The chart scores newly fired "
        "alerts; the list shows every alert still open."
    )
    st.markdown("##### An independent check: planted stock-outs")
    m = load("alert_validation_matched")
    v = m.pivot(index="gap_days", columns="metric", values=["item_aware", "fixed_days"])
    st.dataframe(
        v.set_axis([f"{'Item-aware' if a == 'item_aware' else 'Fixed days'}: {LABELS[b]}" for a, b in v.columns], axis=1)
        .rename_axis("Planted gap (days)")
        .style.format("{:.0%}")
    )
    st.caption(
        f"Known gaps were planted in real sales (Feb–May 2016) and each family was compared at the same volume, "
        f"{m.volume.iloc[0]:.1f} alerts per store per day before the cap of 5. The item-aware rule wins at equal volume "
        "but still misses most short gaps. The fixed rule must wait about 20 days to stay at that volume, which is why it catches so little; a 5-day rule catches every 7-day gap but at about 85 alerts per store per day. Planted gaps are random and total, so real results could differ."
    )
