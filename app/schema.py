"""多维表格的表结构定义。setup 脚本按这里自动建表，业务代码也按这里的字段名读写。

飞书字段类型：1 文本 / 2 数字 / 3 单选 / 5 日期 / 7 复选框 / 15 超链接 / 17 附件
"""
from __future__ import annotations

TEXT, NUMBER, SINGLE_SELECT, DATETIME, CHECKBOX, URL, ATTACHMENT = 1, 2, 3, 5, 7, 15, 17

# ---- 表名 ----
T_PRODUCTS = "产品库"
T_LEADS = "询盘客户"
T_QUOTES = "报价记录"
T_FOLLOWUPS = "跟进记录"

# ---- 询盘客户表的字段名（业务代码统一用这些常量）----
F_COMPANY = "客户公司"
F_CONTACT = "联系人"
F_EMAIL = "邮箱"
F_COUNTRY = "国家"
F_SOURCE = "来源"
F_PRODUCTS = "询盘产品"
F_QTY = "需求数量"
F_BUDGET = "目标价/预算"
F_RAW = "询盘原文"
F_SUMMARY = "AI摘要"
F_LEVEL = "意向等级"
F_LEVEL_REASON = "分级理由"
F_STATUS = "状态"
F_FIRST_AT = "首次询盘时间"
F_LAST_AT = "最近联系时间"
F_NEXT_AT = "下次跟进日期"
F_FOLLOW_COUNT = "跟进次数"
F_CHAT_LOG = "沟通记录"
F_QUOTE_BTN = "生成报价单"
F_QUOTE_FILE = "报价单"
F_QUOTE_EMAIL = "报价邮件草稿"
F_FOLLOW_DRAFT = "跟进话术"
F_FOLLOWED_BTN = "已跟进"
F_OWNER = "负责人"
F_MSG_ID = "邮件ID"

SOURCES = ["邮箱", "阿里国际站", "WhatsApp", "展会", "官网", "其他"]
LEVELS = ["A", "B", "C"]
STATUSES = ["新询盘", "已报价", "跟进中", "已寄样", "已成交", "已流失"]
ACTIVE_STATUSES = ["已报价", "跟进中"]


def _select(options: list[str]) -> dict:
    return {"options": [{"name": o} for o in options]}


TABLES: dict[str, list[dict]] = {
    T_PRODUCTS: [
        {"field_name": "型号", "type": TEXT},
        {"field_name": "产品名称", "type": TEXT},
        {"field_name": "规格描述", "type": TEXT},
        {"field_name": "单价", "type": NUMBER, "property": {"formatter": "0.00"}},
        {"field_name": "起订量", "type": NUMBER, "property": {"formatter": "0"}},
        {"field_name": "交期(天)", "type": NUMBER, "property": {"formatter": "0"}},
        {"field_name": "包装", "type": TEXT},
        {"field_name": "备注", "type": TEXT},
    ],
    T_LEADS: [
        {"field_name": F_COMPANY, "type": TEXT},
        {"field_name": F_LEVEL, "type": SINGLE_SELECT, "property": _select(LEVELS)},
        {"field_name": F_STATUS, "type": SINGLE_SELECT, "property": _select(STATUSES)},
        {"field_name": F_COUNTRY, "type": TEXT},
        {"field_name": F_CONTACT, "type": TEXT},
        {"field_name": F_EMAIL, "type": TEXT},
        {"field_name": F_SOURCE, "type": SINGLE_SELECT, "property": _select(SOURCES)},
        {"field_name": F_PRODUCTS, "type": TEXT},
        {"field_name": F_QTY, "type": TEXT},
        {"field_name": F_BUDGET, "type": TEXT},
        {"field_name": F_SUMMARY, "type": TEXT},
        {"field_name": F_LEVEL_REASON, "type": TEXT},
        {"field_name": F_QUOTE_BTN, "type": CHECKBOX},
        {"field_name": F_QUOTE_FILE, "type": ATTACHMENT},
        {"field_name": F_QUOTE_EMAIL, "type": TEXT},
        {"field_name": F_NEXT_AT, "type": DATETIME, "property": {"date_formatter": "yyyy/MM/dd"}},
        {"field_name": F_FOLLOW_DRAFT, "type": TEXT},
        {"field_name": F_FOLLOWED_BTN, "type": CHECKBOX},
        {"field_name": F_FOLLOW_COUNT, "type": NUMBER, "property": {"formatter": "0"}},
        {"field_name": F_LAST_AT, "type": DATETIME, "property": {"date_formatter": "yyyy/MM/dd HH:mm"}},
        {"field_name": F_FIRST_AT, "type": DATETIME, "property": {"date_formatter": "yyyy/MM/dd HH:mm"}},
        {"field_name": F_CHAT_LOG, "type": TEXT},
        {"field_name": F_RAW, "type": TEXT},
        {"field_name": F_OWNER, "type": TEXT},
        {"field_name": F_MSG_ID, "type": TEXT},
    ],
    T_QUOTES: [
        {"field_name": "报价单号", "type": TEXT},
        {"field_name": "客户公司", "type": TEXT},
        {"field_name": "报价日期", "type": DATETIME, "property": {"date_formatter": "yyyy/MM/dd"}},
        {"field_name": "币种", "type": TEXT},
        {"field_name": "金额合计", "type": NUMBER, "property": {"formatter": "0.00"}},
        {"field_name": "报价明细", "type": TEXT},
        {"field_name": "PDF", "type": ATTACHMENT},
    ],
    T_FOLLOWUPS: [
        {"field_name": "客户公司", "type": TEXT},
        {"field_name": "跟进时间", "type": DATETIME, "property": {"date_formatter": "yyyy/MM/dd HH:mm"}},
        {"field_name": "第几次跟进", "type": NUMBER, "property": {"formatter": "0"}},
        {"field_name": "使用的话术", "type": TEXT},
    ],
}
