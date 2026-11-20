"""Excel workbook: a live price-test ROI model, the product segments and comparable sales.

    python -m retailrev.excel     # -> reports/walmart_price_test_and_segments.xlsx

Every derived number is an Excel formula, so the model recalculates when an input changes.
Inputs are blue; key assumptions have a yellow fill; each hardcoded number says where it
came from. Data values are copied from outputs/ at build time.
"""

from __future__ import annotations

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from retailrev.paths import OUTPUTS, ROOT

OUT = ROOT / "reports" / "walmart_price_test_and_segments.xlsx"
FONT = "Arial"
BLUE_IN = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT, color="000000")
BOLD = Font(name=FONT, bold=True)
TITLE = Font(name=FONT, bold=True, size=14)
NOTE = Font(name=FONT, italic=True, color="595959", size=9)
HEAD = Font(name=FONT, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F63B8")
KEY_FILL = PatternFill("solid", fgColor="FFFF00")
TOTAL_TOP = Border(top=Side(style="thin", color="000000"))
MONEY = '$#,##0;($#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
PCT_SIGNED = '+0.0%;-0.0%;"-"'
MONEY_SIGNED = '+$#,##0;-$#,##0;"-"'


def _cell(ws, ref, value, font=BLACK, fmt=None, fill=None, note=None, align=None):
    c = ws[ref]
    c.value = value
    c.font = font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if note:
        c.comment = Comment(note, "retailrev")
    if align:
        c.alignment = Alignment(horizontal=align)
    return c


def _header(ws, row, labels, start_col=1):
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=label)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def read_me(wb):
    ws = wb.active
    ws.title = "Read me"
    _widths(ws, [110])
    rows = [
        ("Walmart Revenue Review: price test and segments workbook", TITLE),
        ("Companion to github.com/MaxListon/walmart-revenue-analytics. Data: Walmart M5 competition, FY2016.", BLACK),
        ("", BLACK),
        ("Sheets", BOLD),
        ("Price test ROI: what a Household price rise is worth at different price-sensitivity levels (live model).", BLACK),
        ("Segments: the five product segments, their shares, and how much stock-out loss is realistically recoverable.", BLACK),
        ("Comparable sales: total vs like-for-like growth by fiscal year, calculated from the underlying revenue.", BLACK),
        ("", BLACK),
        ("How to use it", BOLD),
        ("Blue text = an input you can change. Yellow fill = a key assumption. Black text = a formula; don't overwrite.", BLACK),
        ("Example: on 'Price test ROI', change the price-change cell from 5% to 3% and every result updates.", BLACK),
        ("", BLACK),
        (
            "Price elasticity = % change in units for a 1% change in price. Above −1 (e.g. −0.4), a price rise raises revenue.",
            BLACK,
        ),
        ("Hover over a cell with a red corner for its source or assumption.", BLACK),
    ]
    for i, (text, font) in enumerate(rows, start=1):
        _cell(ws, f"A{i}", text, font)
    _cell(ws, "A16", "Blue input", BLUE_IN)
    _cell(ws, "A17", "Key assumption", BLUE_IN, fill=KEY_FILL)
    _cell(ws, "A18", "Formula", BLACK)


