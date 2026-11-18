"""How much of the stock-out loss is realistically recoverable, and at what inventory cost?

There are no inventory records, so this is a simulation, calibrated to what we can measure:

    demand      FY2016 daily units for every store-product in the two segments where stock-outs
                concentrate (SNAP-driven staples, availability risk), with the estimated lost units
                added back on detected store stock-out days
    policy      weekly review, 3-day lead time, order-up-to level
                    S = forecast demand over the next 10 days + z x sd(daily demand) x sqrt(10)
                where demand stats come from the trailing 8 weeks, as a store system would see them
    calibrate   pick the safety factor z so the simulated "current" policy loses the same revenue
                the stock-out detector measured for these products in FY2016
    scenarios   (a) raise z for every product; (b) SNAP-aware for staples: same z, but for SNAP-driven
                staples the forecast scales each day by the state x department SNAP-day multiplier
                learned from the prior year, so stock is built before SNAP windows instead of carried
                all month. Policies are compared at equal inventory (losses interpolated along the
                flat-forecast curve), since holding more stock always cuts losses.
    cost        average inventory on hand, valued at shelf price

The absolute numbers depend on assumptions (lead time, review cycle); the comparison between
policies is the point. Results are relative to the calibrated baseline.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from retailrev.paths import OUTPUTS, connect

REVIEW, LEAD = 7, 3
COVER = REVIEW + LEAD
TRAIL = 56
SEGMENTS = ("SNAP-driven staples", "Availability risk")
FY_START, FY_END = pd.Timestamp("2015-01-31"), pd.Timestamp("2016-01-29")  # FY2016, 52 weeks

DAILY_SQL = """
SELECT v.store_id, v.state_id, v.item_id, v.dept_id, v.date, v.units, v.sell_price,
       coalesce(o.lost_units, 0) AS lost_units
FROM v_sales_daily_priced v
LEFT JOIN fct_oos_days o
  ON o.store_id = v.store_id AND o.item_id = v.item_id AND o.date = v.date
 AND o.strict_flag AND o.spell_class = 'Store stock-out'
