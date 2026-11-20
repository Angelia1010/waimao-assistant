"""HTTP 服务（只用 Python 标准库）。

公开：
- GET  /                      产品展示页
- GET  /health                健康检查
网页系统（STORAGE=sqlite 时）：
- GET  /app                   登录后使用的操作系统
- /api/...                    JSON 接口，见 app/web.py
- GET  /files/<id>            下载报价单 PDF（需登录）
兼容旧版（用 API_TOKEN 鉴权，请求头 X-Token 或 ?token=）：
- GET  /paste                 手动粘贴询盘的网页
- POST /api/inquiry           粘贴询盘入库
- POST /hooks/quote | /hooks/followed | /hooks/daily | /hooks/check-mail
"""
from __future__ import annotations

import html
import json
import logging
import mimetypes
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import schema as S
from .web import Api, ApiError

log = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parent / "static"
LANDING_PAGE = STATIC / "index.html"
APP_DIR = STATIC / "app"
COOKIE = "wm_session"
MAX_BODY = 2 * 1024 * 1024
MAX_UPLOAD = 30 * 1024 * 1024  # 单证核对：最多 8 份、每份 5MB，base64 后约大 1/3

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
    api = Api(assistant, worker) if cfg.storage == "sqlite" else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "WaimaoAssistant/2.0"

        def log_message(self, fmt, *args):
            log.info("%s - %s", self.address_string(), fmt % args)

        # ------------------------------------------------------------ helpers
        def _query(self) -> dict:
            return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _token_ok(self) -> bool:
            token = self.headers.get("X-Token") or self._query().get("token", "")
            return bool(cfg.api_token) and cfg.api_token != "change-me" and token == cfg.api_token

        def _raw_body(self) -> str:
            n = int(self.headers.get("Content-Length") or 0)
            limit = MAX_UPLOAD if urlparse(self.path).path == "/api/doccheck" else MAX_BODY
            if n > limit:
                raise ApiError(413, "请求内容太大")
            return self.rfile.read(n).decode("utf-8") if n else ""

        def _is_json(self) -> bool:
            return "application/json" in (self.headers.get("Content-Type") or "")

        def _session(self) -> str:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c[COOKIE].value if COOKIE in c else ""

        def _send(self, code: int, payload, content_type="application/json; charset=utf-8", headers=None):
            data = payload if isinstance(payload, bytes) else (
                payload.encode("utf-8") if isinstance(payload, str) else
                json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _cookie_header(self, value: str, max_age: int) -> str:
            parts = [f"{COOKIE}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
            if cfg.cookie_secure:
                parts.append("Secure")
            return "; ".join(parts)

        def _static(self, path: Path, cache: bool = False):
            if not path.is_file():
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, path.read_bytes(), ctype,
                              {"Cache-Control": "public, max-age=300" if cache else "no-cache"})

        def _paste_page(self, msg_html: str = "", code: int = 200):
            options = "".join(f'<option value="{s}">{s}</option>' for s in S.SOURCES if s != "邮箱")
            token = html.escape(self._query().get("token", ""))
            self._send(code, PASTE_PAGE.format(msg=msg_html, token=token, options=options), "text/html; charset=utf-8")

        # --------------------------------------------------------------- GET
        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                page = LANDING_PAGE.read_text("utf-8").replace("{{CONTACT}}", html.escape(cfg.landing_contact))
                return self._send(200, page, "text/html; charset=utf-8")
            if path == "/health":
                return self._send(200, {"ok": True, "storage": cfg.storage, "mail": cfg.mail_enabled})
            if path == "/favicon.ico":
                svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" '
                       'fill="#4F8CFF"/><path d="M8 11l8 5 8-5M7 10h18v12H7z" fill="none" stroke="#0B1220" '
                       'stroke-width="2.4" stroke-linejoin="round"/></svg>')
                return self._send(200, svg, "image/svg+xml", {"Cache-Control": "public, max-age=86400"})
            if path in ("/app", "/app/"):
                if not api:
                    return self._send(200, "网页系统需要 STORAGE=sqlite。当前为飞书模式，请在飞书多维表格里操作。",
                                      "text/plain; charset=utf-8")
                return self._static(APP_DIR / "index.html")
            if path.startswith("/app/static/"):
                name = path.rsplit("/", 1)[-1]
                if not name or name.startswith(".") or "/" in path[len("/app/static/"):]:
                    return self._send(404, {"error": "not found"})
                return self._static(APP_DIR / name, cache=False)
            if path.startswith("/files/") and api:
                return self._file(path[len("/files/"):])
            if path == "/paste":
                if not self._token_ok():
                    return self._send(401, "token 错误", "text/plain; charset=utf-8")
                return self._paste_page()
            if path.startswith("/api/") and api:
                return self._api("GET", path)
            return self._send(404, {"error": "not found"})

        def _file(self, fid: str):
            user = api.store.session_user(self._session())
            if not user:
                return self._send(401, "请先登录", "text/plain; charset=utf-8")
            f = api.store.get_file(fid)
            if not f or not Path(f["path"]).is_file():
                return self._send(404, "文件不存在", "text/plain; charset=utf-8")
            disp = "attachment" if self._query().get("download") == "1" else "inline"
            return self._send(200, Path(f["path"]).read_bytes(), "application/pdf",
                              {"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(f['name'])}",
                               "Cache-Control": "private, no-store"})

        # -------------------------------------------------------------- API
        def _api(self, method: str, path: str):
            try:
                body = {}
                if method != "GET":
                    # 跨站表单只能发 POST（PUT/PATCH/DELETE 浏览器会先预检），所以 POST 必须是 JSON
                    raw = self._raw_body()
                    if method == "POST" and not self._is_json():
                        raise ApiError(415, "请求必须是 JSON")
                    if raw:
                        if not self._is_json():
                            raise ApiError(415, "请求必须是 JSON")
                        body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise ApiError(400, "请求体格式错误")
                token = self._session()
                user = api.store.session_user(token)
                code, payload = api.dispatch(method, path, self._query(), body, user, self.client_address[0])
                headers = {"Cache-Control": "no-store"}
                if isinstance(payload, dict) and "_set_session" in payload:
                    headers["Set-Cookie"] = self._cookie_header(payload.pop("_set_session"), 14 * 86400)
                if isinstance(payload, dict) and payload.pop("_clear_session", False):
                    if token:
                        api.store.delete_session(token)
                    headers["Set-Cookie"] = self._cookie_header("", 0)
                return self._send(code, payload, headers=headers)
            except ApiError as e:
                return self._send(e.status, {"error": e.msg})
            except json.JSONDecodeError:
                return self._send(400, {"error": "请求体不是合法的 JSON"})
            except Exception as e:
                log.exception("接口出错 %s %s", method, path)
                return self._send(500, {"error": f"服务器出错：{e}"})

        def do_PUT(self):
            path = urlparse(self.path).path
            if api and path.startswith("/api/"):
                return self._api("PUT", path)
            return self._send(404, {"error": "not found"})

        def do_PATCH(self):
            path = urlparse(self.path).path
            if api and path.startswith("/api/"):
                return self._api("PATCH", path)
            return self._send(404, {"error": "not found"})

        def do_DELETE(self):
            path = urlparse(self.path).path
            if api and path.startswith("/api/"):
                return self._api("DELETE", path)
            return self._send(404, {"error": "not found"})

        # -------------------------------------------------------------- POST
        def do_POST(self):
            path = urlparse(self.path).path
            legacy = path == "/api/inquiry" or path.startswith("/hooks/")
            if api and path.startswith("/api/") and not legacy:
                return self._api("POST", path)
            if not legacy:
                return self._send(404, {"error": "not found"})
            if not self._token_ok():
                return self._send(401, {"error": "token 错误"})
            is_form = not self._is_json()
            try:
                raw = self._raw_body()
                body = json.loads(raw or "{}") if not is_form else {k: v[0] for k, v in parse_qs(raw).items()}
            except Exception:
                return self._send(400, {"error": "请求体格式错误"})
            try:
                with worker.lock:
                    if path == "/api/inquiry":
                        text = (body.get("text") or "").strip()
                        if not text:
                            raise ValueError("询盘内容为空")
                        rid = assistant.ingest_text(text, source=body.get("source") or "其他",
                                                    sender=body.get("sender", ""))
                        if is_form:
                            msg = ('<div class="msg ok">✅ 已写入客户表。</div>' if rid else
                                   '<div class="msg info">AI 判断这不是采购询盘（像推广或垃圾信息），没有入库。</div>')
                            return self._paste_page(msg)
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
                    return self._paste_page(f'<div class="msg err">处理失败：{html.escape(str(e))}</div>', 500)
                return self._send(500, {"error": str(e)})

    return Handler


def serve(assistant, worker) -> None:
    cfg = assistant.cfg
    httpd = ThreadingHTTPServer((cfg.server_host, cfg.server_port), make_handler(assistant, worker))
    log.info("HTTP 服务已启动：http://%s:%s  （网页系统：/app）", cfg.server_host, cfg.server_port)
    httpd.serve_forever()