def price_test(wb):
    ws = wb.create_sheet("Price test ROI")
    _widths(ws, [44, 16, 16, 16, 16, 16, 16, 4, 60])
    hh = pd.read_csv(OUTPUTS / "revenue_bridge.csv")
    hh = hh[(hh.fiscal_year == 2016) & (hh.level == "Category") & (hh.segment == "HOUSEHOLD")].iloc[0]
    el = pd.read_csv(OUTPUTS / "price_elasticity.csv")
    main = el[(el.spec == "Poisson, all item-stores") & el.dept_id.str.startswith("HOUSEHOLD")]

    _cell(ws, "A1", "Household price increase: what is it worth?", TITLE)
    _cell(ws, "A2", "Change the blue inputs; everything else recalculates.", NOTE)
    _cell(ws, "A4", "Inputs", BOLD)
    _cell(ws, "A5", "Household revenue, FY2016 ($)")
    _cell(
        ws,
        "B5",
        round(float(hh.revenue_current), 2),
        BLUE_IN,
        MONEY,
        note="outputs/revenue_bridge.csv, FY2016, level=Category, segment=HOUSEHOLD (52-week basis).",
    )
    _cell(ws, "A6", "Price change")
    _cell(ws, "B6", 0.05, BLUE_IN, PCT, note="The recommended test size (docs/price_test_brief.md).")
    _cell(ws, "A7", "Price elasticity (central case)")
    _cell(
        ws,
        "B7",
        round(float(main.elasticity.mean()), 2),
        BLUE_IN,
        "0.00",
        KEY_FILL,
        note="Mean of HOUSEHOLD_1 and HOUSEHOLD_2, main Poisson model (outputs/price_elasticity.csv). "
        "Robustness checks are noisier: that is why the test exists.",
    )
    _cell(ws, "A8", "Gross margin before the change")
    _cell(
        ws,
        "B8",
        0.246,
        BLUE_IN,
        PCT,
        KEY_FILL,
        note="Assumption: Walmart's consolidated gross profit rate, about 24.6% in FY2016 (Walmart 10-K). "
        "The M5 data has no costs; replace with the category's real margin.",
    )

    _cell(ws, "A10", "Results (central case)", BOLD)
    rows = [
        ("Change in units", "=(1+B6)^B7-1", PCT_SIGNED),
        ("Change in revenue (%)", "=(1+B6)^(1+B7)-1", PCT_SIGNED),
        ("Change in revenue ($ a year)", "=B5*B12", MONEY_SIGNED),
        ("Change in gross profit ($ a year)", "=B5*((1+B6)^(1+B7)-(1-B8)*(1+B6)^B7-B8)", MONEY_SIGNED),
        ("Break-even elasticity for revenue", "=-1", "0.00"),
        # profit change = 0  ->  (1+p)^e (1+p-(1-m)) = m  ->  e = ln(m/(p+m)) / ln(1+p)
        ("Break-even elasticity for gross profit", "=LN(B8/(B6+B8))/LN(1+B6)", "0.00"),
    ]
    for i, (label, f, fmt) in enumerate(rows, start=11):
        _cell(ws, f"A{i}", label)
        _cell(ws, f"B{i}", f, BLACK, fmt)
    _cell(ws, "I15", "A price rise raises revenue whenever elasticity is above −1.", NOTE)
    _cell(ws, "I16", "Gross profit rises even at more negative elasticities, because cost falls with units.", NOTE)

    _cell(ws, "A18", "Scenarios", BOLD)
    _header(ws, 19, ["Scenario", "Elasticity", "Units", "Revenue %", "Revenue $", "Gross profit $"])
    scen = [
        ("Optimistic (fast-mover check)", -0.2),
        ("Central (main model)", "=B7"),
        ("Pessimistic: break-even", -1.0),
        ("Event study, HOUSEHOLD_1 alone", -1.6),
    ]
    for i, (name, e) in enumerate(scen, start=20):
        _cell(ws, f"A{i}", name)
        _cell(
            ws,
            f"B{i}",
            e,
            BLUE_IN if not isinstance(e, str) else BLACK,
            "0.00",
            note=None if isinstance(e, str) else "Illustrative elasticity from the project's robustness checks.",
        )
        _cell(ws, f"C{i}", f"=(1+$B$6)^B{i}-1", BLACK, PCT_SIGNED)
        _cell(ws, f"D{i}", f"=(1+$B$6)^(1+B{i})-1", BLACK, PCT_SIGNED)
        _cell(ws, f"E{i}", f"=$B$5*D{i}", BLACK, MONEY_SIGNED)
        _cell(ws, f"F{i}", f"=$B$5*((1+$B$6)^(1+B{i})-(1-$B$8)*(1+$B$6)^B{i}-$B$8)", BLACK, MONEY_SIGNED)

    _cell(ws, "A25", "Sensitivity: change in revenue ($ a year)", BOLD)
    _cell(ws, "A26", "Elasticity ↓   Price change →", NOTE)
    prices = [0.02, 0.03, 0.05, 0.075, 0.10]
    elasticities = [-0.2, -0.4, -0.6, -0.8, -1.0, -1.2, -1.6]
    for j, pch in enumerate(prices):
        _cell(ws, f"{get_column_letter(2 + j)}26", pch, BLUE_IN, PCT, align="center")
    for i, e in enumerate(elasticities, start=27):
        _cell(ws, f"A{i}", e, BLUE_IN, "0.00", align="center")
        for j in range(len(prices)):
            col = get_column_letter(2 + j)
            _cell(ws, f"{col}{i}", f"=$B$5*((1+{col}$26)^(1+$A{i})-1)", BLACK, MONEY_SIGNED)

    _cell(ws, "A35", "Sensitivity: change in gross profit ($ a year)", BOLD)
    _cell(ws, "A36", "Elasticity ↓   Price change →", NOTE)
    for j in range(len(prices)):
        _cell(ws, f"{get_column_letter(2 + j)}36", f"={get_column_letter(2 + j)}26", BLACK, PCT, align="center")
    for i in range(37, 37 + len(elasticities)):
        _cell(ws, f"A{i}", f"=A{i - 10}", BLACK, "0.00", align="center")
        for j in range(len(prices)):
            col = get_column_letter(2 + j)
            _cell(
                ws,
                f"{col}{i}",
                f"=$B$5*((1+{col}$36)^(1+$A{i})-(1-$B$8)*(1+{col}$36)^$A{i}-$B$8)",
                BLACK,
                MONEY_SIGNED,
            )
    _cell(
        ws,
        "A45",
        "Formulas: units × (1+p)^e; revenue × (1+p)^(1+e); gross profit = revenue − cost, with cost "
        "proportional to units. Constant elasticity; ignores shoppers switching to other categories.",
        NOTE,
    )
    ws.freeze_panes = "A4"


