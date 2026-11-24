"""Build the interactive case study: one self-contained HTML page, generated from outputs/*.csv.

python -m retailrev.site     # -> site/index.html (open it in any browser; no server needed)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from retailrev.paths import OUTPUTS, ROOT

OUT = ROOT / "site" / "index.html"
TEMPLATE = Path(__file__).with_name("site_template.html")
PARTS = {
    "volume_effect": "Existing products: volume",
    "mix_effect": "Existing products: mix",
    "price_effect": "Existing products: price",
    "launch_annualization_effect": "Last year's launches, full year",
    "new_listings_effect": "New listings",
    "lost_listings_effect": "Lost listings",
}


def page_data() -> dict:
    comp = pd.read_csv(OUTPUTS / "comp_sales.csv")
    br = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    seg = pd.read_csv(OUTPUTS / "segment_profile.csv")
    el = pd.read_csv(OUTPUTS / "price_elasticity.csv")
    ann = pd.read_csv(OUTPUTS / "annual_revenue.csv").set_index("fiscal_year").revenue_52wk
    seg["stockout_share"] = seg.stockout_lost / seg.stockout_lost.sum()
    hh = br[(br.fiscal_year == 2016) & (br.level == "Category") & (br.segment == "HOUSEHOLD")].iloc[0]
    main = el[(el.spec == "Poisson, all item-stores") & el.dept_id.str.startswith("HOUSEHOLD")]
    total = br[br.level == "Total"].sort_values("fiscal_year")
    return {
        "growth": comp.rename(columns={"total_growth_52wk": "total", "comp_growth": "comp"})[
            ["fiscal_year", "total", "comp"]
        ].to_dict("records"),
        "bridge": [
            {
                "year": int(b.fiscal_year),
                "prior": float(b.revenue_prior),
                "current": float(b.revenue_current),
                "parts": [{"name": n, "v": float(b[c])} for c, n in PARTS.items()],
            }
            for _, b in total.iterrows()
        ],
        "segments": seg[["segment", "product_share", "revenue_share", "stockout_share", "playbook"]].to_dict("records"),
        "alert": pd.read_csv(OUTPUTS / "alert_validation.csv").round(4).to_dict("records"),
        "matched": pd.read_csv(OUTPUTS / "alert_validation_matched.csv").round(4).to_dict("records"),
        "household": float(hh.revenue_current),
        "elasticity": round(float(main.elasticity.mean()), 2),
        "growth_total": float(ann[2016] / ann[2012] - 1),
    }


def build() -> None:
    d = page_data()
    html = TEMPLATE.read_text(encoding="utf-8")
    html = (
        html.replace("__GROWTH__", f"{d['growth_total']:.0%}")
        .replace("__ELASTTXT__", f"{d['elasticity']:.2f}".replace("-", "\u2212"))
        .replace("__ELAST__", f"{d['elasticity']:.2f}")
    )
    html = html.replace("__DATA__", json.dumps(d).replace("</", "<\\/"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"  wrote site/index.html ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
