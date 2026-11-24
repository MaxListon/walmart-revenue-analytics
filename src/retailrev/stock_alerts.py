"""Daily stock-out alerts: a working version of the "zero-sales alert" recommendation, with a backtest.

Each morning, every product that hasn't sold for a while is checked against its *own* recent history:

    p0         = smoothed share of zero-sale days in the 28 listed days before the run = (zeros + 1) / 30
    P(run)     = p0 ^ days_without_a_sale
    alert when P(run) < threshold   ->   alert on day  floor(ln(threshold) / ln(p0)) + 1  of the run

so a product that sells every day is flagged on its 3rd quiet day and a slow seller only after weeks. Unlike the
retrospective detector (sql/03_stockouts.sql), an alert uses only sales up to the alert day.

Alerts are ranked by revenue at risk per day (the item's recent daily units x shelf price) and capped
per store per day, so a store team gets a short list. An item that is also dark in 4+ other stores, or dark
for more than 28 days, goes to a merchandising list instead (likely a supply or range decision).

Backtest (FY2016): an alert is "confirmed" if the retrospective detector, which also sees the 28 days
*after* the run, flags the run at its 0.1% level. That label is NOT independent: the alert is close to
the detector's own before-window test at the same threshold, so it is strongly favoured over fixed
"no sale in N days" rules. The threshold was also compared on the same year it is scored on. Read the
results as agreement with the detector, not as accuracy against real inventory, which the data lacks.

    python -m retailrev.stock_alerts   # -> outputs/stockout_alert_backtest.csv, outputs/stockout_alerts_latest_*.csv
"""

from __future__ import annotations

import math

import duckdb
import pandas as pd

from retailrev.paths import OUTPUTS, connect

THRESHOLD = 0.001  # same strict level as the headline stock-out detector
CAP_PER_STORE_DAY = 5  # alerts a store team sees each morning
MAX_STORE_DAYS = 28  # dark longer than this -> merchandising
CHAIN_STORES = 4  # other stores dark for the same item -> route to merchandising
FY2016 = ("2015-01-31", "2016-01-29")

DAILY_SQL = """
CREATE OR REPLACE TEMP TABLE daily AS
SELECT s.store_id, s.item_id, s.dept_id, s.cat_id, c.date, s.units, CAST(p.sell_price AS DOUBLE) AS price
FROM stg_sales_daily s
JOIN stg_calendar c USING (day_num)
JOIN stg_prices p ON p.store_id = s.store_id AND p.item_id = s.item_id AND p.wm_yr_wk = c.wm_yr_wk
WHERE c.date >= DATE '{start}'
  AND NOT (c.calendar_month = 12 AND extract(day FROM c.date) = 25)   -- stores closed
"""

# One row per zero-sale run, with only what was known when the run started.
RUNS_SQL = """
CREATE OR REPLACE TEMP TABLE runs AS
WITH seq AS (
    SELECT *,
        sum(CASE WHEN units > 0 THEN 1 ELSE 0 END) OVER w AS block,
        avg(units) OVER (w ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS rate_before,
        count(*)   OVER (w ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS n_before,
        sum(CASE WHEN units = 0 THEN 1 ELSE 0 END) OVER (w ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS zeros_before
    FROM daily
    WINDOW w AS (PARTITION BY store_id, item_id ORDER BY date)
)
SELECT store_id, item_id, any_value(dept_id) AS dept_id, any_value(cat_id) AS cat_id,
       min(date) AS start_date, max(date) AS end_date, count(*) AS zero_days,
       list(date ORDER BY date) AS run_dates,
       arg_min(rate_before, date) AS rate_before, arg_min(n_before, date) AS n_before,
       arg_min(zeros_before, date) AS zeros_before, avg(price) AS price
FROM seq
WHERE units = 0
GROUP BY store_id, item_id, block
"""


def alert_day(zeros_before: int, threshold: float = THRESHOLD) -> int:
    """Day of a zero-sale run on which the alert fires, given zero days in the 28 days before it."""
    p0 = (zeros_before + 1) / 30
    return math.floor(math.log(threshold) / math.log(p0)) + 1


def _alert_len_sql(threshold: float) -> str:
    return f"CAST(floor(ln({threshold}) / ln((zeros_before + 1) / 30.0)) AS BIGINT) + 1"


