"""读取 .env 配置。所有配置都集中在这里，部署时只需要改 .env。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # python-dotenv 不是必须的
    pass


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


@dataclass
class Config:
    # ---- 飞书 ----
    feishu_app_id: str = field(default_factory=lambda: _get("FEISHU_APP_ID"))
    feishu_app_secret: str = field(default_factory=lambda: _get("FEISHU_APP_SECRET"))
    feishu_base_url: str = field(default_factory=lambda: _get("FEISHU_BASE_URL", "https://open.feishu.cn"))
    bitable_app_token: str = field(default_factory=lambda: _get("BITABLE_APP_TOKEN"))
    feishu_bot_webhook: str = field(default_factory=lambda: _get("FEISHU_BOT_WEBHOOK"))
    feishu_bot_secret: str = field(default_factory=lambda: _get("FEISHU_BOT_SECRET"))
    bitable_url: str = field(default_factory=lambda: _get("BITABLE_URL"))

    # ---- 大模型（任何 OpenAI 兼容接口：DeepSeek / 通义千问 / Kimi / 智谱 ...）----
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "openai_compatible"))
    llm_base_url: str = field(default_factory=lambda: _get("LLM_BASE_URL", "https://api.deepseek.com"))
    llm_api_key: str = field(default_factory=lambda: _get("LLM_API_KEY"))
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "deepseek-chat"))

    # ---- 邮箱（IMAP）----
    imap_host: str = field(default_factory=lambda: _get("IMAP_HOST"))
    imap_port: int = field(default_factory=lambda: _int("IMAP_PORT", 993))
    imap_user: str = field(default_factory=lambda: _get("IMAP_USER"))
    imap_password: str = field(default_factory=lambda: _get("IMAP_PASSWORD"))
    imap_folder: str = field(default_factory=lambda: _get("IMAP_FOLDER", "INBOX"))
    imap_lookback_days: int = field(default_factory=lambda: _int("IMAP_LOOKBACK_DAYS", 3))

    # ---- 运行 ----
    server_host: str = field(default_factory=lambda: _get("SERVER_HOST", "0.0.0.0"))
    server_port: int = field(default_factory=lambda: _int("SERVER_PORT", 8080))
    api_token: str = field(default_factory=lambda: _get("API_TOKEN", "change-me"))
    poll_seconds: int = field(default_factory=lambda: _int("POLL_SECONDS", 30))
    mail_poll_seconds: int = field(default_factory=lambda: _int("MAIL_POLL_SECONDS", 120))
    followup_time: str = field(default_factory=lambda: _get("FOLLOWUP_TIME", "09:00"))
    timezone_offset_hours: int = field(default_factory=lambda: _int("TZ_OFFSET_HOURS", 8))
    data_dir: str = field(default_factory=lambda: _get("DATA_DIR", "./data"))
    # 产品展示页底部按钮的文字（不要放微信号/手机号，避免录屏发小红书时违规）
    landing_contact: str = field(default_factory=lambda: _get("LANDING_CONTACT", "预约演示"))

    # ---- 公司信息（打印在报价单上）----
    company_name_en: str = field(default_factory=lambda: _get("COMPANY_NAME_EN", "Demo Hardware Co., Ltd."))
    company_name_cn: str = field(default_factory=lambda: _get("COMPANY_NAME_CN", ""))
    company_address: str = field(default_factory=lambda: _get("COMPANY_ADDRESS", "Ningbo, Zhejiang, China"))
    company_contact: str = field(default_factory=lambda: _get("COMPANY_CONTACT", "Sales Team"))
    company_email: str = field(default_factory=lambda: _get("COMPANY_EMAIL", "sales@example.com"))
    company_phone: str = field(default_factory=lambda: _get("COMPANY_PHONE", ""))
    company_website: str = field(default_factory=lambda: _get("COMPANY_WEBSITE", ""))
    company_logo_path: str = field(default_factory=lambda: _get("COMPANY_LOGO_PATH", ""))
    quote_currency: str = field(default_factory=lambda: _get("QUOTE_CURRENCY", "USD"))
    quote_incoterm: str = field(default_factory=lambda: _get("QUOTE_INCOTERM", "FOB Ningbo"))
    quote_payment_terms: str = field(default_factory=lambda: _get("QUOTE_PAYMENT_TERMS", "T/T 30% deposit, 70% before shipment"))
    quote_validity_days: int = field(default_factory=lambda: _int("QUOTE_VALIDITY_DAYS", 30))
    quote_bank_info: str = field(default_factory=lambda: _get("QUOTE_BANK_INFO", ""))

    @property
    def feishu_enabled(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret and self.bitable_app_token)

    @property
    def mail_enabled(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_password)


def load_config() -> Config:
    return Config()
