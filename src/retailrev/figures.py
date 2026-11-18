"""Static report figures (PNG) built from outputs/*.csv.

Palette: validated categorical slots (blue, orange, aqua) assigned to a fixed
entity, plus a blue/red diverging pair for up/down. Usage:
    python -m retailrev.figures          # report figures -> reports/figures/
    python -m retailrev.figures --deck   # slide versions -> reports/figures/deck/

Deck mode draws each chart at the pixel size of its slide slot, with slide-sized
text, a transparent background and no chart title (the slide headline is the title).
"""

from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from retailrev.paths import FIGURES, OUTPUTS

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, AQUA, RED, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#a8a69f"
CAT_COLORS = {"FOODS": BLUE, "HOUSEHOLD": ORANGE, "HOBBIES": AQUA}
STATE_COLORS = {"CA": BLUE, "TX": ORANGE, "WI": AQUA}

plt.rcParams.update(
    {
        "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK2,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titlepad": 30,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": 200,
        "legend.frameon": False,
        "text.parse_math": False,
    }
)


# Deck mode: slot sizes in slide pixels (1920x1080 canvas, 1664px content width).
FULL, SIDE, HALF, SEG = (1664, 560), (1150, 560), (1056, 560), (900, 560)
DECK = False
PAPER = "#f7f6f2"  # slide background, used for gaps between stacked segments
_SCALE = 1.0


def _fs(size: float) -> float:
    """Font size that scales up in deck mode."""
    return size * _SCALE


def _pct(v: float, decimals: int = 1, sign: bool = True) -> str:
    """Percent label with a true minus sign."""
    return f"{v:{'+' if sign else ''}.{decimals}%}".replace("-", "\u2212")


def _subplots(*args, figsize, slot, **kwargs):
    if DECK:
        return plt.subplots(*args, figsize=(slot[0] / 100, slot[1] / 100), layout="constrained", **kwargs)
    return plt.subplots(*args, figsize=figsize, **kwargs)


def _title(ax, text: str) -> None:
    if not DECK:
        ax.set_title(text)


def _suptitle(fig, text: str, **kwargs) -> None:
    if not DECK:
        fig.suptitle(text, **kwargs)


def _m(x, _=None):
    return f"${x / 1e6:,.1f}M"


def _save(fig, name: str, note: str | None = None) -> None:
    if DECK:
        out = FIGURES / "deck" / f"{name}.png"
        fig.savefig(out, dpi=200, transparent=True)
    else:
        if note:
            fig.text(0.01, -0.07, note, color=MUTED, fontsize=_fs(8), ha="left", va="bottom")
        out = FIGURES / f"{name}.png"
        fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out.relative_to(FIGURES.parent.parent)}")


def growth_vs_comp() -> None:
    a = pd.read_csv(OUTPUTS / "annual_revenue.csv")
    c = pd.read_csv(OUTPUTS / "comp_sales.csv")
    d = a.merge(c[["fiscal_year", "comp_growth"]], on="fiscal_year").dropna(subset=["yoy_52wk"])
    x = np.arange(len(d))
    fig, ax = _subplots(figsize=(8, 4.2), slot=FULL)
    w = 0.36
    ax.bar(x - w / 2 - 0.01, d["yoy_52wk"], w, color=GRAY, label="Total revenue growth")
    ax.bar(
        x + w / 2 + 0.01,
        d["comp_growth"],
        w,
        color=[BLUE if v >= 0 else RED for v in d["comp_growth"]],
        label="Comparable sales growth",
    )
    for i, (t, cg) in enumerate(zip(d["yoy_52wk"], d["comp_growth"])):
        ax.text(
            i - w / 2,
            t + (0.006 if t >= 0 else -0.006),
            _pct(t),
            ha="center",
            va="bottom" if t >= 0 else "top",
            color=INK2,
            fontsize=_fs(9),
        )
        ax.text(
            i + w / 2,
            cg + (0.006 if cg >= 0 else -0.006),
            _pct(cg),
            ha="center",
            va="bottom" if cg >= 0 else "top",
            color=INK,
            fontsize=_fs(9),
            fontweight="bold",
        )
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_ylim(min(d["comp_growth"].min(), 0) - 0.04, d["yoy_52wk"].max() + 0.04)  # room for labels
    ax.set_xticks(x, [f"FY{y}" for y in d["fiscal_year"]])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    _title(ax, "Revenue grew every year, but existing products shrank for three years")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (GRAY, BLUE, RED)]
    ax.legend(
        handles, ["Total revenue growth", "Comparable growth (up)", "Comparable growth (down)"], loc="upper right", handlelength=1
    )
    _save(
        fig,
        "01_growth_vs_comp",
        "52-week basis. Comparable = store-items listed all 52 weeks of both years. Source: Walmart M5 data.",
    )


