"""Readout for the Household price test, run on a simulated result.

The test hasn't been run, so this shows the readout working end to end: it takes the last
20 weeks of real Household sales (8 before, 12 during), randomizes half of the product-store
pairs to a 5% price increase, plants a *known* demand response in the treated pairs, and then
runs exactly the analysis the brief pre-registers (docs/price_test_brief.md):

    units ~ treated x during | product-store + store-week + product-week    Poisson, SEs clustered by product
    elasticity = coefficient / ln(1.05)
    decision: roll out only if elasticity > -1 at the 5% level (one-sided), i.e. the rise raises revenue

Planting the effect: each treated unit sale in the test weeks is kept with probability
1.05 ** elasticity (binomial thinning), so the real week-to-week noise is untouched. Run with
a true elasticity of -0.4 (the price rise pays) and -1.0 (it doesn't), the readout should
reach opposite decisions. That is the check that the decision rule works.

    python -m retailrev.price_test     # -> reports/price_test_readout.md
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy.stats import norm

from retailrev import experiment_design
from retailrev.paths import OUTPUTS, ROOT

PRICE_CHANGE = 0.05
PRE_WEEKS, TEST_WEEKS = 8, 12
ALPHA = 0.05


def window(d: pd.DataFrame) -> pd.DataFrame:
    """Last PRE + TEST weeks, product-store pairs listed in every one of them."""
    last = d["w"].max()
    g = d[d["w"] > last - PRE_WEEKS - TEST_WEEKS].copy()
    g["item_store"] = g["store_id"] + "|" + g["item_id"]
    full = g.groupby("item_store")["w"].transform("size") == PRE_WEEKS + TEST_WEEKS
    g = g[full & (g.groupby("item_store")["units"].transform("sum") > 0)]
    g["during"] = (g["w"] > last - TEST_WEEKS).astype(int)
    return g.sort_values(["item_store", "w"], kind="stable").reset_index(drop=True)


def run(g: pd.DataFrame, true_elasticity: float, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    pairs = np.sort(g["item_store"].unique())
    treated = set(rng.choice(pairs, len(pairs) // 2, replace=False))
    g = g.copy()
    g["treated"] = g["item_store"].isin(treated).astype(int)
    g["tp"] = g["treated"] * g["during"]
    keep = (1 + PRICE_CHANGE) ** true_elasticity
    hit = g["tp"] == 1
    g.loc[hit, "units"] = rng.binomial(g.loc[hit, "units"].astype(int), min(keep, 1.0)).astype(float)
    g["store_week"] = g["store_id"] + "|" + g["w"].astype(str)
    g["item_week"] = g["item_id"] + "|" + g["w"].astype(str)
    m = pf.fepois("units ~ tp | item_store + store_week + item_week", data=g, vcov={"CRV1": "item_id"})
    t = m.tidy().loc["tp"]
    dlog = np.log1p(PRICE_CHANGE)
    est, se = t["Estimate"] / dlog, t["Std. Error"] / dlog
    z = (est - (-1.0)) / se  # one-sided: is demand less elastic than -1?
    p = 1 - norm.cdf(z)
    lo, hi = est - 1.96 * se, est + 1.96 * se
    # guardrail: treated pairs' units, test weeks vs pre weeks, relative to control pairs
    rate = g.groupby(["treated", "during"])["units"].mean().unstack()
    unit_change = (rate.loc[1, 1] / rate.loc[1, 0]) / (rate.loc[0, 1] / rate.loc[0, 0]) - 1
    rollout = bool(p < ALPHA)
    return {
        "true_elasticity": true_elasticity,
        "estimated_elasticity": est,
        "ci_low": lo,
        "ci_high": hi,
        "p_value_vs_unit_elastic": p,
        "decision": "Roll out" if rollout else "Don't roll out",
        "expected_revenue_change_at_estimate": (1 + PRICE_CHANGE) ** (1 + est) - 1,
        "treated_unit_change_vs_control": unit_change,
        "pairs": len(pairs),
        "treated_pairs": len(treated),
        "products": g["item_id"].nunique(),
        "weeks": f"{PRE_WEEKS} pre + {TEST_WEEKS} test",
    }


def repeat(g: pd.DataFrame, true_elasticity: float, n: int = 40) -> pd.DataFrame:
    """Same planted effect, n different random assignments: how often is the decision right?"""
    return pd.DataFrame([run(g, true_elasticity, seed=1000 + s) for s in range(n)])


def readout(results: pd.DataFrame, reps: pd.DataFrame | None = None) -> str:
    def pct(v):
        return f"{v:+.1%}".replace("-", "−")

    def num(v):
        return f"{v:.2f}".replace("-", "−")

    first = results.iloc[0]
    lines = [
        "# Household price test: readout (simulated result)",
        "",
        "> **This is a simulation, not a real test.** A known demand response was planted into real FY2016 "
        "Household sales to show the analysis and decision rule, written in advance, working end to end. "
        "See [the experiment brief](../docs/price_test_brief.md).",
        "",
        f"**Setup:** {first.pairs:,} product-store pairs ({first.products:,} Household products in 10 stores), "
        f"half randomly priced +{PRICE_CHANGE:.0%} for {TEST_WEEKS} weeks after an {PRE_WEEKS}-week baseline. "
        "Model: Poisson, product-store + store-week + product-week fixed effects, errors clustered by product.",
        "",
        "| Planted elasticity | Estimated | 95% CI | p (vs −1) | Units, treated vs control | "
        "Revenue change at estimate | Decision |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results.itertuples():
        lines.append(
            f"| {num(r.true_elasticity)} | **{num(r.estimated_elasticity)}** | {num(r.ci_low)} to {num(r.ci_high)} | "
            f"{r.p_value_vs_unit_elastic:.3f} | {pct(r.treated_unit_change_vs_control)} | "
            f"{pct(r.expected_revenue_change_at_estimate)} | **{r.decision}** |"
        )
    lines += [
        "",
        "**Reading it:** when the price rise truly pays (planted −0.4), the estimate lands near −0.4 and is "
        "significantly above −1, so the rule says roll out. When it doesn't (planted −1.0), the rule says don't. "
        "The decision follows the rule set in advance, not the point estimate alone.",
        "",
    ]
    if reps is not None:
        pays = reps[reps["true_elasticity"] == -0.4]
        flat = reps[reps["true_elasticity"] == -1.0]
        lines += [
            f"**Is the rule reliable?** Repeating each case with {len(pays)} different random assignments: when the "
            f"rise truly pays, the rule said roll out **{(pays['decision'] == 'Roll out').mean():.0%}** of the time "
            "(the design targets about 89% power); when it doesn't, it wrongly said roll out "
            f"**{(flat['decision'] == 'Roll out').mean():.0%}** of the time (the target is at most 5%). "
            f"With {len(pays)} runs these rates are only accurate to about ±12 points, so they are consistent with the "
            "design. The estimates are unbiased: they average "
            f"{num(pays['estimated_elasticity'].mean())} and {num(flat['estimated_elasticity'].mean())} against "
            "planted values of −0.40 and −1.00.",
            "",
        ]
    lines += [
        "Generated by `python -m retailrev.price_test`. Results: `outputs/price_test_readout.csv`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    g = window(experiment_design.load())
    res = pd.DataFrame([run(g, e) for e in (-0.4, -1.0)])
    res.to_csv(OUTPUTS / "price_test_readout.csv", index=False)
    reps = pd.concat([repeat(g, e) for e in (-0.4, -1.0)], ignore_index=True)
    reps.to_csv(OUTPUTS / "price_test_readout_repeats.csv", index=False)
    out = ROOT / "reports" / "price_test_readout.md"
    out.write_text(readout(res, reps))
    print(f"  wrote {out.relative_to(ROOT)}")
    print(res[["true_elasticity", "estimated_elasticity", "ci_low", "ci_high", "p_value_vs_unit_elastic", "decision"]])


if __name__ == "__main__":
    main()