def segments(wb):
    ws = wb.create_sheet("Segments")
    _widths(ws, [24, 11, 14, 16, 13, 13, 15, 15, 16, 62])
    p = pd.read_csv(OUTPUTS / "segment_profile.csv")
    sim = pd.read_csv(OUTPUTS / "stockout_policy_simulation.csv")
    rec = sim[(sim.segment == "All") & (sim.policy == "Flat forecast (current)") & (sim.z_increase == 0.5)].iloc[0]

    _cell(ws, "A1", "Five product segments", TITLE)
    _cell(
        ws,
        "A2",
        "FY2016. Products grouped by how they sell (k-means on five sales behaviours). Source: outputs/segment_profile.csv.",
        NOTE,
    )
    _cell(ws, "A4", "Recoverable share of stock-out loss")
    _cell(
        ws,
        "C4",
        round(float(rec.share_of_loss_recovered), 3),
        BLUE_IN,
        PCT,
        KEY_FILL,
        note="From the ordering simulation (outputs/stockout_policy_simulation.csv): a +0.5 SD safety-stock "
        "rise recovers this share of losses. An estimate from a model, not a measurement.",
    )
    cols = [
        "Segment",
        "Products",
        "Revenue ($)",
        "Stock-out loss ($)",
        "Share of products",
        "Share of revenue",
        "Share of stock-out loss",
        "Loss as % of revenue",
        "Recoverable ($ a year)",
        "Playbook",
    ]
    _header(ws, 6, cols)
    first, last = 7, 7 + len(p) - 1
    for r, row in enumerate(p.itertuples(), start=first):
        _cell(ws, f"A{r}", row.segment)
        _cell(ws, f"B{r}", int(row.products), BLUE_IN, "#,##0")
        _cell(ws, f"C{r}", round(float(row.revenue), 2), BLUE_IN, MONEY)
        _cell(ws, f"D{r}", round(float(row.stockout_lost), 2), BLUE_IN, MONEY)
        _cell(ws, f"E{r}", f"=B{r}/B${last + 1}", BLACK, PCT)
        _cell(ws, f"F{r}", f"=C{r}/C${last + 1}", BLACK, PCT)
        _cell(ws, f"G{r}", f"=D{r}/D${last + 1}", BLACK, PCT)
        _cell(ws, f"H{r}", f"=IFERROR(D{r}/C{r},0)", BLACK, PCT)
        _cell(ws, f"I{r}", f"=D{r}*$C$4", BLACK, MONEY)
        _cell(ws, f"J{r}", row.playbook)
    t = last + 1
    _cell(ws, f"A{t}", "Total", BOLD)
    for col, fmt in [("B", "#,##0"), ("C", MONEY), ("D", MONEY), ("E", PCT), ("F", PCT), ("G", PCT), ("I", MONEY)]:
        _cell(ws, f"{col}{t}", f"=SUM({col}{first}:{col}{last})", BOLD, fmt)
    _cell(ws, f"H{t}", f"=IFERROR(D{t}/C{t},0)", BOLD, PCT)
    for col in "ABCDEFGHI":
        ws[f"{col}{t}"].border = TOTAL_TOP
    _cell(
        ws,
        f"A{t + 2}",
        "Store stock-out losses here cover the 3,046 products with FY2016 sales; they total the headline $0.79M.",
        NOTE,
    )
    ws.freeze_panes = "B7"


