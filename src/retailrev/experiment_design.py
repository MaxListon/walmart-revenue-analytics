"""Design the recommended Household price test before running it.

Question the test must answer: is Household demand inelastic (elasticity
about -0.4, so a price rise increases revenue) or unit-elastic (-1, so it
doesn't)? Under a price change of p%, the two hypotheses differ in units by
about p x 0.6 %, so the design has to detect a small effect.

Design: randomize *products*, not stores (10 stores is far too few, and
store sales drift together week to week). Half of the Household products
get the price change in every store; the other half are controls. Analyse
with Poisson fixed effects:

    units ~ treated x post  |  item-store FE + store-week FE      (SEs clustered by item)

Power is estimated by simulation on real history ("A/A tests"): take real
FY2015-FY2016 weeks where nothing was changed, randomly label half the
products "treated", and fit the model. The spread of the estimates across
simulations is the test's true noise; the share of A/A tests that come out
"significant" checks the false-positive rate. Power for each price change
follows from that noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy.stats import norm

from retailrev.paths import connect

PANEL_SQL = """
SELECT store_id, item_id, wm_yr_wk, CAST(units AS DOUBLE) AS units
FROM fct_item_store_week
WHERE cat_id = 'HOUSEHOLD' AND days_observed = 7 AND fiscal_year IN (2015, 2016)
ORDER BY item_id, store_id, wm_yr_wk
"""
H0_ELASTICITY, H1_ELASTICITY = -1.0, -0.4  # unit-elastic vs measured
PRE_WEEKS = 8


def load() -> pd.DataFrame:
    d = connect().execute(PANEL_SQL).df()
    weeks = np.sort(d["wm_yr_wk"].unique())
    d["w"] = np.searchsorted(weeks, d["wm_yr_wk"])
    return d


DESIGNS = {
    # unit randomized, fixed effects
    "Products: half of products treated in all stores": ("item", "item_store + store_week"),
    "Product-stores: each product treated in a random half of stores": ("item_store", "item_store + store_week + item_week"),
}


def aa_tests(d: pd.DataFrame, test_weeks: int, design: str, n_sims: int = 120, seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_w = d["w"].max() + 1
    rows = []
    for s in range(n_sims):
        t0 = rng.integers(PRE_WEEKS, n_w - test_weeks)
        g = d[(d["w"] >= t0 - PRE_WEEKS) & (d["w"] < t0 + test_weeks)].copy()
        # keep item-stores listed for the whole window
        full = g.groupby(["store_id", "item_id"])["w"].transform("size") == PRE_WEEKS + test_weeks
        g = g[full]
        items = np.sort(g["item_id"].unique())
        g["item_store"] = g["store_id"] + "|" + g["item_id"]
        unit, fe = DESIGNS[design]
        if unit == "item":
            treated = set(rng.choice(items, len(items) // 2, replace=False))
            g["tp"] = (g["item_id"].isin(treated) & (g["w"] >= t0)).astype(int)
        else:
            pairs = np.sort(g["item_store"].unique())
            treated = set(rng.choice(pairs, len(pairs) // 2, replace=False))
            g["tp"] = (g["item_store"].isin(treated) & (g["w"] >= t0)).astype(int)
        g["store_week"] = g["store_id"] + "|" + g["w"].astype(str)
        g["item_week"] = g["item_id"] + "|" + g["w"].astype(str)
        g = g[g.groupby("item_store")["units"].transform("sum") > 0]
        m = pf.fepois(f"units ~ tp | {fe}", data=g, vcov={"CRV1": "item_id"})
        t = m.tidy().loc["tp"]
        rows.append(
            {
                "design": design,
                "test_weeks": test_weeks,
                "sim": s,
                "estimate": t["Estimate"],
                "std_error": t["Std. Error"],
                "p_value": t["Pr(>|t|)"],
                "items": len(items),
                "observations": m._N,
            }
        )
    return pd.DataFrame(rows)


def power_table(aa: pd.DataFrame, price_changes=(0.02, 0.03, 0.05), alpha: float = 0.05) -> pd.DataFrame:
    rows = []
    z = norm.ppf(1 - alpha)  # one-sided: is demand less elastic than -1?
    for (design, weeks), g in aa.groupby(["design", "test_weeks"]):
        se_true = g["estimate"].std(ddof=1)  # noise measured from A/A tests
        # uncertainty in that noise estimate itself (SE of a standard deviation)
        se_of_se = se_true / np.sqrt(2 * (len(g) - 1))
        for p in price_changes:
            dlog = np.log1p(p)
            delta = dlog * (H1_ELASTICITY - H0_ELASTICITY)
            power = norm.cdf(delta / se_true - z)
            power_low = norm.cdf(delta / (se_true + 1.96 * se_of_se) - z)
            power_high = norm.cdf(delta / max(se_true - 1.96 * se_of_se, 1e-9) - z)
            mde_elasticity_gap = (z + norm.ppf(0.8)) * se_true / dlog
            rows.append(
                {
                    "design": design,
                    "test_weeks": weeks,
                    "price_change": p,
                    "noise_se_log_units": se_true,
                    "model_se_avg": g["std_error"].mean(),
                    "aa_false_positive_rate": (g["p_value"] < alpha).mean(),
                    "power_detect_-0.4_vs_-1": power,
                    "power_ci_low": power_low,
                    "power_ci_high": power_high,
                    "a_a_simulations": len(g),
                    "min_detectable_elasticity_gap_80pct": mde_elasticity_gap,
                    "expected_revenue_lift_if_-0.4": (1 + p) ** (1 + H1_ELASTICITY) - 1,
                }
            )
    return pd.DataFrame(rows)
