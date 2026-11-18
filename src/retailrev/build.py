"""Build the DuckDB warehouse from the raw M5 files.

Usage:  python -m retailrev.build
"""

from __future__ import annotations

import time

from retailrev.paths import RAW_DIR, SQL_DIR, WAREHOUSE, connect

STEPS = ["01_staging.sql", "02_marts.sql", "03_stockouts.sql"]


def build() -> None:
    missing = [f for f in ("calendar.csv", "sell_prices.csv", "sales_train_evaluation.csv") if not (RAW_DIR / f).exists()]
    if missing:
        raise SystemExit(f"Missing raw files in {RAW_DIR}: {missing}. See README > Data.")

    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = connect(read_only=False)
    for step in STEPS:
        t0 = time.time()
        sql = (SQL_DIR / step).read_text().replace("{raw}", RAW_DIR.as_posix())
        con.execute(sql)
        print(f"  {step:<18} {time.time() - t0:6.1f}s")
    for table in ("stg_sales_daily", "fct_item_store_week", "fct_store_dept_day"):
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  {table:<22} {n:>12,} rows")
    con.close()


if __name__ == "__main__":
    build()