def build_runs(con: duckdb.DuckDBPyConnection, start: str = "2014-11-01") -> None:
    """Zero-sale runs from the warehouse (temp tables `daily` and `runs`)."""
    con.execute(DAILY_SQL.format(start=start))
    con.execute(RUNS_SQL)


def alerts(
    con: duckdb.DuckDBPyConnection,
    alert_len_sql: str,
    first: str,
    last: str,
    cap: int | None = CAP_PER_STORE_DAY,
) -> pd.DataFrame:
    """Alerts fired between two dates under a rule, capped per store per day by revenue at risk."""
    qualify = (
        ""
        if cap is None
        else f"QUALIFY row_number() OVER (PARTITION BY store_id, alert_date ORDER BY risk_per_day DESC, item_id) <= {cap}"
    )
    return con.execute(f"""
        WITH a AS (
            SELECT r.*, {alert_len_sql} AS alert_len
            FROM runs r
            WHERE n_before = 28 AND rate_before > 0          -- a full month of history, and it was selling
        ),
        fired AS (
            SELECT *, run_dates[alert_len] AS alert_date FROM a
            WHERE zero_days >= alert_len AND run_dates[alert_len] BETWEEN DATE '{first}' AND DATE '{last}'
        ),
        known AS (      -- everything here is known on the alert morning: that day's price, who else is dark
            SELECT f.* EXCLUDE (price, run_dates), f.rate_before * p.price AS risk_per_day,
                   (SELECT count(DISTINCT o.store_id) FROM runs o
                     WHERE o.item_id = f.item_id AND o.store_id <> f.store_id
                       AND o.start_date <= f.alert_date - 6 AND o.end_date >= f.alert_date) AS other_stores_dark
            FROM fired f
            JOIN daily p ON p.store_id = f.store_id AND p.item_id = f.item_id AND p.date = f.alert_date
        )
        SELECT store_id, item_id, dept_id, cat_id, start_date, end_date, zero_days, alert_len, alert_date,
               risk_per_day, other_stores_dark, pow((zeros_before + 1) / 30.0, alert_len) AS p_at_alert
        FROM known
        WHERE other_stores_dark < {CHAIN_STORES} AND alert_len <= {MAX_STORE_DAYS}   -- the rest go to merchandising
        {qualify}
    """).df()


def _label(con: duckdb.DuckDBPyConnection, a: pd.DataFrame) -> pd.DataFrame:
    """Attach the retrospective detector's verdict on each alerted run."""
    con.register("a_df", a)
    out = con.execute("""
        SELECT a.*, o.spell_class, coalesce(o.strict_flag, false) AS confirmed, o.base_rate * o.avg_price AS loss_per_day
        FROM a_df a
        LEFT JOIN fct_oos_spells o ON o.store_id = a.store_id AND o.item_id = a.item_id AND o.start_date = a.start_date
    """).df()
    con.unregister("a_df")
    return out


def score(lab: pd.DataFrame, total_store_loss: float, store_days: int) -> dict:
    """Workload, precision and how much store stock-out loss was still ahead when the alert fired."""
    real = lab.confirmed & lab.spell_class.notna()
    seasonal = real & (lab.spell_class == "Seasonal gap")
    store = real & (lab.spell_class == "Store stock-out")
    days_left = lab.zero_days - lab.alert_len + 1
    return {
        "alerts": len(lab),
        "alerts_per_store_day": len(lab) / store_days,
        "real_gap_share": real.mean(),
        "seasonal_gap_share": seasonal.mean(),  # real, but intentional: not worth acting on
        "actionable_gap_share": (real & ~seasonal).mean(),
        "store_stockout_share": store.mean(),
        "loss_after_alert_share": (lab.loss_per_day * days_left)[store].sum() / total_store_loss,
        "median_alert_day": lab.alert_len.median(),
        "median_days_dark_after_alert": days_left[real].median(),
        "median_days_left_store_stockout": days_left[store].median(),
    }