def bridge_waterfall(fy: int = 2016) -> None:
    b = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    b = b[(b["fiscal_year"] == fy) & (b["level"] == "Total")].iloc[0]
    steps = [
        ("Volume", b.volume_effect),
        ("Mix", b.mix_effect),
        ("Price", b.price_effect),
        ("Prior-year\nlaunches\nannualizing", b.launch_annualization_effect),
        ("New\nlistings", b.new_listings_effect),
        ("Lost\nlistings", b.lost_listings_effect),
    ]
    labels = [f"FY{fy - 1}"] + [s[0] for s in steps] + [f"FY{fy}"]
    fig, ax = _subplots(figsize=(9, 4.4), slot=FULL)
    ax.bar(0, b.revenue_prior, color=GRAY, width=0.6)
    run = b.revenue_prior
    for i, (_, v) in enumerate(steps, start=1):
        ax.bar(i, v, bottom=run if v >= 0 else run + v, color=BLUE if v >= 0 else RED, width=0.6)
        amount = f"${abs(v) / 1e6:.2f}M" if abs(v) >= 1e5 else f"${abs(v) / 1e3:.0f}K"
        ax.text(i, run + max(v, 0) + 2e5, f"{'+' if v >= 0 else '−'}{amount}", ha="center", color=INK, fontsize=_fs(9))
        run += v
    ax.bar(len(steps) + 1, b.revenue_current, color=GRAY, width=0.6)
    for i, v in [(0, b.revenue_prior), (len(steps) + 1, b.revenue_current)]:
        ax.text(i, v + 2e5, _m(v), ha="center", color=INK, fontsize=_fs(9), fontweight="bold")
    ax.axvspan(0.5, 3.5, color="#2a78d6", alpha=0.05, lw=0)
    ax.text(2, b.revenue_prior * 0.55, "Existing products\n(comp)", ha="center", color=INK2, fontsize=_fs(9))
    ax.text(5, b.revenue_prior * 0.55, "Assortment\nexpansion", ha="center", color=INK2, fontsize=_fs(9))
    ax.set_ylim(b.revenue_prior * 0.5, b.revenue_current * 1.04)
    ax.set_xticks(range(len(labels)), labels, fontsize=_fs(9))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_m))
    comp = b.volume_effect + b.mix_effect + b.price_effect
    total = b.revenue_current - b.revenue_prior
    _title(ax, f"FY{fy} revenue bridge: {comp / total:.0%} of the +${total / 1e6:.1f}M came from existing products")
    _save(
        fig,
        "02_revenue_bridge_fy2016",
        "52-week basis. Y-axis truncated. Lost listings are near zero because the data only has products still sold in 2016.",
    )


def pareto() -> None:
    p = pd.read_csv(OUTPUTS / "item_pareto_fy2016.csv")
    fig, ax = _subplots(figsize=(8, 4.2), slot=FULL)
    ax.plot(p["cum_item_share"], p["cum_share"], color=BLUE, lw=2)
    for share, _label in [(0.80, "A"), (0.95, "B")]:
        k = p.loc[p["cum_share"] >= share, "cum_item_share"].iloc[0]
        ax.plot([k, k], [0, share], color=AXIS, lw=1)
        ax.plot([0, k], [share, share], color=AXIS, lw=1)
        ax.annotate(
            f"{k:.0%} of items → {share:.0%} of revenue",
            (k, share),
            xytext=(8, -14),
            textcoords="offset points",
            color=INK,
            fontsize=_fs(9),
        )
    c_share = (p["abc_class"] == "C").mean()
    ax.text(
        0.98,
        0.5,
        f"Long tail (C):\n{c_share:.0%} of items,\n5% of revenue",
        ha="right",
        color=INK2,
        fontsize=_fs(9),
        transform=ax.transAxes,
    )
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.set_xlabel("Share of items (ranked by revenue)")
    ax.set_ylabel("Cumulative share of revenue")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    _title(ax, "Revenue concentration, FY2016: 43% of items make 80% of revenue")
    _save(fig, "03_item_pareto", "3,049 items across 10 stores. Source: Walmart M5 data.")


def store_growth() -> None:
    s = pd.read_csv(OUTPUTS / "store_scorecard_fy2016.csv").sort_values("yoy_growth")
    b = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    b = b[(b["fiscal_year"] == 2016) & (b["level"] == "Store")].set_index("segment")
    s["comp_growth"] = s["store_id"].map(b["comp_growth"])
    fig, ax = _subplots(figsize=(8, 4.4), slot=FULL)
    y = np.arange(len(s))
    ax.barh(y + 0.19, s["yoy_growth"], 0.36, color=GRAY, label="Total growth")
    ax.barh(
        y - 0.19,
        s["comp_growth"],
        0.36,
        color=[STATE_COLORS[st] for st in s["state_id"]],
        label="Comparable growth (color = state)",
    )
    for i, (t, c) in enumerate(zip(s["yoy_growth"], s["comp_growth"])):
        ax.text(max(t, 0) + 0.004, i + 0.19, _pct(t), va="center", color=INK2, fontsize=_fs(8))
        ax.text(max(c, 0) + 0.004, i - 0.19, _pct(c), va="center", color=INK, fontsize=_fs(8))
    ax.set_yticks(y, s["store_id"])
    ax.axvline(0, color=AXIS, lw=1)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    handles = [plt.Rectangle((0, 0), 1, 1, color=GRAY)] + [plt.Rectangle((0, 0), 1, 1, color=c) for c in STATE_COLORS.values()]
    ax.legend(handles, ["Total growth", "Comp: CA", "Comp: TX", "Comp: WI"], loc="lower right", handlelength=1)
    _title(ax, "FY2016 store growth: CA_2 led on both measures; CA_3, the largest store, was flat on comp")
    _save(fig, "04_store_growth_fy2016", "52-week basis. Source: Walmart M5 data.")


