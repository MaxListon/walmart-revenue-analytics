"""Store step changes: detect them formally, then measure them.

1. Changepoint detection. For each store, take weekly revenue relative to the
   average of the other nine stores (removes chain-wide seasonality and
   trend), and find the single week that best splits that series into two
   different levels (largest t-statistic for a mean shift, with at least 26
   weeks on each side).
2. Synthetic control. For each flagged store, build a weighted blend of the
   donor stores (stores with no step change) that tracks the store's weekly
   revenue index over the 52 weeks before the break. The gap between the
   store and its synthetic twin after the break estimates the effect.
3. Placebo inference. Re-run step 2 pretending each donor store had the break
   on the same date. If the real store's post/pre fit ratio is larger than
   every placebo's, the effect is unlikely to be noise (p = rank / (n + 1)).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from retailrev.paths import connect

PRE, POST = 52, 52
WEEKLY_SQL = """
SELECT week_start, store_id, cat_id, sum(revenue) AS revenue
FROM fct_item_store_week WHERE days_observed = 7
GROUP BY ALL ORDER BY week_start
"""


def weekly() -> pd.DataFrame:
    d = connect().execute(WEEKLY_SQL).df()
    d["week_start"] = pd.to_datetime(d["week_start"])
    return d


def _store_matrix(d: pd.DataFrame) -> pd.DataFrame:
    m = d.groupby(["week_start", "store_id"])["revenue"].sum().unstack()
    # drop Christmas weeks (store closures distort a one-week window)
    return m[~((m.index.month == 12) & (m.index.day >= 19) & (m.index.day <= 25))]


def detect_breaks(d: pd.DataFrame, min_seg: int = 26) -> pd.DataFrame:
    m = _store_matrix(d)
    rows = []
    for s in m.columns:
        rel = np.log(m[s] / m.drop(columns=s).mean(axis=1)).to_numpy()
        best = (0.0, None, 0.0)
        for k in range(min_seg, len(rel) - min_seg):
            a, b = rel[:k], rel[k:]
            se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
            # use local windows for the size of the jump
            t = (b[:min_seg].mean() - a[-min_seg:].mean()) / se
            if abs(t) > abs(best[0]):
                best = (t, k, b[:min_seg].mean() - a[-min_seg:].mean())
        rows.append({"store_id": s, "break_week": m.index[best[1]], "t_stat": best[0], "jump_vs_other_stores": np.expm1(best[2])})
    return pd.DataFrame(rows).sort_values("t_stat", key=abs, ascending=False)


def _weights(y_pre: np.ndarray, X_pre: np.ndarray) -> np.ndarray:
    k = X_pre.shape[1]
    res = minimize(
        lambda w: np.sum((y_pre - X_pre @ w) ** 2),
        np.full(k, 1 / k),
        bounds=[(0, 1)] * k,
        constraints={"type": "eq", "fun": lambda w: w.sum() - 1},
        method="SLSQP",
    )
    return res.x


def _synth(m: pd.DataFrame, treated: str, donors: list[str], break_week) -> dict:
    i = m.index.get_indexer([break_week], method="bfill")[0]
    window = m.iloc[max(0, i - PRE) : i + POST]
    pre_mask = window.index < m.index[i]
    idx = window / window[pre_mask].mean()  # revenue index, pre-period mean = 1
    w = _weights(idx.loc[pre_mask, treated].to_numpy(), idx.loc[pre_mask, donors].to_numpy())
    synth = idx[donors].to_numpy() @ w
    gap = idx[treated].to_numpy() - synth
    rmspe_pre = np.sqrt(np.mean(gap[pre_mask] ** 2))
    rmspe_post = np.sqrt(np.mean(gap[~pre_mask] ** 2))
    return {
        "weights": dict(zip(donors, w)),
        "index": idx[treated],
        "synthetic": pd.Series(synth, idx.index),
        "effect": idx.loc[~pre_mask, treated].mean() / synth[~pre_mask].mean() - 1,
        "rmspe_ratio": rmspe_post / rmspe_pre,
        "rmspe_pre": rmspe_pre,
        "pre_mask": pre_mask,
    }


def synthetic_controls(d: pd.DataFrame, breaks: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = _store_matrix(d)
    donors = [s for s in m.columns if s not in breaks]
    summary, paths = [], []
    for store, bw in breaks.items():
        bw = pd.Timestamp(bw)
        res = _synth(m, store, donors, bw)
        placebo = [_synth(m, p, [x for x in donors if x != p], bw)["rmspe_ratio"] for p in donors]
        rank = 1 + sum(r >= res["rmspe_ratio"] for r in placebo)
        i = m.index.get_indexer([bw], method="bfill")[0]
        weeks_after = m.index[i : i + POST]
        cat = d[d["store_id"] == store].pivot_table(index="week_start", columns="cat_id", values="revenue", aggfunc="sum")
        cat_post = cat.reindex(weeks_after).sum()
        summary.append(
            {
                "store_id": store,
                "break_week": bw.date(),
                "effect_vs_synthetic": res["effect"],
                "pre_period_fit_rmspe": res["rmspe_pre"],
                "post_pre_rmspe_ratio": res["rmspe_ratio"],
                "placebo_p_value": rank / (len(placebo) + 1),
                "placebo_stores": len(placebo),
                "extra_weekly_revenue": res["effect"] * m.loc[weeks_after, store].mean() / (1 + res["effect"]),
                "top_donors": ", ".join(
                    f"{k} {v:.0%}" for k, v in sorted(res["weights"].items(), key=lambda kv: -kv[1]) if v > 0.05
                ),
                **{f"post_share_{c.lower()}": cat_post[c] / cat_post.sum() for c in cat_post.index},
            }
        )
        p = pd.DataFrame(
            {
                "week_start": res["index"].index,
                "actual_index": res["index"].to_numpy(),
                "synthetic_index": res["synthetic"].to_numpy(),
            }
        )
        p["store_id"] = store
        p["weeks_from_break"] = np.arange(len(p)) - int(res["pre_mask"].sum())
        paths.append(p)
    return pd.DataFrame(summary), pd.concat(paths, ignore_index=True)


def category_jumps(d: pd.DataFrame, breaks: dict[str, str], window: int = 26) -> pd.DataFrame:
    """Which categories stepped up? Revenue relative to the other stores, 26 weeks after vs before."""
    rows = []
    for store, bw in breaks.items():
        bw = pd.Timestamp(bw)
        for cat, g in d.groupby("cat_id"):
            m = g.pivot_table(index="week_start", columns="store_id", values="revenue", aggfunc="sum")
            rel = m[store] / m.drop(columns=list(breaks)).mean(axis=1)
            before = rel[(rel.index < bw) & (rel.index >= bw - pd.Timedelta(weeks=window))].mean()
            after = rel[(rel.index >= bw) & (rel.index < bw + pd.Timedelta(weeks=window))].mean()
            rows.append({"store_id": store, "cat_id": cat, "relative_jump": after / before - 1})
    return pd.DataFrame(rows)
