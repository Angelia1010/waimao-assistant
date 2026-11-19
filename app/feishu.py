"""飞书开放平台的最小客户端：多维表格读写、附件上传、群机器人推送。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


class FeishuError(RuntimeError):
    pass


def text_of(value: Any) -> str:
    """把多维表格返回的各种字段值统一转成纯文本。

    search 接口返回的文本字段是 [{"type":"text","text":"..."}] 这样的片段数组，
    普通字段可能是字符串、数字、或 {"text":..., "link":...}。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "是" if value else ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("link") or "")
    if isinstance(value, list):
        return "".join(text_of(v) for v in value)
    return str(value)


def num_of(value: Any, default: float = 0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(text_of(value).replace(",", "").strip())
    except ValueError:
        return default


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, app_token: str, base_url: str = "https://open.feishu.cn",
                 bot_webhook: str = "", bot_secret: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.base = base_url.rstrip("/") + "/open-apis"
        self.bot_webhook = bot_webhook
        self.bot_secret = bot_secret
        self._token = ""
        self._token_exp = 0.0
        self._table_ids: dict[str, str] = {}
        # 同一张表不支持并发写，所有写操作串行
        self._write_lock = threading.Lock()
        self.session = requests.Session()

    # ------------------------------------------------------------------ auth
    def _tenant_token(self, force: bool = False) -> str:
        if not force and self._token and time.time() < self._token_exp - 300:
            return self._token
        r = self.session.post(f"{self.base}/auth/v3/tenant_access_token/internal",
                              json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            raise FeishuError(f"获取 tenant_access_token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_exp = time.time() + int(data.get("expire", 7200))
        return self._token

    def _request(self, method: str, path: str, *, params: dict | None = None, json_body: Any = None,
                 files: dict | None = None, data: dict | None = None, write: bool = False) -> dict:
        def do(force: bool) -> dict:
            headers = {"Authorization": f"Bearer {self._tenant_token(force)}"}
            r = self.session.request(method, f"{self.base}{path}", params=params, json=json_body,
                                     files=files, data=data, headers=headers, timeout=30)
            try:
                return r.json()
            except ValueError:
                raise FeishuError(f"{method} {path} 返回非 JSON: HTTP {r.status_code} {r.text[:200]}")

        if write:
            with self._write_lock:
                resp = do(False)
                time.sleep(0.3)
        else:
            resp = do(False)
        if resp.get("code") in (99991663, 99991661, 99991668):  # token 失效，强制刷新后重试一次
            resp = do(True)
        if resp.get("code") != 0:
            raise FeishuError(f"{method} {path} 失败: code={resp.get('code')} msg={resp.get('msg')}")
        return resp.get("data") or {}

    # ---------------------------------------------------------------- tables
    def list_tables(self) -> dict[str, str]:
        out: dict[str, str] = {}
        page_token = None
        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"/bitable/v1/apps/{self.app_token}/tables", params=params)
            for t in data.get("items", []):
                out[t["name"]] = t["table_id"]
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        self._table_ids.update(out)
        return out

    def table_id(self, name: str) -> str:
        if name not in self._table_ids:
            self.list_tables()
        if name not in self._table_ids:
            raise FeishuError(f"多维表格里找不到数据表「{name}」，请先运行 scripts/setup_feishu.py")
        return self._table_ids[name]

    def create_table(self, name: str, fields: list[dict]) -> str:
        data = self._request("POST", f"/bitable/v1/apps/{self.app_token}/tables",
                             json_body={"table": {"name": name, "default_view_name": "全部", "fields": fields}},
                             write=True)
        tid = data["table_id"]
        self._table_ids[name] = tid
        return tid

    def list_fields(self, table: str) -> list[dict]:
        data = self._request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/fields",
                             params={"page_size": 100})
        return data.get("items", [])

    def create_field(self, table: str, field: dict) -> None:
        self._request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/fields",
                      json_body=field, write=True)

    # --------------------------------------------------------------- records
    def create_record(self, table: str, fields: dict) -> str:
        data = self._request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/records",
                             json_body={"fields": _clean(fields)}, write=True)
        return data["record"]["record_id"]

    def batch_create(self, table: str, rows: list[dict]) -> list[str]:
        ids: list[str] = []
        for i in range(0, len(rows), 500):
            chunk = [{"fields": _clean(r)} for r in rows[i:i + 500]]
            data = self._request("POST",
                                 f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/records/batch_create",
                                 json_body={"records": chunk}, write=True)
            ids += [r["record_id"] for r in data.get("records", [])]
        return ids

    def update_record(self, table: str, record_id: str, fields: dict) -> None:
        self._request("PUT",
                      f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/records/{record_id}",
                      json_body={"fields": _clean(fields, keep_none=True)}, write=True)

    def get_record(self, table: str, record_id: str) -> dict:
        data = self._request("GET",
                             f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/records/{record_id}")
        rec = data.get("record", {})
        return {"record_id": rec.get("record_id", record_id), "fields": rec.get("fields", {})}

    def search(self, table: str, conditions: list[dict] | None = None, conjunction: str = "and",
               field_names: list[str] | None = None) -> list[dict]:
        """返回 [{"record_id":..., "fields":{...}}]，自动翻页。"""
        body: dict[str, Any] = {"automatic_fields": False}
        if field_names:
            body["field_names"] = field_names
        if conditions:
            body["filter"] = {"conjunction": conjunction, "conditions": conditions}
        out: list[dict] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request("POST",
                                 f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id(table)}/records/search",
                                 params=params, json_body=body)
            for it in data.get("items", []) or []:
                out.append({"record_id": it["record_id"], "fields": it.get("fields", {})})
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        return out

    # ------------------------------------------------------------ attachment
    def upload_attachment(self, path: str | Path) -> str:
        """上传到当前多维表格，返回 file_token，用于写入附件字段。"""
        p = Path(path)
        content = p.read_bytes()
        with self._write_lock:
            headers = {"Authorization": f"Bearer {self._tenant_token()}"}
            r = self.session.post(
                f"{self.base}/drive/v1/medias/upload_all",
                headers=headers,
                data={"file_name": p.name, "parent_type": "bitable_file", "parent_node": self.app_token,
                      "size": str(len(content))},
                files={"file": (p.name, content, "application/pdf")},
                timeout=60,
            )
        data = r.json()
        if data.get("code") != 0:
            raise FeishuError(f"上传附件失败: {data}")
        return data["data"]["file_token"]

    # ------------------------------------------------------------------- bot
    def send_card(self, title: str, markdown: str, template: str = "blue", button: tuple[str, str] | None = None) -> None:
        if not self.bot_webhook:
            log.info("未配置群机器人，跳过推送：%s", title)
            return
        elements: list[dict] = [{"tag": "markdown", "content": markdown}]
        if button and button[1]:
            elements.append({"tag": "action", "actions": [{
                "tag": "button", "text": {"tag": "plain_text", "content": button[0]},
                "type": "primary", "url": button[1]}]})
        body: dict[str, Any] = {
            "msg_type": "interactive",
            "card": {"config": {"wide_screen_mode": True},
                     "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
                     "elements": elements},
        }
        if self.bot_secret:
            ts = str(int(time.time()))
            string_to_sign = f"{ts}\n{self.bot_secret}"
            sign = base64.b64encode(hmac.new(string_to_sign.encode(), b"", hashlib.sha256).digest()).decode()
            body.update({"timestamp": ts, "sign": sign})
        r = requests.post(self.bot_webhook, json=body, timeout=15)
        data = r.json()
        if data.get("code", data.get("StatusCode", 0)) != 0:
            raise FeishuError(f"群机器人推送失败: {data}")


def _clean(fields: dict, keep_none: bool = False) -> dict:
    """去掉空值，避免把空字符串写进单选等字段导致报错。更新时 None 表示清空。"""
    out = {}
    for k, v in fields.items():
        if v is None:
            if keep_none:
                out[k] = None
            continue
        if isinstance(v, str) and v == "" and not keep_none:
            continue
        out[k] = v
    return out


def ms(ts: float | None = None) -> int:
    """秒级时间戳 -> 飞书需要的毫秒时间戳"""
    return int((ts if ts is not None else time.time()) * 1000)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
