"""部署后自检：逐项检查大模型、数据库/飞书表格、邮箱、群机器人是否配置正确。

    python scripts/doctor.py
    docker compose exec waimao-assistant python scripts/doctor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mailbox, schema as S  # noqa: E402
from app.config import load_config  # noqa: E402
from app.feishu import FeishuClient  # noqa: E402
from app.llm import MockLLM, build_llm, parse_json  # noqa: E402


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
    print(f"运行模式：{'网页系统 + 自带数据库' if cfg.storage == 'sqlite' else '飞书多维表格'}（STORAGE={cfg.storage}）\n")

    if cfg.storage == "sqlite":
        from app.db import SqliteStore
        from app.config import apply_settings

        def db():
            store = SqliteStore(cfg.data_dir)
            saved = store.get_settings()
            if saved:
                apply_settings(cfg, saved)  # 网页「设置」里保存的机器人地址等也一起检查
            users = store.user_count()
            return (f"{store.path}，成员 {users} 个，产品 {len(store.search(S.T_PRODUCTS))} 个，"
                    f"客户 {len(store.search(S.T_LEADS))} 个" + ("" if users else "（启动服务时会自动创建管理员）"))
        check("数据库", db)
    else:
        fs = FeishuClient(cfg.feishu_app_id, cfg.feishu_app_secret, cfg.bitable_app_token, cfg.feishu_base_url)
        if check("飞书应用凭证", lambda: fs._tenant_token(force=True) and ""):
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
            raise RuntimeError("没有配置 LLM_API_KEY，现在是演示模式（规则版 AI），不能给真实客户用")
        out = m.chat("你只输出 JSON。", '请输出 {"ok": true}', json_mode=True)
        if parse_json(out).get("ok") is not True:
            raise RuntimeError(f"模型能连上，但没有按要求返回 JSON：{out[:80]}")
        return f"{cfg.llm_model} @ {cfg.llm_base_url}，能正常返回 JSON"
    check("大模型", llm)

    if cfg.mail_enabled:
        check("业务邮箱 IMAP", lambda: f"最近 {cfg.imap_lookback_days} 天共 "
              f"{len(mailbox.fetch_recent(cfg.imap_host, cfg.imap_port, cfg.imap_user, cfg.imap_password, cfg.imap_folder, cfg.imap_lookback_days))} 封邮件")
    else:
        print("⏭  业务邮箱未配置（可以只用「录入询盘」粘贴）")

    if cfg.feishu_bot_webhook:
        bot = FeishuClient("", "", "", bot_webhook=cfg.feishu_bot_webhook, bot_secret=cfg.feishu_bot_secret)
        check("飞书群机器人", lambda: bot.send_card("✅ 外贸订单助手连接成功", "这是一条测试消息。", template="green") or "已发送测试消息，去群里看看")
    else:
        print("⏭  飞书群机器人未配置（提醒只保存在网页「提醒」里）")


if __name__ == "__main__":
    main()
