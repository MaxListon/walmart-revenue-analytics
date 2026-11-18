"""Monthly business review (MBR): a one-page HTML report for any calendar month.

    python -m retailrev.report --month 2016-04        # -> reports/monthly/mbr_2016-04.html
    python -m retailrev.report                        # latest complete month

Each month is compared with the same days 52 weeks (364 days) earlier, so both periods
have the same mix of weekdays: the usual retail convention. Sections:

    headline KPIs     revenue, growth, comparable sales, store stock-out losses, fiscal year to date
    what happened     an auto-written summary of the numbers below
    revenue bridge    comparable store-products split into volume, mix and price; the rest is listings
    by category/state revenue, growth and comparable growth
    top movers        products with the biggest revenue change among comparable store-products
    stock-outs        the store-departments losing the most to store stock-outs

Comparable = a store-product with a shelf price on every day of both periods. The bridge
reconciles exactly: volume + mix + price = comparable change; plus other = total change.
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
from datetime import date, timedelta
from html import escape
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from retailrev.paths import ROOT, connect

SHIFT = timedelta(days=364)
BLUE, ORANGE, GRAY, INK, MUTED = "#2a78d6", "#eb6834", "#a8a69f", "#14213d", "#6b6a65"

PERIOD_SQL = """
SELECT store_id, state_id, item_id, dept_id, cat_id,
       count(*) FILTER (WHERE sell_price IS NOT NULL) AS listed_days,
       coalesce(sum(units), 0)                        AS units,
       coalesce(sum(revenue), 0)                      AS revenue
