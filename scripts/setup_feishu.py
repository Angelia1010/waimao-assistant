"""一键在多维表格里建好 4 张表（已存在的表只补缺失字段，不会删数据）。

用法：
    python scripts/setup_feishu.py            # 只建表
    python scripts/setup_feishu.py --demo     # 建表 + 写入演示产品库
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import schema as S  # noqa: E402
from app.config import load_config  # noqa: E402
from app.demo import load_products_csv  # noqa: E402
from app.feishu import FeishuClient, text_of  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="写入演示产品库")
    ap.add_argument("--products", help="从你自己的 CSV 导入产品库（格式同 demo/products.csv）")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.feishu_enabled:
        sys.exit("请先在 .env 填写 FEISHU_APP_ID / FEISHU_APP_SECRET / BITABLE_APP_TOKEN")
    fs = FeishuClient(cfg.feishu_app_id, cfg.feishu_app_secret, cfg.bitable_app_token, cfg.feishu_base_url)

    existing = fs.list_tables()
    for name, fields in S.TABLES.items():
        if name not in existing:
            fs.create_table(name, fields)
            print(f"✅ 已创建数据表「{name}」（{len(fields)} 个字段）")
            continue
        have = {f["field_name"] for f in fs.list_fields(name)}
        missing = [f for f in fields if f["field_name"] not in have]
        for f in missing:
            fs.create_field(name, f)
        print(f"✔ 数据表「{name}」已存在" + (f"，补充了 {len(missing)} 个字段" if missing else ""))

    csv_path = Path(args.products) if args.products else (Path(__file__).resolve().parent.parent / "demo/products.csv"
                                                          if args.demo else None)
    if csv_path:
        rows = load_products_csv(csv_path)
        current = {text_of(r["fields"].get("型号")) for r in fs.search(S.T_PRODUCTS)}
        new_rows = [r for r in rows if r["型号"] not in current]
        if new_rows:
            fs.batch_create(S.T_PRODUCTS, new_rows)
        print(f"✅ 产品库写入 {len(new_rows)} 个型号（已存在的跳过）")

    print("\n全部完成。提示：新建多维表格时自带的空表「数据表」可以手动删掉。")


if __name__ == "__main__":
    main()
