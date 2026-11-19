"""部署后自检：逐项检查飞书、表格、大模型、邮箱、群机器人是否配置正确。

    python scripts/doctor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mailbox, schema as S  # noqa: E402
from app.config import load_config  # noqa: E402
from app.feishu import FeishuClient  # noqa: E402
from app.llm import MockLLM, build_llm  # noqa: E402


def check(name, fn):
    try:
        msg = fn()
        print(f"✅ {name}" + (f"：{msg}" if msg else ""))
        return True
    except Exception as e:
        print(f"❌ {name}：{e}")
        return False


def main() -> None:
    cfg = load_config()
    fs = FeishuClient(cfg.feishu_app_id, cfg.feishu_app_secret, cfg.bitable_app_token, cfg.feishu_base_url,
                      cfg.feishu_bot_webhook, cfg.feishu_bot_secret)
    ok = check("飞书应用凭证", lambda: fs._tenant_token(force=True) and "")
    if ok:
        def tables():
            have = fs.list_tables()
            missing = [t for t in S.TABLES if t not in have]
            if missing:
                raise RuntimeError(f"缺少数据表 {missing}，请运行 python scripts/setup_feishu.py；"
                                   "如果提示无权限，请把应用添加为多维表格的协作者")
            return f"4 张表都在，产品库 {len(fs.search(S.T_PRODUCTS))} 个型号"
        check("多维表格", tables)

    def llm():
        m = build_llm(cfg)
        if isinstance(m, MockLLM):
            return "⚠️ 未配置 LLM_API_KEY，正在使用规则版 mock（仅用于演示）"
        return "返回：" + m.chat("Reply with one word.", "Say OK", json_mode=False)[:20]
    check("大模型", llm)

    if cfg.mail_enabled:
        check("邮箱 IMAP", lambda: f"最近 {cfg.imap_lookback_days} 天 "
              f"{len(mailbox.fetch_recent(cfg.imap_host, cfg.imap_port, cfg.imap_user, cfg.imap_password, cfg.imap_folder, cfg.imap_lookback_days))} 封邮件")
    else:
        print("⏭  邮箱未配置（可以只用粘贴页面录入询盘）")

    if cfg.feishu_bot_webhook:
        check("群机器人", lambda: fs.send_card("✅ 外贸AI助手连接成功", "这是一条测试消息。", template="green") or "")
    else:
        print("⏭  群机器人未配置（不会推送提醒）")


if __name__ == "__main__":
    main()
