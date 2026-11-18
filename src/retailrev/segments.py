"""Product segmentation: group the 3,049 products by how they sell, then give each group a playbook.

M5 has no customer data, so this segments *products*, which is what a category or
replenishment team actually manages. Five behavioural features per product, FY2016:

    log_velocity    units per listed store-week (log)
    zero_share      share of listed store-weeks with no sales (intermittency)
    seasonality     coefficient of variation of the 13 four-week periods' sales rate (log)
    snap_lift       sales rate on the state's SNAP days vs other days, minus 1
    stockout_share  revenue lost to store stock-outs / (revenue + that loss), square-rooted

Features are standardised and clustered with k-means (k-means++ starts, 20 restarts, best
inertia). Silhouette is flat across k = 4-6 (about 0.19-0.21), so it can't pick k on its own;
k = 5 is the smallest k that separates a stock-out-risk group, which has its own action.
The k table is still saved so the choice is visible. Segments are named by rules on their
centroids, not by hand, so a re-run cannot silently relabel them. Products are sorted
first so results never depend on database row order.

Silhouette around 0.2 means the segments are useful groupings of a continuum, not
sharply separated types; the stability check reports how often products land in the
same segment across different random starts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans2
from scipy.spatial.distance import cdist

from retailrev.paths import connect

FEATURES = ["log_velocity", "zero_share", "seasonality", "snap_lift", "stockout_share"]

FEATURE_SQL = """
WITH wk AS (
    SELECT item_id, dept_id, cat_id, fiscal_week, units, revenue, sell_price IS NOT NULL AS listed
    FROM fct_item_store_week WHERE fiscal_year = {fy} AND fiscal_week <= 52
),
base AS (
    SELECT item_id, any_value(dept_id) AS dept_id, any_value(cat_id) AS cat_id,
           count(*) FILTER (WHERE listed) AS listed_store_weeks,
           sum(units) AS units, sum(revenue) AS revenue,
           count(*) FILTER (WHERE listed AND units = 0) AS zero_weeks
    FROM wk GROUP BY item_id
),
per AS (  -- 13 four-week periods
    SELECT item_id, (fiscal_week - 1) // 4 AS period,
           sum(units) / nullif(count(*) FILTER (WHERE listed), 0) AS rate
    FROM wk GROUP BY ALL
),
seas AS (SELECT item_id, stddev_pop(rate) / nullif(avg(rate), 0) AS seasonality FROM per GROUP BY item_id),
day AS (
    SELECT v.item_id, v.units,
           CASE v.state_id WHEN 'CA' THEN c.snap_CA WHEN 'TX' THEN c.snap_TX ELSE c.snap_WI END = 1 AS snap
    FROM v_sales_daily_priced v JOIN stg_calendar c USING (date)
    WHERE v.fiscal_year = {fy} AND v.fiscal_week <= 52 AND v.sell_price IS NOT NULL
),
snap AS (
    SELECT item_id, avg(units) FILTER (WHERE snap) / nullif(avg(units) FILTER (WHERE NOT snap), 0) - 1 AS snap_lift
    FROM day GROUP BY item_id
),
oos AS (
    SELECT item_id, sum(lost_revenue) AS stockout_lost
    FROM fct_oos_days
    WHERE strict_flag AND fiscal_year = {fy} AND spell_class = 'Store stock-out'
    GROUP BY item_id
),
prior AS (
    SELECT item_id, sum(revenue) AS revenue_prior
    FROM fct_item_store_week WHERE fiscal_year = {fy} - 1 AND fiscal_week <= 52 GROUP BY item_id
)
SELECT b.*, s.seasonality AS seasonality_cv, n.snap_lift AS snap_lift_raw,
       coalesce(o.stockout_lost, 0) AS stockout_lost, p.revenue_prior
FROM base b
LEFT JOIN seas s USING (item_id) LEFT JOIN snap n USING (item_id)
LEFT JOIN oos o USING (item_id) LEFT JOIN prior p USING (item_id)
ORDER BY item_id
"""

PLAYBOOK = {
    "Core fast movers": "Protect: daily replenishment and a close price watch on the biggest revenue block.",
    "SNAP-driven staples": "Time it: build stock and staff ahead of each state's SNAP days, when these run out.",
    "Availability risk": "Fix supply: zero-sales alerts and more safety stock where stock-outs are frequent.",
    "Seasonal": "Plan by season: buy to the curve and review the range; sales are shrinking.",
    "Long tail": "Review the range: many products, little revenue.",
}


def features(fy: int = 2016, con=None) -> pd.DataFrame:
    d = (con or connect()).execute(FEATURE_SQL.format(fy=fy)).df()
    return add_derived(d)


def add_derived(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["velocity"] = d["units"] / d["listed_store_weeks"]
    d["zero_share_raw"] = d["zero_weeks"] / d["listed_store_weeks"]
    d["stockout_share_raw"] = d["stockout_lost"] / (d["revenue"] + d["stockout_lost"])
    d["growth"] = (d["revenue"] / d["revenue_prior"] - 1).replace([np.inf, -np.inf], np.nan)
    d["log_velocity"] = np.log(d["velocity"] + 0.1)
    d["zero_share"] = d["zero_share_raw"]
    d["seasonality"] = np.log(d["seasonality_cv"].clip(0.03, 3))
    d["snap_lift"] = d["snap_lift_raw"].clip(-0.5, 1)
    d["stockout_share"] = np.sqrt(d["stockout_share_raw"].clip(0, 0.3))
    return d


def _eligible(d: pd.DataFrame) -> pd.DataFrame:
    ok = (d["revenue"] > 0) & d[FEATURES].notna().all(axis=1)
    return d[ok].sort_values("item_id", kind="stable").reset_index(drop=True)


def standardise(d: pd.DataFrame) -> np.ndarray:
    f = d[FEATURES]
    return ((f - f.mean()) / f.std(ddof=0)).to_numpy()


def kmeans(X: np.ndarray, k: int, n_init: int = 20, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Best of n_init k-means++ runs (lowest within-cluster sum of squares)."""
    best = None
    for s in range(seed, seed + n_init):
        c, lab = kmeans2(X, k, seed=s, minit="++")
        if len(np.unique(lab)) < k:
            continue
        inertia = ((X - c[lab]) ** 2).sum()
        if best is None or inertia < best[0]:
            best = (inertia, c, lab)
    return best[1], best[2]


