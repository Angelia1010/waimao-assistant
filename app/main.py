"""启动入口：python -m app.main"""
from __future__ import annotations

import logging
import secrets
import sys

from .config import apply_settings, load_config
from .feishu import FeishuClient
from .llm import build_llm
from .pipeline import Assistant
from .server import serve
from .store import State
from .worker import Worker

log = logging.getLogger("app")


def build_assistant(cfg=None) -> Assistant:
    cfg = cfg or load_config()
    bot = FeishuClient(cfg.feishu_app_id, cfg.feishu_app_secret, cfg.bitable_app_token, cfg.feishu_base_url,
                       cfg.feishu_bot_webhook, cfg.feishu_bot_secret)
    if cfg.storage == "sqlite":
        from .db import SqliteStore
        store = SqliteStore(cfg.data_dir, bot_sender=bot)
        saved = store.get_settings()
        if saved:
            apply_settings(cfg, saved)  # 网页「设置」里保存的值优先
            bot.bot_webhook, bot.bot_secret = cfg.feishu_bot_webhook, cfg.feishu_bot_secret
        backend = store
    else:
        backend = bot
    return Assistant(cfg, backend, build_llm(cfg), State(cfg.data_dir))


def ensure_admin(assistant: Assistant) -> None:
    store = assistant.fs
    if store.user_count():
        return
    cfg = assistant.cfg
    password = cfg.admin_password or secrets.token_urlsafe(9)
    store.create_user(cfg.admin_username, "管理员", password, role="admin")
    if cfg.admin_password:
        log.info("已创建管理员账号：%s（密码为 .env 里的 ADMIN_PASSWORD）", cfg.admin_username)
    else:
        log.warning("=" * 60)
        log.warning("已创建管理员账号  用户名：%s  初始密码：%s", cfg.admin_username, password)
        log.warning("请登录后在「成员」里修改密码。这条信息只显示一次。")
        log.warning("=" * 60)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stdout)
    cfg = load_config()
    if cfg.storage not in ("sqlite", "feishu"):
        logging.error("STORAGE 只能是 sqlite 或 feishu")
        sys.exit(1)
    if cfg.storage == "feishu" and not cfg.feishu_enabled:
        logging.error("飞书模式缺少配置：请填写 FEISHU_APP_ID / FEISHU_APP_SECRET / BITABLE_APP_TOKEN")
        sys.exit(1)
    assistant = build_assistant(cfg)
    if cfg.storage == "sqlite":
        ensure_admin(assistant)
    else:
        assistant.fs.table_id("询盘客户")  # 启动时检查表是否已建好
    worker = Worker(assistant)
    worker.start()
    serve(assistant, worker)


if __name__ == "__main__":
    main()