def comparable(wb):
    ws = wb.create_sheet("Comparable sales")
    _widths(ws, [14, 18, 18, 16, 18, 18, 16, 16])
    a = pd.read_csv(OUTPUTS / "annual_revenue.csv").set_index("fiscal_year")
    c = pd.read_csv(OUTPUTS / "comp_sales.csv").set_index("fiscal_year")
    _cell(ws, "A1", "Total vs comparable sales growth", TITLE)
    _cell(
        ws,
        "A2",
        "52-week basis. Comparable = store-items listed in all 52 weeks of both years. Sources: "
        "outputs/annual_revenue.csv, outputs/comp_sales.csv.",
        NOTE,
    )
    _header(
        ws,
        4,
        [
            "Fiscal year",
            "Total revenue ($)",
            "Comparable revenue, prior year ($)",
            "Comparable revenue, this year ($)",
            "Total growth",
            "Comparable growth",
            "Growth gap (points)",
            "Comparable share of revenue",
        ],
    )
    years = list(range(2012, 2017))
    for r, fy in enumerate(years, start=5):
        _cell(ws, f"A{r}", str(fy), BLACK, align="center")
        _cell(ws, f"B{r}", round(float(a.loc[fy, "revenue_52wk"]), 2), BLUE_IN, MONEY)
        if fy in c.index:
            _cell(ws, f"C{r}", round(float(c.loc[fy, "comp_revenue_prior"]), 2), BLUE_IN, MONEY)
            _cell(ws, f"D{r}", round(float(c.loc[fy, "comp_revenue_current"]), 2), BLUE_IN, MONEY)
            _cell(ws, f"E{r}", f"=B{r}/B{r - 1}-1", BLACK, PCT_SIGNED)
            _cell(ws, f"F{r}", f"=D{r}/C{r}-1", BLACK, PCT_SIGNED)
            _cell(ws, f"G{r}", f"=(E{r}-F{r})*100", BLACK, "0.0")
            _cell(ws, f"H{r}", f"=D{r}/B{r}", BLACK, PCT)
    _cell(ws, "A11", "Growth gap = growth from adding products rather than from existing products selling more.", NOTE)
    _cell(ws, "A12", "Four-year total growth, FY2012 → FY2016")
    _cell(ws, "E12", "=B9/B5-1", BOLD, PCT_SIGNED)
    ws.freeze_panes = "B5"


def build() -> None:
    wb = Workbook()
    read_me(wb)
    price_test(wb)
    segments(wb)
    comparable(wb)
    wb.calculation = CalcProperties(fullCalcOnLoad=True)  # Excel computes every formula on open
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"  wrote {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}")


if __name__ == "__main__":
    build()