def snap() -> None:
    s = pd.read_csv(OUTPUTS / "snap_lift.csv")
    s = s[s["state_id"] != "ALL"]
    cats = ["FOODS", "HOUSEHOLD", "HOBBIES"]
    states = ["CA", "TX", "WI"]
    fig, ax = _subplots(figsize=(8, 4), slot=FULL)
    w = 0.26
    for j, cat in enumerate(cats):
        d = s[s["cat_id"] == cat].set_index("state_id").loc[states]
        x = np.arange(3) + (j - 1) * (w + 0.02)
        ax.bar(x, d["snap_lift"], w, color=CAT_COLORS[cat], label=cat.title())
        ax.errorbar(
            x,
            d["snap_lift"],
            yerr=[d["snap_lift"] - d["ci_low"], d["ci_high"] - d["snap_lift"]],
            fmt="none",
            ecolor=INK2,
            elinewidth=1,
            capsize=2,
        )
        if cat == "FOODS":
            for xi, v, hi in zip(x, d["snap_lift"], d["ci_high"]):
                ax.text(xi, hi + 0.008, f"+{v:.0%}", ha="center", color=INK, fontsize=_fs(9), fontweight="bold")
    ax.set_xticks(range(3), ["California", "Texas", "Wisconsin"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.legend(loc="upper left", handlelength=1)
    _title(ax, "SNAP benefit days lift food revenue 9–28%; non-food barely moves")
    _save(fig, "05_snap_lift", "Fixed-effects model: store-month and store-weekday effects; 95% CI. Source: Walmart M5 data.")


def events() -> None:
    e = pd.read_csv(OUTPUTS / "event_lift.csv")
    keep = [
        "Thanksgiving",
        "NewYear",
        "Easter",
        "Mother's day",
        "SuperBowl",
        "IndependenceDay",
        "ValentinesDay",
        "MemorialDay",
        "LaborDay",
    ]
    e = e[e["event_name"].isin(keep)].set_index("event_name").loc[keep[::-1]]
    fig, ax = _subplots(figsize=(8, 4.6), slot=FULL)
    y = np.arange(len(e))
    ax.barh(y + 0.19, e["median_lift_day_before"], 0.36, color=GRAY, label="Day before")
    ax.barh(y - 0.19, e["median_lift"], 0.36, color=[BLUE if v >= 0 else RED for v in e["median_lift"]], label="Event day")
    for i, v in enumerate(e["median_lift"]):
        ax.text(
            v + (0.008 if v >= 0 else -0.008),
            i - 0.19,
            _pct(v, 0),
            va="center",
            ha="left" if v >= 0 else "right",
            color=INK,
            fontsize=_fs(8),
        )
    names = {
        "NewYear": "New Year's Day",
        "SuperBowl": "Super Bowl",
        "IndependenceDay": "Independence Day",
        "ValentinesDay": "Valentine's Day",
        "MemorialDay": "Memorial Day",
        "LaborDay": "Labor Day",
        "Mother's day": "Mother's Day",
    }
    ax.set_yticks(y, [names.get(n, n) for n in e.index])
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlim(-0.42, 0.42)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, handlelength=1)
    _title(ax, "Holiday shopping shifts to the day before; Monday holidays pull weekend trips forward")
    _save(fig, "06_event_lift", "Median lift vs same weekday ±4 weeks, chain-wide, 2011–2016. Christmas (stores closed) omitted.")


def elasticity() -> None:
    el = pd.read_csv(OUTPUTS / "price_elasticity.csv")
    ev = pd.read_csv(OUTPUTS / "price_event_elasticity.csv")
    depts = sorted(el["dept_id"].unique(), reverse=True)
    fig, (ax, ax2) = _subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.5, 1]}, slot=FULL)
    for _k, (spec, color, off, label) in enumerate(
        [
            ("Poisson, all item-stores", BLUE, 0.15, "All items with price changes"),
            ("Poisson, fast movers (>=5 units/week)", ORANGE, -0.15, "Fast movers (≥5 units/week)"),
        ]
    ):
        d = el[el["spec"] == spec].set_index("dept_id").loc[depts]
        y = np.arange(len(d)) + off
        ax.errorbar(
            d["elasticity"],
            y,
            xerr=[d["elasticity"] - d["ci_low"], d["ci_high"] - d["elasticity"]],
            fmt="o",
            color=color,
            ecolor=color,
            elinewidth=1.5,
            markersize=6,
            label=label,
        )
    ax.axvline(-1, color=INK2, lw=1)
    for i, dept in enumerate(depts):
        if dept.startswith("HOUSEHOLD"):
            ax.axhspan(i - 0.45, i + 0.45, color=BLUE, alpha=0.08, lw=0)
    ax.set_yticks(range(len(depts)), depts)
    for lbl in ax.get_yticklabels():
        if lbl.get_text().startswith("HOUSEHOLD"):
            lbl.set_fontweight("bold")
            lbl.set_color(INK)
    ax.set_xlabel("Panel elasticity, Poisson fixed effects (95% CI)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, handlelength=1, fontsize=_fs(9))
    e = ev[ev["segment"] == "All departments (excl. week before change)"].set_index("direction").loc[["increase", "decrease"]]
    y = np.arange(2)
    ax2.errorbar(
        e["elasticity"],
        y,
        xerr=[e["elasticity"] - e["ci_low"], e["ci_high"] - e["elasticity"]],
        fmt="o",
        color=INK,
        elinewidth=1.5,
        markersize=7,
    )
    for yi, (v, n) in enumerate(zip(e["elasticity"], e["events"])):
        ax2.text(v, yi + 0.18, f"{v:.2f}  ({n:,} events)".replace("-", "\u2212"), ha="center", color=INK, fontsize=_fs(9))
    ax2.axvline(-1, color=INK2, lw=1)
    ax2.set_yticks(y, ["Permanent\nincreases", "Permanent\ndecreases"])
    ax2.set_ylim(-0.6, 1.6)
    ax2.set_xlabel("Event-study elasticity vs same item, other stores")
    _suptitle(
        fig,
        "Household is the least price-sensitive area; shoppers react far less to price increases than to cuts",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.06,
    )
    _save(
        fig,
        "07_price_elasticity",
        "Left: units ~ Poisson(log price) with item-store and store-week FE. Right: stacked diff-in-diff around 15,246 price changes. SEs clustered.",
    )


def comp_decline_drivers() -> None:
    d = pd.read_csv(OUTPUTS / "availability_decomposition.csv")
    d = d[d["level"] == "Total"]
    x = np.arange(len(d))
    fig, ax = _subplots(figsize=(8, 4.2), slot=HALF)
    ax.bar(x - 0.2, d["availability_pts"], 0.38, color=ORANGE, label="Availability (days on shelf)")
    ax.bar(x + 0.2, d["rate_of_sale_pts"], 0.38, color=BLUE, label="Sales per available day")
    ax.scatter(x, d["comp_growth"], color=INK, zorder=3, s=40, label="Comp growth (total)")
    for i, (v, a_, r_) in enumerate(zip(d["comp_growth"], d["availability_pts"], d["rate_of_sale_pts"])):
        # label clear of the bars: above the group when up, below it when down
        y = max(v, a_, r_, 0) + 0.006 if v >= 0 else min(v, a_, r_) - 0.006
        ax.text(i, y, _pct(v), ha="center", va="bottom" if v >= 0 else "top", color=INK, fontsize=_fs(9), fontweight="bold")
    ax.margins(y=0.12)
    ax.yaxis.set_major_locator(mtick.MultipleLocator(0.04 if DECK else 0.02))
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(x, [f"FY{y}" for y in d["fiscal_year"]])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2 if DECK else 3, handlelength=1, fontsize=_fs(9))
    _title(ax, "Why existing products shrank: mostly fewer sales per day on shelf, partly stock-outs")
    _save(
        fig,
        "09_comp_decline_drivers",
        "Comp store-items. Unavailable = likely stock-out or gap spells (seasonal gaps excluded). Reconciles exactly.",
    )


