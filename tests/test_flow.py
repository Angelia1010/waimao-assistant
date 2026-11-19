import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from app import schema as S
from app.config import Config
from app.demo import demo_emails, history_rows, load_products_csv
from app.llm import MockLLM
from app.pipeline import Assistant, next_interval
from app.store import State
from tests.fakes import FakeFeishu


@pytest.fixture
def env(tmp_path):
    cfg = Config()
    cfg.data_dir = str(tmp_path)
    cfg.api_token = "t0k"
    cfg.bitable_url = "https://example.feishu.cn/base/x"
    fs = FakeFeishu()
    fs.batch_create(S.T_PRODUCTS, load_products_csv())
    a = Assistant(cfg, fs, MockLLM(), State(cfg.data_dir))
    return a, fs


def test_products_csv_parses_inch_quotes():
    rows = load_products_csv()
    assert len(rows) == 8
    assert rows[0]["产品名称"].endswith('4"')
    assert rows[0]["单价"] == 0.86


def test_ingest_demo_emails(env):
    a, fs = env
    results = {m["subject"]: a.ingest(m) for m in demo_emails()}
    assert sum(1 for r in results.values() if r) == 4, results  # 垃圾邮件被跳过
    _, de = fs.lead_by("Nordbau")
    assert de[S.F_LEVEL] == "A" and de[S.F_COUNTRY] == "德国" and "DS-450" in de[S.F_PRODUCTS]
    assert de[S.F_STATUS] == "新询盘"
    _, au = fs.lead_by("Coastal")
    assert au[S.F_LEVEL] == "B"
    _, gm = fs.lead_by("gmail")
    assert gm[S.F_LEVEL] == "C"
    # A 级询盘立即推送
    assert any("A级" in t for t, _ in fs.cards)


def test_dedupe_by_message_id(env):
    a, fs = env
    m = demo_emails()[0]
    assert a.ingest(m)
    assert a.ingest(m) is None
    assert len(fs.leads()) == 1


def test_generate_quote_end_to_end(env, tmp_path):
    a, fs = env
    a.ingest(demo_emails()[0])
    rid, _ = fs.lead_by("Nordbau")
    res = a.generate_quote(rid)
    lead = fs.tables[S.T_LEADS][rid]
    assert lead[S.F_STATUS] == "已报价"
    assert lead[S.F_QUOTE_FILE] == [{"file_token": "file_1"}]
    assert lead[S.F_QUOTE_BTN] is False
    assert "Dear Klaus Weber" in lead[S.F_QUOTE_EMAIL]
    assert lead[S.F_NEXT_AT] > lead[S.F_LAST_AT]
    # 5000 * 2.35 + 8000 * 0.86
    assert res["total"] == pytest.approx(5000 * 2.35 + 8000 * 0.86)
    assert res["pdf"].endswith(".pdf") and "Nordbau" in res["pdf"]
    q = list(fs.tables[S.T_QUOTES].values())[0]
    assert q["报价单号"].startswith("Q") and q["金额合计"] == res["total"]


def test_checkbox_triggers_quote_with_moq(env):
    a, fs = env
    for m in demo_emails():
        a.ingest(m)
    rid, _ = fs.lead_by("HomeFix")
    fs.update_record(S.T_LEADS, rid, {S.F_QUOTE_BTN: True})
    done = a.process_checkboxes()
    assert done == {"quotes": 1, "followed": 0, "errors": 0}
    detail = list(fs.tables[S.T_QUOTES].values())[0]["报价明细"]
    assert "DS-500 × 1,000" in detail  # 客户要300，按起订量1000报


def test_checkbox_error_is_written_back(env):
    a, fs = env
    rid = fs.create_record(S.T_LEADS, {S.F_COMPANY: "Broken Demo", S.F_QUOTE_BTN: True})
    fs.tables[S.T_PRODUCTS].clear()
    done = a.process_checkboxes()
    assert done["errors"] == 1
    assert fs.tables[S.T_LEADS][rid][S.F_QUOTE_BTN] is False
    assert "处理失败" in fs.tables[S.T_LEADS][rid][S.F_QUOTE_EMAIL]


def test_daily_followups_and_mark_followed(env):
    a, fs = env
    fs.batch_create(S.T_LEADS, history_rows())
    a.ingest(demo_emails()[1])  # 一个未报价的B级新询盘
    res = a.daily_followups(push=True)
    assert [r["company"].split()[0] for r in res] == ["Lumière", "Gulf", "Polska"]  # A 级排最前
    polska = [r for r in res if r["company"].startswith("Polska")][0]
    assert polska["action"] == "建议止损"
    title, md = fs.cards[-1]
    assert "跟进提醒" in title and "今天要跟进 3 位客户" in md and "没报价" in md
    rid, lead = fs.lead_by("Gulf")
    assert lead[S.F_FOLLOW_DRAFT]
    a.mark_followed(rid)
    lead = fs.tables[S.T_LEADS][rid]
    assert lead[S.F_FOLLOW_COUNT] == 2 and lead[S.F_STATUS] == "跟进中"
    assert S.F_FOLLOW_DRAFT not in lead
    assert lead[S.F_NEXT_AT] - lead[S.F_LAST_AT] == next_interval("B", 2) * 86400000
    # 第5次跟进后自动标记流失
    rid_p, _ = fs.lead_by("Polska")
    a.mark_followed(rid_p)
    assert fs.tables[S.T_LEADS][rid_p][S.F_STATUS] == "已流失"
    assert len(fs.tables[S.T_FOLLOWUPS]) == 2


def test_empty_day_card(env):
    a, fs = env
    assert a.daily_followups(push=True) == []
    assert "没有需要跟进" in fs.cards[-1][1]


def test_worker_daily_push_once_per_day(env):
    from app.worker import Worker
    a, fs = env
    a.cfg.followup_time = "00:00"
    w = Worker(a)
    assert w.maybe_daily_push() is True
    assert w.maybe_daily_push() is False


def test_http_server(env):
    from http.server import ThreadingHTTPServer
    from app.server import make_handler
    from app.worker import Worker
    a, fs = env
    w = Worker(a)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(a, w))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        assert json.load(urllib.request.urlopen(base + "/health"))["ok"] is True
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/paste?token=wrong")
        assert e.value.code == 401
        page = urllib.request.urlopen(base + "/paste?token=t0k").read().decode()
        assert "录入一条询盘" in page and "WhatsApp" in page
        form = urllib.parse.urlencode({"source": "WhatsApp", "sender": "",
                                       "text": open("demo/whatsapp_chile.txt", encoding="utf-8").read()}).encode()
        resp = urllib.request.urlopen(base + "/api/inquiry?token=t0k", data=form).read().decode()
        assert "已写入客户表" in resp
        rid, lead = fs.lead_by("Andes")
        assert lead[S.F_SOURCE] == "WhatsApp" and lead[S.F_COUNTRY] == "智利" and lead[S.F_LEVEL] == "A"
        req = urllib.request.Request(base + "/hooks/quote", data=json.dumps({"record_id": rid}).encode(),
                                     headers={"Content-Type": "application/json", "X-Token": "t0k"})
        out = json.load(urllib.request.urlopen(req))
        # PH-160 客户要 2000，起订量 3000，按起订量报
        assert out["total"] == pytest.approx(3000 * 0.55 + 3000 * 0.68)
    finally:
        httpd.shutdown()
