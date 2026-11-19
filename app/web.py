"""网页系统的 JSON 接口（只在 STORAGE=sqlite 时启用）。

鉴权：登录后浏览器带 HttpOnly 会话 Cookie；改数据的请求必须是 application/json（挡住跨站表单提交）。
角色：admin（老板/管理员）可以改设置、管成员、删客户；sales（业务员）可以处理询盘、报价、跟进、维护产品。
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime
from typing import Any, Callable

from . import schema as S
from .config import EDITABLE_SETTINGS, apply_settings
from .feishu import ms, num_of, text_of

LEAD_FIELDS = {  # 接口字段名 -> 表字段名
    "company": S.F_COMPANY, "contact": S.F_CONTACT, "email": S.F_EMAIL, "country": S.F_COUNTRY,
    "source": S.F_SOURCE, "products": S.F_PRODUCTS, "qty": S.F_QTY, "budget": S.F_BUDGET,
    "summary": S.F_SUMMARY, "level": S.F_LEVEL, "level_reason": S.F_LEVEL_REASON, "status": S.F_STATUS,
    "first_at": S.F_FIRST_AT, "last_at": S.F_LAST_AT, "next_at": S.F_NEXT_AT, "follow_count": S.F_FOLLOW_COUNT,
    "chat_log": S.F_CHAT_LOG, "quote_email": S.F_QUOTE_EMAIL, "follow_draft": S.F_FOLLOW_DRAFT,
    "owner": S.F_OWNER, "raw": S.F_RAW,
}
LEAD_EDITABLE = {"company", "contact", "email", "country", "source", "products", "qty", "budget", "summary",
                 "level", "status", "owner", "next_at"}
PRODUCT_FIELDS = {"model": "型号", "name": "产品名称", "spec": "规格描述", "price": "单价", "moq": "起订量",
                  "lead_days": "交期(天)", "packing": "包装", "note": "备注"}


class ApiError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def _num_or_none(v):
    n = num_of(v, default=None) if v not in (None, "") else None
    return int(n) if isinstance(n, float) and n.is_integer() else n


def lead_out(rec: dict, full: bool = False) -> dict:
    f = rec["fields"]
    out: dict[str, Any] = {"id": rec["record_id"]}
    for k, col in LEAD_FIELDS.items():
        v = f.get(col)
        if k in ("first_at", "last_at", "next_at", "follow_count"):
            out[k] = _num_or_none(v)
        else:
            out[k] = text_of(v)
    files = f.get(S.F_QUOTE_FILE) or []
    out["quote_url"] = f"/files/{files[-1]['file_token']}" if files else ""
    if not full:
        for k in ("chat_log", "raw", "quote_email", "follow_draft", "level_reason"):
            out.pop(k, None)
        out["has_draft"] = bool(text_of(f.get(S.F_FOLLOW_DRAFT)))
    return out


def product_out(rec: dict) -> dict:
    f = rec["fields"]
    return {"id": rec["record_id"], "model": text_of(f.get("型号")), "name": text_of(f.get("产品名称")),
            "spec": text_of(f.get("规格描述")), "price": num_of(f.get("单价")), "moq": num_of(f.get("起订量")),
            "lead_days": int(num_of(f.get("交期(天)"))), "packing": text_of(f.get("包装")),
            "note": text_of(f.get("备注"))}


def parse_date_ms(v, tz) -> int | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(hour=9, tzinfo=tz)
        return int(dt.timestamp() * 1000)
    raise ApiError(400, "日期格式应为 YYYY-MM-DD")


class Api:
    def __init__(self, assistant, worker):
        self.a = assistant
        self.store = assistant.fs
        self.worker = worker
        self.cfg = assistant.cfg
        self.routes: list[tuple[str, re.Pattern, Callable, str]] = []
        self._fails: dict[str, list[float]] = {}
        r = self.route
        r("POST", r"/api/login", self.login, "public")
        r("POST", r"/api/logout", self.logout, "public")
        r("GET", r"/api/me", self.me, "user")
        r("GET", r"/api/dashboard", self.dashboard, "user")
        r("GET", r"/api/leads", self.leads, "user")
        r("POST", r"/api/leads", self.lead_create, "user")
        r("GET", r"/api/leads/(?P<id>rec\w+)", self.lead_get, "user")
        r("PATCH", r"/api/leads/(?P<id>rec\w+)", self.lead_patch, "user")
        r("DELETE", r"/api/leads/(?P<id>rec\w+)", self.lead_delete, "admin")
        r("POST", r"/api/leads/(?P<id>rec\w+)/quote", self.lead_quote, "user")
        r("POST", r"/api/leads/(?P<id>rec\w+)/draft", self.lead_draft, "user")
        r("POST", r"/api/leads/(?P<id>rec\w+)/followed", self.lead_followed, "user")
        r("POST", r"/api/leads/(?P<id>rec\w+)/note", self.lead_note, "user")
        r("GET", r"/api/products", self.products, "user")
        r("POST", r"/api/products", self.product_create, "user")
        r("PUT", r"/api/products/(?P<id>rec\w+)", self.product_update, "user")
        r("DELETE", r"/api/products/(?P<id>rec\w+)", self.product_delete, "user")
        r("POST", r"/api/products/import", self.product_import, "user")
        r("GET", r"/api/quotes", self.quotes, "user")
        r("GET", r"/api/notifications", self.notifications, "user")
        r("GET", r"/api/settings", self.settings_get, "user")
        r("PUT", r"/api/settings", self.settings_put, "admin")
        r("POST", r"/api/settings/test-push", self.test_push, "admin")
        r("POST", r"/api/tasks/check-mail", self.task_mail, "user")
        r("POST", r"/api/tasks/daily", self.task_daily, "admin")
        r("GET", r"/api/users", self.users, "admin")
        r("POST", r"/api/users", self.user_create, "admin")
        r("PATCH", r"/api/users/(?P<uid>\d+)", self.user_update, "admin")

    def route(self, method: str, pattern: str, fn: Callable, level: str) -> None:
        self.routes.append((method, re.compile(pattern + r"$"), fn, level))

    def dispatch(self, method: str, path: str, query: dict, body: dict, user: dict | None, ip: str) -> tuple[int, Any]:
        allowed = False
        for m, pat, fn, level in self.routes:
            mt = pat.match(path)
            if not mt:
                continue
            allowed = True
            if m != method:
                continue
            if level != "public" and not user:
                raise ApiError(401, "请先登录")
            if level == "admin" and user["role"] != "admin":
                raise ApiError(403, "只有管理员可以操作")
            return fn(user=user, query=query, body=body, ip=ip, **mt.groupdict())
        raise ApiError(405 if allowed else 404, "接口不存在")

    # ----------------------------------------------------------------- auth
    def login(self, body, ip, **_):
        now = time.time()
        fails = [t for t in self._fails.get(ip, []) if now - t < 600]
        if len(fails) >= 10:
            raise ApiError(429, "失败次数太多，请 10 分钟后再试")
        u = self.store.authenticate(str(body.get("username", "")), str(body.get("password", "")))
        if not u:
            fails.append(now)
            self._fails[ip] = fails
            raise ApiError(401, "用户名或密码错误")
        self._fails.pop(ip, None)
        return 200, {"user": u, "_set_session": self.store.create_session(u["id"])}

    def logout(self, **_):
        return 200, {"ok": True, "_clear_session": True}

    def me(self, user, **_):
        return 200, {"user": user, "company": self.cfg.company_name_en}

    # ------------------------------------------------------------ dashboard
    def _all_leads(self) -> list[dict]:
        return [lead_out(r) for r in self.store.search(S.T_LEADS)]

    def dashboard(self, user, query, **_):
        leads = self._all_leads()
        if query.get("mine") == "1":
            leads = [x for x in leads if x["owner"] == user["name"]]
        end_today = self.a.end_of_today_ms()
        now_ms = ms(time.time())
        week_ago = now_ms - 7 * 86400000
        rank = {"A": 0, "B": 1, "C": 2}
        due = [x for x in leads if x["status"] in S.ACTIVE_STATUSES and x["next_at"] and x["next_at"] <= end_today]
        due.sort(key=lambda x: (rank.get(x["level"], 3), x["next_at"]))
        drafts = {r["record_id"]: text_of(r["fields"].get(S.F_FOLLOW_DRAFT)) for r in
                  self.store.search(S.T_LEADS, field_names=[S.F_FOLLOW_DRAFT])}
        for x in due:
            x["follow_draft"] = drafts.get(x["id"], "")
            x["days"] = max(0, int((now_ms - (x["last_at"] or now_ms)) / 86400000))
        to_quote = [x for x in leads if x["status"] == "新询盘" and x["level"] in ("A", "B")]
        to_quote.sort(key=lambda x: (rank.get(x["level"], 3), -(x["first_at"] or 0)))
        open_leads = [x for x in leads if x["status"] != "已流失"]
        return 200, {
            "metrics": {
                "due_today": len(due), "to_quote": len(to_quote),
                "week_new": sum(1 for x in leads if (x["first_at"] or 0) >= week_ago),
                "won": sum(1 for x in leads if x["status"] == "已成交"),
            },
            "levels": {lv: sum(1 for x in open_leads if x["level"] == lv) for lv in S.LEVELS},
            "statuses": {st: sum(1 for x in leads if x["status"] == st) for st in S.STATUSES},
            "due": due, "to_quote": to_quote[:8],
            "recent": sorted(leads, key=lambda x: -(x["first_at"] or 0))[:6],
        }

    # ---------------------------------------------------------------- leads
    def leads(self, user, query, **_):
        items = self._all_leads()
        q = (query.get("q") or "").strip().lower()
        if q:
            items = [x for x in items if q in " ".join(str(x[k]) for k in
                     ("company", "contact", "email", "country", "products", "summary")).lower()]
        if query.get("status"):
            items = [x for x in items if x["status"] == query["status"]]
        if query.get("level"):
            items = [x for x in items if x["level"] == query["level"]]
        if query.get("mine") == "1":
            items = [x for x in items if x["owner"] == user["name"]]
        if query.get("due") == "1":
            end = self.a.end_of_today_ms()
            items = [x for x in items if x["status"] in S.ACTIVE_STATUSES and x["next_at"] and x["next_at"] <= end]
        items.sort(key=lambda x: -(x["first_at"] or 0))
        return 200, {"items": items, "total": len(items)}

    def _lead(self, lead_id: str) -> dict:
        try:
            return self.store.get_record(S.T_LEADS, lead_id)
        except KeyError:
            raise ApiError(404, "客户不存在")

    def lead_get(self, id, **_):
        rec = self._lead(id)
        out = lead_out(rec, full=True)
        out["followups"] = sorted(
            [{"at": num_of(r["fields"].get("跟进时间")), "n": int(num_of(r["fields"].get("第几次跟进"))),
              "text": text_of(r["fields"].get("使用的话术")), "by": text_of(r["fields"].get("操作人"))}
             for r in self.store.search(S.T_FOLLOWUPS) if text_of(r["fields"].get("线索ID")) == id],
            key=lambda x: -x["at"])
        out["quotes"] = sorted(
            [{"no": text_of(r["fields"].get("报价单号")), "at": num_of(r["fields"].get("报价日期")),
              "total": num_of(r["fields"].get("金额合计")), "currency": text_of(r["fields"].get("币种")),
              "url": f"/files/{(r['fields'].get('PDF') or [{}])[0].get('file_token', '')}"}
             for r in self.store.search(S.T_QUOTES) if text_of(r["fields"].get("线索ID")) == id],
            key=lambda x: -x["at"])
        return 200, out

    def lead_create(self, user, body, **_):
        text = str(body.get("text") or "").strip()
        if len(text) < 10:
            raise ApiError(400, "请粘贴完整的询盘内容")
        if len(text) > 20000:
            raise ApiError(400, "内容太长了，请只粘贴询盘本身")
        source = body.get("source") if body.get("source") in S.SOURCES else "其他"
        rid = self.a.ingest_text(text, source=source, sender=str(body.get("sender") or "")[:200], owner=user["name"])
        if not rid:
            return 200, {"is_inquiry": False}
        return 200, {"is_inquiry": True, "lead": lead_out(self._lead(rid), full=True)}

    def lead_patch(self, id, user, body, **_):
        self._lead(id)
        updates: dict[str, Any] = {}
        for k, v in body.items():
            if k not in LEAD_EDITABLE:
                continue
            if k == "level" and v not in S.LEVELS:
                raise ApiError(400, "等级只能是 A/B/C")
            if k == "status" and v not in S.STATUSES:
                raise ApiError(400, "状态不正确")
            if k == "source" and v not in S.SOURCES:
                raise ApiError(400, "来源不正确")
            if k == "next_at":
                v = parse_date_ms(v, self.a.tz)
            elif isinstance(v, str):
                v = v.strip()[:2000]
            updates[LEAD_FIELDS[k]] = v
        if "company" in body and not str(body["company"]).strip():
            raise ApiError(400, "客户公司不能为空")
        if updates:
            if S.F_STATUS in updates:
                log = text_of(self._lead(id)["fields"].get(S.F_CHAT_LOG))
                updates[S.F_CHAT_LOG] = (log + f"\n[{self.a.now():%Y-%m-%d} {user['name']}] 状态改为「{updates[S.F_STATUS]}」").strip()
            self.store.update_record(S.T_LEADS, id, updates)
        return 200, lead_out(self._lead(id), full=True)

    def lead_delete(self, id, **_):
        self._lead(id)
        self.store.delete_record(S.T_LEADS, id)
        return 200, {"ok": True}

    def lead_quote(self, id, **_):
        self._lead(id)
        try:
            res = self.a.generate_quote(id)
        except RuntimeError as e:
            raise ApiError(400, str(e))
        return 200, {"quote_no": res["quote_no"], "total": res["total"], "email": res["email"],
                     "url": f"/files/{res['file_token']}", "lead": lead_out(self._lead(id), full=True)}

    def lead_draft(self, id, **_):
        self._lead(id)
        res = self.a.draft_followup(id)
        return 200, {"draft": res, "lead": lead_out(self._lead(id), full=True)}

    def lead_followed(self, id, user, **_):
        rec = self._lead(id)
        if text_of(rec["fields"].get(S.F_STATUS)) == "新询盘":
            raise ApiError(400, "还没有报价，请先生成报价单")
        self.a.mark_followed(id, operator=user["name"])
        return 200, lead_out(self._lead(id), full=True)

    def lead_note(self, id, user, body, **_):
        rec = self._lead(id)
        text = str(body.get("text") or "").strip()
        if not text:
            raise ApiError(400, "内容不能为空")
        log = text_of(rec["fields"].get(S.F_CHAT_LOG))
        line = f"[{self.a.now():%Y-%m-%d} {user['name']}] {text[:2000]}"
        self.store.update_record(S.T_LEADS, id, {S.F_CHAT_LOG: (log + "\n" + line).strip(), S.F_LAST_AT: ms()})
        return 200, lead_out(self._lead(id), full=True)

    # ------------------------------------------------------------- products
    def products(self, **_):
        items = [product_out(r) for r in self.store.search(S.T_PRODUCTS)]
        items.sort(key=lambda x: x["model"])
        return 200, {"items": items}

    def _product_fields(self, body: dict) -> dict:
        model = str(body.get("model") or "").strip()
        if not model:
            raise ApiError(400, "型号不能为空")
        out = {"型号": model}
        for k in ("name", "spec", "packing", "note"):
            out[PRODUCT_FIELDS[k]] = str(body.get(k) or "").strip()[:500]
        for k in ("price", "moq", "lead_days"):
            try:
                v = float(body.get(k) or 0)
            except (TypeError, ValueError):
                raise ApiError(400, f"{PRODUCT_FIELDS[k]} 必须是数字")
            if v < 0:
                raise ApiError(400, f"{PRODUCT_FIELDS[k]} 不能是负数")
            out[PRODUCT_FIELDS[k]] = v
        return out

    def _model_taken(self, model: str, except_id: str = "") -> bool:
        return any(text_of(r["fields"].get("型号")).lower() == model.lower() and r["record_id"] != except_id
                   for r in self.store.search(S.T_PRODUCTS))

    def product_create(self, body, **_):
        f = self._product_fields(body)
        if self._model_taken(f["型号"]):
            raise ApiError(400, "这个型号已经存在")
        rid = self.store.create_record(S.T_PRODUCTS, f)
        return 200, product_out(self.store.get_record(S.T_PRODUCTS, rid))

    def product_update(self, id, body, **_):
        try:
            self.store.get_record(S.T_PRODUCTS, id)
        except KeyError:
            raise ApiError(404, "产品不存在")
        f = self._product_fields(body)
        if self._model_taken(f["型号"], except_id=id):
            raise ApiError(400, "这个型号已经存在")
        self.store.update_record(S.T_PRODUCTS, id, f)
        return 200, product_out(self.store.get_record(S.T_PRODUCTS, id))

    def product_delete(self, id, **_):
        self.store.delete_record(S.T_PRODUCTS, id)
        return 200, {"ok": True}

    def product_import(self, body, **_):
        text = str(body.get("csv") or "")
        if not text.strip():
            raise ApiError(400, "CSV 内容为空")
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        need = {"型号", "单价"}
        if not reader.fieldnames or not need <= set(h.strip() for h in reader.fieldnames):
            raise ApiError(400, "CSV 第一行必须包含：型号,产品名称,规格描述,单价,起订量,交期(天),包装,备注")
        existing = {text_of(r["fields"].get("型号")).lower(): r["record_id"] for r in self.store.search(S.T_PRODUCTS)}
        added = updated = 0
        for i, row in enumerate(reader, start=2):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if not row.get("型号"):
                continue
            try:
                f = self._product_fields({"model": row.get("型号"), "name": row.get("产品名称"),
                                          "spec": row.get("规格描述"), "price": row.get("单价") or 0,
                                          "moq": row.get("起订量") or 0, "lead_days": row.get("交期(天)") or 0,
                                          "packing": row.get("包装"), "note": row.get("备注")})
            except ApiError as e:
                raise ApiError(400, f"第 {i} 行：{e.msg}")
            rid = existing.get(f["型号"].lower())
            if rid:
                self.store.update_record(S.T_PRODUCTS, rid, f)
                updated += 1
            else:
                existing[f["型号"].lower()] = self.store.create_record(S.T_PRODUCTS, f)
                added += 1
        return 200, {"added": added, "updated": updated}

    # --------------------------------------------------------------- quotes
    def quotes(self, **_):
        items = []
        for r in self.store.search(S.T_QUOTES):
            f = r["fields"]
            pdf = (f.get("PDF") or [{}])[0].get("file_token", "")
            items.append({"id": r["record_id"], "no": text_of(f.get("报价单号")), "company": text_of(f.get("客户公司")),
                          "at": num_of(f.get("报价日期")), "currency": text_of(f.get("币种")),
                          "total": num_of(f.get("金额合计")), "detail": text_of(f.get("报价明细")),
                          "lead_id": text_of(f.get("线索ID")), "url": f"/files/{pdf}" if pdf else ""})
        items.sort(key=lambda x: -x["at"])
        return 200, {"items": items}

    def notifications(self, **_):
        return 200, {"items": self.store.notifications()}

    # ------------------------------------------------------------- settings
    def settings_get(self, user, **_):
        values = {k: getattr(self.cfg, k) for k in EDITABLE_SETTINGS}
        if user["role"] != "admin":
            values.pop("feishu_bot_secret", None)
            values["feishu_bot_webhook"] = "已配置" if self.cfg.feishu_bot_webhook else ""
        from .llm import MockLLM
        return 200, {"values": values, "status": {
            "mail": f"{self.cfg.imap_user} @ {self.cfg.imap_host}" if self.cfg.mail_enabled else "",
            "llm": "演示模式（未配置大模型 Key）" if isinstance(self.a.llm, MockLLM) else self.cfg.llm_model,
            "feishu_bot": bool(self.cfg.feishu_bot_webhook),
        }}

    def settings_put(self, body, **_):
        try:
            clean = apply_settings(self.cfg, body.get("values") or {})
        except ValueError as e:
            raise ApiError(400, str(e))
        self.store.set_settings(clean)
        if self.store.bot_sender is not None:
            self.store.bot_sender.bot_webhook = self.cfg.feishu_bot_webhook
            self.store.bot_sender.bot_secret = self.cfg.feishu_bot_secret
        return self.settings_get(user={"role": "admin"})

    def test_push(self, **_):
        try:
            self.store.send_card("外贸订单助手连接成功", "这是一条测试提醒。", template="green")
        except Exception as e:
            raise ApiError(400, f"站内提醒已保存，但飞书推送失败：{e}")
        return 200, {"ok": True}

    def task_mail(self, **_):
        if not self.cfg.mail_enabled:
            raise ApiError(400, "还没有配置业务邮箱（.env 里的 IMAP_*）")
        with self.worker.lock:
            n = self.worker.check_mail()
        return 200, {"new_inquiries": n}

    def task_daily(self, **_):
        with self.worker.lock:
            res = self.a.daily_followups(push=True)
        return 200, {"count": len(res)}

    # ---------------------------------------------------------------- users
    def users(self, **_):
        return 200, {"items": self.store.list_users()}

    def user_create(self, body, **_):
        username = str(body.get("username") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            raise ApiError(400, "用户名 3–32 位，只能用字母、数字和 _ . -")
        try:
            uid = self.store.create_user(username, str(body.get("name") or ""), str(body.get("password") or ""),
                                         str(body.get("role") or "sales"))
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, self.store.get_user(uid)

    def user_update(self, uid, user, body, **_):
        uid = int(uid)
        if not self.store.get_user(uid):
            raise ApiError(404, "成员不存在")
        if uid == user["id"] and (body.get("active") is False or body.get("role") == "sales"):
            raise ApiError(400, "不能停用自己或取消自己的管理员身份")
        try:
            self.store.update_user(uid, name=body.get("name"), role=body.get("role"),
                                   active=body.get("active") if isinstance(body.get("active"), bool) else None,
                                   password=body.get("password") or None)
        except ValueError as e:
            raise ApiError(400, str(e))
        return 200, self.store.get_user(uid)
