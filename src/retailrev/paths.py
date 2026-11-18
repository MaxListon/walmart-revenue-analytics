"""Project paths and a single place to open the warehouse."""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
SQL_DIR = ROOT / "sql"
OUTPUTS = ROOT / "outputs"
FIGURES = ROOT / "reports" / "figures"


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(WAREHOUSE.as_posix(), read_only=read_only)
