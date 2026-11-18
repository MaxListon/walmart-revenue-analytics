"""Predict at week 4 whether a new product will become a top seller.

A "launch" is a product's first week on the shelf in any store, at least 10 weeks after the
data starts (so its true launch is observed) and at least 52 weeks before it ends (so its
outcome is observed). Everything the model sees comes from the first 4 weeks; the outcome
comes from weeks 13-52, so there is no overlap.

    outcome   top seller = top quarter of launches by revenue per listed store-week, weeks 13-52
    features  sales speed (units per listed store-week, log), share of store-weeks with no sales,
              stores carrying it by week 4, week-4 vs week-1 speed (log), price vs its department's
              launches (log), category
    split     by time: the earliest 70% of launches train the model, the latest 30% test it
    models    (1) a one-line rule: rank by first-4-week revenue per store-week (same currency as the
              outcome, so the comparison is fair); (2) logistic regression
    metrics   AUC (chance a top seller is ranked above a non-top seller; 0.5 = coin flip),
              precision in the top 20% of predictions, with bootstrap 95% CIs

Caveat: M5 only includes products still sold in 2016, so launches that failed and were
withdrawn are missing. The model ranks surviving launches; it can't predict withdrawals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import rankdata

from retailrev.paths import connect

TRAIN_SHARE = 0.7
FEATURES = ["log_velocity", "zero_share", "stores_by_week4", "log_momentum", "log_rel_price"]

LAUNCH_SQL = """
WITH wk AS (
    SELECT wm_yr_wk, min(week_start) AS week_start, dense_rank() OVER (ORDER BY wm_yr_wk) - 1 AS w
    FROM fct_item_store_week GROUP BY wm_yr_wk
),
iw AS (
    SELECT f.item_id, f.dept_id, f.cat_id, f.store_id, wk.w, f.units, f.revenue, f.sell_price,
           f.sell_price IS NOT NULL AS listed
    FROM fct_item_store_week f JOIN wk USING (wm_yr_wk)
),
first AS (SELECT item_id, min(w) FILTER (WHERE listed) AS launch_w FROM iw GROUP BY item_id),
agg AS (
    SELECT i.item_id, any_value(i.dept_id) AS dept_id, any_value(i.cat_id) AS cat_id, any_value(f.launch_w) AS launch_w,
           sum(units) FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3)       AS units_4wk,
           sum(revenue) FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3)     AS revenue_4wk,
           count(*)   FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3)       AS store_weeks_4wk,
           count(*)   FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3 AND units = 0) AS zero_weeks_4wk,
           count(DISTINCT store_id) FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3) AS stores_by_week4,
           sum(units) FILTER (WHERE listed AND w = launch_w)
               / nullif(count(*) FILTER (WHERE listed AND w = launch_w), 0)               AS velocity_week1,
           sum(units) FILTER (WHERE listed AND w = launch_w + 3)
               / nullif(count(*) FILTER (WHERE listed AND w = launch_w + 3), 0)           AS velocity_week4,
           avg(sell_price) FILTER (WHERE listed AND w BETWEEN launch_w AND launch_w + 3) AS price_4wk,
           sum(revenue) FILTER (WHERE listed AND w BETWEEN launch_w + 13 AND launch_w + 52) AS revenue_later,
           count(*)     FILTER (WHERE listed AND w BETWEEN launch_w + 13 AND launch_w + 52) AS store_weeks_later
    FROM iw i JOIN first f USING (item_id)
    GROUP BY i.item_id
)
SELECT a.*, wk.week_start AS launch_week
FROM agg a JOIN wk ON wk.w = a.launch_w
WHERE a.launch_w > 10 AND a.launch_w <= (SELECT max(w) FROM wk) - 52 AND a.store_weeks_later > 0
ORDER BY a.item_id
"""


def launches(con=None) -> pd.DataFrame:
    d = (con or connect()).execute(LAUNCH_SQL).df()
    return add_features(d)


def add_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["velocity_4wk"] = d["units_4wk"] / d["store_weeks_4wk"]
    d["log_revenue_rate_4wk"] = np.log(d["revenue_4wk"] / d["store_weeks_4wk"] + 0.1)
    d["log_velocity"] = np.log(d["velocity_4wk"] + 0.1)
    d["zero_share"] = d["zero_weeks_4wk"] / d["store_weeks_4wk"]
    d["log_momentum"] = np.log((d["velocity_week4"].fillna(0) + 0.1) / (d["velocity_week1"].fillna(0) + 0.1))
    dept_median = d.groupby("dept_id")["price_4wk"].transform("median")
    d["log_rel_price"] = np.log(d["price_4wk"] / dept_median)
    d["later_rev_per_store_week"] = d["revenue_later"] / d["store_weeks_later"]
    d["top_seller"] = (d["later_rev_per_store_week"] >= d["later_rev_per_store_week"].quantile(0.75)).astype(int)
    return d.sort_values("item_id", kind="stable").reset_index(drop=True)


def auc(y: np.ndarray, score: np.ndarray) -> float:
    y = np.asarray(y)
    r = rankdata(score)
    n1, n0 = y.sum(), len(y) - y.sum()
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def precision_at(y: np.ndarray, score: np.ndarray, share: float = 0.2) -> float:
    k = max(1, int(round(len(y) * share)))
    top = np.argsort(-score, kind="stable")[:k]
    return float(np.asarray(y)[top].mean())


def _design(d: pd.DataFrame, mu: pd.Series, sd: pd.Series, cats: list[str]) -> pd.DataFrame:
    x = (d[list(mu.index)] - mu) / sd
    for c in cats[1:]:
        x[f"cat_{c}"] = (d["cat_id"] == c).astype(float)
    return sm.add_constant(x, has_constant="add")


def fit_and_evaluate(d: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict:
    split = d["launch_week"].sort_values().iloc[int(len(d) * TRAIN_SHARE)]
    train = d[d["launch_week"] < split].reset_index(drop=True)
    test = d[d["launch_week"] >= split].reset_index(drop=True)
    feats = [f for f in FEATURES if train[f].std() > 0]  # a feature that never varies can't be fitted
    mu, sd = train[feats].mean(), train[feats].std()
    cats = sorted(d["cat_id"].unique())
    model = sm.Logit(train["top_seller"], _design(train, mu, sd, cats)).fit(disp=0)
    p_test = model.predict(_design(test, mu, sd, cats)).to_numpy()
    rule = test["log_revenue_rate_4wk"].to_numpy()
    y = test["top_seller"].to_numpy()

    rng = np.random.default_rng(seed)
    boots = {"model_auc": [], "rule_auc": [], "model_p20": [], "rule_p20": []}
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        boots["model_auc"].append(auc(y[i], p_test[i]))
        boots["rule_auc"].append(auc(y[i], rule[i]))
        boots["model_p20"].append(precision_at(y[i], p_test[i]))
        boots["rule_p20"].append(precision_at(y[i], rule[i]))
    diff = np.array(boots["model_auc"]) - np.array(boots["rule_auc"])

    def ci(v):
        return np.percentile(v, [2.5, 97.5])

    scores = pd.DataFrame(
        [
            {
                "model": "Rule: rank by first-4-week revenue per store-week",
                "auc": auc(y, rule),
                "auc_ci_low": ci(boots["rule_auc"])[0],
                "auc_ci_high": ci(boots["rule_auc"])[1],
                "precision_top20": precision_at(y, rule),
                "p20_ci_low": ci(boots["rule_p20"])[0],
                "p20_ci_high": ci(boots["rule_p20"])[1],
            },
            {
                "model": "Logistic regression (all week-4 signals)",
                "auc": auc(y, p_test),
                "auc_ci_low": ci(boots["model_auc"])[0],
                "auc_ci_high": ci(boots["model_auc"])[1],
                "precision_top20": precision_at(y, p_test),
                "p20_ci_low": ci(boots["model_p20"])[0],
                "p20_ci_high": ci(boots["model_p20"])[1],
            },
        ]
    )
    scores["base_rate"] = y.mean()
    scores["train_launches"], scores["test_launches"] = len(train), len(test)
    scores["test_from"] = split.date()
    scores["model_minus_rule_auc_ci_low"], scores["model_minus_rule_auc_ci_high"] = ci(diff)

    coefs = pd.DataFrame(
        {
            "term": model.params.index,
            "coef": model.params.values,
            "ci_low": model.conf_int()[0].values,
            "ci_high": model.conf_int()[1].values,
            "odds_ratio_per_sd": np.exp(model.params.values),
        }
    )
    test = test.assign(predicted_probability=p_test)
    test["decile"] = pd.qcut(rankdata(p_test, method="ordinal"), 10, labels=False) + 1
    calib = (
        test.groupby("decile")
        .agg(launches=("item_id", "size"), predicted=("predicted_probability", "mean"), actual=("top_seller", "mean"))
        .reset_index()
    )
    keep = ["item_id", "dept_id", "cat_id", "launch_week", "velocity_4wk", "stores_by_week4", "predicted_probability"]
    return {"scores": scores, "coefficients": coefs, "calibration": calib, "test": test[keep + ["top_seller"]]}
