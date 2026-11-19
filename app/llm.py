"""大模型调用。支持任何 OpenAI 兼容接口（DeepSeek、通义千问、Kimi、智谱等），
另外提供一个不联网的 mock 模式，用于本地测试和没有 API Key 时的演示。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from . import prompts

log = logging.getLogger(__name__)


def parse_json(text: str) -> dict:
    """容错解析：去掉 ```json 包裹、截取第一个 {...}。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


class LLM:
    def chat(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        last_err: Exception | None = None
        for _ in range(2):
            try:
                return parse_json(self.chat(system, user, json_mode=True, temperature=temperature))
            except Exception as e:  # 解析失败重试一次
                last_err = e
        raise RuntimeError(f"大模型返回的 JSON 无法解析: {last_err}")


class OpenAICompatibleLLM(LLM):
    def __init__(self, base_url: str, api_key: str, model: str):
        base = base_url.rstrip("/")
        self.url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        self.api_key = api_key
        self.model = model

    def chat(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(3):
            try:
                r = requests.post(self.url, json=body, timeout=90,
                                  headers={"Authorization": f"Bearer {self.api_key}"})
                if r.status_code == 400 and json_mode and "response_format" in body:
                    body.pop("response_format")  # 部分模型不支持 json_object，退回普通模式
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                log.warning("调用大模型失败（第%d次）: %s", attempt + 1, e)
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("大模型连续调用失败，请检查 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL")


# ---------------------------------------------------------------------- mock
_COUNTRY_HINTS = {
    ".de": "德国", "germany": "德国", "+49": "德国", ".fr": "法国", "france": "法国", "+33": "法国",
    ".co.uk": "英国", "united kingdom": "英国", " uk": "英国", "+44": "英国", ".it": "意大利", "+39": "意大利",
    ".es": "西班牙", "spain": "西班牙", ".com.au": "澳大利亚", "australia": "澳大利亚", "+61": "澳大利亚",
    ".ca": "加拿大", "canada": "加拿大", "usa": "美国", "united states": "美国", "+1 ": "美国",
    ".com.br": "巴西", "brazil": "巴西", ".mx": "墨西哥", "mexico": "墨西哥", ".ae": "阿联酋", "dubai": "阿联酋",
    "saudi": "沙特", ".sa": "沙特", ".pl": "波兰", "poland": "波兰", ".nl": "荷兰", "netherlands": "荷兰",
    "chile": "智利", ".cl": "智利", "thailand": "泰国", ".th": "泰国", "vietnam": "越南", ".vn": "越南",
}
_FREE_MAIL = ("gmail.", "yahoo.", "hotmail.", "outlook.", "163.com", "qq.com", "aol.", "mail.ru")
_SPAM_WORDS = ("seo", "website design", "backlink", "unsubscribe", "promotion", "lottery", "verify your account",
               "google ranking", "digital marketing", "invoice overdue")


class MockLLM(LLM):
    """规则版“大模型”：不联网，用于测试和演示。效果不如真模型，但流程完全一致。"""

    def chat(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        if system == prompts.INQUIRY_SYSTEM:
            return json.dumps(self._inquiry(user), ensure_ascii=False)
        if system == prompts.QUOTE_ITEMS_SYSTEM:
            return json.dumps(self._quote_items(user), ensure_ascii=False)
        if system == prompts.QUOTE_EMAIL_SYSTEM:
            return self._quote_email(user)
        if system == prompts.FOLLOWUP_SYSTEM:
            return json.dumps(self._followup(user), ensure_ascii=False)
        return "{}"

    @staticmethod
    def _section(user: str, start: str, end: str | None = None) -> str:
        s = user.split(start, 1)[1] if start in user else ""
        if end and end in s:
            s = s.split(end, 1)[0]
        return s.strip()

    def _catalog(self, user: str) -> list[dict]:
        cat = self._section(user, "目录】", "【")
        rows = []
        for line in cat.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[0]:
                rows.append({"model": parts[0], "name": parts[1], "moq": parts[-1] if len(parts) >= 4 else ""})
        return rows

    def _inquiry(self, user: str) -> dict:
        sender = self._section(user, "发件人:", "主题:")
        subject = self._section(user, "主题:", "正文:")
        body = self._section(user, "正文:", "请输出 JSON")
        text = f"{sender}\n{subject}\n{body}"
        low = text.lower()
        email_m = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", sender) or re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", body)
        email = email_m.group(0) if email_m else ""
        if any(w in low for w in _SPAM_WORDS):
            return {"is_inquiry": False, "company": "", "contact": "", "email": email, "country": "", "products": "",
                    "quantity": "", "budget": "", "summary": "推广/垃圾邮件", "level": "C", "level_reason": "非询盘"}
        country = next((v for k, v in _COUNTRY_HINTS.items() if k in low), "")
        name_m = re.search(r"^\s*([A-Z][^<\n]+?)\s*<", sender)
        contact = name_m.group(1).strip() if name_m else ""
        comp_m = re.search(r"\n\s*([A-Z][\w&.,' -]+(?:GmbH|Ltd\.?|LLC|Inc\.?|S\.?A\.?S?|S\.?r\.?l\.?|Pty Ltd|B\.V\.|Co\.?|Trading|Group|Supplies|Import))",
                           body)
        company = comp_m.group(1).strip() if comp_m else ""
        if not company:
            from_m = re.search(r"\bfrom ([A-Z][\w&.' -]{2,40}?)[,.\n]", body)
            company = from_m.group(1).strip() if from_m else ""
        if not contact:
            iam = re.search(r"\b(?:I am|I'm|this is) ([A-Z][a-z]+)", body)
            contact = iam.group(1) if iam else ""
        if not company and email and not any(f in email for f in _FREE_MAIL):
            company = email.split("@")[1].split(".")[0].title()
        body_low = body.lower()
        models = [c["model"] for c in self._catalog(user) if c["model"].lower() in low]
        names = [c["name"] for c in self._catalog(user) if c["name"] and c["name"].lower() in low]
        products = "、".join(models or names)
        per_model = []
        for mdl in models:
            q = re.search(re.escape(mdl.lower()) + r"[^\d\n]{0,25}(\d[\d,]*)", body_low)
            if q:
                per_model.append(f"{mdl}: {q.group(1)}")
        qty_m = re.search(r"(\d[\d,\.]*\s*(?:k\b|pcs|pieces|pairs|units|sets|cartons|ctns|tons|containers?)[\w']*)",
                          body_low)
        quantity = "; ".join(per_model) if per_model else (qty_m.group(1) if qty_m else "")
        price_m = re.search(r"((?:target|budget|price)[^\n]{0,40}?(?:usd|\$|eur|€)\s?\d[\d.,]*\d(?:/\w+)?"
                            r"(?:\s+(?:FOB|CIF|DDP|EXW)\s+[A-Z][a-z]+)?)", body, flags=re.I)
        budget = price_m.group(1).strip() if price_m else ""
        detail_signals = sum([bool(budget), "deliver" in low or "lead time" in low or "by " in low,
                              "ce" in low.split() or "certificate" in low or "fob" in low or "cif" in low or "ddp" in low,
                              bool(email) and not any(f in email for f in _FREE_MAIL)])
        if (models or names) and quantity and detail_signals >= 1:
            level, reason = "A", "产品和数量明确，并给出了价格/交期/条款等细节"
        elif (models or names) or ("quotation" in low and len(body) > 200):
            level, reason = "B", "产品方向明确，但数量或细节不全，需要追问"
        else:
            level, reason = "C", "只索要目录或价格表，需求不具体"
        bits = [f"询问{products or '产品目录/价格'}"]
        if quantity:
            bits.append(f"数量{quantity}")
        if budget:
            bits.append(f"价格要求：{budget}")
        if "sample" in low:
            bits.append("提到样品")
        if "fob" in low or "cif" in low or "ddp" in low:
            bits.append("提到贸易条款")
        return {"is_inquiry": True, "company": company, "contact": contact, "email": email, "country": country,
                "products": products, "quantity": quantity, "budget": budget, "summary": "，".join(bits) + "。",
                "level": level, "level_reason": reason}

    def _quote_items(self, user: str) -> dict:
        catalog = self._catalog(user)
        products = self._section(user, "询盘产品:", "需求数量:").lower()
        qty_text = self._section(user, "需求数量:", "需求摘要:")
        qty_m = re.search(r"[\d][\d,\.]*", qty_text)
        default_qty = float(qty_m.group(0).replace(",", "")) if qty_m else 0
        if "k" in qty_text.lower() and default_qty < 1000:
            default_qty *= 1000
        items = []
        for c in catalog:
            if c["model"].lower() in products or (c["name"] and c["name"].lower() in products):
                own = re.search(re.escape(c["model"]) + r":\s*([\d,]+)", qty_text)
                qty = float(own.group(1).replace(",", "")) if own else default_qty
                moq = float(re.sub(r"[^\d.]", "", c["moq"]) or 0)
                q = max(qty, moq) if qty else moq
                items.append({"model": c["model"], "qty": int(q), "note": "MOQ applied" if qty and qty < moq else ""})
        if not items and catalog:
            c = catalog[0]
            items.append({"model": c["model"], "qty": int(float(re.sub(r"[^\d.]", "", c["moq"]) or 100)), "note": ""})
        summary = self._section(user, "需求摘要:", "【").lower()
        remarks = []
        if "cif" in summary or "ddp" in summary:
            remarks.append("CIF/DDP price will be confirmed after checking the latest freight rate.")
        if "样品" in summary or "sample" in summary:
            remarks.append("Samples can be sent within 3 days; courier cost to be paid by buyer.")
        return {"items": items[:8], "unmatched": "", "remarks": remarks}

    def _quote_email(self, user: str) -> str:
        contact = re.search(r'start with "Dear (.+?),"', user)
        sig = re.search(r'Sign off as "(.+?)"', user)
        return (f"Dear {contact.group(1) if contact else 'Sir/Madam'},\n\n"
                "Thank you for your inquiry. Please find attached our quotation based on the quantities you mentioned. "
                "All items are produced in our own factory with 100% inspection before shipment, and we can keep the "
                "lead time within the schedule you need.\n\n"
                "To prepare the samples correctly, which packing do you prefer: bulk carton or retail box?\n\n"
                f"Best regards,\n{sig.group(1) if sig else 'Sales Team'}")

    def _followup(self, user: str) -> dict:
        count = int(re.search(r"已经跟进次数: (\d+)", user).group(1)) if "已经跟进次数" in user else 0
        contact = self._section(user, "联系人:", "意向等级:") or "there"
        if count >= 4:
            return {"message_en": f"Hi {contact}, I understand you may have chosen another supplier or the project is on "
                                  "hold. I will close this file for now so I don't keep bothering you. If anything changes, "
                                  "just reply 'yes' and I will update the price for you right away.",
                    "tip_cn": "已跟进多次无回复，发一封礼貌的“最后确认”邮件，然后转入低频维护。",
                    "action": "建议止损"}
        msgs = [
            (f"Hi {contact}, hope you had time to check our quotation. Our production slot for next month is filling up — "
             "would you like me to reserve capacity for you, or is it still at the internal review stage?",
             "第一次跟进：轻松提醒，用产能排期制造一点紧迫感，问题二选一。"),
            (f"Hi {contact}, a quick update: we can send 2 free samples (you only cover express cost) so your team can "
             "check the quality first. Shall I prepare them in the standard version or with your logo?",
             "第二次跟进：提供免费样品这个新价值，降低客户决策门槛。"),
            (f"Hi {contact}, if the full quantity is too much for a first order, we can accept a trial order at 50% of MOQ "
             "with the same unit price. Would a smaller trial work better for you?",
             "第三次跟进：主动降低试单门槛，看是不是数量或预算卡住了客户。"),
        ]
        m, tip = msgs[min(count, 2)]
        return {"message_en": m, "tip_cn": tip, "action": "继续跟进"}


def build_llm(cfg) -> LLM:
    if cfg.llm_provider == "mock" or not cfg.llm_api_key:
        log.warning("使用 mock 大模型（规则版）。正式使用请在 .env 配置 LLM_API_KEY")
        return MockLLM()
    return OpenAICompatibleLLM(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
