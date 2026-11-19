"""写入演示数据，方便录屏和试用。所有演示客户名都带 Demo 字样。

用法：
    python scripts/seed_demo.py products   # 写入 8 个演示产品（自带数据库模式；飞书模式请用 setup_feishu.py --demo）
    python scripts/seed_demo.py emails     # 把 demo/emails 里的 5 封演示邮件交给 AI 处理入库（含1封垃圾邮件）
    python scripts/seed_demo.py history    # 写入 3 个“已报价、今天该跟进”的演示客户
    python scripts/seed_demo.py whatsapp   # 模拟粘贴一条 WhatsApp 询盘
    python scripts/seed_demo.py all        # 以上全部
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import schema as S  # noqa: E402
from app.demo import DEMO_DIR, demo_emails, history_rows, load_products_csv  # noqa: E402
from app.feishu import text_of  # noqa: E402
from app.main import build_assistant  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what not in ("products", "emails", "history", "whatsapp", "all"):
        sys.exit(__doc__)
    a = build_assistant()
    if what in ("products", "all") and a.cfg.storage == "sqlite":
        have = {text_of(r["fields"].get("型号")) for r in a.fs.search(S.T_PRODUCTS)}
        rows = [r for r in load_products_csv() if r["型号"] not in have]
        a.fs.batch_create(S.T_PRODUCTS, rows)
        print(f"✅ 写入 {len(rows)} 个演示产品")
    if what in ("emails", "all"):
        for m in demo_emails():
            m["msg_id"] = ""  # 演示可重复导入
            rid = a.ingest(m, source="邮箱")
            print(("✅ 入库 " if rid else "⏭  跳过（非询盘）") + m["subject"])
    if what in ("whatsapp", "all"):
        text = (DEMO_DIR / "whatsapp_chile.txt").read_text("utf-8")
        rid = a.ingest_text(text, source="WhatsApp")
        print("✅ WhatsApp 询盘入库" if rid else "⏭  跳过")
    if what in ("history", "all"):
        a.fs.batch_create(S.T_LEADS, history_rows())
        print("✅ 写入 3 个今天该跟进的演示客户")


if __name__ == "__main__":
    main()
