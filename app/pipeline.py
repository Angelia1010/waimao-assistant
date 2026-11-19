"""核心业务：询盘入库分级 → 生成报价单 → 每日跟进提醒 → 记录跟进。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import prompts
from . import schema as S
from .config import Config
from .feishu import ms, num_of, text_of
from .llm import LLM
from .quote_pdf import QuoteData, QuoteItem, Seller, render_quote
from .store import State

log = logging.getLogger(__name__)

# 报价后第 n 次跟进的间隔天数（按意向等级）
CADENCE = {"A": [2, 3, 5, 7, 10], "B": [3, 4, 7, 10, 14], "C": [5, 7, 14, 21, 30]}
MAX_FOLLOWUPS = 5


def next_interval(level: str, count: int) -> int:
    seq = CADENCE.get(level or "B", CADENCE["B"])
    return seq[count] if count < len(seq) else 30


@dataclass
class Product:
    model: str
    name: str
    spec: str
    price: float
    moq: float
    lead_days: int
    packing: str


class Assistant:
    def __init__(self, cfg: Config, feishu, llm: LLM, state: State):
        self.cfg = cfg
        self.fs = feishu
        self.llm = llm
        self.state = state
        self.tz = timezone(timedelta(hours=cfg.timezone_offset_hours))

    # ----------------------------------------------------------------- utils
    def now(self) -> datetime:
        return datetime.now(self.tz)

    def end_of_today_ms(self) -> int:
        n = self.now()
        end = n.replace(hour=23, minute=59, second=59, microsecond=0)
        return int(end.timestamp() * 1000)

    def products(self) -> list[Product]:
        out = []
        for r in self.fs.search(S.T_PRODUCTS):
            f = r["fields"]
            model = text_of(f.get("型号")).strip()
            if not model:
                continue
            out.append(Product(model=model, name=text_of(f.get("产品名称")), spec=text_of(f.get("规格描述")),
                               price=num_of(f.get("单价")), moq=num_of(f.get("起订量")),
                               lead_days=int(num_of(f.get("交期(天)"))), packing=text_of(f.get("包装"))))
        return out

    @staticmethod
    def catalog_text(products: list[Product]) -> str:
        if not products:
            return "（产品库为空）"
        return "\n".join(f"{p.model} | {p.name} | {p.spec} | {p.moq:g}" for p in products)

    # ------------------------------------------------------- 1. 询盘入库分级
    def ingest(self, msg: dict, source: str = "邮箱", owner: str = "") -> str | None:
        """msg: {msg_id, sender, subject, body, date}。返回新建的记录ID；不是询盘返回 None。"""
        msg_id = msg.get("msg_id") or ""
        if msg_id and self.state.seen(msg_id):
            return None
        products = self.products()
        info = self.llm.chat_json(prompts.INQUIRY_SYSTEM, prompts.INQUIRY_USER.format(
            catalog=self.catalog_text(products), sender=msg.get("sender", ""),
            subject=msg.get("subject", ""), body=msg.get("body", "")[:6000]))
        if msg_id:
            self.state.mark_seen(msg_id)
        if not info.get("is_inquiry"):
            log.info("跳过非询盘邮件：%s", msg.get("subject"))
            return None
        level = str(info.get("level", "B")).strip().upper()[:1]
        level = level if level in S.LEVELS else "B"
        ts = ms(msg.get("date") or time.time())
        company = (info.get("company") or "").strip() or (info.get("email") or msg.get("sender_email") or "未知客户")
        fields = {
            S.F_COMPANY: company,
            S.F_CONTACT: info.get("contact", ""),
            S.F_EMAIL: info.get("email") or msg.get("sender_email", ""),
            S.F_COUNTRY: info.get("country", ""),
            S.F_SOURCE: source if source in S.SOURCES else "其他",
            S.F_PRODUCTS: info.get("products", ""),
            S.F_QTY: str(info.get("quantity", "")),
            S.F_BUDGET: str(info.get("budget", "")),
            S.F_SUMMARY: info.get("summary", ""),
            S.F_LEVEL: level,
            S.F_LEVEL_REASON: info.get("level_reason", ""),
            S.F_STATUS: "新询盘",
            S.F_FIRST_AT: ts,
            S.F_LAST_AT: ts,
            S.F_NEXT_AT: ms(time.time()) if level in ("A", "B") else ms(time.time() + 86400),
            S.F_FOLLOW_COUNT: 0,
            S.F_RAW: (f"主题：{msg.get('subject', '')}\n\n" if msg.get("subject") else "") + msg.get("body", "")[:4000],
            S.F_MSG_ID: msg_id,
            S.F_OWNER: owner,
        }
        rid = self.fs.create_record(S.T_LEADS, fields)
        log.info("新询盘入库：%s [%s]", company, level)
        if level == "A":
            self._safe_card(f"🔥 新的A级询盘：{company}",
                            f"**{info.get('country', '')}** · {fields[S.F_PRODUCTS] or '产品待确认'} · {fields[S.F_QTY]}\n"
                            f"{fields[S.F_SUMMARY]}\n\n分级理由：{fields[S.F_LEVEL_REASON]}\n"
                            f"建议今天内报价：在表格里勾选「{S.F_QUOTE_BTN}」即可自动生成报价单。",
                            template="red")
        return rid

    def ingest_text(self, text: str, source: str = "其他", sender: str = "", owner: str = "") -> str | None:
        """手动粘贴的询盘（阿里国际站、WhatsApp、展会名片等）。"""
        return self.ingest({"msg_id": "", "sender": sender, "subject": "", "body": text, "date": None},
                           source=source, owner=owner)

    # --------------------------------------------------------- 2. 生成报价单
    def generate_quote(self, record_id: str) -> dict:
        rec = self.fs.get_record(S.T_LEADS, record_id)
        f = rec["fields"]
        products = self.products()
        if not products:
            raise RuntimeError("产品库为空，请先在「产品库」表里填写型号和单价")
        by_model = {p.model.lower(): p for p in products}
        company = text_of(f.get(S.F_COMPANY))
        plan = self.llm.chat_json(prompts.QUOTE_ITEMS_SYSTEM, prompts.QUOTE_ITEMS_USER.format(
            catalog=self.catalog_text(products), products=text_of(f.get(S.F_PRODUCTS)),
            quantity=text_of(f.get(S.F_QTY)), summary=text_of(f.get(S.F_SUMMARY)),
            terms=f"{self.cfg.quote_incoterm}; {self.cfg.quote_payment_terms}; currency {self.cfg.quote_currency}"))
        items: list[QuoteItem] = []
        for it in plan.get("items", [])[:8]:
            p = by_model.get(str(it.get("model", "")).strip().lower())
            if not p:
                continue
            qty = max(num_of(it.get("qty")), 0) or p.moq or 1
            items.append(QuoteItem(model=p.model, name=p.name, description=p.spec, qty=qty, unit_price=p.price,
                                   lead_days=p.lead_days, packing=p.packing, note=str(it.get("note") or "")))
        if not items:
            raise RuntimeError("没有在产品库里匹配到可报价的型号，请检查「询盘产品」或产品库")

        today = self.now()
        quote = QuoteData(
            quote_no=self.state.next_quote_no(today.strftime("%Y%m%d")),
            date=today.strftime("%Y-%m-%d"),
            valid_until=(today + timedelta(days=self.cfg.quote_validity_days)).strftime("%Y-%m-%d"),
            customer_company=company, customer_contact=text_of(f.get(S.F_CONTACT)),
            customer_email=text_of(f.get(S.F_EMAIL)), customer_country=text_of(f.get(S.F_COUNTRY)),
            currency=self.cfg.quote_currency, incoterm=self.cfg.quote_incoterm,
            payment_terms=self.cfg.quote_payment_terms, items=items,
            remarks=[str(x) for x in (plan.get("remarks") or [])[:3] if x] + (
                ["Some requested items are not in our standard range; we will confirm them separately."]
                if plan.get("unmatched") else []),
        )
        pdf = render_quote(quote, self.seller(), Path(self.cfg.data_dir) / "quotes")
        token = self.fs.upload_attachment(pdf)

        contact = text_of(f.get(S.F_CONTACT))
        email_draft = self.llm.chat(prompts.QUOTE_EMAIL_SYSTEM, prompts.QUOTE_EMAIL_USER.format(
            company=company, contact=contact, country=text_of(f.get(S.F_COUNTRY)),
            summary=text_of(f.get(S.F_SUMMARY)),
            items="; ".join(f"{i.model} x {i.qty:,.0f} @ {i.unit_price:.2f}" for i in items),
            currency=quote.currency, total=f"{quote.total:,.2f}", incoterm=quote.incoterm, lead_time=quote.lead_time,
            contact_or_team=contact or "Sir/Madam", signature=f"{self.cfg.company_contact}\n{self.cfg.company_name_en}"),
            json_mode=False, temperature=0.6).strip()

        level = text_of(f.get(S.F_LEVEL)) or "B"
        now_ms = ms(time.time())
        log_line = f"[{quote.date}] 发送报价 {quote.quote_no}，合计 {quote.currency} {quote.total:,.2f}"
        self.fs.update_record(S.T_LEADS, record_id, {
            S.F_QUOTE_FILE: [{"file_token": token}],
            S.F_QUOTE_EMAIL: email_draft,
            S.F_STATUS: "已报价",
            S.F_LAST_AT: now_ms,
            S.F_NEXT_AT: now_ms + next_interval(level, 0) * 86400 * 1000,
            S.F_FOLLOW_COUNT: 0,
            S.F_QUOTE_BTN: False,
            S.F_CHAT_LOG: (text_of(f.get(S.F_CHAT_LOG)) + "\n" + log_line).strip(),
        })
        self.fs.create_record(S.T_QUOTES, {
            "报价单号": quote.quote_no, "客户公司": company, "报价日期": now_ms, "币种": quote.currency,
            "金额合计": quote.total,
            "报价明细": "\n".join(f"{i.model} × {i.qty:,.0f} @ {i.unit_price:.2f} = {i.amount:,.2f}" for i in items),
            "PDF": [{"file_token": token}],
            "线索ID": record_id,
        })
        log.info("已生成报价单 %s → %s", quote.quote_no, company)
        return {"quote_no": quote.quote_no, "total": quote.total, "pdf": str(pdf), "email": email_draft,
                "file_token": token}

    def seller(self) -> Seller:
        c = self.cfg
        return Seller(name_en=c.company_name_en, name_cn=c.company_name_cn, address=c.company_address,
                      contact=c.company_contact, email=c.company_email, phone=c.company_phone,
                      website=c.company_website, logo_path=c.company_logo_path, bank_info=c.quote_bank_info)

    # ----------------------------------------------------- 3. 每日跟进提醒
    def daily_followups(self, push: bool = True) -> list[dict]:
        cutoff = self.end_of_today_ms()
        now_ms = ms(time.time())
        due, to_quote = [], []
        for r in self.fs.search(S.T_LEADS):
            f = r["fields"]
            status = text_of(f.get(S.F_STATUS))
            next_at = num_of(f.get(S.F_NEXT_AT), default=0)
            if status in S.ACTIVE_STATUSES and next_at and next_at <= cutoff:
                due.append(r)
            elif status == "新询盘" and text_of(f.get(S.F_LEVEL)) in ("A", "B"):
                to_quote.append(r)

        level_rank = {"A": 0, "B": 1, "C": 2}
        due.sort(key=lambda r: (level_rank.get(text_of(r["fields"].get(S.F_LEVEL)), 3),
                                num_of(r["fields"].get(S.F_NEXT_AT))))
        results = [self._draft(r) for r in due]
        if push:
            self._push_followup_card(results, to_quote)
        return results

    def _draft(self, r: dict) -> dict:
        """给一个客户写下一次跟进话术，并写回「跟进话术」字段。"""
        f = r["fields"]
        now_ms = ms(time.time())
        count = int(num_of(f.get(S.F_FOLLOW_COUNT)))
        last = num_of(f.get(S.F_LAST_AT), default=now_ms)
        days = max(0, int((now_ms - last) / 86400000))
        draft = self.llm.chat_json(prompts.FOLLOWUP_SYSTEM, prompts.FOLLOWUP_USER.format(
            company=text_of(f.get(S.F_COMPANY)), country=text_of(f.get(S.F_COUNTRY)),
            contact=text_of(f.get(S.F_CONTACT)) or "there", level=text_of(f.get(S.F_LEVEL)),
            summary=text_of(f.get(S.F_SUMMARY)), count=count, days=days,
            chat_log=text_of(f.get(S.F_CHAT_LOG))[-2000:] or "（无）"), temperature=0.6)
        msg = str(draft.get("message_en", "")).strip()
        tip = str(draft.get("tip_cn", "")).strip()
        action = str(draft.get("action", "继续跟进"))
        self.fs.update_record(S.T_LEADS, r["record_id"], {S.F_FOLLOW_DRAFT: f"{msg}\n\n💡 {tip}"})
        return {"record_id": r["record_id"], "company": text_of(f.get(S.F_COMPANY)),
                "country": text_of(f.get(S.F_COUNTRY)), "level": text_of(f.get(S.F_LEVEL)),
                "count": count, "days": days, "message": msg, "tip": tip, "action": action}

    def draft_followup(self, record_id: str) -> dict:
        return self._draft(self.fs.get_record(S.T_LEADS, record_id))

    def _push_followup_card(self, results: list[dict], to_quote: list[dict]) -> None:
        today = self.now().strftime("%m月%d日")
        if not results and not to_quote:
            self._safe_card(f"☀️ {today} 跟进提醒", "今天没有需要跟进的客户，可以专心开发新客户 💪", template="green")
            return
        lines = []
        if results:
            lines.append(f"**今天要跟进 {len(results)} 位客户**（按意向等级排序）\n")
            for i, x in enumerate(results, 1):
                flag = " ⚠️建议止损" if x["action"] == "建议止损" else ""
                lines.append(f"**{i}. {x['company']}**（{x['country'] or '国家未知'} · {x['level']}级 · "
                             f"第{x['count'] + 1}次跟进 · 已{x['days']}天未联系）{flag}\n"
                             f"💡 {x['tip']}\n> {x['message']}\n")
        if to_quote:
            names = "、".join(text_of(r["fields"].get(S.F_COMPANY)) for r in to_quote[:10])
            lines.append(f"\n**还有 {len(to_quote)} 个A/B级新询盘没报价**：{names}")
        lines.append(f"\n跟进完后，在表格里勾选「{S.F_FOLLOWED_BTN}」，系统会自动排好下次跟进时间。")
        self._safe_card(f"☀️ {today} 跟进提醒", "\n".join(lines), template="blue",
                        button=("打开客户表", self.cfg.bitable_url))

    # ------------------------------------------------------- 4. 记录已跟进
    def mark_followed(self, record_id: str, operator: str = "") -> None:
        rec = self.fs.get_record(S.T_LEADS, record_id)
        f = rec["fields"]
        count = int(num_of(f.get(S.F_FOLLOW_COUNT))) + 1
        level = text_of(f.get(S.F_LEVEL)) or "B"
        now_ms = ms(time.time())
        draft = text_of(f.get(S.F_FOLLOW_DRAFT))
        today = self.now().strftime("%Y-%m-%d")
        updates = {
            S.F_FOLLOW_COUNT: count,
            S.F_LAST_AT: now_ms,
            S.F_FOLLOWED_BTN: False,
            S.F_FOLLOW_DRAFT: None,
            S.F_CHAT_LOG: (text_of(f.get(S.F_CHAT_LOG)) + f"\n[{today}] 第{count}次跟进：{draft.split(chr(10))[0][:200]}").strip(),
        }
        if count >= MAX_FOLLOWUPS:
            updates[S.F_STATUS] = "已流失"
            updates[S.F_NEXT_AT] = None
        else:
            updates[S.F_STATUS] = "跟进中"
            updates[S.F_NEXT_AT] = now_ms + next_interval(level, count) * 86400 * 1000
        self.fs.update_record(S.T_LEADS, record_id, updates)
        self.fs.create_record(S.T_FOLLOWUPS, {"客户公司": text_of(f.get(S.F_COMPANY)), "跟进时间": now_ms,
                                              "第几次跟进": count, "使用的话术": draft, "线索ID": record_id,
                                              "操作人": operator})

    # ------------------------------------------------------ 轮询：复选框触发
    def process_checkboxes(self) -> dict:
        done = {"quotes": 0, "followed": 0, "errors": 0}
        rows = self.fs.search(S.T_LEADS, field_names=[S.F_COMPANY, S.F_QUOTE_BTN, S.F_FOLLOWED_BTN])
        for r in rows:
            f = r["fields"]
            try:
                if f.get(S.F_QUOTE_BTN) is True:
                    self.generate_quote(r["record_id"])
                    done["quotes"] += 1
                if f.get(S.F_FOLLOWED_BTN) is True:
                    self.mark_followed(r["record_id"])
                    done["followed"] += 1
            except Exception as e:
                done["errors"] += 1
                log.exception("处理记录 %s 失败", r["record_id"])
                # 取消勾选并把错误写回表格，避免每30秒重复报错
                try:
                    self.fs.update_record(S.T_LEADS, r["record_id"], {
                        S.F_QUOTE_BTN: False, S.F_FOLLOWED_BTN: False,
                        S.F_QUOTE_EMAIL: f"⚠️ 处理失败：{e}"})
                except Exception:
                    pass
        return done

    def _safe_card(self, title: str, md: str, template: str = "blue", button=None) -> None:
        try:
            self.fs.send_card(title, md, template=template, button=button)
        except Exception as e:
            log.warning("群推送失败：%s", e)