def stockouts() -> None:
    s = pd.read_csv(OUTPUTS / "stockout_summary.csv")
    t = s.groupby(["fiscal_year", "spell_class"])["lost_revenue"].sum().unstack()
    order = ["Store stock-out", "Store long gap", "Chain-wide gap", "Seasonal gap"]
    colors = [RED, ORANGE, "#eda100", GRAY]
    fig, ax = _subplots(figsize=(8, 4.2), slot=SIDE)
    bottom = np.zeros(len(t))
    for cls, c in zip(order, colors):
        ax.bar(range(len(t)), t[cls], 0.6, bottom=bottom, color=c, label=cls, edgecolor=PAPER if DECK else SURFACE, linewidth=1)
        bottom += t[cls].to_numpy()
    for i, (_fy, v) in enumerate(t["Store stock-out"].items()):
        ax.text(i, v / 2, f"${v / 1e6:.2f}M", ha="center", va="center", color="white", fontsize=_fs(8), fontweight="bold")
    ax.set_xticks(range(len(t)), [f"FY{y}" for y in t.index])
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_m))
    ax.legend(loc="upper left", handlelength=1, fontsize=_fs(9))
    _title(ax, "Revenue lost while products sat at zero sales: store stock-outs are ~$0.8M a year")
    _save(
        fig,
        "10_stockouts",
        "Zero-sale runs with <0.1% chance given the item's own sales history before and after. Seasonal gaps are intentional.",
    )


