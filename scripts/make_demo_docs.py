"""生成单证核对的演示单据（全部为虚构数据）。

    python scripts/make_demo_docs.py            # 生成 demo/docs/ 下 4 份单据，故意埋了 3 处错误
    python scripts/make_demo_docs.py --clean    # 生成 4 份完全一致的单据（用来对比“没有问题”的效果）

埋的错误：
1. 装箱单：DS-450 数量写成 1,020（其他单据都是 1,200）
2. 报关资料：毛重写成 2,416 KG，比净重 2,466 还小（装箱单是 2,616）
3. 报关资料：HG-304A 的 HS 编码少了一位（830210000）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
NAVY = colors.HexColor("#1F3A5F")
LIGHT = colors.HexColor("#EEF2F7")

SELLER = "Demo Hardware Co., Ltd."
SELLER_ADDR = "No. 88 Demo Road, Ningbo, China"
BUYER = "Nordbau Demo GmbH"
BUYER_ADDR = "Musterstrasse 12, 20095 Hamburg, Germany"
INV = "NB-2611-018"
PI_NO = "PI-2611-018"
DATE = "2026-11-18"

# model, desc, hs, qty, unit, price, per_ctn, nw/ctn, gw/ctn, cbm/ctn
ITEMS = [
    ("DS-450", "Ball Bearing Drawer Slide 450mm", "8302420000", 1200, "PAIRS", 2.35, 10, 14.2, 15.0, 0.032),
    ("HG-304A", "Stainless Steel Door Hinge 4\"", "8302100000", 6000, "PCS", 0.86, 100, 9.5, 10.1, 0.018),
    ("PH-128", "Aluminum Cabinet Handle 128mm", "8302420000", 6000, "PCS", 0.55, 200, 6.4, 7.0, 0.020),
]


def money(v: float) -> str:
    return f"{v:,.2f}"


def num(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def pdf(path: Path, title: str, head_left: list[str], head_right: list[str], header: list[str], rows: list[list[str]],
        total: list[str], foot: list[str], widths: list[float]):
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12)
    h1 = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY)
    story = [Paragraph(f"<b>{SELLER}</b>", ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=11, leading=14)),
             Paragraph(SELLER_ADDR, st), Spacer(1, 8), Paragraph(title, h1), Spacer(1, 8)]
    info = Table([[Paragraph("<br/>".join(head_left), st), Paragraph("<br/>".join(head_right), st)]],
                 colWidths=[95 * mm, 85 * mm])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [info, Spacer(1, 10)]
    t = Table([header] + rows + [total], colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C2D0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
    ]))
    story += [t, Spacer(1, 12)] + [Paragraph(x, st) for x in foot]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                      bottomMargin=14 * mm, title=title).build(story)


def xlsx(path: Path, title: str, kv: list[tuple[str, str]], header: list[str], rows: list[list], total: list):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    thin = Side(style="thin", color="B8C2D0")
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    ws.append([])
    for k, v in kv:
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    ws.append(header)
    hr = ws.max_row
    for c in ws[hr]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows + [total]:
        ws.append(r)
    for row in ws.iter_rows(min_row=hr, max_row=ws.max_row):
        for c in row:
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="EEF2F7")
    widths = [10, 16, 14, 34, 12, 12, 12, 12, 12, 12]
    for i, w in enumerate(widths[:len(header)]):
        ws.column_dimensions[chr(65 + i)].width = w
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="不埋错误")
    ap.add_argument("--out", default=str(ROOT / "demo" / "docs"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bad = not args.clean

    tot_qty = sum(i[3] for i in ITEMS)
    tot_amt = sum(i[3] * i[5] for i in ITEMS)
    ctns = [i[3] // i[6] for i in ITEMS]
    nws = [c * i[7] for c, i in zip(ctns, ITEMS)]
    gws = [c * i[8] for c, i in zip(ctns, ITEMS)]
    cbms = [round(c * i[9], 2) for c, i in zip(ctns, ITEMS)]

    # 1. PI
    pdf(out / f"PI_{INV}.pdf", "PROFORMA INVOICE",
        [f"<b>Buyer:</b> {BUYER}", BUYER_ADDR],
        [f"<b>PI No.:</b> {PI_NO}", f"<b>Date:</b> {DATE}", "<b>Trade Term:</b> FOB Ningbo", "<b>Currency:</b> USD"],
        ["No.", "Model", "Description", "Quantity", "Unit", "Unit Price (USD)", "Amount (USD)"],
        [[str(n), i[0], i[1], num(i[3]), i[4], money(i[5]), money(i[3] * i[5])] for n, i in enumerate(ITEMS, 1)],
        ["TOTAL", "", "", num(tot_qty), "", "", money(tot_amt)],
        ["Payment: 30% T/T deposit, 70% balance against copy of B/L.", "Lead time: 30 days after deposit.",
         "Demo data for illustration only."],
        [12, 22, 56, 20, 14, 26, 30])

    # 2. 商业发票
    pdf(out / f"CI_{INV}.pdf", "COMMERCIAL INVOICE",
        [f"<b>Consignee:</b> {BUYER}", BUYER_ADDR],
        [f"<b>Invoice No.:</b> {INV}", f"<b>Date:</b> {DATE}", "<b>Trade Term:</b> FOB Ningbo",
         "<b>Currency:</b> USD", "<b>From:</b> Ningbo, China  <b>To:</b> Hamburg, Germany"],
        ["No.", "Model", "Description", "HS Code", "Quantity", "Unit Price (USD)", "Amount (USD)"],
        [[str(n), i[0], i[1], i[2], num(i[3]), money(i[5]), money(i[3] * i[5])] for n, i in enumerate(ITEMS, 1)],
        ["TOTAL", "", "", "", num(tot_qty), "", money(tot_amt)],
        ["Country of origin: China.", "Demo data for illustration only."],
        [12, 20, 52, 22, 18, 26, 30])

    # 3. 装箱单（Excel）
    pl_rows = []
    for n, (i, c, nw, gw, cbm) in enumerate(zip(ITEMS, ctns, nws, gws, cbms), 1):
        qty = 1020 if (bad and i[0] == "DS-450") else i[3]
        pl_rows.append([n, i[0], i[1], i[6], c, qty, nw, gw, cbm])
    xlsx(out / f"PL_{INV}.xlsx", "PACKING LIST",
         [("Invoice No", INV), ("Consignee", BUYER), ("Date", DATE), ("Shipping Marks", "NORDBAU / HAMBURG / C/NO. 1-210")],
         ["No.", "Model", "Description", "PCS/CTN", "CTNS", "Qty (PCS)", "N.W. (KG)", "G.W. (KG)", "CBM"],
         pl_rows, ["TOTAL", "", "", "", sum(ctns), "", sum(nws), sum(gws), round(sum(cbms), 2)])

    # 4. 报关资料（Excel，报关单草稿）
    gw_total = 2416 if bad else sum(gws)
    cd_rows = []
    for n, i in enumerate(ITEMS, 1):
        hs = "830210000" if (bad and i[0] == "HG-304A") else i[2]
        cd_rows.append([n, hs, i[0], i[1], i[3], "个" if i[4] == "PCS" else "对", i[5], round(i[3] * i[5], 2)])
    xlsx(out / f"报关资料_{INV}.xlsx", "出口报关资料（报关单草稿）",
         [("境外收货人", BUYER), ("合同协议号", INV), ("成交方式", "FOB"), ("币制", "USD"),
          ("运抵国", "德国"), ("指运港", "汉堡"), ("件数", str(sum(ctns))), ("毛重(千克)", num(gw_total)),
          ("净重(千克)", num(sum(nws)))],
         ["项号", "商品编号", "货号", "商品名称", "数量", "单位", "单价", "总价"],
         cd_rows, ["合计", "", "", "", tot_qty, "", "", round(tot_amt, 2)])

    print(f"已生成 4 份{'（含 3 处错误）' if bad else '（完全一致）'}：{out}")


if __name__ == "__main__":
    sys.exit(main())
