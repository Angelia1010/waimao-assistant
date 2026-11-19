"""测试用的假飞书：数据存在内存里，返回格式模仿真实 search 接口（文本字段是片段数组）。"""
from __future__ import annotations

import itertools
from pathlib import Path

from app import schema as S


class FakeFeishu:
    def __init__(self):
        self.tables: dict[str, dict[str, dict]] = {name: {} for name in S.TABLES}
        self.cards: list[tuple[str, str]] = []
        self.uploads: list[str] = []
        self._ids = itertools.count(1)

    @staticmethod
    def _out(v):
        # 真实 search 接口把文本字段返回成 [{"type":"text","text":...}]
        if isinstance(v, str):
            return [{"type": "text", "text": v}]
        return v

    def table_id(self, name):
        assert name in self.tables, name
        return name

    def search(self, table, conditions=None, conjunction="and", field_names=None):
        out = []
        for rid, f in self.tables[table].items():
            fields = {k: self._out(v) for k, v in f.items() if v is not None and v != ""}
            if field_names:
                fields = {k: v for k, v in fields.items() if k in field_names}
            out.append({"record_id": rid, "fields": fields})
        return out

    def create_record(self, table, fields):
        rid = f"rec{next(self._ids)}"
        self.tables[table][rid] = {k: v for k, v in fields.items() if v not in (None, "")}
        return rid

    def batch_create(self, table, rows):
        return [self.create_record(table, r) for r in rows]

    def update_record(self, table, record_id, fields):
        rec = self.tables[table][record_id]
        for k, v in fields.items():
            if v is None:
                rec.pop(k, None)
            else:
                rec[k] = v

    def get_record(self, table, record_id):
        f = self.tables[table][record_id]
        return {"record_id": record_id, "fields": {k: self._out(v) for k, v in f.items()}}

    def upload_attachment(self, path):
        assert Path(path).exists() and Path(path).stat().st_size > 1000
        self.uploads.append(str(path))
        return f"file_{len(self.uploads)}"

    def send_card(self, title, markdown, template="blue", button=None):
        self.cards.append((title, markdown))

    # 便捷方法
    def leads(self):
        return list(self.tables[S.T_LEADS].values())

    def lead_by(self, company_part):
        for rid, f in self.tables[S.T_LEADS].items():
            if company_part.lower() in str(f.get(S.F_COMPANY, "")).lower():
                return rid, f
        raise KeyError(company_part)
