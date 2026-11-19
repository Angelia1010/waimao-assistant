"""演示数据：产品库 CSV、演示询盘邮件，以及带历史记录的“已报价客户”。"""
from __future__ import annotations

import csv
import time
from pathlib import Path

from . import schema as S
from .feishu import ms

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def load_products_csv(path: Path | None = None) -> list[dict]:
    path = path or DEMO_DIR / "products.csv"
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "型号": r["型号"].strip(), "产品名称": r["产品名称"].strip(), "规格描述": r["规格描述"].strip(),
                "单价": float(r["单价"]), "起订量": float(r["起订量"]), "交期(天)": float(r["交期(天)"]),
                "包装": r.get("包装", "").strip(), "备注": r.get("备注", "").strip(),
            })
    return rows


def parse_demo_email(path: Path) -> dict:
    text = path.read_text("utf-8")
    head, _, body = text.partition("\n\n")
    hdr = {}
    for line in head.splitlines():
        k, _, v = line.partition(":")
        hdr[k.strip().lower()] = v.strip()
    sender = hdr.get("from", "")
    addr = sender.split("<")[-1].rstrip(">") if "<" in sender else sender
    return {"msg_id": f"demo-{path.stem}", "sender": sender, "sender_email": addr,
            "subject": hdr.get("subject", ""), "body": body.strip(), "date": None}


def demo_emails() -> list[dict]:
    return [parse_demo_email(p) for p in sorted((DEMO_DIR / "emails").glob("*.txt"))]


# 已经报过价、今天到了跟进时间的演示客户（用来录“每日跟进提醒”）
HISTORY_LEADS = [
    {S.F_COMPANY: "Lumière Maison Demo SAS", S.F_COUNTRY: "法国", S.F_CONTACT: "Camille Durand",
     S.F_EMAIL: "camille@lumiere-demo.fr", S.F_SOURCE: "阿里国际站", S.F_LEVEL: "A",
     S.F_PRODUCTS: "SC-500 缓冲隐藏滑轨", S.F_QTY: "2,000 pairs", S.F_BUDGET: "",
     S.F_SUMMARY: "法国橱柜品牌，询问SC-500缓冲隐藏滑轨2000对，要求提供SGS报告，计划Q2上新。",
     S.F_LEVEL_REASON: "型号和数量明确，企业邮箱，提到认证要求",
     S.F_STATUS: "已报价", S.F_FOLLOW_COUNT: 0, "_days_ago": 3,
     S.F_CHAT_LOG: "[3天前] 发送报价 Q-DEMO-001，合计 USD 13,800.00；客户已读未回复"},
    {S.F_COMPANY: "Gulf Build Demo Trading LLC", S.F_COUNTRY: "阿联酋", S.F_CONTACT: "Ahmed Khan",
     S.F_EMAIL: "ahmed@gulfbuild-demo.ae", S.F_SOURCE: "展会", S.F_LEVEL: "B",
     S.F_PRODUCTS: "HG-304B 5寸不锈钢铰链", S.F_QTY: "", S.F_BUDGET: "",
     S.F_SUMMARY: "广交会认识的迪拜建材贸易商，对HG-304B感兴趣，数量未定，说要和老板商量。",
     S.F_LEVEL_REASON: "产品明确但数量未定", S.F_STATUS: "跟进中", S.F_FOLLOW_COUNT: 1, "_days_ago": 4,
     S.F_CHAT_LOG: "[10天前] 发送报价，合计 USD 2,360.00\n[4天前] 第1次跟进：提醒价格有效期，客户回复 will check with my boss"},
    {S.F_COMPANY: "Polska Meble Demo Sp. z o.o.", S.F_COUNTRY: "波兰", S.F_CONTACT: "Piotr Nowak",
     S.F_EMAIL: "piotr@pmeble-demo.pl", S.F_SOURCE: "邮箱", S.F_LEVEL: "B",
     S.F_PRODUCTS: "DS-450 抽屉滑轨", S.F_QTY: "1,000 pairs", S.F_BUDGET: "USD 2.0/pair",
     S.F_SUMMARY: "波兰家具厂，DS-450 1000对，目标价2.0美元，嫌我们价格高。",
     S.F_LEVEL_REASON: "有数量和目标价，但价格差距较大", S.F_STATUS: "跟进中", S.F_FOLLOW_COUNT: 4, "_days_ago": 14,
     S.F_CHAT_LOG: "[40天前] 发送报价，合计 USD 2,350.00；客户回复 too expensive\n[30天前] 第1次跟进\n"
                   "[23天前] 第2次跟进：提供小批量试单\n[18天前] 第3次跟进\n[14天前] 第4次跟进：未回复"},
]


def history_rows() -> list[dict]:
    now = time.time()
    rows = []
    for h in HISTORY_LEADS:
        r = {k: v for k, v in h.items() if not k.startswith("_")}
        last = now - h["_days_ago"] * 86400
        r.update({S.F_LAST_AT: ms(last), S.F_FIRST_AT: ms(last - 7 * 86400), S.F_NEXT_AT: ms(now - 3600)})
        rows.append(r)
    return rows