def price_event_dynamics() -> None:
    d = pd.read_csv(OUTPUTS / "price_event_dynamics.csv")
    d = d[d["kind"] == "permanent"].sort_values("rel_week")
    pre_mean = d.loc[d["rel_week"].between(-8, -2), "estimate"].mean()
    fig, ax = _subplots(figsize=(8, 4), slot=FULL)
    ax.fill_between(d["rel_week"], d["ci_low"] - pre_mean, d["ci_high"] - pre_mean, color=BLUE, alpha=0.15, lw=0)
    ax.plot(d["rel_week"], d["estimate"] - pre_mean, color=BLUE, lw=2, marker="o", markersize=4)
    ax.axvline(-0.5, color=INK2, lw=1)
    ax.axhline(0, color=AXIS, lw=1)
    ax.text(-0.3, ax.get_ylim()[1] * 0.85 if ax.get_ylim()[1] > 0 else 0.2, "price changes", color=INK2, fontsize=_fs(9))
    ax.set_xlabel("Weeks relative to permanent price change")
    ax.set_ylabel("Effect per unit of log price change")
    _title(ax, "Units shift immediately after a permanent price change and stay shifted")
    _save(
        fig,
        "11_price_event_study",
        "Treated store vs same item in stores with unchanged prices. Re-centered on weeks −8 to −2; note the dip in week −1.",
    )


def snap_timing() -> None:
    d = pd.read_csv(OUTPUTS / "snap_timing.csv")
    fig, axes = _subplots(1, 3, figsize=(12, 3.6), sharey=True, slot=FULL)
    for ax, st in zip(axes, ["CA", "TX", "WI"]):
        g = d[d["state_id"] == st]
        ax.bar(g["day_of_month"], g["foods_vs_household"], 0.8, color=[STATE_COLORS[st] if s else GRAY for s in g["snap_day"]])
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_title({"CA": "California", "TX": "Texas", "WI": "Wisconsin"}[st], fontsize=_fs(11), pad=8)
        ax.set_xticks([1, 10, 20, 31])
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    axes[0].set_ylabel("Food vs household spending")
    axes[0].legend(
        [plt.Rectangle((0, 0), 1, 1, color=STATE_COLORS["CA"]), plt.Rectangle((0, 0), 1, 1, color=GRAY)],
        ["SNAP benefit day", "Other days"],
        loc="lower left",
        handlelength=1,
        fontsize=_fs(9),
    )
    _suptitle(
        fig,
        "Food spending follows each state's SNAP calendar, then sags toward month-end (color = SNAP day)",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.08,
    )
    _save(fig, "12_snap_timing", "FOODS/HOUSEHOLD revenue ratio by day of month; store-month and store-weekday fixed effects.")


def synthetic_controls() -> None:
    p = pd.read_csv(OUTPUTS / "store_synthetic_paths.csv")
    s = pd.read_csv(OUTPUTS / "store_synthetic_control.csv").set_index("store_id")
    stores = list(s.index)
    fig, axes = _subplots(1, len(stores), figsize=(3.2 * len(stores), 3.4), sharey=True, slot=FULL)
    for ax, st in zip(axes, stores):
        g = p[p["store_id"] == st]
        ax.plot(g["weeks_from_break"], g["synthetic_index"], color=GRAY, lw=1.5, label="Synthetic twin")
        ax.plot(g["weeks_from_break"], g["actual_index"], color=BLUE, lw=1.5, label="Actual")
        ax.axvline(0, color=INK2, lw=1)
        ax.set_title(f"{st}: {_pct(s.loc[st, 'effect_vs_synthetic'], 0)}", fontsize=_fs(11), pad=8)
        ax.set_xlabel("Weeks from break")
    axes[0].set_ylabel("Revenue index (pre = 1)")
    axes[0].legend(loc="upper left", fontsize=_fs(8), handlelength=1)
    _suptitle(
        fig,
        "Four store step changes, each vs a synthetic twin built from stores without one",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.1,
    )
    _save(
        fig,
        "13_store_synthetic_controls",
        "Each effect larger than all 6 placebo stores (p = 1/7, the minimum possible with 6 donors).",
    )


