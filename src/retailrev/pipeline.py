"""Run every analysis and write the results to outputs/ as CSV.

outputs/ is small and committed, so the dashboard and Tableau workbook run
without the 350 MB raw data.

Usage:  python -m retailrev.pipeline
"""

from __future__ import annotations

import time

import pandas as pd

from retailrev import (
    drivers,
    events,
    experiment_design,
    inflation,
    launches,
    outlook,
    price_events,
    pricing,
    quality,
    robustness,
    segments,
    stockouts,
    store_events,
)
from retailrev.paths import OUTPUTS, connect
from retailrev.sqlrun import run_metric

LATEST = 2016  # latest complete fiscal year


def _save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUTPUTS / f"{name}.csv", index=False)
    print(f"  wrote outputs/{name}.csv ({len(df):,} rows)")


def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    t0 = time.time()

    print("Data quality")
    checks = quality.run_checks()
    _save(checks, "data_quality_checks")
    failed = checks[(checks["type"] == "hard") & ~checks["passed"]]
    if len(failed):
        raise SystemExit(f"Hard data-quality checks failed:\n{failed}")

    con = connect()
    print("Revenue growth")
    _save(run_metric(con, "annual_revenue"), "annual_revenue")
    _save(run_metric(con, "comp_sales"), "comp_sales")
    bridges = []
    for y in range(2013, LATEST + 1):
        for level, col in [
            ("Total", "'Total'"),
            ("Category", "cat_id"),
            ("State", "state_id"),
            ("Store", "store_id"),
            ("Department", "dept_id"),
        ]:
            b = run_metric(con, "pvm_bridge", y0=y - 1, y1=y, group_col=col)
            b.insert(0, "level", level)
            b.insert(0, "fiscal_year", y)
            bridges.append(b)
    _save(pd.concat(bridges, ignore_index=True), "revenue_bridge")
    ytd = []
    for level, col in [("Total", "'Total'"), ("Category", "cat_id"), ("State", "state_id"), ("Store", "store_id")]:
        t = run_metric(con, "ytd_tracking", group_col=col)
        t.insert(0, "level", level)
        ytd.append(t)
    _save(pd.concat(ytd, ignore_index=True), "ytd_fy2017")
    _save(run_metric(con, "weekly_trend"), "weekly_revenue_store_category")

    print("Assortment")
    _save(run_metric(con, "item_pareto", fy=LATEST), "item_pareto_fy2016")
    _save(run_metric(con, "item_growth", y0=LATEST - 1, y1=LATEST), "item_growth_fy2016")
    _save(run_metric(con, "store_scorecard", fy=LATEST), "store_scorecard_fy2016")
    con.close()

    print("Calendar effects")
    daily = events.load_daily()
    lift = events.event_lift(daily)
    pre = events.event_lift(daily, offset_days=-1)
    summary = events.summarize_event_lift(lift)
    pre_summary = events.summarize_event_lift(pre)[["event_name", "median_lift"]].rename(
        columns={"median_lift": "median_lift_day_before"}
    )
    _save(summary.merge(pre_summary, on="event_name", how="left"), "event_lift")
    _save(events.snap_lift(daily), "snap_lift")
    _save(events.weekday_profile(daily), "weekday_profile")

    print("Pricing: panel elasticities (Poisson + OLS comparison)")
    _save(pricing.department_elasticities(), "price_elasticity")
    _save(pricing.price_moves(), "price_moves")

    print("Pricing: price-change event studies")
    panel = price_events.load_panel()
    ev = price_events.build_events(panel)
    _save(price_events.permanent_elasticities(ev), "price_event_elasticity")
    _save(
        pd.concat([price_events.dynamic_effects(ev, "permanent"), price_events.dynamic_effects(ev, "temporary")]),
        "price_event_dynamics",
    )
    promo = price_events.promo_effects(ev)
    _save(promo, "promo_effects")
    _save(price_events.promo_cost(ev, panel, promo), "promo_cost")
    _save(price_events.price_dip_screen(panel), "price_dip_screen")

    print("Product segmentation")
    seg_items, seg_profile, seg_k = segments.segment_products(segments.features(LATEST, con))
    _save(seg_items, "product_segments")
    _save(seg_profile, "segment_profile")
    _save(seg_k, "segment_k_selection")

    print("Drivers of the comp decline")
    _save(drivers.cannibalization_models(drivers.panel()), "cannibalization_models")
    _save(drivers.comp_by_cohort(), "comp_by_cohort")
    conc, items = drivers.decline_concentration()
    _save(conc, "comp_decline_concentration")
    _save(drivers.monthly_same_item_yoy(), "monthly_same_item_yoy")

    print("Stock-outs and availability")
    _save(stockouts.summary(), "stockout_summary")
    _save(stockouts.by_store(LATEST), "stockout_by_store_dept_fy2016")
    _save(stockouts.top_items(LATEST), "stockout_top_items_fy2016")
    _save(stockouts.availability_decomposition(), "availability_decomposition")

    print("Robustness")
    _save(robustness.comp_sensitivity(), "comp_sensitivity")
    _save(robustness.bootstrap(), "bootstrap_ci")
    _save(robustness.external_benchmark(pd.read_csv(OUTPUTS / "comp_sales.csv")), "external_benchmark")

    print("Launches")
    _save(launches.rollout(), "launch_rollout")
    _save(launches.ramp_curve(), "launch_ramp_curve")
    _save(launches.outcomes(pd.read_csv(OUTPUTS / "item_pareto_fy2016.csv")), "launch_outcomes_fy2016")

    print("SNAP timing")
    _save(events.snap_timing(daily), "snap_timing")

    print("Store step changes")
    wk = store_events.weekly()
    breaks = store_events.detect_breaks(wk)
    _save(breaks, "store_breaks")
    flagged = {r.store_id: r.break_week for r in breaks.itertuples() if abs(r.t_stat) > 10 and abs(r.jump_vs_other_stores) > 0.15}
    synth, paths = store_events.synthetic_controls(wk, flagged)
    _save(synth, "store_synthetic_control")
    _save(paths, "store_synthetic_paths")
    _save(store_events.category_jumps(wk, flagged), "store_break_categories")

    print("FY2017 outlook")
    ol = outlook.load()
    bt = outlook.backtest(ol, flagged)
    _save(bt, "outlook_backtest")
    fc, weekly_fc = outlook.forecast_fy2017(ol, flagged, bt)
    _save(fc, "outlook_fy2017")
    _save(weekly_fc, "outlook_weekly")

    print("Inflation (BLS CPI)")
    _save(inflation.real_growth(), "inflation_adjusted_growth")
    _save(inflation.shelf_price_vs_cpi(), "shelf_price_vs_cpi")

    print("Price-test design (A/A simulations; takes a few minutes)")
    hh = experiment_design.load()
    aa = pd.concat(
        [experiment_design.aa_tests(hh, w, design, n_sims=200) for design in experiment_design.DESIGNS for w in (4, 8, 12)],
        ignore_index=True,
    )
    _save(aa, "price_test_aa_simulations")
    _save(experiment_design.power_table(aa), "price_test_power")

    print(f"Done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
