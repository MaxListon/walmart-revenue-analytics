"""Price-change event studies: a stronger test of price sensitivity.

The panel elasticity in pricing.py uses every price movement, including
temporary cuts that probably coincide with promotions (displays, ads) that
are not in the data. Here we separate the two kinds of price change and
compare each store that changed price with stores selling the *same item in
the same weeks* that did not (a stacked difference-in-differences).

Permanent change: price stable for 8 weeks before, new price held for at
    least 8 weeks after. Controls: all other stores whose price for that item was
    unchanged for the full 16-week window.
Temporary cut: price drops, then returns to the original price within 1-4
    weeks. Controls as above. Measures promo lift and any post-promo dip.

Models are Poisson with fixed effects (handles zero-sale weeks without the
log(1+units) approximation):

    units = exp(b * treated x post x dlog(price) + unit-event FE + week-event FE)

so b is directly an elasticity. Dynamic versions estimate one effect per
relative week to check that treated and control stores moved together
before the change (pre-trends).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyfixest as pf

from retailrev.paths import connect

PRE, POST = 8, 8
PANEL_SQL = """
SELECT store_id, item_id, dept_id, cat_id, wm_yr_wk, units, CAST(sell_price AS DOUBLE) AS price
FROM fct_item_store_week
WHERE days_observed = 7 AND sell_price > 0.05
ORDER BY item_id, store_id, wm_yr_wk
"""


def load_panel() -> pd.DataFrame:
    df = connect().execute(PANEL_SQL).df()
    weeks = np.sort(df["wm_yr_wk"].unique())
    df["w"] = np.searchsorted(weeks, df["wm_yr_wk"])
    df["units"] = df["units"].astype(float)
    return df


def _item_events(g: pd.DataFrame):
    """Find permanent changes and temporary cuts for one item across stores."""
    P = g.pivot(index="store_id", columns="w", values="price")
    U = g.pivot(index="store_id", columns="w", values="units")
    stores, cols = P.index.to_numpy(), P.columns.to_numpy()
    p, u = P.to_numpy(), U.to_numpy()
    n_w = len(cols)
    # cols may skip weeks; require consecutive weeks inside each window
    consecutive = np.r_[False, np.diff(cols) == 1]
    perm, temp = [], []
    for si in range(len(stores)):
        row = p[si]
        for j in range(PRE, n_w - POST + 1):
            if np.isnan(row[j]) or np.isnan(row[j - 1]) or row[j] == row[j - 1]:
                continue
            if not consecutive[j - PRE + 1 : j + POST].all():
                continue
            pre = row[j - PRE : j]
            dlog = np.log(row[j] / row[j - 1])
            if not (np.all(pre == pre[0]) and 0.03 <= abs(dlog) <= 0.7):
                continue
            window = p[:, j - PRE : j + POST]
            stable = ~np.isnan(window).any(axis=1) & np.all(window == window[:, :1], axis=1)
            stable[si] = False
            ctrl = np.flatnonzero(stable)
            if len(ctrl) == 0:
                continue
            post = row[j : j + POST]
            if np.all(post == post[0]):
                perm.append((si, j, dlog, ctrl))
            elif dlog < 0:
                # temporary cut: back to the original price within 1-4 weeks, then stays
                back = np.flatnonzero(post == pre[0])
                if len(back) and 1 <= back[0] <= 4 and np.all(post[back[0] :] == pre[0]):
                    temp.append((si, j, dlog, ctrl, back[0]))
    out = []
    for kind, events in (("permanent", perm), ("temporary", temp)):
        for e in events:
            si, j, dlog, ctrl = e[:4]
            promo_len = e[4] if kind == "temporary" else POST
            for s_idx, treated in [(si, 1)] + [(c, 0) for c in ctrl]:
                for k in range(-PRE, POST):
                    out.append(
                        (
                            kind,
                            stores[si],
                            g["item_id"].iat[0],
                            g["dept_id"].iat[0],
                            j,
                            stores[s_idx],
                            treated,
                            k,
                            u[s_idx, j + k],
                            p[s_idx, j + k],
                            cols[j + k],
                            dlog,
                            promo_len,
                        )
                    )
    return out


def build_events(df: pd.DataFrame) -> pd.DataFrame:
    """Every eligible control store is used (no sampling), so results are fully reproducible."""
    rows = []
    for _, g in df.sort_values(["item_id", "store_id", "w"]).groupby("item_id", sort=True):
        rows.extend(_item_events(g))
    ev = pd.DataFrame(
        rows,
        columns=[
            "kind",
            "event_store",
            "item_id",
            "dept_id",
            "event_w",
            "store_id",
            "treated",
            "rel_week",
            "units",
            "price",
            "w",
            "dlog_price",
            "promo_weeks",
        ],
    )
    ev["event_id"] = ev["kind"] + "|" + ev["item_id"] + "|" + ev["event_store"] + "|" + ev["event_w"].astype(str)
    ev["unit_event"] = ev["event_id"] + "|" + ev["store_id"]
    ev["week_event"] = ev["event_id"] + "|" + ev["rel_week"].astype(str)
    ev["post"] = (ev["rel_week"] >= 0).astype(int)
    ev["direction"] = np.where(ev["dlog_price"] > 0, "increase", "decrease")
    return ev


def _fit(d: pd.DataFrame, fml: str):
    return pf.fepois(fml, data=d, vcov={"CRV1": "event_id"})


def permanent_elasticities(ev: pd.DataFrame) -> pd.DataFrame:
    d = ev[ev["kind"] == "permanent"].copy()
    d["dose"] = d["treated"] * d["post"] * d["dlog_price"]
    rows = []
    groups = [("All departments", "all", d)]
    groups += [(dept, "all", g) for dept, g in d.groupby("dept_id")]
    groups += [("All departments", direction, g) for direction, g in d.groupby("direction")]
    # robustness: treated stores dip in the week before a change, so re-run
    # without that week in the pre-period
    no_dip = d[d["rel_week"] != -1]
    groups += [
        ("All departments (excl. week before change)", direction, g)
        for direction, g in [("all", no_dip)] + list(no_dip.groupby("direction"))
    ]
    for name, direction, g in groups:
        # drop events whose units are all zero (no information for Poisson)
        keep = g.groupby("event_id")["units"].transform("sum") > 0
        g = g[keep]
        m = _fit(g, "units ~ dose | unit_event + week_event")
        t = m.tidy().loc["dose"]
        rows.append(
            {
                "segment": name,
                "direction": direction,
                "elasticity": t["Estimate"],
                "ci_low": t["2.5%"],
                "ci_high": t["97.5%"],
                "std_error": t["Std. Error"],
                "events": g["event_id"].nunique(),
                "observations": m._N,
            }
        )
    return pd.DataFrame(rows)


def dynamic_effects(ev: pd.DataFrame, kind: str = "permanent") -> pd.DataFrame:
    """Elasticity-scaled effect by relative week (k = -1 is the reference)."""
    d = ev[ev["kind"] == kind].copy()
    d = d[d.groupby("event_id")["units"].transform("sum") > 0]
    terms = []
    for k in range(-PRE, POST):
        if k == -1:
            continue
        name = f"k_{k + PRE}"
        d[name] = d["treated"] * (d["rel_week"] == k) * (d["dlog_price"] if kind == "permanent" else 1)
        terms.append((k, name))
    m = _fit(d, "units ~ " + " + ".join(n for _, n in terms) + " | unit_event + week_event")
    t = m.tidy()
    rows = [
        {"rel_week": k, "estimate": t.loc[n, "Estimate"], "ci_low": t.loc[n, "2.5%"], "ci_high": t.loc[n, "97.5%"]}
        for k, n in terms
    ]
    rows.append({"rel_week": -1, "estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0})
    out = pd.DataFrame(rows).sort_values("rel_week")
    out["kind"] = kind
    out["scale"] = "elasticity (per unit of log price change)" if kind == "permanent" else "log change in units"
    return out


def promo_effects(ev: pd.DataFrame) -> pd.DataFrame:
    """Temporary cuts: lift during the cut, and the dip in the weeks after it ends."""
    d = ev[ev["kind"] == "temporary"].copy()
    d = d[d.groupby("event_id")["units"].transform("sum") > 0]
    d["during"] = d["treated"] * (d["rel_week"] >= 0) * (d["rel_week"] < d["promo_weeks"])
    d["after"] = d["treated"] * (d["rel_week"] >= d["promo_weeks"])
    m = _fit(d, "units ~ during + after | unit_event + week_event")
    t = m.tidy()
    cut = d.loc[d["treated"] == 1].groupby("event_id")["dlog_price"].first()
    rows = []
    for term, label in [("during", "Units during temporary cut"), ("after", "Units after price returns")]:
        rows.append(
            {
                "effect": label,
                "log_effect": t.loc[term, "Estimate"],
                "pct_effect": np.expm1(t.loc[term, "Estimate"]),
                "ci_low_pct": np.expm1(t.loc[term, "2.5%"]),
                "ci_high_pct": np.expm1(t.loc[term, "97.5%"]),
                "events": d["event_id"].nunique(),
                "median_price_cut": np.expm1(cut.median()),
            }
        )
    rows.append(
        {
            "effect": "Implied promo elasticity",
            "log_effect": t.loc["during", "Estimate"] / cut.mean(),
            "pct_effect": np.nan,
            "ci_low_pct": np.nan,
            "ci_high_pct": np.nan,
            "events": d["event_id"].nunique(),
            "median_price_cut": np.expm1(cut.median()),
        }
    )
    return pd.DataFrame(rows)


def promo_cost(ev: pd.DataFrame, panel: pd.DataFrame, promo: pd.DataFrame) -> pd.DataFrame:
    """Revenue effect of temporary cuts, by fiscal year.

    For each promo week of each treated store-item: actual revenue (units x promo price)
    vs what the same shopper demand would have paid at the regular price, after removing
    the measured promo lift: units / (1 + lift) x regular price. Negative = revenue given away.
    Shown at the lift's point estimate and both ends of its 95% CI.
    """
    d = ev[(ev["kind"] == "temporary") & (ev["treated"] == 1)].copy()
    regular = d[d["rel_week"] == -1].set_index("event_id")["price"]
    d = d[(d["rel_week"] >= 0) & (d["rel_week"] < d["promo_weeks"])].copy()
    d["regular_price"] = d["event_id"].map(regular)
    wk = panel.drop_duplicates("w").set_index("w")["wm_yr_wk"]
    d["fiscal_year"] = 2000 + (d["w"].map(wk) // 100) - 100 + 1
    d["revenue"] = d["units"] * d["price"]
    d["discount_given"] = d["units"] * (d["regular_price"] - d["price"])
    lift = promo.set_index("effect").loc["Units during temporary cut"]
    for name, val in [("point", lift.pct_effect), ("lift_ci_low", lift.ci_low_pct), ("lift_ci_high", lift.ci_high_pct)]:
        d[f"net_{name}"] = d["revenue"] - d["units"] / (1 + val) * d["regular_price"]
    g = d.groupby("fiscal_year").agg(
        events=("event_id", "nunique"),
        promo_units=("units", "sum"),
        promo_revenue=("revenue", "sum"),
        discount_given=("discount_given", "sum"),
        net_revenue_effect=("net_point", "sum"),
        net_if_lift_high=("net_lift_ci_high", "sum"),
        net_if_lift_low=("net_lift_ci_low", "sum"),
    )
    g["measured_lift"] = lift.pct_effect
    return g.reset_index()


def price_dip_screen(panel: pd.DataFrame, depth: float = 0.03, window: int = 4) -> pd.DataFrame:
    """Broad upper bound on temporary-cut discounts, by fiscal year.

    Any week where a store-item's price is at least `depth` below the highest price
    seen in BOTH the `window` weeks before and the `window` weeks after (so the price
    came back) counts as a dip; discount = units x (that regular price - dip price).
    Unlike promo_cost, no control stores or clean pre-period are needed, so it catches
    every short dip.
    """
    d = panel.sort_values(["item_id", "store_id", "w"]).copy()
    g = d.groupby(["item_id", "store_id"], sort=False)["price"]
    before = g.transform(lambda s: s.shift(1).rolling(window, min_periods=1).max())
    after = g.transform(lambda s: s[::-1].shift(1).rolling(window, min_periods=1).max()[::-1])
    regular = np.minimum(before, after)
    dip = d["price"] < regular * (1 - depth)
    d["fiscal_year"] = 2000 + d["wm_yr_wk"] // 100 - 100 + 1
    d["revenue"] = d["units"] * d["price"]
    d["dip_week"] = dip.astype(int)
    d["discount_given"] = np.where(dip, d["units"] * (regular - d["price"]), 0.0)
    out = d.groupby("fiscal_year").agg(
        item_store_weeks=("dip_week", "size"),
        dip_weeks=("dip_week", "sum"),
        revenue=("revenue", "sum"),
        discount_given=("discount_given", "sum"),
    )
    out["discount_share_of_revenue"] = out["discount_given"] / out["revenue"]
    return out.reset_index()
