"""Run a metric SQL file from sql/metrics with simple {placeholder} params."""

from __future__ import annotations

import duckdb
import pandas as pd

from retailrev.paths import SQL_DIR


def run_metric(con: duckdb.DuckDBPyConnection, name: str, **params) -> pd.DataFrame:
    sql = (SQL_DIR / "metrics" / f"{name}.sql").read_text()
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", str(value))
    df = con.execute(sql).df()
    # DuckDB returns DECIMAL sums as objects; analysts want floats.
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
    return df
