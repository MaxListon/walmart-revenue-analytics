"""The SQL showcase compiles, and its noted answers match what the queries return.

* Compile test runs in CI: every query is executed against an empty table with the warehouse's schema.
* Answer test runs locally when the warehouse exists (raw data is not in the repo).
Also checks the Tableau Public extracts are up to date with outputs/.
"""

from __future__ import annotations

import re

import duckdb
import pandas as pd
import pytest

from retailrev import tableau
from retailrev.paths import OUTPUTS, SQL_DIR, WAREHOUSE

SHOWCASE = SQL_DIR / "showcase.sql"
FCT_SCHEMA = """
CREATE TABLE fct_item_store_week (
    store_id VARCHAR, state_id VARCHAR, item_id VARCHAR, dept_id VARCHAR, cat_id VARCHAR,
    wm_yr_wk BIGINT, fiscal_year BIGINT, fiscal_week BIGINT, week_start DATE, days_observed BIGINT,
    units HUGEINT, sell_price DECIMAL(10, 2), revenue DECIMAL(38, 2), zero_sale_days BIGINT
)
"""


def queries() -> dict[str, str]:
    parts = re.split(r"(?m)^(?=-- Q\d+:)", SHOWCASE.read_text())[1:]
    return {re.match(r"-- (Q\d+):", p).group(1): p for p in parts}


def test_showcase_has_six_answered_questions():
    q = queries()
    assert list(q) == [f"Q{i}" for i in range(1, 7)]
    assert all("-- Answer:" in sql and "-- Skills:" in sql for sql in q.values())


def test_showcase_queries_compile():
    con = duckdb.connect()
    con.execute(FCT_SCHEMA)
    for name, sql in queries().items():
        con.execute(sql).df()  # raises on any syntax or binding error
        assert name


@pytest.mark.skipif(not WAREHOUSE.exists(), reason="warehouse not built (raw data absent)")
def test_showcase_answers_match_results():
    con = duckdb.connect(WAREHOUSE.as_posix(), read_only=True)
    r = {name: con.execute(sql).df() for name, sql in queries().items()}

    q1 = r["Q1"].set_index("fiscal_year")
    assert round(float(q1.loc[2016, "revenue_52wk"]) / 1e6, 1) == 42.8
    assert round(q1.loc[2016, "yoy_growth"], 3) == 0.124
    annual = pd.read_csv(OUTPUTS / "annual_revenue.csv").set_index("fiscal_year")
    assert float(q1.loc[2016, "revenue_52wk"]) == pytest.approx(annual.loc[2016, "revenue_52wk"])

    q2 = r["Q2"]
    assert q2.dept_id.tolist()[:3] == ["HOUSEHOLD_1", "HOBBIES_1", "FOODS_2"]
    assert round(q2.growth.iloc[0], 3) == 0.190
    assert round(q2.set_index("dept_id").loc["FOODS_3", "growth"], 3) == -0.010

    q3 = r["Q3"].set_index("store_id")
    assert q3.loc["CA_3", "rank_in_state"] == 1 and round(q3.loc["CA_3", "share_of_state"], 2) == 0.37

    q4 = r["Q4"].set_index("cat_id").item_id.to_dict()
    assert q4 == {"HOBBIES": "HOBBIES_1_354", "FOODS": "FOODS_3_120", "HOUSEHOLD": "HOUSEHOLD_1_110"}

    q5 = r["Q5"].iloc[0]
    pareto = pd.read_csv(OUTPUTS / "item_pareto_fy2016.csv")
    assert q5.items_for_80pct == 1310 == (pareto.cum_share < 0.8).sum() + 1
    assert q5["items"] == 3049

    q6 = r["Q6"].set_index("store_id")
    assert q6.index[0] == "WI_3" and q6.loc["WI_3", "weeks_down_fy2014"] == 45
    assert (q6.weeks_down_fy2016 == 0).sum() == 6


def test_tableau_public_extracts_are_current():
    for name, df in tableau.public_extracts().items():
        committed = pd.read_csv(OUTPUTS / "tableau" / "public" / f"{name}.csv")
        pd.testing.assert_frame_equal(df.reset_index(drop=True), committed, check_dtype=False, check_exact=False)
    kpis = tableau.public_extracts()["kpis"].display.tolist()
    assert kpis == ["$42.8M", "+5.6%", "43%", "$0.79M", "$48.7M"]  # the executive summary's headline numbers