WHERE v.item_id IN (SELECT item_id FROM seg) AND v.date BETWEEN ? AND ?
"""


def load(con=None, segments=SEGMENTS) -> dict:
    con = con or connect()
    seg = pd.read_csv(OUTPUTS / "product_segments.csv")
    seg = seg[seg["segment"].isin(segments)][["item_id", "segment"]]
    con.register("seg", seg)
    d = con.execute(DAILY_SQL, [FY_START - pd.Timedelta(days=364 + TRAIL), FY_END]).df()
    d["series"] = d["store_id"] + "|" + d["item_id"]
    d["demand"] = d["units"] + d["lost_units"]
    grid = {c: d.pivot(index="date", columns="series", values=c).sort_index() for c in ["demand", "sell_price"]}
    dates = grid["demand"].index
    cal = con.execute("SELECT date, snap_CA, snap_TX, snap_WI FROM stg_calendar").df().set_index("date").reindex(dates)
    attrs = d.drop_duplicates("series").set_index("series").loc[grid["demand"].columns, ["state_id", "dept_id", "item_id"]]
    attrs = attrs.join(seg.set_index("item_id"), on="item_id")
    snap = np.column_stack([cal[f"snap_{s}"].to_numpy() == 1 for s in attrs["state_id"]])
    return {
        "demand": grid["demand"].fillna(0).to_numpy(),
        "price": grid["sell_price"].to_numpy(),  # NaN = not listed that day
        "snap": snap,
        "dates": dates,
        "attrs": attrs,
        "measured_loss": float((d["lost_units"] * d["sell_price"].fillna(0))[d["date"] >= FY_START].sum()),
    }


def snap_multipliers(demand: np.ndarray, listed: np.ndarray, snap: np.ndarray, attrs: pd.DataFrame) -> np.ndarray:
    """Per series: the state x department ratio of SNAP-day to other-day demand (prior year)."""
    key = (attrs["state_id"] + "|" + attrs["dept_id"]).to_numpy()
    on = np.where(listed & snap, demand, 0).sum(0)
    off = np.where(listed & ~snap, demand, 0).sum(0)
    n_on, n_off = (listed & snap).sum(0), (listed & ~snap).sum(0)
    out = np.ones(demand.shape[1])
    for k in np.unique(key):
        m = key == k
        rate_on, rate_off = on[m].sum() / max(n_on[m].sum(), 1), off[m].sum() / max(n_off[m].sum(), 1)
        out[m] = rate_on / rate_off if rate_off > 0 else 1.0
    return out


def simulate(data: dict, z: float, snap_aware: bool = False) -> dict:
    # products not yet listed in the trailing window give empty-slice warnings; their rate is 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return _simulate(data, z, snap_aware)


def _simulate(data: dict, z: float, snap_aware: bool = False) -> dict:
    """snap_aware=True scales the forecast for SNAP-driven staples only (other products: multiplier 1)."""
    demand, price, snap = data["demand"], data["price"], data["snap"]
    listed = ~np.isnan(price)
    t0 = int(np.searchsorted(data["dates"], FY_START))
    mult = np.ones(demand.shape[1])
    if snap_aware:
        staples = (data["attrs"]["segment"] == "SNAP-driven staples").to_numpy()
        mult = np.where(staples, snap_multipliers(demand[:t0], listed[:t0], snap[:t0], data["attrs"]), 1.0)
    n_days, n = demand.shape[0], demand.shape[1]
    p = np.nan_to_num(price)
    on_hand = np.zeros(n)
    pipeline = np.zeros((LEAD + 1, n))  # orders arriving in 0..LEAD days
    lost = np.zeros(n)
    sold = np.zeros(n)
    inv = np.zeros(n)
    for t in range(t0 - REVIEW, n_days):
        on_hand += pipeline[0]
        pipeline = np.roll(pipeline, -1, axis=0)
        pipeline[-1] = 0
        if t >= t0:
            d = np.where(listed[t], demand[t], 0)
            sales = np.minimum(on_hand, d)
            on_hand -= sales
            lost += (d - sales) * p[t]
            sold += sales * p[t]
            inv += on_hand * p[t]
        if (t - t0) % REVIEW == 0:
            hist = demand[t - TRAIL : t]
            hist_listed = listed[t - TRAIL : t]
            if snap_aware:  # de-season history to a non-SNAP rate, then scale the coming days
                adj = np.where(snap[t - TRAIL : t], mult, 1.0)
                base = np.where(hist_listed, hist / adj, np.nan)
                rate = np.nan_to_num(np.nanmean(base, axis=0))
                sd = np.nan_to_num(np.nanstd(base, axis=0))
                coming = np.where(snap[t : t + COVER], mult, 1.0).sum(0)
                cover_demand = rate * coming
            else:
                base = np.where(hist_listed, hist, np.nan)
                rate = np.nan_to_num(np.nanmean(base, axis=0))
                sd = np.nan_to_num(np.nanstd(base, axis=0))
                cover_demand = rate * COVER
            target = cover_demand + z * sd * np.sqrt(COVER)
            position = on_hand + pipeline.sum(0)
            pipeline[LEAD] += np.maximum(np.ceil(target - position), 0)
    days = n_days - t0
    seg = data["attrs"]["segment"].to_numpy()
    out = {"z": z, "snap_aware": snap_aware}
    for name, m in [("All", np.ones(n, dtype=bool))] + [(s_, seg == s_) for s_ in np.unique(seg)]:
        prefix = "" if name == "All" else f"{name}: "
        out[f"{prefix}lost_revenue"] = float(lost[m].sum())
        out[f"{prefix}fill_rate"] = float(sold[m].sum() / (sold[m].sum() + lost[m].sum()))
        out[f"{prefix}avg_inventory_value"] = float(inv[m].sum() / days)
    return out


def calibrate(data: dict, lo: float = -1.5, hi: float = 3.0, iters: int = 18) -> float:
    """Safety factor z at which the flat-forecast policy loses what was measured."""
    target = data["measured_loss"]
    for _ in range(iters):
        mid = (lo + hi) / 2
        if simulate(data, mid)["lost_revenue"] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def scenarios(data: dict) -> pd.DataFrame:
    """Long table: policy x safety-stock step x segment (All / each segment)."""
    z0 = calibrate(data)
    runs = []
    for dz in (0.0, 0.25, 0.5, 0.75, 1.0):
        for snap_aware in (False, True):
            runs.append((dz, snap_aware, simulate(data, z0 + dz, snap_aware)))
    rows = []
    for seg in ["All", *sorted(data["attrs"]["segment"].unique())]:
        prefix = "" if seg == "All" else f"{seg}: "
        for dz, snap_aware, r in runs:
            rows.append(
                {
                    "segment": seg,
                    "policy": "SNAP-aware for staples" if snap_aware else "Flat forecast (current)",
                    "z_increase": dz,
                    "z": z0 + dz,
                    "lost_revenue": r[f"{prefix}lost_revenue"],
                    "fill_rate": r[f"{prefix}fill_rate"],
                    "avg_inventory_value": r[f"{prefix}avg_inventory_value"],
                }
            )
    out = pd.DataFrame(rows)
    parts = []
    for _seg, g in out.groupby("segment", sort=False):
        flat = g[g["policy"] == "Flat forecast (current)"].sort_values("avg_inventory_value")
        base = flat[flat["z_increase"] == 0].iloc[0]
        g = g.copy()
        g["revenue_recovered"] = base["lost_revenue"] - g["lost_revenue"]
        g["share_of_loss_recovered"] = g["revenue_recovered"] / base["lost_revenue"]
        g["extra_inventory_value"] = g["avg_inventory_value"] - base["avg_inventory_value"]
        g["recovered_per_extra_inventory_dollar"] = g["revenue_recovered"] / g["extra_inventory_value"].where(
            g["extra_inventory_value"] > 0
        )
        # what the flat policy would lose holding the same inventory (linear along its curve)
        g["flat_loss_at_same_inventory"] = np.interp(
            g["avg_inventory_value"], flat["avg_inventory_value"], flat["lost_revenue"], left=np.nan, right=np.nan
        )
        g["saving_vs_flat_at_same_inventory"] = g["flat_loss_at_same_inventory"] - g["lost_revenue"]
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    out["measured_loss"] = data["measured_loss"]
    out["calibrated_z"] = z0
    return out