def outlook() -> None:
    """Cumulative revenue: FY2016, FY2017 actual + forecast, and the naive run-rate the forecast beats."""
    w = pd.read_csv(OUTPUTS / "outlook_weekly.csv")
    f = pd.read_csv(OUTPUTS / "outlook_fy2017.csv")
    sel = f[f["selected"]].iloc[0]
    naive = f[f["method"] == "Chain run-rate"].iloc[0]
    last = w[w["fiscal_year"] == 2016].set_index("fiscal_week")["revenue"]
    act = w[(w["fiscal_year"] == 2017) & (w["kind"] == "actual")].set_index("fiscal_week")["revenue"]
    fc = w[(w["fiscal_year"] == 2017) & (w["kind"] == "forecast")].set_index("fiscal_week")["revenue"]
    cut = act.index.max()
    # naive chain run-rate: the rest of last year x chain YTD growth (as in outlook.py)
    growth = act.sum() / last.loc[:cut].sum()
    naive_path = act.sum() + (last.loc[cut + 1 :] * growth).cumsum()
    assert abs(naive_path.iloc[-1] - naive.fy2017_forecast) < 1, "naive path must match outlook_fy2017.csv"
    fc_path = act.sum() + fc.cumsum()
    m = 1e6
    fig, ax = _subplots(figsize=(9, 4), slot=SIDE)
    ax.plot(last.index, last.cumsum() / m, color=GRAY, lw=2)
    ax.plot(act.index, act.cumsum() / m, color=BLUE, lw=2.5)
    ax.plot([cut, *fc_path.index], [act.sum() / m, *(fc_path / m)], color=ORANGE, lw=2.5, ls=(0, (4, 2)))
    ax.plot([cut, *naive_path.index], [act.sum() / m, *(naive_path / m)], color=INK2, lw=1.5, ls=(0, (1, 2)))
    ax.plot([53.5, 53.5], [sel.range_low / m, sel.range_high / m], color=ORANGE, lw=3, solid_capstyle="butt")
    kw = {"fontsize": _fs(9), "color": INK, "va": "center"}
    ax.text(55, naive.fy2017_forecast / m + 0.25, f"${naive.fy2017_forecast / m:.1f}M naive run-rate", **{**kw, "va": "bottom"})
    ax.text(
        55,
        sel.fy2017_forecast / m - 0.25,
        f"${sel.fy2017_forecast / m:.1f}M forecast",
        **{**kw, "va": "top", "fontweight": "bold"},
    )
    ax.text(55, last.sum() / m, f"${last.sum() / m:.1f}M FY2016", **kw)
    ax.annotate(
        "FY2017 actual",
        (cut, act.sum() / m),
        xytext=(-6, 14),
        textcoords="offset points",
        ha="right",
        fontsize=_fs(9),
        color=INK,
    )
    ax.set_xlim(0, 76 if DECK else 72)
    ax.set_xticks([1, 13, 26, 39, 52])
    ax.set_ylim(0, naive.fy2017_forecast / m * 1.1)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:.0f}M"))
    ax.set_xlabel("Fiscal week (cumulative revenue)")
    _title(
        ax,
        f"FY2017 outlook: ${sel.fy2017_forecast / m:.1f}M ({sel.growth_vs_fy2016:+.1%}); "
        f"a naive run-rate would say ${naive.fy2017_forecast / m:.1f}M",
    )
    _save(
        fig,
        "14_fy2017_outlook",
        f"Store run-rate adjusted for step changes annualizing; backtest error {sel.mean_abs_full_year_error:.1%} (avg). "
        f"Orange bar = range ${sel.range_low / m:.1f}–{sel.range_high / m:.1f}M.",
    )


def weekly_trend() -> None:
    w = pd.read_csv(OUTPUTS / "weekly_revenue_store_category.csv", parse_dates=["week_start"])
    t = w.groupby(["week_start", "state_id"])["revenue"].sum().unstack()
    t = t[t.index >= "2011-02-05"]
    fig, ax = _subplots(figsize=(9, 4.2), slot=FULL)
    for st in ["CA", "TX", "WI"]:
        ax.plot(t.index, t[st], color=STATE_COLORS[st], lw=1.5)
        offset = {"CA": 0, "TX": -9000, "WI": 9000}[st]
        ax.text(
            t.index[-1] + pd.Timedelta(days=12),
            t[st].iloc[-8:].mean() + offset,
            st,
            color=INK,
            va="center",
            fontsize=_fs(9),
            fontweight="bold",
        )
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v / 1e3:,.0f}K"))
    _title(ax, "Weekly revenue by state: Wisconsin jumped in 2012 when two of its stores stepped up")
    _save(
        fig, "08_weekly_revenue_by_state", "Weekly revenue, full weeks only. Dips are Christmas weeks. Source: Walmart M5 data."
    )


def price_test_power() -> None:
    d = pd.read_csv(OUTPUTS / "price_test_power.csv")
    fig, axes = _subplots(1, 2, figsize=(11, 4), sharey=True, slot=FULL)
    names = {
        "Products: half of products treated in all stores": "Randomize products",
        "Product-stores: each product treated in a random half of stores": "Randomize product-store pairs",
    }
    for ax, (design, g) in zip(axes, sorted(d.groupby("design"), key=lambda kv: kv[0].startswith("Products"))):
        for p_, color in [(0.02, GRAY), (0.03, ORANGE), (0.05, BLUE)]:
            h = g[g["price_change"] == p_].sort_values("test_weeks")
            ax.fill_between(h["test_weeks"], h["power_ci_low"], h["power_ci_high"], color=color, alpha=0.15, lw=0)
            ax.plot(h["test_weeks"], h["power_detect_-0.4_vs_-1"], color=color, lw=2, marker="o", label=f"+{p_:.0%} price")
            if design.startswith("Product-stores") and p_ == 0.05:
                last = h.iloc[-1]
                ax.annotate(
                    f"{last['power_detect_-0.4_vs_-1']:.0%}",
                    (last["test_weeks"], last["power_detect_-0.4_vs_-1"]),
                    xytext=(-10, 10),
                    textcoords="offset points",
                    ha="right",
                    color=INK,
                    fontsize=_fs(11),
                    fontweight="bold",
                )
        ax.axhline(0.8, color=INK2, lw=1)
        ax.set_title(names[design], fontsize=_fs(11), pad=8)
        ax.set_xticks([4, 8, 12])
        ax.set_xlabel("Test length (weeks)")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    axes[0].set_ylabel("Power to tell −0.4 from −1")
    axes[1].text(12, 0.815, "80% target", color=INK2, fontsize=_fs(9), ha="right", va="bottom")
    axes[1].legend(loc="center right", fontsize=_fs(9), handlelength=1.5)
    _suptitle(
        fig,
        "A 5% Household test needs product-store randomization: 89% power at 12 weeks vs 25%",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.08,
    )
    _save(
        fig,
        "15_price_test_power",
        "Noise measured by 200 A/A simulations per design on real FY2015–16 Household sales; Poisson FE, SEs clustered by item.",
    )