FROM v_sales_daily_priced
WHERE date BETWEEN ? AND ?
GROUP BY ALL
"""
DAILY_SQL = """
SELECT date, coalesce(sum(revenue), 0) AS revenue
FROM v_sales_daily_priced WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date
"""
STOCKOUT_SQL = """
SELECT store_id, dept_id, sum(lost_revenue) AS lost_revenue
FROM fct_oos_days
WHERE strict_flag AND spell_class = 'Store stock-out' AND date BETWEEN ? AND ?
GROUP BY ALL
"""


def month_bounds(month: str) -> tuple[date, date]:
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
    return start, end


def latest_complete_month(con) -> str:
    last = con.execute("SELECT max(date) FROM v_sales_daily_priced").fetchone()[0]
    first_of_month = last.replace(day=1)
    if last == month_bounds(f"{last:%Y-%m}")[1]:
        return f"{last:%Y-%m}"
    prev = first_of_month - timedelta(days=1)
    return f"{prev:%Y-%m}"


def _period(con, start: date, end: date) -> pd.DataFrame:
    return con.execute(PERIOD_SQL, [start, end]).df()


def bridge(cur: pd.DataFrame, prev: pd.DataFrame, n_days: int) -> tuple[pd.DataFrame, dict]:
    """Store-product join of two periods plus a reconciling volume / mix / price split."""
    key = ["store_id", "item_id"]
    attrs = ["state_id", "dept_id", "cat_id"]
    j = cur.merge(prev, on=key, how="outer", suffixes=("1", "0"))
    for a in attrs:
        j[a] = j[f"{a}1"].fillna(j[f"{a}0"])
    for c in ["listed_days", "units", "revenue"]:
        for sfx in "01":
            j[f"{c}{sfx}"] = j[f"{c}{sfx}"].fillna(0)
    j["comp"] = (j["listed_days1"] == n_days) & (j["listed_days0"] == n_days)
    c = j[j["comp"]]
    q0, q1, r0, r1 = (c[x].to_numpy(float) for x in ["units0", "units1", "revenue0", "revenue1"])
    p1 = np.divide(r1, q1, out=np.zeros_like(r1), where=q1 > 0)
    p0 = np.divide(r0, q0, out=p1.copy(), where=q0 > 0)  # no prior units: value at current price
    p0_avg = r0.sum() / q0.sum() if q0.sum() else 0.0
    volume = (q1.sum() - q0.sum()) * p0_avg
    price = float((q1 * (p1 - p0)).sum())
    comp_change = r1.sum() - r0.sum()
    mix = comp_change - volume - price
    total_change = j["revenue1"].sum() - j["revenue0"].sum()
    parts = {
        "revenue_prior": j["revenue0"].sum(),
        "revenue_current": j["revenue1"].sum(),
        "volume": volume,
        "mix": mix,
        "price": price,
        "other": total_change - comp_change,
        "comp_prior": r0.sum(),
        "comp_current": r1.sum(),
    }
    return j, parts


def _growth(cur: float, prev: float) -> float:
    return cur / prev - 1 if prev else float("nan")


def build(con, month: str) -> dict:
    start, end = month_bounds(month)
    last = con.execute("SELECT max(date) FROM v_sales_daily_priced").fetchone()[0]
    if end > last:
        raise ValueError(f"{month} is not complete in the data (last day {last}); try {latest_complete_month(con)}")
    n_days = (end - start).days + 1
    cur, prev = _period(con, start, end), _period(con, start - SHIFT, end - SHIFT)
    j, parts = bridge(cur, prev, n_days)

    def split(by: str) -> pd.DataFrame:
        g = j.groupby(by).agg(
            revenue=("revenue1", "sum"),
            revenue_prior=("revenue0", "sum"),
        )
        cg = j[j["comp"]].groupby(by).agg(comp1=("revenue1", "sum"), comp0=("revenue0", "sum"))
        g = g.join(cg)
        g["growth"] = g["revenue"] / g["revenue_prior"] - 1
        g["comp_growth"] = g["comp1"] / g["comp0"] - 1
        g["share"] = g["revenue"] / g["revenue"].sum()
        return g.sort_values("revenue", ascending=False).reset_index()

    movers = (
        j[j["comp"]]
        .groupby(["item_id", "dept_id"], as_index=False)
        .agg(revenue=("revenue1", "sum"), revenue_prior=("revenue0", "sum"))
        .assign(change=lambda d: d["revenue"] - d["revenue_prior"])
        .sort_values(["change", "item_id"], ascending=[False, True])
    )
    so = con.execute(STOCKOUT_SQL, [start, end]).df()
    so_prev = con.execute(STOCKOUT_SQL, [start - SHIFT, end - SHIFT]).df()

    fy_start = con.execute(
        "SELECT min(date) FROM stg_calendar WHERE fiscal_year = (SELECT fiscal_year FROM stg_calendar WHERE date = ?)",
        [end],
    ).fetchone()[0]
    ytd = con.execute("SELECT coalesce(sum(revenue), 0) FROM v_sales_daily_priced WHERE date BETWEEN ? AND ?", [fy_start, end])
    ytd_cur = float(ytd.fetchone()[0])
    ytd_prev = float(
        con.execute(
            "SELECT coalesce(sum(revenue), 0) FROM v_sales_daily_priced WHERE date BETWEEN ? AND ?",
            [fy_start - SHIFT, end - SHIFT],
        ).fetchone()[0]
    )
    fiscal_year = con.execute("SELECT fiscal_year FROM stg_calendar WHERE date = ?", [end]).fetchone()[0]

    daily = con.execute(DAILY_SQL, [start, end]).df()
    daily_prev = con.execute(DAILY_SQL, [start - SHIFT, end - SHIFT]).df()
    return {
        "month": month,
        "start": start,
        "end": end,
        "n_days": n_days,
        "parts": parts,
        "growth": _growth(parts["revenue_current"], parts["revenue_prior"]),
        "comp_growth": _growth(parts["comp_current"], parts["comp_prior"]),
        "comp_share": parts["comp_current"] / parts["revenue_current"] if parts["revenue_current"] else 0,
        "category": split("cat_id"),
        "state": split("state_id"),
        "movers_up": movers.head(5),
        "movers_down": movers.sort_values(["change", "item_id"]).head(5),
        # detection needs 28 days of sales after a zero-sale run, so recent months are undercounted
        "stockout_complete": end + timedelta(days=28) <= last,
        "stockout": float(so["lost_revenue"].sum()),
        "stockout_prior": float(so_prev["lost_revenue"].sum()),
        "stockout_top": so.sort_values(["lost_revenue", "store_id"], ascending=[False, True]).head(5),
        "fiscal_year": fiscal_year,
        "ytd": ytd_cur,
        "ytd_prior": ytd_prev,
        "daily": daily,
        "daily_prior": daily_prev,
    }


# ---------------------------------------------------------------- rendering


def _money(v: float) -> str:
    sign = "−" if v < 0 else ""
    v = abs(v)
    if v >= 1e6:
        return f"{sign}${v / 1e6:,.2f}M"
    return f"{sign}${v / 1e3:,.1f}K" if v < 1e4 else f"{sign}${v / 1e3:,.0f}K"


def _signed_money(v: float) -> str:
    return ("+" if v >= 0 else "") + _money(v)


def _pct(v: float, d: int = 1) -> str:
    return "n/a" if pd.isna(v) else f"{v:+.{d}%}".replace("-", "−")


def narrative(r: dict) -> list[str]:
    p = r["parts"]
    change = p["revenue_current"] - p["revenue_prior"]
    comp_change = p["comp_current"] - p["comp_prior"]
    lines = [
        f"Revenue was {_money(p['revenue_current'])}, {_pct(r['growth'])} versus the same days last year "
        f"({_signed_money(change)}).",
        f"Comparable sales (store-products on the shelf every day of both periods, {r['comp_share']:.0%} of revenue) "
        f"{'grew' if comp_change >= 0 else 'fell'} {_pct(r['comp_growth'])}: volume {_signed_money(p['volume'])}, "
        f"mix {_signed_money(p['mix'])}, price {_signed_money(p['price'])}.",
        f"Listing changes (new, returning and dropped store-products) added {_signed_money(p['other'])}.",
    ]
    cat = r["category"]
    if len(cat):
        best = cat.loc[cat["comp_growth"].idxmax()]
        worst = cat.loc[cat["comp_growth"].idxmin()]
        lines.append(
            f"By category, {best.cat_id.title()} led on comparable sales ({_pct(best.comp_growth)}) and "
            f"{worst.cat_id.title()} was weakest ({_pct(worst.comp_growth)})."
        )
    dark = r["movers_down"][r["movers_down"]["revenue"] == 0]
    if len(dark):
        lines.append(
            f"{len(dark)} of the top fallers ({', '.join(dark['item_id'])}) had a shelf price all month but sold "
            "nothing: likely out of stock or quietly delisted. Worth checking first."
        )
    so_delta = r["stockout"] - r["stockout_prior"]
    if r["stockout_complete"]:
        lines.append(
            f"Store stock-outs cost an estimated {_money(r['stockout'])}, "
            f"{'up' if so_delta >= 0 else 'down'} {_money(abs(so_delta))} on last year."
        )
    else:
        lines.append(
            f"Store stock-outs so far: {_money(r['stockout'])}. This is a floor, not a final number: detection needs "
            "28 days of later sales, so runs near the end of the data can't be confirmed yet."
        )
    lines.append(
        f"Fiscal {r['fiscal_year']} to date: {_money(r['ytd'])}, {_pct(_growth(r['ytd'], r['ytd_prior']))} "
        "versus the same days last year."
    )
    return lines


def _chart(r: dict) -> str:
    d, dp = r["daily"], r["daily_prior"]
    fig, ax = plt.subplots(figsize=(7.2, 2.4), dpi=150)
    ax.plot(range(1, len(dp) + 1), dp["revenue"] / 1e3, color=GRAY, lw=2, label="Same days last year")
    ax.plot(range(1, len(d) + 1), d["revenue"] / 1e3, color=BLUE, lw=2.4, label="This month")
    ax.set_xlabel("Day of period", color=MUTED, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}K"))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color="#e1e0d9", lw=0.6)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _bridge_bars(r: dict) -> str:
    p = r["parts"]
    rows = [("Volume", p["volume"]), ("Mix", p["mix"]), ("Price", p["price"]), ("Listing changes", p["other"])]
    top = max(abs(v) for _, v in rows) or 1
    out = []
    for name, v in rows:
        w = abs(v) / top * 100
        cls = "pos" if v >= 0 else "neg"
        out.append(
            f'<div class="brow"><span class="bname">{name}</span><span class="btrack">'
            f'<span class="bar {cls}" style="width:{w:.1f}%"></span></span>'
            f'<span class="bval">{_signed_money(v)}</span></div>'
        )
    return "\n".join(out)


def _table(df: pd.DataFrame, cols: list[tuple[str, str, callable]]) -> str:
    head = "".join(f"<th>{escape(label)}</th>" for _, label, _ in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(fmt(row[c]))}</td>" for c, _, fmt in cols) + "</tr>" for _, row in df.iterrows()
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


CSS = """
:root { --ink:#14213d; --soft:#4a5568; --muted:#6b6a65; --paper:#f7f6f2; --card:#fdfcf9; --line:#e1e0d9;
        --blue:#2a78d6; --red:#e34948; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.45 Inter, -apple-system, Segoe UI, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 24px 48px; }
h1, h2 { font-family: 'Space Grotesk', Inter, sans-serif; margin: 0; }
h1 { font-size: 30px; } h2 { font-size: 18px; margin: 28px 0 10px; }
.sub { color: var(--muted); margin-top: 4px; }
.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 20px; }
.kpi { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.kpi .l { font-size: 12px; color: var(--muted); } .kpi .v { font: 600 22px 'Space Grotesk', Inter, sans-serif; margin-top: 2px; }
.kpi .d { font-size: 12px; color: var(--soft); }
ul.story { margin: 0; padding-left: 20px; } ul.story li { margin: 4px 0; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
th { text-align: left; color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--line); padding: 6px 4px; }
td { border-bottom: 1px solid var(--line); padding: 6px 4px; }
.brow { display: grid; grid-template-columns: 120px 1fr 90px; align-items: center; gap: 10px; margin: 6px 0; font-size: 13px; }
.btrack { background: #ecebe5; border-radius: 4px; height: 12px; }
.bar { display: block; height: 12px; border-radius: 4px; } .pos { background: var(--blue); } .neg { background: var(--red); }
.bval { text-align: right; font-variant-numeric: tabular-nums; }
img.chart { width: 100%; }
footer { margin-top: 28px; color: var(--muted); font-size: 12px; }
@media (max-width: 720px) { .kpis { grid-template-columns: repeat(2, 1fr); } .grid2 { grid-template-columns: 1fr; } }
"""


def render(r: dict) -> str:
    p = r["parts"]
    title = f"{r['start']:%B %Y}"
    pct0 = lambda v: _pct(v, 1)  # noqa: E731
    kpis = [
        ("Revenue", _money(p["revenue_current"]), f"{_pct(r['growth'])} vs same days last year"),
        ("Comparable sales", _pct(r["comp_growth"]), f"{r['comp_share']:.0%} of revenue is comparable"),
        ("Growth from comparable", _signed_money(p["comp_current"] - p["comp_prior"]), "volume + mix + price"),
        (
            "Store stock-out losses",
            _money(r["stockout"]) + ("" if r["stockout_complete"] else "+"),
            f"last year {_money(r['stockout_prior'])}" if r["stockout_complete"] else "incomplete: needs 28 more days",
        ),
        (f"FY{r['fiscal_year']} to date", _money(r["ytd"]), f"{_pct(_growth(r['ytd'], r['ytd_prior']))} vs last year"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="l">{escape(a)}</div><div class="v">{escape(b)}</div><div class="d">{escape(c)}</div></div>'
        for a, b, c in kpis
    )
    cat_table = _table(
        r["category"],
        [
            ("cat_id", "Category", str.title),
            ("revenue", "Revenue", _money),
            ("growth", "Growth", pct0),
            ("comp_growth", "Comparable", pct0),
            ("share", "Share", lambda v: f"{v:.0%}"),
        ],
    )
    state_table = _table(
        r["state"],
        [
            ("state_id", "State", str),
            ("revenue", "Revenue", _money),
            ("growth", "Growth", pct0),
            ("comp_growth", "Comparable", pct0),
            ("share", "Share", lambda v: f"{v:.0%}"),
        ],
    )
    mover_cols = [
        ("item_id", "Product", str),
        ("dept_id", "Department", str),
        ("revenue", "Revenue", lambda v: "$0 (no sales)" if v == 0 else _money(v)),
        ("change", "Change", _signed_money),
    ]
    up, down = _table(r["movers_up"], mover_cols), _table(r["movers_down"], mover_cols)
    so_table = _table(
        r["stockout_top"],
        [("store_id", "Store", str), ("dept_id", "Department", str), ("lost_revenue", "Est. lost revenue", _money)],
    )
    story = "".join(f"<li>{escape(s)}</li>" for s in narrative(r))
    prev_start, prev_end = r["start"] - SHIFT, r["end"] - SHIFT
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monthly business review · {title}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">
<style>{CSS}</style></head>
<body><main>
<h1>Monthly business review · {title}</h1>
<div class="sub">10 Walmart stores (CA, TX, WI) · {r["start"]:%b %d}–{r["end"]:%b %d, %Y} vs the same weekdays one year earlier
({prev_start:%b %d}–{prev_end:%b %d, %Y})</div>
<div class="kpis">{kpi_html}</div>
<h2>What happened</h2><ul class="story">{story}</ul>
<h2>Daily revenue</h2><img class="chart" alt="Daily revenue this month vs the same days last year"
 src="data:image/png;base64,{_chart(r)}">
<div class="grid2">
<div><h2>Where the change came from</h2>{_bridge_bars(r)}</div>
<div><h2>Biggest store stock-out losses</h2>{so_table}</div>
</div>
<div class="grid2"><div><h2>By category</h2>{cat_table}</div><div><h2>By state</h2>{state_table}</div></div>
<div class="grid2"><div><h2>Top risers (comparable products)</h2>{up}</div>
<div><h2>Top fallers (comparable products)</h2>{down}</div></div>
<footer>Comparable = store-products with a shelf price on every day of both periods. Volume + mix + price add up exactly to the
comparable change; listing changes are the rest. Stock-outs are estimated statistically (no inventory records).
Source: Walmart M5 data. Generated by <code>python -m retailrev.report --month {r["month"]}</code>.</footer>
</main></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a one-page monthly business review.")
    ap.add_argument("--month", help="YYYY-MM (default: latest complete month)")
    ap.add_argument("--out", default=str(ROOT / "reports" / "monthly"))
    args = ap.parse_args()
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    plt.switch_backend("Agg")
    con = connect()
    month = args.month or latest_complete_month(con)
    r = build(con, month)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"mbr_{month}.html"
    path.write_text(render(r))
    print(f"  wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    for line in narrative(r):
        print("  -", line)


if __name__ == "__main__":
    main()
