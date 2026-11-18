"""Small, dependency-light statistics helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def demean(df: pd.DataFrame, cols: list[str], fe: list[str], iters: int = 50, tol: float = 1e-10) -> pd.DataFrame:
    """Remove several sets of fixed effects by alternating projections.

    Equivalent to including a dummy for every level of every column in `fe`
    (the "within" transformation), without building millions of dummies.
    """
    out = df[cols].astype(float).copy()
    for _ in range(iters):
        before = out.to_numpy().copy()
        for f in fe:
            out = out - out.groupby(df[f], observed=True).transform("mean")
        if np.max(np.abs(out.to_numpy() - before)) < tol:
            break
    return out


def fe_ols(
    df: pd.DataFrame, y: str, x: list[str], fe: list[str], cluster: str
) -> sm.regression.linear_model.RegressionResultsWrapper:
    """OLS of y on x with fixed effects absorbed and cluster-robust SEs."""
    d = demean(df, [y, *x], fe)
    model = sm.OLS(d[y].to_numpy(), d[x].to_numpy())
    res = model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(df[cluster])[0]})
    res.model.exog_names[:] = x
    return res