def shelf_price_vs_cpi() -> None:
    d = pd.read_csv(OUTPUTS / "shelf_price_vs_cpi.csv")
    d = d[d["segment"] != "Total"]
    cats = ["FOODS", "HOUSEHOLD", "HOBBIES"]
    fig, axes = _subplots(1, 3, figsize=(12, 3.8), sharey=True, slot=FULL)
    for ax, cat in zip(axes, cats):
        g = d[d["segment"] == cat]
        x = np.arange(len(g))
        ax.bar(x - 0.19, g["cpi_inflation"], 0.36, color=GRAY, label="Market inflation (CPI)")
        ax.bar(x + 0.19, g["shelf_price_change"], 0.36, color=CAT_COLORS[cat], label="Walmart same-item prices")
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_xticks(x, [f"FY{y % 100}" for y in g["fiscal_year"]])
        short = {"FOODS": "CPI food at home", "HOUSEHOLD": "CPI household furn. & ops", "HOBBIES": "CPI recreation"}[cat]
        ax.set_title(f"{cat.title()} vs {short}", fontsize=_fs(10), pad=8)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=1))
    handles = [plt.Rectangle((0, 0), 1, 1, color=GRAY), plt.Rectangle((0, 0), 1, 1, color=BLUE)]
    fig.legend(
        handles,
        ["Market inflation (CPI)", "Walmart same-item prices (category color)"],
        loc="upper left",
        bbox_to_anchor=(0.01, 1.02),
        ncol=2,
        fontsize=_fs(9),
        handlelength=1,
        frameon=False,
    )
    _suptitle(
        fig,
        "Walmart held food prices 1.4–1.7 pts under food inflation in FY2014–15, yet volume still fell",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.12,
    )
    _save(
        fig,
        "16_shelf_price_vs_cpi",
        "CPI-U, U.S. city average (BLS), fiscal-year averages. Shelf prices: comparable store-items, Paasche index.",
    )


def _use_deck_style() -> None:
    """Slide versions: 1 slide px = 1 pt * 100/72, so 17pt text shows at about 24px."""
    global DECK, _SCALE
    DECK, _SCALE = True, 1.9
    # The deck's text face. Optional: put Inter TTFs (Google Fonts, OFL) in assets/fonts/.
    import logging

    from matplotlib import font_manager

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)  # Inter ships 600, used for bold

    for ttf in sorted((FIGURES.parent.parent / "assets" / "fonts").glob("*.ttf")):
        font_manager.fontManager.addfont(str(ttf))
    plt.rcParams.update(
        {
            "font.family": ["Inter", "Avenir Next", "Helvetica Neue", "Arial", "DejaVu Sans"],
            "font.size": 17,
            "axes.labelsize": 17,
            "xtick.labelsize": 17,
            "ytick.labelsize": 17,
            "legend.fontsize": 17,
            "axes.linewidth": 1.2,
            "grid.linewidth": 1,
            "lines.linewidth": 3,
        }
    )
    (FIGURES / "deck").mkdir(parents=True, exist_ok=True)


def segment_shares() -> None:
    p = pd.read_csv(OUTPUTS / "segment_profile.csv")
    p["stockout_share"] = p["stockout_lost"] / p["stockout_lost"].sum()
    p = p.iloc[::-1].reset_index(drop=True)  # largest revenue on top
    fig, ax = _subplots(figsize=(8, 4.4), slot=SEG)
    y = np.arange(len(p))
    h = 0.26
    bars = [
        ("product_share", GRAY, "Share of products"),
        ("revenue_share", BLUE, "Share of revenue"),
        ("stockout_share", ORANGE, "Share of store stock-out losses"),
    ]
    for j, (col, color, label) in enumerate(bars):
        yy = y + (1 - j) * (h + 0.02)
        ax.barh(yy, p[col], h, color=color, label=label)
        for yi, v in zip(yy, p[col]):
            ax.text(v + 0.006, yi, f"{v:.0%}", va="center", color=INK, fontsize=_fs(8))
    ax.set_yticks(y, p["segment"])
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.set_xlim(0, p[[b[0] for b in bars]].to_numpy().max() * 1.15)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", handlelength=1, fontsize=_fs(9))
    _title(ax, "Five product segments: SNAP staples are 14% of products but 41% of stock-out losses")
    _save(
        fig,
        "17_product_segments",
        "k-means on five FY2016 sales behaviours per product (speed, gaps, seasonality, SNAP lift, stock-outs).",
    )


