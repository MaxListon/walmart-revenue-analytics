"""Data-quality audit: every check is a SQL query with an expected result.

Checks are either hard (pipeline is wrong if they fail) or findings
(real-world quirks the analysis has to handle, documented in the README).
"""

from __future__ import annotations

import pandas as pd

from retailrev.paths import connect

CHECKS = [
    # name, kind, sql returning one number, expectation, what it means
    (
        "Units reconcile: raw daily = weekly fact",
        "hard",
        "SELECT (SELECT sum(units) FROM stg_sales_daily) - (SELECT sum(units) FROM fct_item_store_week)",
        "== 0",
        "No units lost or duplicated when joining prices and rolling up to weeks.",
    ),
    (
        "Revenue reconciles: weekly fact = daily store-dept fact",
        "hard",
        "SELECT abs((SELECT sum(revenue) FROM fct_item_store_week) - (SELECT sum(revenue) FROM fct_store_dept_day))",
        "< 0.01",
        "Both marts tie to the cent.",
    ),
    (
        "Sales on days with no shelf price",
        "hard",
        "SELECT count(*) FROM v_sales_daily_priced WHERE sell_price IS NULL AND units > 0",
        "== 0",
        "Every unit sold has a price, so revenue = units x price is complete.",
    ),
    (
        "Negative unit values",
        "hard",
        "SELECT count(*) FROM stg_sales_daily WHERE units < 0",
        "== 0",
        "No returns or corrections are mixed in.",
    ),
    (
        "Duplicate store-item-week price rows",
        "hard",
        "SELECT count(*) - count(DISTINCT (store_id, item_id, wm_yr_wk)) FROM stg_prices",
        "== 0",
        "One price per item per store per week.",
    ),
    (
        "Days with near-zero chain sales (store closures)",
        "finding",
        "SELECT count(*) FROM (SELECT date FROM fct_store_dept_day GROUP BY date HAVING sum(units) < 100)",
        "== 5",
        "All 5 are Christmas Day: stores closed. Excluded from baselines.",
    ),
    (
        "53-week fiscal years",
        "finding",
        "SELECT count(*) FROM (SELECT fiscal_year FROM stg_calendar GROUP BY 1 HAVING max(fiscal_week) = 53)",
        "== 1",
        "FY2014 has 53 weeks; growth is reported on a 52-week basis.",
    ),
    (
        "Implausible prices (<= $0.05)",
        "finding",
        "SELECT count(*) FROM stg_prices WHERE sell_price <= 0.05",
        "> 0",
        "105 of 6.8M price rows. Excluded from elasticity models.",
    ),
    (
        "Store-items added to the assortment after FY2012",
        "finding",
        "SELECT count(*) FROM (SELECT store_id, item_id FROM fct_item_store_week GROUP BY ALL HAVING min(fiscal_year) > 2012)",
        "> 0",
        "Assortment grew ~79%. Total growth is split into comp vs. new listings.",
    ),
    (
        "Listed full weeks with zero sales",
        "finding",
        "SELECT round(100.0 * count(*) FILTER (WHERE units = 0) / count(*), 1) FROM fct_item_store_week WHERE days_observed = 7",
        "> 0",
        "~24% of listed weeks sell nothing: slow movers or out-of-stocks.",
    ),
]


def _passes(value: float, expectation: str) -> bool:
    op, target = expectation.split()
    target = float(target)
    return {"==": value == target, "<": value < target, ">": value > target}[op]


def run_checks() -> pd.DataFrame:
    con = connect()
    rows = []
    for name, kind, sql, expectation, meaning in CHECKS:
        value = float(con.execute(sql).fetchone()[0])
        rows.append(
            {
                "check": name,
                "type": kind,
                "value": value,
                "expectation": expectation,
                "passed": _passes(value, expectation),
                "meaning": meaning,
            }
        )
    con.close()
    return pd.DataFrame(rows)