def silhouette(X: np.ndarray, lab: np.ndarray) -> float:
    D = cdist(X, X)
    ks = np.unique(lab)
    mean_to = np.column_stack([D[:, lab == k].mean(axis=1) for k in ks])
    own = np.searchsorted(ks, lab)
    n_own = np.bincount(own)[own]
    a = mean_to[np.arange(len(X)), own] * n_own / np.maximum(n_own - 1, 1)  # exclude self
    mean_to[np.arange(len(X)), own] = np.inf
    b = mean_to.min(axis=1)
    return float(np.mean((b - a) / np.maximum(a, b)))


def adjusted_rand(a: np.ndarray, b: np.ndarray) -> float:
    """Agreement between two labelings, 1 = identical, ~0 = chance."""
    ct = pd.crosstab(a, b).to_numpy()

    def c2(x):
        return x * (x - 1) / 2

    index = c2(ct).sum()
    ra, rb, n = c2(ct.sum(1)).sum(), c2(ct.sum(0)).sum(), c2(ct.sum())
    expected = ra * rb / n
    return float((index - expected) / ((ra + rb) / 2 - expected))


def name_segments(centroids: pd.DataFrame) -> dict[int, str]:
    """Rule-based names from standardised centroids (works for k = 4-6)."""
    left = list(centroids.index)
    names = {}
    for name, col, pick in [
        ("SNAP-driven staples", "snap_lift", max),
        ("Seasonal", "seasonality", max),
        ("Core fast movers", "log_velocity", max),
        ("Long tail", "log_velocity", min),
        ("Availability risk", "stockout_share", max),
    ]:
        if not left:
            break
        seg = pick(left, key=lambda s: centroids.loc[s, col])
        names[seg] = name
        left.remove(seg)
    for i, seg in enumerate(left, start=1):
        names[seg] = f"Mixed {i}"
    return names


def segment_products(d: pd.DataFrame, k: int = 5, ks=(4, 5, 6), seed: int = 0):
    """Returns (item table with segment, segment profile, k-selection table)."""
    d = _eligible(d)
    X = standardise(d)
    rows, fits = [], {}
    for kk in ks:
        c_, lab_ = kmeans(X, kk, seed=seed)
        fits[kk] = (c_, lab_)
        rows.append({"k": kk, "silhouette": silhouette(X, lab_), "smallest_segment": int(np.bincount(lab_).min())})
    k_table = pd.DataFrame(rows)
    c, lab = fits[k] if k in fits else kmeans(X, k, seed=seed)
    # stability: re-fit with different random starts and compare
    stab = [adjusted_rand(lab, kmeans(X, k, seed=seed + 100 * r)[1]) for r in range(1, 6)]
    k_table["selected"] = k_table["k"] == k
    k_table["stability_ari"] = np.where(k_table["selected"], float(np.mean(stab)), np.nan)

    centroids = pd.DataFrame(c, columns=FEATURES)
    names = name_segments(centroids)
    d["segment"] = [names[i] for i in lab]
    total_rev, total_items = d["revenue"].sum(), len(d)
    prof = (
        d.groupby("segment")
        .agg(
            products=("item_id", "size"),
            revenue=("revenue", "sum"),
            stockout_lost=("stockout_lost", "sum"),
            median_velocity=("velocity", "median"),
            median_zero_share=("zero_share_raw", "median"),
            median_seasonality=("seasonality_cv", "median"),
            median_snap_lift=("snap_lift_raw", "median"),
            median_growth=("growth", "median"),
            food_share=("cat_id", lambda s: (s == "FOODS").mean()),
            household_share=("cat_id", lambda s: (s == "HOUSEHOLD").mean()),
        )
        .reset_index()
    )
    prof["product_share"] = prof["products"] / total_items
    prof["revenue_share"] = prof["revenue"] / total_rev
    z = centroids.rename(index=names).add_prefix("z_")
    prof = prof.merge(z, left_on="segment", right_index=True)
    prof["playbook"] = prof["segment"].map(PLAYBOOK)
    prof = prof.sort_values("revenue", ascending=False).reset_index(drop=True)
    keep = ["item_id", "dept_id", "cat_id", "segment", "revenue", "velocity", "zero_share_raw", "seasonality_cv"]
    items = d[keep + ["snap_lift_raw", "stockout_share_raw", "growth"]].rename(
        columns={
            "zero_share_raw": "zero_share",
            "seasonality_cv": "seasonality",
            "snap_lift_raw": "snap_lift",
            "stockout_share_raw": "stockout_share",
        }
    )
    return items, prof, k_table
