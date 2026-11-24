"""Independent check of the stock-out alert: plant known stock-outs in real sales and see what it catches.

The FY2016 backtest in stock_alerts.py scores alerts against a detector that uses nearly the same test.
Here the truth is known by construction. For random store-products in the FY2017 weeks (not used to
compare thresholds), real sales are set to zero for a fixed number of days. The sales that were removed
are the true loss. Each rule then sees only the altered history.

* detected       alert fires on a planted day
* revenue ahead  share of truly removed revenue falling after the alert day (action starts next morning)
* volume         alerts per store per day the rule fires on the unaltered data, with no cap. Some of those
                 are real stock-outs, so this is workload, not a false-alarm rate.

Rules are compared at equal volume by interpolating along each family's volume/outcome curve.

    python -m retailrev.alert_validation   # -> outputs/alert_validation.csv, outputs/alert_validation_matched.csv,
                                           #    outputs/alert_pilot_power.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retailrev import stock_alerts
from retailrev.paths import OUTPUTS, connect
from retailrev.stock_alerts import THRESHOLD, alert_day

START, END = "2016-01-30", "2016-05-08"  # planted gaps start here, so a 14-day gap ends inside the data
GAPS = (3, 7, 14)
N, SEED, BOOT = 30_000, 20160130, 500
THRESHOLDS = (0.1, 0.03, 0.01, 0.003, THRESHOLD, 0.0003, 0.0001, 0.00001)
FIXED = (2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 18, 21, 24, 28)
RULES = [("Item-aware", t) for t in THRESHOLDS] + [("Fixed days", n) for n in FIXED]


def load() -> tuple[np.ndarray, np.ndarray, pd.DataFrame, pd.DatetimeIndex]:
    """Units and prices as store-item x day matrices (NaN = not listed), from well before the window."""
    con = connect()
    df = con.execute("""
        SELECT s.store_id, s.item_id, c.date, s.units, CAST(p.sell_price AS DOUBLE) AS price
        FROM stg_sales_daily s JOIN stg_calendar c USING (day_num)
        JOIN stg_prices p ON p.store_id = s.store_id AND p.item_id = s.item_id AND p.wm_yr_wk = c.wm_yr_wk
        WHERE c.date >= DATE '2015-10-01' AND NOT (c.calendar_month = 12 AND extract(day FROM c.date) = 25)
    """).df()
    con.close()
    units = df.pivot(index=["store_id", "item_id"], columns="date", values="units").sort_index()
    price = df.pivot(index=["store_id", "item_id"], columns="date", values="price").reindex_like(units)
    return units.to_numpy(float), price.to_numpy(float), units.index.to_frame(index=False), pd.DatetimeIndex(units.columns)


def needed_days(rule: str, setting: float, zeros_before: int) -> int:
    return alert_day(zeros_before, setting) if rule == "Item-aware" else int(setting)


def run_start(u: np.ndarray, d: int) -> int:
    """First day of the zero-sale run containing day d (d itself is treated as zero)."""
    while d > 0 and u[d - 1] == 0:
        d -= 1
    return d


def plant(u: np.ndarray, d: int, gap: int, rule: str, setting: float) -> int | None:
    """Days into the planted gap (1 = first day) on which the alert fires; None if it doesn't.

    Returns 0 if the product was already alerted before the gap began.
    """
    s = run_start(u, d)
    hist = u[s - 28 : s]
    need = needed_days(rule, setting, int((hist == 0).sum()))
    day = need - (d - s)
    return 0 if day <= 0 else (day if day <= gap else None)


def volume(u: np.ndarray, first: int, last: int, stores: int) -> pd.Series:
    """Uncapped alerts per store per day each rule fires on the unaltered data."""
    counts = dict.fromkeys(RULES, 0)
    for row in u:
        z = np.flatnonzero(row == 0)
        if not len(z):
            continue
        for run in np.split(z, np.flatnonzero(np.diff(z) > 1) + 1):
            s = run[0]
            if run[-1] < first or s < 28:
                continue
            hist = row[s - 28 : s]
            if np.isnan(hist).any() or hist.sum() == 0:
                continue
            zb = int((hist == 0).sum())
            for r in RULES:
                k = needed_days(*r, zb)
                if k <= len(run) and first <= s + k - 1 <= last:
                    counts[r] += 1
    return pd.Series(counts) / (stores * (last - first + 1))


def sample(u: np.ndarray, first: int, last: int, gap: int, rng: np.random.Generator, n: int) -> list[tuple[int, int]]:
    """Random (product, start day) pairs: a full month of selling history, listed through the gap."""
    out = []
    while len(out) < n:
        i, d = int(rng.integers(len(u))), int(rng.integers(first, last + 1))
        row = u[i]
        s = run_start(row, d)
        if s >= 28 and not np.isnan(row[s - 28 : d + gap]).any() and row[s - 28 : s].sum() > 0:
            out.append((i, d))
    return out


def outcomes(u, p, pairs, gap) -> dict[tuple, np.ndarray]:
    """Per rule: rows of (detected, already alerted, true loss, true loss after the alert day)."""
    res = {}
    for r in RULES:
        a = np.zeros((len(pairs), 4))
        for j, (i, d) in enumerate(pairs):
            lost = u[i, d : d + gap] * p[i, d : d + gap]
            k = plant(u[i], d, gap, *r)
            a[j] = (k is not None and k > 0, k == 0, lost.sum(), 0 if not k else lost[k:].sum())
        res[r] = a
    return res


def _rates(a: np.ndarray) -> tuple[float, float]:
    live = a[:, 1] == 0  # products already alerted before the gap are not a fair test of this gap
    return a[live, 0].mean(), a[live, 3].sum() / a[live, 2].sum()


def matched(vol: pd.Series, rates: dict[tuple, float], target: float) -> dict[str, float]:
    """Each family's outcome at the target volume, interpolated on log volume."""
    out = {}
    for fam in ("Item-aware", "Fixed days"):
        rs = sorted((r for r in RULES if r[0] == fam), key=lambda r: vol[r])
        x = np.log([vol[r] for r in rs])
        out[fam] = float(np.interp(np.log(target), x, [rates[r] for r in rs]))
    return out