def backtest(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Item-aware thresholds vs fixed 'no sale in N days' rules, at the same daily workload, over FY2016."""
    total = con.execute(f"""
        SELECT sum(base_rate * avg_price * zero_days) FROM fct_oos_spells
        WHERE spell_class = 'Store stock-out' AND strict_flag AND start_date BETWEEN DATE '{FY2016[0]}' AND DATE '{FY2016[1]}'
    """).fetchone()[0]
    store_days = con.execute(
        f"SELECT count(DISTINCT store_id) * count(DISTINCT date) FROM daily WHERE date BETWEEN DATE '{FY2016[0]}' AND DATE '{FY2016[1]}'"
    ).fetchone()[0]
    rules = [("Item-aware", f"p < {t:g}", _alert_len_sql(t), t == THRESHOLD) for t in (0.01, 0.001, 0.0001)]
    rules += [("Fixed days", f"{n} days without a sale", str(n), False) for n in (3, 5, 7, 10, 14)]
    rows = []
    for rule, setting, sql, chosen in rules:
        lab = _label(con, alerts(con, sql, *FY2016))
        rows.append({"rule": rule, "setting": setting, "chosen": chosen, **score(lab, total, store_days)})
    return pd.DataFrame(rows)


def latest(con: duckdb.DuckDBPyConnection, threshold: float = THRESHOLD) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Alert lists for the last day in the data: (store list, merchandising list).

    Store list: open runs past the threshold, dark 28 days or less, not dark in 4+ other stores;
    the top 5 per store by revenue at risk. Merchandising list: items dark in 4+ other stores or for
    more than 28 days, one row per item (likely supply or range decisions, not a shelf to refill).
    """
    last = con.execute("SELECT max(date) FROM daily").fetchone()[0]
    runs = con.execute(f"""
        WITH a AS (
            SELECT r.*, {_alert_len_sql(threshold)} AS alert_len
            FROM runs r WHERE n_before = 28 AND rate_before > 0 AND end_date = DATE '{last}'
        )
        SELECT a.store_id, a.item_id, a.dept_id, a.cat_id, a.zero_days AS days_without_sale,
               a.run_dates[a.alert_len] AS first_alert_date,
               a.rate_before * p.price AS revenue_at_risk_per_day,
               pow((a.zeros_before + 1) / 30.0, a.zero_days) AS chance_if_selling_normally,
               (SELECT count(*) FROM runs o
                 WHERE o.item_id = a.item_id AND o.store_id <> a.store_id
                   AND o.end_date = DATE '{last}' AND o.zero_days >= 7) AS other_stores_dark
        FROM a JOIN daily p ON p.store_id = a.store_id AND p.item_id = a.item_id AND p.date = DATE '{last}'
        WHERE a.zero_days >= a.alert_len
    """).df()
    to_store = (runs.other_stores_dark < CHAIN_STORES) & (runs.days_without_sale <= MAX_STORE_DAYS)
    store = (
        runs[to_store]
        .sort_values(["store_id", "revenue_at_risk_per_day", "item_id"], ascending=[True, False, True])
        .groupby("store_id")
        .head(CAP_PER_STORE_DAY)
        .assign(revenue_lost_so_far=lambda d: d.revenue_at_risk_per_day * d.days_without_sale)
    )
    merch = (
        runs[~to_store]
        .groupby(["item_id", "dept_id", "cat_id"], as_index=False)
        .agg(
            stores_dark=("store_id", "nunique"),
            stores=("store_id", lambda x: ", ".join(sorted(x))),
            longest_days_dark=("days_without_sale", "max"),
            revenue_at_risk_per_day=("revenue_at_risk_per_day", "sum"),
        )
        .sort_values(["revenue_at_risk_per_day", "item_id"], ascending=[False, True])
    )
    for df in (store, merch):
        df.insert(0, "as_of", pd.Timestamp(last).date())
        df["revenue_at_risk_per_day"] = df.revenue_at_risk_per_day.round(2)
    store["revenue_lost_so_far"] = store.revenue_lost_so_far.round(2)
    return store.reset_index(drop=True), merch.reset_index(drop=True)


def main() -> None:
    con = connect()
    build_runs(con)
    bt = backtest(con)
    bt.to_csv(OUTPUTS / "stockout_alert_backtest.csv", index=False)
    store, merch = latest(con)
    store.to_csv(OUTPUTS / "stockout_alerts_latest_store.csv", index=False)
    merch.to_csv(OUTPUTS / "stockout_alerts_latest_merchandising.csv", index=False)
    con.close()
    c = bt[bt.chosen].iloc[0]
    print(
        f"  alerts: {c.alerts_per_store_day:.1f} per store per day, {c.real_gap_share:.0%} confirmed, {c.store_stockout_share:.0%} store stock-outs, "
        f"{c.loss_after_alert_share:.0%} of store stock-out loss still ahead at alert; "
        f"latest: {len(store)} store alerts, {len(merch)} items for merchandising"
    )


if __name__ == "__main__":
    main()
