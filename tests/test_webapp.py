"""网页系统端到端测试：真实 HTTP 服务 + SQLite + 规则版大模型。"""
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import schema as S
from app.config import Config
from app.db import SqliteStore
from app.demo import history_rows, load_products_csv
from app.llm import MockLLM
from app.pipeline import Assistant
from app.server import make_handler
from app.store import State
from app.worker import Worker

GERMANY = open("demo/emails/01_germany_A.txt", encoding="utf-8").read().split("\n\n", 1)[1]
SPAM = open("demo/emails/04_spam.txt", encoding="utf-8").read().split("\n\n", 1)[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, method, path, body=None, ctype="application/json", raw=False):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", ctype)
        try:
            resp = self.op.open(r)
            content = resp.read()
            return resp.status, (content if raw else json.loads(content or b"{}")), resp.headers
        except urllib.error.HTTPError as e:
            content = e.read()
            try:
                return e.code, json.loads(content), e.headers
            except ValueError:
                return e.code, content, e.headers

    def login(self, u, p):
        return self.req("POST", "/api/login", {"username": u, "password": p})


@pytest.fixture
def srv(tmp_path):
    cfg = Config()
    cfg.data_dir = str(tmp_path)
    cfg.storage = "sqlite"
    cfg.api_token = "tok-legacy"
    store = SqliteStore(cfg.data_dir)
    store.batch_create(S.T_PRODUCTS, load_products_csv())
    store.create_user("boss", "王总", "boss-pass", "admin")
    store.create_user("lily", "Lily", "lily-pass", "sales")
    a = Assistant(cfg, store, MockLLM(), State(cfg.data_dir))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(a, Worker(a)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, a, store
    httpd.shutdown()


def test_pages_and_auth(srv):
    base, a, store = srv
    c = Client(base)
    code, page, _ = c.req("GET", "/app", raw=True)
    assert code == 200 and b"/app/static/app.js" in page
    for f in ("app.js", "app.css"):
        assert c.req("GET", "/app/static/" + f, raw=True)[0] == 200
    assert c.req("GET", "/app/static/..%2Fdb.py", raw=True)[0] == 404
    assert c.req("GET", "/api/me")[0] == 401
    assert c.req("GET", "/api/leads")[0] == 401
    code, d, _ = c.login("lily", "wrong")
    assert code == 401 and "错误" in d["error"]
    code, d, h = c.login("lily", "lily-pass")
    assert code == 200 and d["user"]["role"] == "sales"
    assert "HttpOnly" in h["Set-Cookie"] and "SameSite=Lax" in h["Set-Cookie"]
    assert c.req("GET", "/api/me")[1]["user"]["name"] == "Lily"
    # 改数据必须是 JSON（挡住跨站表单）
    assert c.req("POST", "/api/leads", b"text=hi", ctype="application/x-www-form-urlencoded")[0] == 415
    # 业务员不能进管理员接口
    assert c.req("GET", "/api/users")[0] == 403
    assert c.req("PUT", "/api/settings", {"values": {}})[0] == 403
    c.req("POST", "/api/logout", {})
    assert c.req("GET", "/api/me")[0] == 401


def test_login_rate_limit(srv):
    base, *_ = srv
    c = Client(base)
    for _ in range(10):
        c.login("boss", "nope")
    assert c.login("boss", "boss-pass")[0] == 429


def test_full_sales_flow(srv):
    base, a, store = srv
    c = Client(base)
    c.login("lily", "lily-pass")
    # 录入询盘
    code, d, _ = c.req("POST", "/api/leads", {"text": GERMANY, "source": "阿里国际站"})
    assert code == 200 and d["is_inquiry"]
    lead = d["lead"]
    assert lead["level"] == "A" and lead["country"] == "德国" and lead["owner"] == "Lily"
    assert lead["source"] == "阿里国际站" and lead["status"] == "新询盘"
    lid = lead["id"]
    # 垃圾信息不入库
    assert c.req("POST", "/api/leads", {"text": SPAM})[1] == {"is_inquiry": False}
    assert c.req("POST", "/api/leads", {"text": "hi"})[0] == 400
    # 列表与筛选
    assert c.req("GET", "/api/leads")[1]["total"] == 1
    assert c.req("GET", "/api/leads?level=B")[1]["total"] == 0
    assert c.req("GET", "/api/leads?q=nordbau&mine=1")[1]["total"] == 1
    # 还没报价不能标记已跟进
    assert c.req("POST", f"/api/leads/{lid}/followed", {})[0] == 400
    # 生成报价单
    code, q, _ = c.req("POST", f"/api/leads/{lid}/quote", {})
    assert code == 200 and q["total"] == pytest.approx(5000 * 2.35 + 8000 * 0.86)
    assert q["lead"]["status"] == "已报价" and q["lead"]["quote_url"] == q["url"]
    code, pdf, h = c.req("GET", q["url"], raw=True)
    assert code == 200 and pdf[:4] == b"%PDF" and h["Content-Type"] == "application/pdf"
    assert "attachment" in c.req("GET", q["url"] + "?download=1", raw=True)[2]["Content-Disposition"]
    assert Client(base).req("GET", q["url"], raw=True)[0] == 401  # 没登录不能下载
    quotes = c.req("GET", "/api/quotes")[1]["items"]
    assert len(quotes) == 1 and quotes[0]["lead_id"] == lid
    # 写跟进话术、标记已跟进
    code, dr, _ = c.req("POST", f"/api/leads/{lid}/draft", {})
    assert code == 200 and dr["lead"]["follow_draft"]
    code, l2, _ = c.req("POST", f"/api/leads/{lid}/followed", {})
    assert l2["follow_count"] == 1 and l2["status"] == "跟进中" and not l2["follow_draft"]
    detail = c.req("GET", f"/api/leads/{lid}")[1]
    assert detail["followups"][0]["by"] == "Lily" and detail["quotes"][0]["no"].startswith("Q")
    # 编辑、备注、改日期
    code, l3, _ = c.req("PATCH", f"/api/leads/{lid}", {"status": "已寄样", "qty": "6000 pairs", "next_at": "2030-01-02",
                                                       "follow_count": 99})
    assert l3["status"] == "已寄样" and l3["qty"] == "6000 pairs" and l3["follow_count"] == 1
    assert "状态改为「已寄样」" in l3["chat_log"]
    assert c.req("PATCH", f"/api/leads/{lid}", {"level": "Z"})[0] == 400
    assert c.req("PATCH", f"/api/leads/{lid}", {"next_at": "明天"})[0] == 400
    l4 = c.req("POST", f"/api/leads/{lid}/note", {"text": "客户说下周确认颜色"})[1]
    assert "Lily] 客户说下周确认颜色" in l4["chat_log"]
    # 业务员不能删客户
    assert c.req("DELETE", f"/api/leads/{lid}")[0] == 403
    assert c.req("GET", "/api/leads/recDOESNOTEXIST")[0] == 404


def test_dashboard(srv):
    base, a, store = srv
    store.batch_create(S.T_LEADS, history_rows())
    c = Client(base)
    c.login("boss", "boss-pass")
    c.req("POST", "/api/leads", {"text": GERMANY})
    d = c.req("GET", "/api/dashboard")[1]
    assert d["metrics"]["due_today"] == 3 and d["metrics"]["to_quote"] == 1
    assert [x["level"] for x in d["due"]] == ["A", "B", "B"]
    assert d["levels"]["A"] == 2 and d["statuses"]["跟进中"] == 2
    assert c.req("GET", "/api/dashboard?mine=1")[1]["metrics"]["to_quote"] == 1
    # 管理员触发每日提醒 → 站内提醒
    assert c.req("POST", "/api/tasks/daily", {})[1]["count"] == 3
    notes = c.req("GET", "/api/notifications")[1]["items"]
    assert any("跟进提醒" in n["title"] for n in notes) and any("A级" in n["title"] for n in notes)


def test_products(srv):
    base, a, store = srv
    c = Client(base)
    c.login("lily", "lily-pass")
    items = c.req("GET", "/api/products")[1]["items"]
    assert len(items) == 8
    code, p, _ = c.req("POST", "/api/products", {"model": "NEW-1", "name": "Hook", "price": "1.5", "moq": 100})
    assert code == 200 and p["price"] == 1.5
    assert c.req("POST", "/api/products", {"model": "new-1"})[0] == 400  # 型号重复（忽略大小写）
    assert c.req("POST", "/api/products", {"model": "X", "price": "-1"})[0] == 400
    assert c.req("PUT", f"/api/products/{p['id']}", {"model": "NEW-1", "price": 2})[1]["price"] == 2
    csv_text = "﻿型号,产品名称,规格描述,单价,起订量,交期(天),包装,备注\nNEW-1,Hook v2,,3,100,10,,\nNEW-2,Rail,,4,50,12,,\n"
    assert c.req("POST", "/api/products/import", {"csv": csv_text})[1] == {"added": 1, "updated": 1}
    bad = "型号,单价\nZ,abc\n"
    code, d, _ = c.req("POST", "/api/products/import", {"csv": bad})
    assert code == 400 and "第 2 行" in d["error"]
    assert c.req("DELETE", f"/api/products/{p['id']}")[0] == 200
    assert len(c.req("GET", "/api/products")[1]["items"]) == 9


def test_settings_and_users(srv):
    base, a, store = srv
    c = Client(base)
    c.login("boss", "boss-pass")
    code, s, _ = c.req("PUT", "/api/settings", {"values": {"company_name_en": "Ningbo Star Demo Co.",
                                                           "quote_validity_days": "45", "evil": "x"}})
    assert code == 200 and s["values"]["company_name_en"] == "Ningbo Star Demo Co."
    assert a.cfg.quote_validity_days == 45 and store.get_settings()["company_name_en"] == "Ningbo Star Demo Co."
    assert "evil" not in store.get_settings()
    assert c.req("PUT", "/api/settings", {"values": {"followup_time": "25:00"}})[0] == 400
    assert c.req("PUT", "/api/settings", {"values": {"feishu_bot_webhook": "http://evil.example"}})[0] == 400
    assert c.req("POST", "/api/settings/test-push", {})[0] == 200
    # 成员管理
    code, u, _ = c.req("POST", "/api/users", {"username": "tom", "name": "Tom", "password": "tom-pass", "role": "sales"})
    assert code == 200 and u["role"] == "sales"
    assert c.req("POST", "/api/users", {"username": "tom", "name": "T2", "password": "xxxxxx"})[0] == 400
    assert c.req("POST", "/api/users", {"username": "a b", "name": "x", "password": "xxxxxx"})[0] == 400
    assert c.req("POST", "/api/users", {"username": "sam", "name": "x", "password": "123"})[0] == 400
    me = c.req("GET", "/api/me")[1]["user"]
    assert c.req("PATCH", f"/api/users/{me['id']}", {"active": False})[0] == 400  # 不能停用自己
    tom = Client(base)
    assert tom.login("tom", "tom-pass")[0] == 200
    c.req("PATCH", f"/api/users/{u['id']}", {"active": False})
    assert tom.req("GET", "/api/me")[0] == 401  # 停用后会话立刻失效
    assert Client(base).login("tom", "tom-pass")[0] == 401
    # 业务员看不到飞书密钥
    lily = Client(base)
    lily.login("lily", "lily-pass")
    assert "feishu_bot_secret" not in lily.req("GET", "/api/settings")[1]["values"]


def _fake_llm_server(good_key="sk-good-key-123456"):
    """一个最小的 OpenAI 兼容接口：密钥对返回 JSON，密钥错返回 401。"""
    from http.server import BaseHTTPRequestHandler
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body["model"])
            if self.headers.get("Authorization") != f"Bearer {good_key}":
                self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":{"message":"bad key"}}'); return
            if self.path != "/v1/chat/completions":
                self.send_response(404); self.end_headers(); return
            sys_prompt = body["messages"][0]["content"]
            content = '{"ok": true}' if "只输出 JSON" in sys_prompt and "ok" in body["messages"][1]["content"] else \
                json.dumps({"is_inquiry": True, "company": "Real Model Co", "level": "A", "summary": "真模型返回",
                            "country": "德国", "products": "DS-450", "quantity": "5000", "level_reason": "x"})
            out = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}/v1", calls


