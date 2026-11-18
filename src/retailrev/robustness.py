"""Robustness: do the headline numbers survive other reasonable choices?

1. Comp definition sensitivity: re-compute comparable sales growth with
   looser rules for which store-items count as "existing".
2. Bootstrap confidence intervals: resample items (all of an item's stores
   together, since an item's sales are correlated across stores) 2,000 times
   to put intervals on comp growth and on the FY2016 share of growth that came
   from existing products.
3. External benchmark: Walmart U.S. comparable sales from Walmart's annual
   reports, as a directional sanity check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retailrev.paths import connect

COMP_RULES = {
    "Listed all 52 weeks of both years (headline)": "a.weeks_listed = 52 AND b.weeks_listed = 52",
    "Listed 48+ weeks of both years": "a.weeks_listed >= 48 AND b.weeks_listed >= 48",
    "Listed 26+ weeks of both years": "a.weeks_listed >= 26 AND b.weeks_listed >= 26",
    "Sold at least once in both years": "a.units > 0 AND b.units > 0",
    "Listed all 52 weeks, excluding WI_1, WI_2, CA_2 (step-change stores)": "a.weeks_listed = 52 AND b.weeks_listed = 52 AND a.store_id NOT IN ('WI_1', 'WI_2', 'CA_2')",
}

YEAR_ITEMS_SQL = """
SELECT store_id, item_id, fiscal_year, count(*) AS weeks_listed, sum(units) AS units, sum(revenue) AS revenue
FROM fct_item_store_week
WHERE fiscal_week <= 52 AND fiscal_year BETWEEN 2012 AND 2016
GROUP BY ALL
"""

# Walmart U.S. comparable sales, fiscal years ending late January.
# Source: Walmart FY2016 Annual Report (Form 10-K Exhibit 13), five-year financial summary.
WALMART_US_COMPS = pd.DataFrame(
    {
        "fiscal_year": [2013, 2014, 2015, 2016],
        "walmart_us_comp_sales": [0.020, -0.006, 0.006, 0.010],
        "source": ["https://www.sec.gov/Archives/edgar/data/104169/000010416916000079/wmtars-1312016.htm"] * 4,
    }
)


def comp_sensitivity() -> pd.DataFrame:
    con = connect()
    con.execute(f"CREATE OR REPLACE TEMP TABLE yi AS {YEAR_ITEMS_SQL}")
    rows = []
    for name, rule in COMP_RULES.items():
        d = con.execute(f"""
            SELECT b.fiscal_year, sum(a.revenue) AS r0, sum(b.revenue) AS r1, count(*) AS n
            FROM yi a JOIN yi b ON a.store_id = b.store_id AND a.item_id = b.item_id
                               AND b.fiscal_year = a.fiscal_year + 1
            WHERE {rule}
            GROUP BY 1 ORDER BY 1""").df()
        for _, r in d.iterrows():
            rows.append(
                {"definition": name, "fiscal_year": int(r.fiscal_year), "comp_growth": r.r1 / r.r0 - 1, "store_items": int(r.n)}
            )
    return pd.DataFrame(rows)


def _item_pairs(con) -> pd.DataFrame:
    """Per item and year pair: comp revenue (prior, current) and total revenue change."""
    return (
        con.execute(
            """
        WITH yi AS ("""
            + YEAR_ITEMS_SQL
            + """),
        j AS (
            SELECT coalesce(a.item_id, b.item_id) AS item_id,
                   coalesce(b.fiscal_year, a.fiscal_year + 1) AS fiscal_year,
                   coalesce(a.revenue, 0) AS r0, coalesce(b.revenue, 0) AS r1,
                   coalesce(a.weeks_listed, 0) = 52 AND coalesce(b.weeks_listed, 0) = 52 AS is_comp
            FROM yi a FULL OUTER JOIN yi b
              ON a.store_id = b.store_id AND a.item_id = b.item_id AND b.fiscal_year = a.fiscal_year + 1
        )
        SELECT item_id, fiscal_year,
               sum(r0) FILTER (WHERE is_comp) AS comp_r0, sum(r1) FILTER (WHERE is_comp) AS comp_r1,
               sum(r1 - r0) AS total_change
        FROM j WHERE fiscal_year BETWEEN 2013 AND 2016
        GROUP BY ALL
    """
        )
        .df()
        .fillna(0.0)
    )


def bootstrap(n_boot: int = 2000, seed: int = 11) -> pd.DataFrame:
    return bootstrap_from_pairs(_item_pairs(connect()), n_boot=n_boot, seed=seed)


def bootstrap_from_pairs(d: pd.DataFrame, n_boot: int = 2000, seed: int = 11) -> pd.DataFrame:
    """Item bootstrap. Items are sorted first, so the same seed draws the same items
    whatever order the database returns rows in (reproducible to the last digit)."""
    rng = np.random.default_rng(seed)
    d = d.sort_values(["fiscal_year", "item_id"], kind="stable").reset_index(drop=True)
    rows = []
    for fy, g in d.groupby("fiscal_year"):
        r0, r1, tot = (g[c].to_numpy() for c in ("comp_r0", "comp_r1", "total_change"))
        n = len(g)
        idx = rng.integers(0, n, size=(n_boot, n))
        comp = r1[idx].sum(1) / r0[idx].sum(1) - 1
        share = (r1[idx] - r0[idx]).sum(1) / tot[idx].sum(1)
        for metric, point, draws in [
            ("Comparable sales growth", r1.sum() / r0.sum() - 1, comp),
            ("Share of total growth from existing products", (r1 - r0).sum() / tot.sum(), share),
        ]:
            rows.append(
                {
                    "fiscal_year": fy,
                    "metric": metric,
                    "estimate": point,
                    "ci_low": np.percentile(draws, 2.5),
                    "ci_high": np.percentile(draws, 97.5),
                    "items": n,
                    "bootstrap_draws": n_boot,
                }
            )
    return pd.DataFrame(rows)


def external_benchmark(comp: pd.DataFrame) -> pd.DataFrame:
    return WALMART_US_COMPS.merge(comp[["fiscal_year", "comp_growth", "total_growth_52wk"]], on="fiscal_year")
