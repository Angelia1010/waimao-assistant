from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.feishu import FeishuClient, num_of, text_of
from app.llm import parse_json
from app.mailbox import parse_message


def test_text_of_variants():
    assert text_of([{"type": "text", "text": "ab"}, {"type": "text", "text": "c"}]) == "abc"
    assert text_of({"text": "x", "link": "y"}) == "x"
    assert text_of(None) == "" and text_of(3) == "3"
    assert num_of([{"type": "text", "text": "1,200"}]) == 1200
    assert num_of(None, 7) == 7


def test_parse_json_tolerant():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('好的：{"a": 2} 以上') == {"a": 2}


def test_parse_html_email_and_strip_quote():
    m = MIMEMultipart("alternative")
    m["From"] = "=?utf-8?b?5byg5LiJ?= <zs@abc-demo.com>"
    m["Subject"] = "=?utf-8?b?6K+i5Lu3?="
    m["Message-ID"] = "<abc@x>"
    m.attach(MIMEText("<p>Need 500 pcs<br>Thanks</p><div>On Mon, Jan 1 2026 Bob wrote:</div><p>old</p>", "html"))
    out = parse_message(m.as_bytes())
    assert out["sender_email"] == "zs@abc-demo.com" and out["sender"].startswith("张三")
    assert out["subject"] == "询价"
    assert "Need 500 pcs" in out["body"] and "old" not in out["body"]


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.text = payload, status, ""

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.token_calls = 0

    def post(self, url, json=None, data=None, files=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, data, files))
        if url.endswith("tenant_access_token/internal"):
            self.token_calls += 1
            return FakeResp({"code": 0, "tenant_access_token": f"t{self.token_calls}", "expire": 7200})
        if url.endswith("medias/upload_all"):
            return FakeResp({"code": 0, "data": {"file_token": "boxcnX"}})
        return FakeResp({"code": 0})

    def request(self, method, url, params=None, json=None, files=None, data=None, headers=None, timeout=None):
        self.calls.append((method, url, json, params, headers))
        if self.token_calls == 1 and "records/search" in url:  # 第一次模拟 token 过期
            return FakeResp({"code": 99991663, "msg": "token expired"})
        if url.endswith("/tables"):
            return FakeResp({"code": 0, "data": {"items": [{"name": "询盘客户", "table_id": "tblA"}]}})
        if "records/search" in url:
            return FakeResp({"code": 0, "data": {"items": [{"record_id": "r1", "fields": {"客户公司": "X"}}],
                                                 "has_more": False}})
        return FakeResp({"code": 0, "data": {"record": {"record_id": "r9"}}})


def test_feishu_client_paths_and_token_refresh(tmp_path):
    c = FeishuClient("id", "sec", "APPTOKEN")
    c.session = FakeSession()
    rows = c.search("询盘客户", field_names=["客户公司"])
    assert rows == [{"record_id": "r1", "fields": {"客户公司": "X"}}]
    assert c.session.token_calls == 2  # 过期后自动刷新一次
    search_call = [x for x in c.session.calls if "records/search" in x[1]][-1]
    assert "/bitable/v1/apps/APPTOKEN/tables/tblA/records/search" in search_call[1]
    assert search_call[2]["field_names"] == ["客户公司"]
    assert c.create_record("询盘客户", {"客户公司": "Y", "空": ""}) == "r9"
    create_call = c.session.calls[-1]
    assert create_call[2] == {"fields": {"客户公司": "Y"}}  # 空值被去掉
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    assert c.upload_attachment(pdf) == "boxcnX"
    up = [x for x in c.session.calls if x[1].endswith("upload_all")][0]
    assert up[3]["parent_type"] == "bitable_file" and up[3]["parent_node"] == "APPTOKEN"
    assert up[3]["size"] == str(len(b"%PDF-1.4 test"))