def forecast_benchmark() -> None:
    b = pd.read_csv(OUTPUTS / "forecast_benchmark_summary.csv").sort_values("mean_wrmsse", ascending=False)
    fig, ax = _subplots(figsize=(8, 3.8), slot=FULL)
    y = np.arange(len(b))
    best = b["mean_wrmsse"].idxmin()
    colors = [BLUE if i == best else GRAY for i in b.index]
    ax.barh(y, b["mean_wrmsse"], 0.6, color=colors)
    ax.errorbar(
        b["mean_wrmsse"],
        y,
        xerr=[b["mean_wrmsse"] - b["best_window"], b["worst_window"] - b["mean_wrmsse"]],
        fmt="none",
        ecolor=INK2,
        elinewidth=1,
        capsize=3,
    )
    for yi, v in zip(y, b["mean_wrmsse"]):
        ax.text(v + 0.03, yi + 0.22, f"{v:.2f}", color=INK, fontsize=_fs(9), va="bottom")
    ax.set_yticks(y, b["method"])
    ax.set_xlabel("WRMSSE, M5 competition metric (lower is better; bars span best and worst window)")
    ax.grid(axis="y", visible=False)
    gain = 1 - b["mean_wrmsse"].min() / b.set_index("method").loc["Seasonal naive (last week)", "mean_wrmsse"]
    _title(ax, f"The calendar-aware forecast is {gain:.0%} more accurate than seasonal naive across 6 windows")
    _save(fig, "18_forecast_benchmark", "28-day forecasts of 70 store x department series, scored on M5 levels 1-9.")


def launch_model() -> None:
    s = pd.read_csv(OUTPUTS / "launch_model_scores.csv")
    base = s["base_rate"].iloc[0]
    labels = ["Pick at random", "Rule: week-4 revenue\nper store-week", "Logistic regression\n(all week-4 signals)"]
    vals = [base, *s["precision_top20"]]
    lo = [np.nan, *s["p20_ci_low"]]
    hi = [np.nan, *s["p20_ci_high"]]
    fig, ax = _subplots(figsize=(8, 3.8), slot=SIDE)
    x = np.arange(3)
    ax.bar(x, vals, 0.55, color=[GRAY, BLUE, ORANGE])
    ax.errorbar(
        x[1:],
        vals[1:],
        yerr=[np.subtract(vals[1:], lo[1:]), np.subtract(hi[1:], vals[1:])],
        fmt="none",
        ecolor=INK2,
        elinewidth=1,
        capsize=4,
    )
    for xi, v in zip(x, vals):
        ax.text(xi, v / 2, f"{v:.0%}", ha="center", va="center", color="white", fontsize=_fs(11), fontweight="bold")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.set_ylabel("Top-20% picks that became top sellers")
    ax.grid(axis="x", visible=False)
    _title(ax, f"Week-4 revenue alone picks future top sellers {vals[1] / base:.1f}x better than chance")
    _save(
        fig,
        "19_launch_success",
        "Later 30% of launches (test set); top seller = top quarter of revenue per store-week in weeks 13-52.",
    )


def stockout_policy() -> None:
    d = pd.read_csv(OUTPUTS / "stockout_policy_simulation.csv")
    fig, axes = _subplots(1, 2, figsize=(11, 4), slot=FULL)
    for ax, seg, title in [
        (axes[0], "All", "All simulated products"),
        (axes[1], "SNAP-driven staples", "SNAP-driven staples"),
    ]:
        g = d[d["segment"] == seg]
        for pol, color, marker in [("Flat forecast (current)", GRAY, "o"), ("SNAP-aware for staples", BLUE, "s")]:
            h = g[g["policy"] == pol].sort_values("avg_inventory_value")
            ax.plot(h["avg_inventory_value"] / 1e3, h["lost_revenue"] / 1e3, color=color, marker=marker, lw=2, label=pol)
        base = g[(g["policy"] == "Flat forecast (current)") & (g["z_increase"] == 0)].iloc[0]
        ax.annotate(
            "today (calibrated)",
            (base["avg_inventory_value"] / 1e3, base["lost_revenue"] / 1e3),
            xytext=(8, 6),
            textcoords="offset points",
            fontsize=_fs(8),
            color=INK2,
        )
        ax.set_title(title, fontsize=_fs(11), pad=8)
        ax.set_xlabel("Average inventory on hand ($K, at shelf price)")
        ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:,.0f}K"))
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:,.0f}K"))
    axes[0].set_ylabel("Revenue lost to stock-outs, FY2016")
    axes[1].legend(loc="upper right", fontsize=_fs(9), handlelength=1.5)
    _suptitle(
        fig,
        "More safety stock recovers about a quarter of losses; SNAP-aware ordering helps staples at no extra stock",
        x=0.01,
        ha="left",
        fontweight="bold",
        fontsize=_fs(12),
        y=1.08,
    )
    _save(
        fig,
        "20_stockout_policy",
        "Simulated weekly ordering, 3-day lead time, calibrated to measured FY2016 losses. Points: safety stock +0 to +1 SD.",
    )


def main() -> None:
    plt.switch_backend("Agg")
    FIGURES.mkdir(parents=True, exist_ok=True)
    if "--deck" in sys.argv[1:]:
        _use_deck_style()
    for f in (
        growth_vs_comp,
        bridge_waterfall,
        pareto,
        store_growth,
        snap,
        events,
        elasticity,
        weekly_trend,
        comp_decline_drivers,
        stockouts,
        price_event_dynamics,
        snap_timing,
        synthetic_controls,
        outlook,
        price_test_power,
        shelf_price_vs_cpi,
        segment_shares,
        forecast_benchmark,
        launch_model,
        stockout_policy,
    ):
        f()


if __name__ == "__main__":
    main()
