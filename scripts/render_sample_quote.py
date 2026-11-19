"""不连飞书，直接生成一份样例报价单 PDF，用来调整报价单样式。

    python scripts/render_sample_quote.py     # 输出到 data/quotes/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.demo import load_products_csv  # noqa: E402
from app.quote_pdf import QuoteData, QuoteItem, Seller, render_quote  # noqa: E402


def main() -> None:
    cfg = load_config()
    p = {r["型号"]: r for r in load_products_csv()}
    items = [
        QuoteItem("DS-450", p["DS-450"]["产品名称"], p["DS-450"]["规格描述"], 5000, p["DS-450"]["单价"], 30,
                  p["DS-450"]["包装"]),
        QuoteItem("HG-304A", p["HG-304A"]["产品名称"], p["HG-304A"]["规格描述"], 8000, p["HG-304A"]["单价"], 25,
                  p["HG-304A"]["包装"], "Salt spray test 48h report available"),
    ]
    q = QuoteData("Q20261119-001", "2026-11-19", "2026-12-19", "Nordbau Demo Handel GmbH", "Klaus Weber",
                  "k.weber@nordbau-demo.de", "Germany", cfg.quote_currency, cfg.quote_incoterm,
                  cfg.quote_payment_terms, items)
    seller = Seller(cfg.company_name_en, cfg.company_name_cn, cfg.company_address, cfg.company_contact,
                    cfg.company_email, cfg.company_phone, cfg.company_website, cfg.company_logo_path,
                    cfg.quote_bank_info)
    print(render_quote(q, seller, Path(cfg.data_dir) / "quotes"))


if __name__ == "__main__":
    main()
