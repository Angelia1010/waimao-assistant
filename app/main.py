"""启动入口：python -m app.main"""
from __future__ import annotations

import logging
import sys

from .config import load_config
from .feishu import FeishuClient
from .llm import build_llm
from .pipeline import Assistant
from .server import serve
from .store import State
from .worker import Worker


def build_assistant(cfg=None) -> Assistant:
    cfg = cfg or load_config()
    fs = FeishuClient(cfg.feishu_app_id, cfg.feishu_app_secret, cfg.bitable_app_token, cfg.feishu_base_url,
                      cfg.feishu_bot_webhook, cfg.feishu_bot_secret)
    return Assistant(cfg, fs, build_llm(cfg), State(cfg.data_dir))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stdout)
    cfg = load_config()
    if not cfg.feishu_enabled:
        logging.error("缺少飞书配置：请在 .env 填写 FEISHU_APP_ID / FEISHU_APP_SECRET / BITABLE_APP_TOKEN")
        sys.exit(1)
    if cfg.api_token in ("", "change-me"):
        logging.warning("API_TOKEN 还是默认值，请在 .env 改成一串随机字符")
    assistant = build_assistant(cfg)
    assistant.fs.table_id("询盘客户")  # 启动时检查表是否已建好
    worker = Worker(assistant)
    worker.start()
    serve(assistant, worker)


if __name__ == "__main__":
    main()