def validate(u, p, first, last, stores, n=N, boot=BOOT, seed=SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    vol = volume(u, first, last, stores)
    target = float(vol[("Item-aware", THRESHOLD)])
    rows, comp = [], []
    for gap in GAPS:
        pairs = sample(u, first, last, gap, rng, n)
        res = outcomes(u, p, pairs, gap)
        for r in RULES:
            det, ahead = _rates(res[r])
            rows.append(dict(gap_days=gap, rule=r[0], setting=r[1], volume=vol[r], detected=det, revenue_ahead=ahead))
        items = np.array([i for i, _ in pairs])
        uniq, inv = np.unique(items, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        bounds = np.searchsorted(inv[order], np.arange(len(uniq) + 1))
        groups = [order[bounds[g] : bounds[g + 1]] for g in range(len(uniq))]
        for metric, pos in (("detected", 0), ("revenue_ahead", 1)):
            point = matched(vol, {r: _rates(res[r])[pos] for r in RULES}, target)
            comp.append([gap, metric, point["Item-aware"], point["Fixed days"], groups, res, pos])
        # resample store-products (a product can be drawn more than once)
        draws = {m: [] for m in ("detected", "revenue_ahead")}
        for _ in range(boot):
            idx = np.concatenate([groups[g] for g in rng.integers(len(groups), size=len(groups))])
            rt = {r: _rates(res[r][idx]) for r in RULES}
            for m, pos in (("detected", 0), ("revenue_ahead", 1)):
                q = matched(vol, {r: rt[r][pos] for r in RULES}, target)
                draws[m].append(q["Item-aware"] - q["Fixed days"])
        for c in comp[-2:]:
            lo, hi = np.percentile(draws[c[1]], [2.5, 97.5])
            c[4:] = [c[2] - c[3], lo, hi, target]
    cols = ["gap_days", "metric", "item_aware", "fixed_days", "difference", "ci_low", "ci_high", "volume"]
    return pd.DataFrame(rows), pd.DataFrame(comp, columns=cols)


def pilot_power(a: pd.DataFrame, reps: int = 400, seed: int = SEED) -> pd.DataFrame:
    """Power of a pilot that acts on a random half of alerts and compares log days still dark.

    Uses real FY2016 alerts (whole days resampled together). Assumes store checks shorten the remaining gap by
    `cut` on the share of alerts that are fixable, and do nothing on the rest. Both are assumptions to vary.
    """
    rng = np.random.default_rng(seed)
    days = a.assign(left=(a.zero_days - a.alert_len + 1).clip(upper=28)).groupby("alert_date").left.apply(np.array).tolist()
    rows = []
    for fixable in (0.25, 0.43):
        for cut in (0.0, 0.3, 0.5):
            for weeks in (4, 8, 12):
                hits = 0
                for _ in range(reps):
                    x = np.concatenate([days[k] for k in rng.integers(len(days), size=7 * weeks)]).astype(float)
                    t = rng.random(len(x)) < 0.5
                    helped = t & (rng.random(len(x)) < fixable)
                    x[helped] = np.maximum(1, np.round(x[helped] * (1 - cut)))
                    y = np.log(x)
                    diff = y[t].mean() - y[~t].mean()
                    se = np.sqrt(y[t].var(ddof=1) / t.sum() + y[~t].var(ddof=1) / (~t).sum())
                    hits += diff / se < -1.96
                rows.append(dict(fixable_share=fixable, cut=cut, weeks=weeks, power=hits / reps))
    return pd.DataFrame(rows)


def main() -> None:
    u, p, idx, dates = load()
    first, last = dates.get_loc(pd.Timestamp(START)), dates.get_loc(pd.Timestamp(END))
    full, m = validate(u, p, first, last, idx.store_id.nunique())
    full.to_csv(OUTPUTS / "alert_validation.csv", index=False)
    m.to_csv(OUTPUTS / "alert_validation_matched.csv", index=False)
    con = connect()
    stock_alerts.build_runs(con)
    a = stock_alerts.alerts(con, stock_alerts._alert_len_sql(THRESHOLD), *stock_alerts.FY2016)
    con.close()
    pw = pilot_power(a.sort_values(["alert_date", "store_id", "item_id"]))
    pw.to_csv(OUTPUTS / "alert_pilot_power.csv", index=False)
    print(pw.to_string(index=False))
    print(m.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
