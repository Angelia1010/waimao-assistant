"""HTTP 服务（只用 Python 标准库）：
- GET  /                      产品展示页（公开，无需 token）
- GET  /health                健康检查
- GET  /paste?token=...       手动粘贴询盘的网页（阿里国际站 / WhatsApp / 展会）
- POST /api/inquiry           粘贴询盘入库
- POST /hooks/quote           生成报价单 {"record_id": "..."}（可给飞书自动化调用）
- POST /hooks/followed        记录已跟进 {"record_id": "..."}
- POST /hooks/daily           立即生成今日跟进提醒并推送
- POST /hooks/check-mail      立即收一次邮件
鉴权：请求头 X-Token 或 URL 参数 ?token= 必须等于 .env 的 API_TOKEN
"""
from __future__ import annotations

import html
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import schema as S

log = logging.getLogger(__name__)

LANDING_PAGE = Path(__file__).resolve().parent / "static" / "index.html"

PASTE_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>录入询盘 · 外贸AI助手</title>
<style>
:root{{--c:#1F3A5F}}*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#F4F6FA;color:#1d2433}}
.wrap{{max-width:720px;margin:32px auto;padding:0 16px}}
.card{{background:#fff;border-radius:14px;padding:28px;box-shadow:0 2px 14px rgba(20,40,80,.08)}}
h1{{font-size:22px;margin:0 0 6px;color:var(--c)}}p.sub{{margin:0 0 20px;color:#667085;font-size:14px}}
label{{display:block;font-size:13px;font-weight:600;margin:14px 0 6px;color:#344054}}
textarea,select,input{{width:100%;border:1px solid #D0D5DD;border-radius:10px;padding:12px;font-size:15px;font-family:inherit}}
textarea{{min-height:240px;resize:vertical}}
button{{margin-top:18px;width:100%;background:var(--c);color:#fff;border:0;border-radius:10px;padding:14px;font-size:16px;font-weight:600;cursor:pointer}}
.msg{{margin-bottom:16px;padding:12px 14px;border-radius:10px;font-size:14px}}
.ok{{background:#ECFDF3;color:#05603A}}.err{{background:#FEF3F2;color:#B42318}}.info{{background:#EFF4FF;color:#1D3E8A}}
</style></head><body><div class="wrap"><div class="card">
<h1>录入一条询盘</h1><p class="sub">把阿里国际站、WhatsApp、展会名片或任何渠道的询盘原文粘贴进来，AI会自动提取信息、打分级，写进客户表。</p>
{msg}
<form method="post" action="/api/inquiry?token={token}">
<label>来源</label><select name="source">{options}</select>
<label>客户邮箱或联系方式（可选）</label><input name="sender" placeholder="例如 john@abc-trading.com">
<label>询盘原文</label><textarea name="text" required placeholder="直接粘贴客户发来的英文原文…"></textarea>
<button type="submit">交给AI处理</button></form></div></div></body></html>"""


def make_handler(assistant, worker):
    cfg = assistant.cfg

    class Handler(BaseHTTPRequestHandler):
        server_version = "WaimaoAssistant/1.0"

        def log_message(self, fmt, *args):  # 统一走 logging
            log.info("%s - %s", self.address_string(), fmt % args)

        # ------------------------------------------------------------ helpers
        def _query(self) -> dict:
            return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _authed(self) -> bool:
            token = self.headers.get("X-Token") or self._query().get("token", "")
            return bool(cfg.api_token) and token == cfg.api_token

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8") if n else ""
            if "application/json" in (self.headers.get("Content-Type") or ""):
                return json.loads(raw or "{}")
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def _send(self, code: int, payload, content_type="application/json; charset=utf-8"):
            data = payload if isinstance(payload, bytes) else (
                payload.encode("utf-8") if isinstance(payload, str) else
                json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _page(self, msg_html: str = "", code: int = 200):
            options = "".join(f'<option value="{s}">{s}</option>' for s in S.SOURCES if s != "邮箱")
            token = html.escape(self._query().get("token", ""))
            self._send(code, PASTE_PAGE.format(msg=msg_html, token=token, options=options),
                       "text/html; charset=utf-8")

        # --------------------------------------------------------------- GET
        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                page = LANDING_PAGE.read_text("utf-8").replace("{{CONTACT}}", html.escape(cfg.landing_contact))
                return self._send(200, page, "text/html; charset=utf-8")
            if path == "/health":
                return self._send(200, {"ok": True, "feishu": cfg.feishu_enabled, "mail": cfg.mail_enabled})
            if path == "/paste":
                if not self._authed():
                    return self._send(401, "token 错误", "text/plain; charset=utf-8")
                return self._page()
            return self._send(404, {"error": "not found"})

        # -------------------------------------------------------------- POST
        def do_POST(self):
            path = urlparse(self.path).path
            if not self._authed():
                return self._send(401, {"error": "token 错误"})
            try:
                body = self._body()
            except Exception:
                return self._send(400, {"error": "请求体格式错误"})
            is_form = "application/json" not in (self.headers.get("Content-Type") or "")
            try:
                with worker.lock:
                    if path == "/api/inquiry":
                        text = (body.get("text") or "").strip()
                        if not text:
                            raise ValueError("询盘内容为空")
                        rid = assistant.ingest_text(text, source=body.get("source") or "其他",
                                                    sender=body.get("sender", ""))
                        if is_form:
                            msg = ('<div class="msg ok">✅ 已写入客户表，去飞书看看AI的分级吧。</div>' if rid else
                                   '<div class="msg info">AI 判断这不是采购询盘（像推广或垃圾信息），没有入库。</div>')
                            return self._page(msg)
                        return self._send(200, {"record_id": rid, "is_inquiry": bool(rid)})
                    if path == "/hooks/quote":
                        return self._send(200, assistant.generate_quote(body["record_id"]))
                    if path == "/hooks/followed":
                        assistant.mark_followed(body["record_id"])
                        return self._send(200, {"ok": True})
                    if path == "/hooks/daily":
                        res = assistant.daily_followups(push=True)
                        return self._send(200, {"count": len(res), "items": res})
                    if path == "/hooks/check-mail":
                        return self._send(200, {"new_inquiries": worker.check_mail()})
                return self._send(404, {"error": "not found"})
            except Exception as e:
                log.exception("处理 %s 失败", path)
                if is_form and path == "/api/inquiry":
                    return self._page(f'<div class="msg err">处理失败：{html.escape(str(e))}</div>', 500)
                return self._send(500, {"error": str(e)})

    return Handler


def serve(assistant, worker) -> None:
    cfg = assistant.cfg
    httpd = ThreadingHTTPServer((cfg.server_host, cfg.server_port), make_handler(assistant, worker))
    log.info("HTTP 服务已启动：http://%s:%s  （粘贴询盘页面：/paste?token=你的API_TOKEN）",
             cfg.server_host, cfg.server_port)
    httpd.serve_forever()
