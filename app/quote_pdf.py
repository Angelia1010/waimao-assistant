"""生成英文 PDF 报价单（reportlab，不依赖外部服务）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = colors.HexColor("#1F3A5F")
LIGHT = colors.HexColor("#EEF2F7")
MUTED = colors.HexColor("#5B6573")

try:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    CJK_FONT = "STSong-Light"
except Exception:  # pragma: no cover
    CJK_FONT = "Helvetica"


@dataclass
class QuoteItem:
    model: str
    name: str
    description: str
    qty: float
    unit_price: float
    lead_days: int = 0
    packing: str = ""
    note: str = ""

    @property
    def amount(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass
class QuoteData:
    quote_no: str
    date: str
    valid_until: str
    customer_company: str
    customer_contact: str = ""
    customer_email: str = ""
    customer_country: str = ""
    currency: str = "USD"
    incoterm: str = "FOB"
    payment_terms: str = ""
    items: list[QuoteItem] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(i.amount for i in self.items), 2)

    @property
    def lead_time(self) -> str:
        days = [i.lead_days for i in self.items if i.lead_days]
        return f"{max(days)} days after deposit" if days else "To be confirmed"


@dataclass
class Seller:
    name_en: str
    name_cn: str = ""
    address: str = ""
    contact: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    logo_path: str = ""
    bank_info: str = ""


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[一-鿿]", s or ""))


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    if _has_cjk(text):
        style = ParagraphStyle(style.name + "-cjk", parent=style, fontName=CJK_FONT)
    return Paragraph(text, style)


def money(v: float) -> str:
    return f"{v:,.2f}"


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "", s or "").strip().replace(" ", "_")
    return s[:60] or "Customer"


def quote_filename(q: QuoteData) -> str:
    first_model = q.items[0].model if q.items else "Items"
    return f"{safe_filename(q.customer_company)}_{safe_filename(first_model)}_Quotation_{q.date.replace('-', '')}.pdf"


def render_quote(q: QuoteData, seller: Seller, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / quote_filename(q)

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.black)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10.5, textColor=MUTED)
    h_company = ParagraphStyle("hc", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=ACCENT)
    h_title = ParagraphStyle("ht", parent=base, fontName="Helvetica-Bold", fontSize=22, leading=26,
                             textColor=ACCENT, alignment=TA_RIGHT)
    label = ParagraphStyle("label", parent=base, fontName="Helvetica-Bold", fontSize=8, textColor=MUTED)
    cell = ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    cell_r = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    head_r = ParagraphStyle("headr", parent=head, alignment=TA_RIGHT)
    section = ParagraphStyle("section", parent=base, fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT,
                             spaceBefore=6, spaceAfter=3)

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Quotation {q.quote_no}", author=seller.name_en)
    width = A4[0] - 32 * mm
    story: list = []

    # ---- 抬头：公司信息 + QUOTATION ----
    left: list = []
    if seller.logo_path and Path(seller.logo_path).exists():
        left.append(Image(seller.logo_path, width=28 * mm, height=12 * mm, kind="proportional"))
    left.append(_p(seller.name_en, h_company))
    if seller.name_cn:
        left.append(_p(seller.name_cn, small))
    contact_bits = [seller.address, " | ".join(x for x in [seller.email, seller.phone] if x), seller.website]
    left.append(_p("\n".join(x for x in contact_bits if x), small))
    right = [_p("QUOTATION", h_title)]
    header = Table([[left, right]], colWidths=[width * 0.62, width * 0.38])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 4 * mm)]
    rule = Table([[""]], colWidths=[width], rowHeights=[1.2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT)]))
    story += [rule, Spacer(1, 4 * mm)]

    # ---- 客户信息 + 报价信息 ----
    to_lines = [q.customer_company, q.customer_contact and f"Attn: {q.customer_contact}", q.customer_email,
                q.customer_country]
    bill_to = [_p("QUOTE TO", label)] + [_p(x, cell_b if i == 0 else cell) for i, x in enumerate(to_lines) if x]
    meta_rows = [("Quote No.", q.quote_no), ("Date", q.date), ("Valid Until", q.valid_until),
                 ("Currency", q.currency), ("Incoterm", q.incoterm)]
    meta = Table([[_p(k, label), _p(v, cell)] for k, v in meta_rows], colWidths=[24 * mm, 40 * mm])
    meta.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    info = Table([[bill_to, meta]], colWidths=[width - 66 * mm, 66 * mm])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [info, Spacer(1, 6 * mm)]

    # ---- 明细表 ----
    cols = [9 * mm, 24 * mm, None, 17 * mm, 24 * mm, 34 * mm]
    fixed = sum(c for c in cols if c)
    cols = [c if c else width - fixed for c in cols]
    rows = [[_p("#", head), _p("Model", head), _p("Description", head), _p("Qty", head_r),
             _p(f"Unit Price ({q.currency})", head_r), _p(f"Amount ({q.currency})", head_r)]]
    for i, it in enumerate(q.items, 1):
        desc = it.name + (f"\n{it.description}" if it.description else "")
        extra = "; ".join(x for x in [it.packing and f"Packing: {it.packing}", it.note] if x)
        if extra:
            desc += f"\n{extra}"
        rows.append([_p(str(i), cell), _p(it.model, cell_b), _p(desc, cell),
                     _p(f"{it.qty:,.0f}", cell_r), _p(money(it.unit_price), cell_r), _p(money(it.amount), cell_r)])
    rows.append(["", "", "", "", _p("TOTAL", ParagraphStyle("t", parent=cell_r, fontName="Helvetica-Bold")),
                 _p(f"{q.currency} {money(q.total)}", ParagraphStyle("tv", parent=cell_r, fontName="Helvetica-Bold",
                                                                      textColor=ACCENT, fontSize=10))])
    tbl = Table(rows, colWidths=cols, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#D5DBE3")),
        ("LINEABOVE", (4, -1), (-1, -1), 1, ACCENT),
    ]
    for r in range(1, len(rows) - 1):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    tbl.setStyle(TableStyle(style))
    story += [tbl, Spacer(1, 6 * mm)]

    # ---- 条款 ----
    terms = [
        ("Price Term", q.incoterm),
        ("Payment", q.payment_terms or "To be confirmed"),
        ("Lead Time", q.lead_time),
        ("Validity", f"This quotation is valid until {q.valid_until}"),
    ]
    story.append(_p("Terms & Conditions", section))
    tt = Table([[_p(k, label), _p(v, cell)] for k, v in terms], colWidths=[28 * mm, width - 28 * mm])
    tt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(tt)
    if q.remarks:
        story.append(_p("Remarks", section))
        for r in q.remarks:
            story.append(_p(f"• {r}", cell))
    if seller.bank_info:
        story.append(_p("Bank Information", section))
        story.append(_p(seller.bank_info, cell))

    story += [Spacer(1, 10 * mm),
              _p("Thank you for your inquiry. We look forward to working with you.", cell),
              Spacer(1, 2 * mm),
              _p(f"{seller.contact}\n{seller.name_en}", cell_b)]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 9 * mm, f"{seller.name_en}  ·  Quotation {q.quote_no}")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