def test_llm_and_feishu_config_page(srv, monkeypatch):
    base, a, store = srv
    from app.llm import MockLLM, OpenAICompatibleLLM
    fake, url, calls = _fake_llm_server()
    try:
        c = Client(base)
        c.login("boss", "boss-pass")
        s = c.req("GET", "/api/settings")[1]
        assert s["status"]["llm_ready"] is False and s["secrets"]["llm_api_key"] == ""
        assert [p["id"] for p in s["presets"]] == ["deepseek", "qwen", "custom"]
        # 测试连接：错误密钥 → 明确提示
        code, d, _ = c.req("POST", "/api/settings/test-llm", {"values": {"llm_base_url": url, "llm_model": "m1",
                                                                          "llm_api_key": "sk-wrong-key-999"}})
        assert code == 400 and "密钥无效" in d["error"]
        code, d, _ = c.req("POST", "/api/settings/test-llm", {"values": {"llm_base_url": url + "/xx", "llm_model": "m1",
                                                                          "llm_api_key": "sk-good-key-123456"}})
        assert code == 400 and "404" in d["error"]
        assert c.req("POST", "/api/settings/test-llm", {"values": {"llm_base_url": url}})[0] == 400  # 缺密钥
        # 测试连接：正确 → 成功（还没保存，系统仍是演示模式）
        code, d, _ = c.req("POST", "/api/settings/test-llm", {"values": {"llm_base_url": url, "llm_model": "m1",
                                                                          "llm_api_key": "sk-good-key-123456"}})
        assert code == 200 and d["ok"] and isinstance(a.llm, MockLLM)
        # 只填密钥不填模型 → 拒绝
        assert c.req("PUT", "/api/settings", {"values": {"llm_base_url": "", "llm_model": "",
                                                         "llm_api_key": "sk-good-key-123456"}})[0] == 400
        a.cfg.llm_api_key = ""  # 上一步被拒绝，复原
        # 保存 → 立即切换到真模型，接口只返回掩码
        code, s, _ = c.req("PUT", "/api/settings", {"values": {"llm_base_url": url + "/", "llm_model": "m1",
                                                               "llm_api_key": "sk-good-key-123456"}})
        assert code == 200 and s["status"]["llm_ready"] and s["secrets"]["llm_api_key"] == "sk-****3456"
        assert "sk-good-key-123456" not in json.dumps(s)
        assert isinstance(a.llm, OpenAICompatibleLLM) and a.cfg.llm_base_url == url
        lead = c.req("POST", "/api/leads", {"text": GERMANY})[1]["lead"]
        assert lead["company"] == "Real Model Co" and lead["summary"] == "真模型返回"
        # 密钥留空 = 不修改；测试连接也会用已保存的密钥
        c.req("PUT", "/api/settings", {"values": {"llm_model": "m2", "llm_api_key": ""}})
        assert store.get_settings()["llm_api_key"] == "sk-good-key-123456" and a.cfg.llm_model == "m2"
        assert c.req("POST", "/api/settings/test-llm", {"values": {"llm_api_key": ""}})[0] == 200
        assert calls[-1] == "m2"
        # 业务员看不到任何密钥和地址
        lily = Client(base)
        lily.login("lily", "lily-pass")
        ls = lily.req("GET", "/api/settings")[1]
        assert "sk-" not in json.dumps(ls) and ls["values"]["llm_base_url"] == "已配置"
        assert lily.req("POST", "/api/settings/test-llm", {"values": {}})[0] == 403
        # 清除密钥 → 回到演示模式
        c.req("PUT", "/api/settings", {"values": {}, "clear": ["llm_api_key"]})
        assert isinstance(a.llm, MockLLM) and store.get_settings()["llm_api_key"] == ""
        # 重启后从数据库读取配置
        from app.main import build_assistant
        cfg2 = type(a.cfg)()
        cfg2.data_dir, cfg2.storage = a.cfg.data_dir, "sqlite"
        c.req("PUT", "/api/settings", {"values": {"llm_api_key": "sk-good-key-123456"}})
        assert isinstance(build_assistant(cfg2).llm, OpenAICompatibleLLM)
    finally:
        fake.shutdown()

    # 飞书：先用表单里的新地址测试，再保存
    sent = []
    monkeypatch.setattr("app.feishu.FeishuClient.send_card",
                        lambda self, title, md, template="blue", button=None: sent.append((self.bot_webhook, self.bot_secret, title)))
    hook = "https://open.feishu.cn/open-apis/bot/v2/hook/abc123"
    assert c.req("POST", "/api/settings/test-push", {"feishu_bot_webhook": "https://evil.example/x"})[0] == 400
    code, d, _ = c.req("POST", "/api/settings/test-push", {"feishu_bot_webhook": hook, "feishu_bot_secret": "sec-123456789"})
    assert code == 200 and d["where"] == "feishu" and sent[-1][:2] == (hook, "sec-123456789")
    s = c.req("PUT", "/api/settings", {"values": {"feishu_bot_webhook": hook, "feishu_bot_secret": "sec-123456789"}})[1]
    assert s["status"]["feishu_bot"] and s["secrets"]["feishu_bot_secret"] == "sec****6789"
    assert "feishu_bot_secret" not in s["values"]


def test_admin_can_delete_and_legacy_paste_still_works(srv):
    base, a, store = srv
    c = Client(base)
    c.login("boss", "boss-pass")
    lid = c.req("POST", "/api/leads", {"text": GERMANY})[1]["lead"]["id"]
    assert c.req("DELETE", f"/api/leads/{lid}")[0] == 200
    assert c.req("GET", f"/api/leads/{lid}")[0] == 404
    anon = Client(base)
    assert anon.req("GET", "/paste?token=tok-legacy", raw=True)[0] == 200
    code, d, _ = anon.req("POST", "/api/inquiry?token=tok-legacy", {"text": GERMANY, "source": "WhatsApp"})
    assert code == 200 and d["is_inquiry"]
