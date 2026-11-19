"""本地假飞书开放平台（仅用于联调测试脚本）：python tests/mock_feishu_server.py 9900"""
from __future__ import annotations

import itertools
from email.parser import BytesParser
from email.policy import default
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TABLES: dict[str, dict] = {}       # table_id -> {"name":..., "fields":[...], "records":{rid: fields}}
CARDS: list[dict] = []
FILES: dict[str, bytes] = {}
ids = itertools.count(1)


def seg(v):
    return [{"type": "text", "text": v}] if isinstance(v, str) else v


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _ok(self, data=None):
        self._json({"code": 0, "msg": "success", "data": data or {}})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self):
        return self.headers.get("Authorization") == "Bearer t-mock"

    def do_GET(self):
        p = self.path.split("?")[0]
        if not self._auth():
            return self._json({"code": 99991663, "msg": "invalid token"})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/(\w+)/tables", p):
            return self._ok({"items": [{"name": t["name"], "table_id": tid} for tid, t in TABLES.items()],
                             "has_more": False})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/fields", p):
            return self._ok({"items": TABLES[m[1]]["fields"], "has_more": False})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/records/(\w+)", p):
            f = TABLES[m[1]]["records"][m[2]]
            return self._ok({"record": {"record_id": m[2], "fields": {k: seg(v) for k, v in f.items()}}})
        self._json({"code": 404, "msg": p}, 404)

    def do_PUT(self):
        p = self.path.split("?")[0]
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/records/(\w+)", p):
            rec = TABLES[m[1]]["records"][m[2]]
            for k, v in json.loads(self._body())["fields"].items():
                if v is None:
                    rec.pop(k, None)
                else:
                    rec[k] = v
            return self._ok({"record": {"record_id": m[2]}})
        self._json({"code": 404}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/open-apis/auth/v3/tenant_access_token/internal":
            b = json.loads(self._body())
            if b.get("app_secret") != "secret":
                return self._json({"code": 10014, "msg": "app secret invalid"})
            return self._json({"code": 0, "tenant_access_token": "t-mock", "expire": 7200})
        if p.startswith("/open-apis/bot/v2/hook/"):
            CARDS.append(json.loads(self._body()))
            return self._json({"code": 0, "msg": "success"})
        if p == "/open-apis/__cards":
            return self._ok({"cards": CARDS, "tables": {t["name"]: t["records"] for t in TABLES.values()}})
        if not self._auth():
            return self._json({"code": 99991663, "msg": "invalid token"})
        if p == "/open-apis/drive/v1/medias/upload_all":
            raw = b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + self._body()
            msg = BytesParser(policy=default).parsebytes(raw)
            form = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                    for part in msg.iter_parts()}
            assert form["parent_type"] == b"bitable_file"
            data = form["file"]
            assert int(form["size"]) == len(data)
            tok = f"box{next(ids)}"
            FILES[tok] = data
            return self._ok({"file_token": tok})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables", p):
            t = json.loads(self._body())["table"]
            tid = f"tbl{next(ids)}"
            TABLES[tid] = {"name": t["name"], "fields": t["fields"], "records": {}}
            return self._ok({"table_id": tid})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/fields", p):
            TABLES[m[1]]["fields"].append(json.loads(self._body()))
            return self._ok({})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/records", p):
            rid = f"rec{next(ids)}"
            TABLES[m[1]]["records"][rid] = json.loads(self._body())["fields"]
            return self._ok({"record": {"record_id": rid}})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/records/batch_create", p):
            out = []
            for r in json.loads(self._body())["records"]:
                rid = f"rec{next(ids)}"
                TABLES[m[1]]["records"][rid] = r["fields"]
                out.append({"record_id": rid})
            return self._ok({"records": out})
        if m := re.fullmatch(r"/open-apis/bitable/v1/apps/\w+/tables/(\w+)/records/search", p):
            body = json.loads(self._body() or b"{}")
            names = body.get("field_names")
            items = []
            for rid, f in TABLES[m[1]]["records"].items():
                ff = {k: seg(v) for k, v in f.items() if (not names or k in names)}
                items.append({"record_id": rid, "fields": ff})
            return self._ok({"items": items, "has_more": False, "total": len(items)})
        self._json({"code": 404, "msg": p}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
