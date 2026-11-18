"""Inflation: how much of revenue growth was real, and how Walmart's own
shelf prices moved against the market.

Price indexes are the U.S. Bureau of Labor Statistics CPI-U, U.S. city
average, not seasonally adjusted, fetched from the BLS public API into
data/external/bls_cpi_raw.json (public domain):

    FOODS      -> CUUR0000SAF11  Food at home
    HOUSEHOLD  -> CUUR0000SAH3   Household furnishings and operations
    HOBBIES    -> CUUR0000SAR    Recreation
    Total      -> CUUR0000SA0    All items

A fiscal year's index is the average of its 12 months (February through the
following January, matching Walmart's fiscal year).

Shelf-price index: for comparable store-items, sum(q1 * p1) / sum(q1 * p0)
- the price change on the same products in the same stores, weighted by
what sold this year (a Paasche index, the same "price effect" as the bridge).
"""

from __future__ import annotations

import json

import pandas as pd

from retailrev.paths import OUTPUTS, ROOT, connect

CPI_FILE = ROOT / "data" / "external" / "bls_cpi_raw.json"
SERIES = {"FOODS": "CUUR0000SAF11", "HOUSEHOLD": "CUUR0000SAH3", "HOBBIES": "CUUR0000SAR", "Total": "CUUR0000SA0"}
SERIES_NAMES = {
    "CUUR0000SAF11": "Food at home",
    "CUUR0000SAH3": "Household furnishings and operations",
    "CUUR0000SAR": "Recreation",
    "CUUR0000SA0": "All items",
}

SHELF_PRICE_SQL = """
WITH yr AS (
    SELECT store_id, item_id, cat_id, fiscal_year, count(*) AS weeks_listed,
           sum(units) AS q, sum(revenue) AS r
    FROM fct_item_store_week
    WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
    GROUP BY ALL
),
comp AS (
    SELECT cur.cat_id, cur.fiscal_year, cur.q AS q1, cur.r AS r1, prev.r / prev.q AS p0
    FROM yr cur JOIN yr prev
      ON prev.store_id = cur.store_id AND prev.item_id = cur.item_id AND prev.fiscal_year = cur.fiscal_year - 1
    WHERE cur.weeks_listed = 52 AND prev.weeks_listed = 52 AND cur.q > 0 AND prev.q > 0
)
SELECT fiscal_year, {grp} AS segment, sum(r1) / sum(q1 * p0) - 1 AS shelf_price_change
FROM comp GROUP BY ALL ORDER BY 1, 2
"""


def load_cpi() -> pd.DataFrame:
    j = json.loads(CPI_FILE.read_text())
    rows = []
    for s in j["Results"]["series"]:
        for o in s["data"]:
            if o["period"].startswith("M") and o["period"] != "M13":
                rows.append(
                    {"series_id": s["seriesID"], "year": int(o["year"]), "month": int(o["period"][1:]), "cpi": float(o["value"])}
                )
    d = pd.DataFrame(rows)
    # Walmart fiscal year: Feb of year Y-1 through Jan of year Y
    d["fiscal_year"] = d["year"] + (d["month"] >= 2).astype(int)
    return d


def fiscal_cpi() -> pd.DataFrame:
    d = load_cpi()
    fy = d.groupby(["series_id", "fiscal_year"]).agg(cpi=("cpi", "mean"), months=("cpi", "size")).reset_index()
    fy = fy[fy["months"] == 12]
    fy["cpi_inflation"] = fy.groupby("series_id")["cpi"].pct_change()
    inv = {v: k for k, v in SERIES.items()}
    fy["segment"] = fy["series_id"].map(inv)
    fy["series_name"] = fy["series_id"].map(SERIES_NAMES)
    return fy


def real_growth() -> pd.DataFrame:
    rev = (
        connect()
        .execute("""
        SELECT fiscal_year, cat_id AS segment, sum(revenue) AS revenue
        FROM fct_item_store_week WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
        GROUP BY ALL
        UNION ALL
        SELECT fiscal_year, 'Total', sum(revenue)
        FROM fct_item_store_week WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
        GROUP BY ALL""")
        .df()
    )
    comp = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    comp = comp[comp["level"].isin(["Total", "Category"])][["fiscal_year", "segment", "comp_growth"]]
    d = rev.merge(fiscal_cpi()[["fiscal_year", "segment", "cpi", "cpi_inflation", "series_name"]], on=["fiscal_year", "segment"])
    d = d.sort_values(["segment", "fiscal_year"])
    d["nominal_growth"] = d.groupby("segment")["revenue"].pct_change()
    d["real_revenue_fy2012_dollars"] = d["revenue"] / d["cpi"] * d.groupby("segment")["cpi"].transform("first")
    d["real_growth"] = (1 + d["nominal_growth"]) / (1 + d["cpi_inflation"]) - 1
    d = d.merge(comp, on=["fiscal_year", "segment"], how="left")
    d["real_comp_growth"] = (1 + d["comp_growth"]) / (1 + d["cpi_inflation"]) - 1
    return d


def shelf_price_vs_cpi() -> pd.DataFrame:
    con = connect()
    sp = pd.concat(
        [con.execute(SHELF_PRICE_SQL.format(grp="cat_id")).df(), con.execute(SHELF_PRICE_SQL.format(grp="'Total'")).df()]
    )
    d = sp.merge(fiscal_cpi()[["fiscal_year", "segment", "cpi_inflation", "series_name"]], on=["fiscal_year", "segment"])
    d["gap_vs_cpi_pts"] = d["shelf_price_change"] - d["cpi_inflation"]
    return d.sort_values(["segment", "fiscal_year"])
