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
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "deepseek-v4-flash"))

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
    # sqlite = 自带数据库 + 网页系统（推荐）；feishu = 旧版，用飞书多维表格当数据库
    storage: str = field(default_factory=lambda: _get("STORAGE", "sqlite").lower())
    admin_username: str = field(default_factory=lambda: _get("ADMIN_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: _get("ADMIN_PASSWORD"))
    # 用 HTTPS 访问时设为 true，登录 Cookie 只走加密连接
    cookie_secure: bool = field(default_factory=lambda: _get("COOKIE_SECURE", "false").lower() == "true")

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


# 可以在网页「设置」里修改、保存在数据库里的配置项（会覆盖 .env 里的同名值）
EDITABLE_SETTINGS: dict[str, type] = {
    "company_name_en": str, "company_name_cn": str, "company_address": str, "company_contact": str,
    "company_email": str, "company_phone": str, "company_website": str,
    "quote_currency": str, "quote_incoterm": str, "quote_payment_terms": str, "quote_validity_days": int,
    "quote_bank_info": str, "followup_time": str, "feishu_bot_webhook": str, "feishu_bot_secret": str,
    "landing_contact": str,
    "llm_base_url": str, "llm_api_key": str, "llm_model": str,
}
# 密钥类配置：接口永远不返回原文，只返回掩码；提交空值表示“不修改”
SECRET_SETTINGS = {"llm_api_key", "feishu_bot_secret"}

# 常用大模型的预设（网页设置里的下拉选项）
LLM_PRESETS = [
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash",
     "help": "platform.deepseek.com → API Keys 创建密钥"},
    {"id": "qwen", "name": "通义千问（阿里云百炼）", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "model": "qwen-plus", "help": "百炼控制台 → API Key；不同地域的地址不同，以控制台显示的为准"},
    {"id": "custom", "name": "其他 OpenAI 兼容接口", "base_url": "", "model": "",
     "help": "Kimi、智谱、豆包、硅基流动等，填它们文档里的 base_url 和模型名"},
]


def mask_secret(v: str) -> str:
    v = v or ""
    if not v:
        return ""
    return (v[:3] + "****" + v[-4:]) if len(v) > 10 else "****"


def apply_settings(cfg: Config, values: dict) -> dict:
    """校验并写入 cfg，返回清洗后的值。"""
    import re
    clean = {}
    for k, v in values.items():
        if k not in EDITABLE_SETTINGS:
            continue
        typ = EDITABLE_SETTINGS[k]
        if typ is int:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} 必须是整数")
            if not 1 <= v <= 365:
                raise ValueError("报价有效期要在 1–365 天之间")
        else:
            v = str(v or "").strip()
            if k == "followup_time" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
                raise ValueError("推送时间格式应为 HH:MM，例如 09:00")
            if k == "feishu_bot_webhook" and v and not v.startswith(
                    ("https://open.feishu.cn/open-apis/bot/", "https://open.larksuite.com/open-apis/bot/")):
                raise ValueError("飞书机器人地址应以 https://open.feishu.cn/open-apis/bot/ 开头")
            if k == "llm_base_url" and v and not re.match(r"https?://[^\s/]+", v):
                raise ValueError("大模型接口地址应以 https:// 开头")
            if k == "llm_base_url":
                v = v.rstrip("/")
            if k in ("llm_api_key", "llm_model", "feishu_bot_secret") and (len(v) > 300 or re.search(r"\s", v)):
                raise ValueError("密钥或模型名里不能有空格或换行，请检查是否复制完整")
        setattr(cfg, k, v)
        clean[k] = v
    return clean
