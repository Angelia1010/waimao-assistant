"""单证核对：把 PI / 商业发票 / 装箱单 / 报关资料放在一起交叉比对。

思路：
1. 读文件：PDF（文字版）、Excel、CSV、TXT、Word。表格优先按表头识别列，标签字段（收货人、毛重…）按“标签: 值”识别。
2. 识别不出表格的单据，交给大模型抽取成同样的结构（演示模式下没有大模型，只走规则）。
3. 比对全部用代码做，不让大模型算数：同一型号的数量 / 单价 / 金额 / HS 编码，
   总金额、总箱数、总毛重 / 净重，收货人、币种、成交方式；再加单据内部的自检（净重>毛重、数量×单价≠金额、HS 位数）。
4. 每处问题给出各单据的值，并按“多数一致 + 明显错误”推断可能写错的是哪一份。
"""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import prompts

DOC_LABELS = {"PI": "PI", "CI": "商业发票", "PL": "装箱单", "CD": "报关资料", "OTHER": "其他单据"}
DOC_ORDER = ["PI", "CI", "PL", "CD", "OTHER"]
MAX_FILES = 8
MAX_FILE_BYTES = 5 * 1024 * 1024
TEXT_EXT = {".txt", ".csv", ".md"}
SUPPORTED_EXT = {".pdf", ".xlsx", ".xlsm", ".docx"} | TEXT_EXT

# 表头关键词 -> 列含义（按优先级匹配，先匹配更具体的）
COLUMN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("per_ctn", ("pcs/ctn", "qty/ctn", "每箱", "装箱率", "per ctn", "per carton")),
    ("unit_price", ("unit price", "单价", "price")),
    ("amount", ("amount", "总价", "金额", "total value", "value")),
    ("nw", ("n.w", "n. w", "net weight", "net wt", "净重")),
    ("gw", ("g.w", "g. w", "gross weight", "gross wt", "毛重")),
    ("cbm", ("cbm", "meas", "体积", "volume")),
    ("ctns", ("ctns", "cartons", "箱数", "件数", "packages", "pkgs")),
    ("hs", ("hs", "商品编号", "税号", "海关编码")),
    ("qty", ("qty", "quantity", "数量")),
    ("model", ("model", "item no", "item", "货号", "型号", "art", "code")),
    ("desc", ("description", "品名", "商品名称", "名称", "goods", "product")),
]
LABEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("consignee", ("consignee", "buyer", "messrs", "sold to", "境外收货人", "收货人", "买方")),
    ("currency", ("currency", "币制", "币种")),
    ("incoterm", ("trade term", "price term", "incoterm", "terms of delivery", "成交方式", "价格条款")),
    ("number", ("invoice no", "pi no", "proforma no", "no.", "发票号", "合同协议号", "编号")),
    ("gw", ("total g.w", "total gross", "gross weight", "毛重")),
    ("nw", ("total n.w", "total net", "net weight", "净重")),
    ("ctns", ("total ctns", "total cartons", "total packages", "件数", "总箱数")),
    ("amount", ("total amount", "总价合计", "总金额")),
]
INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
CURRENCIES = ("USD", "EUR", "GBP", "CNY", "RMB", "JPY", "AUD", "CAD")
_KNOWN_LABELS = sorted({w for _, ws in LABEL_RULES for w in ws} | {
    "date", "from", "to", "payment", "lead time", "shipping marks", "port of loading", "port of discharge",
    "country of origin", "运抵国", "指运港", "日期"}, key=len, reverse=True)
LABEL_SPLIT_RE = re.compile(r"(?i)(?<![A-Za-z])(" + "|".join(re.escape(w) for w in _KNOWN_LABELS) + r")[^:：\n]{0,10}?[:：]\s*")
MODEL_RE = re.compile(r"\b[A-Z]{1,4}-?\d{2,5}[A-Z]?\b")
NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass
class Doc:
    name: str
    kind: str = "OTHER"
    number: str = ""
    consignee: str = ""
    currency: str = ""
    incoterm: str = ""
    items: list[dict] = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    via: str = "规则"  # 规则 / 大模型
    error: str = ""

    @property
    def label(self) -> str:
        return DOC_LABELS.get(self.kind, "单据")


# --------------------------------------------------------------------- 读文件
def to_num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = NUM_RE.search(str(v).replace("，", ","))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def read_file(name: str, data: bytes) -> tuple[str, list[list[list[str]]]]:
    """返回（全文, 表格列表）。表格是行的列表，每行是单元格文字列表。"""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        import pdfplumber
        texts, tables = [], []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:10]:
                texts.append(page.extract_text() or "")
                for t in page.extract_tables() or []:
                    tables.append([[(c or "").strip() for c in row] for row in t])
        return "\n".join(texts), tables
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        rows_all, lines = [], []
        for ws in wb.worksheets[:5]:
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else (f"{c:g}" if isinstance(c, float) else str(c)).strip() for c in row]
                while cells and not cells[-1]:
                    cells.pop()
                if any(cells):
                    rows_all.append(cells)
                    lines.append(" | ".join(c for c in cells if c))
        return "\n".join(lines), [rows_all]
    if ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        tables = [[[c.text.strip() for c in r.cells] for r in t.rows] for t in d.tables]
        return "\n".join(p.text for p in d.paragraphs), tables
    if ext in TEXT_EXT:
        text = data.decode("utf-8", errors="replace")
        if ext == ".csv":
            rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
            return "\n".join(" | ".join(r) for r in rows), [rows]
        return text, []
    raise ValueError(f"暂不支持 {ext or '无扩展名'} 文件，请上传 PDF、Excel、Word 或 CSV")


# --------------------------------------------------------------------- 规则抽取
def detect_kind(text: str, name: str) -> str:
    t = (text[:3000] + " " + name).upper()
    if "PROFORMA" in t or re.search(r"\bPI\b", name.upper()) or "形式发票" in t:
        return "PI"
    if "PACKING" in t or "装箱单" in t:
        return "PL"
    if "报关" in t or "CUSTOMS DECLARATION" in t or "申报要素" in t:
        return "CD"
    if "INVOICE" in t or "发票" in t:
        return "CI"
    return "OTHER"


def _col_kind(header: str) -> str | None:
    h = header.lower().replace("\n", " ").strip()
    if not h:
        return None
    for kind, words in COLUMN_RULES:
        for w in words:
            if (w == "hs" and re.search(r"\bhs\b", h)) or (w != "hs" and w in h):
                return kind
    return None


def _parse_table(rows: list[list[str]]) -> tuple[list[dict], dict]:
    """找到表头行，按列含义取每行；“合计/TOTAL”行作为总计。"""
    header_idx, cols = -1, {}
    for i, row in enumerate(rows[:40]):
        mapping = {}
        for j, cell in enumerate(row):
            k = _col_kind(cell)
            if k and k not in mapping.values():
                mapping[j] = k
        if "qty" in mapping.values() and ("model" in mapping.values() or "desc" in mapping.values()) and len(mapping) >= 3:
            header_idx, cols = i, mapping
            break
    if header_idx < 0:
        return [], {}
    items, totals = [], {}
    for row in rows[header_idx + 1:]:
        cells = {k: (row[j] if j < len(row) else "") for j, k in cols.items()}
        first = "".join(row[:3]).upper().replace(" ", "")
        if "TOTAL" in first or "合计" in first or "总计" in first:
            for k in ("qty", "amount", "ctns", "nw", "gw", "cbm"):
                v = to_num(cells.get(k))
                if v is not None:
                    totals[k] = v
            continue
        model = (cells.get("model") or "").strip()
        if not model:
            m = MODEL_RE.search(cells.get("desc") or "")
            model = m.group(0) if m else ""
        qty = to_num(cells.get("qty"))
        if not model or qty is None or not re.search(r"\d", model):
            continue
        item = {"model": model.upper().replace(" ", ""), "desc": (cells.get("desc") or "").strip(), "qty": qty}
        for k in ("unit_price", "amount", "ctns", "nw", "gw", "cbm", "per_ctn"):
            v = to_num(cells.get(k))
            if v is not None:
                item[k] = v
        hs = re.sub(r"\D", "", cells.get("hs") or "")
        if hs:
            item["hs"] = hs
        items.append(item)
    return items, totals


def _labels(text: str, tables: list[list[list[str]]]) -> dict:
    """抽“标签: 值”。Excel 里两列的“标签 | 值”也算。"""
    pairs: list[tuple[str, str]] = []
    # 一行里可能有好几个“标签: 值”（PDF 两栏排版会被读成一行），按已知标签的位置切开
    for line in text.splitlines():
        ms = list(LABEL_SPLIT_RE.finditer(line))
        for i, m in enumerate(ms):
            end = ms[i + 1].start() if i + 1 < len(ms) else len(line)
            value = line[m.end():end].strip()
            if value:
                pairs.append((m.group(1), value))
    for t in tables:
        for row in t:
            cells = [c for c in row if c]
            if len(cells) == 2 and len(cells[0]) <= 30:
                pairs.append((cells[0], cells[1]))
    out: dict = {}
    for label, value in pairs:
        low = label.lower().strip()
        for key, words in LABEL_RULES:
            if key in out:
                continue
            if any(w in low for w in words):
                out[key] = value.strip()
                break
    return out


def rule_extract(name: str, text: str, tables: list[list[list[str]]]) -> Doc:
    doc = Doc(name=name, kind=detect_kind(text, name))
    for t in tables:
        items, totals = _parse_table(t)
        if items:
            doc.items, doc.totals = items, totals
            break
    lab = _labels(text, tables)
    doc.number = (lab.get("number") or "").split()[0] if lab.get("number") else ""
    doc.consignee = (lab.get("consignee") or "").split("\n")[0][:80]
    up = text.upper()
    cur = (lab.get("currency") or "").upper()
    doc.currency = next((c for c in CURRENCIES if c in cur), "") or next((c for c in CURRENCIES if re.search(rf"\b{c}\b", up)), "")
    if doc.currency == "RMB":
        doc.currency = "CNY"
    term = (lab.get("incoterm") or "").upper()
    doc.incoterm = next((c for c in INCOTERMS if c in term), "") or next((c for c in INCOTERMS if re.search(rf"\b{c}\b", up)), "")
    for k in ("gw", "nw", "ctns", "amount"):
        v = to_num(lab.get(k))
        if v is not None and k not in doc.totals:
            doc.totals[k] = v
    return doc


def llm_extract(llm, name: str, text: str) -> Doc:
    data = llm.chat_json(prompts.DOC_EXTRACT_SYSTEM, prompts.DOC_EXTRACT_USER.format(name=name, text=text[:12000]))
    kind = str(data.get("doc_type") or "").upper()
    doc = Doc(name=name, kind=kind if kind in DOC_LABELS else detect_kind(text, name), via="大模型")
    doc.number = str(data.get("number") or "")
    doc.consignee = str(data.get("consignee") or "")
    doc.currency = str(data.get("currency") or "").upper()
    doc.incoterm = str(data.get("incoterm") or "").upper()
    for it in data.get("items") or []:
        if not isinstance(it, dict) or not it.get("model") or to_num(it.get("qty")) is None:
            continue
        item = {"model": str(it["model"]).upper().replace(" ", ""), "desc": str(it.get("desc") or ""), "qty": to_num(it["qty"])}
        for k in ("unit_price", "amount", "ctns", "nw", "gw", "cbm"):
            v = to_num(it.get(k))
            if v is not None:
                item[k] = v
        hs = re.sub(r"\D", "", str(it.get("hs") or ""))
        if hs:
            item["hs"] = hs
        doc.items.append(item)
    for k, v in (data.get("totals") or {}).items():
        n = to_num(v)
        if n is not None and k in ("qty", "amount", "ctns", "nw", "gw", "cbm"):
            doc.totals[k] = n
    return doc


def extract(llm, name: str, data: bytes) -> Doc:
    try:
        text, tables = read_file(name, data)
    except ValueError as e:
        return Doc(name=name, error=str(e))
    except Exception:  # noqa: BLE001 - 坏文件
        return Doc(name=name, error="文件打不开，可能已损坏或加密")
    if not text.strip() and not any(tables):
        return Doc(name=name, error="没读到文字：可能是扫描件或图片版 PDF，请上传文字版或 Excel")
    doc = rule_extract(name, text, tables)
    if not doc.items and llm is not None:
        try:
            ai = llm_extract(llm, name, text)
            if ai.items:
                return ai
        except Exception:  # noqa: BLE001 - 大模型失败就用规则结果
            pass
    if not doc.items:
        doc.error = "没找到货物明细表（型号 / 数量列）"
    return doc


# --------------------------------------------------------------------- 比对
def _fmt(v, unit="") -> str:
    if isinstance(v, float):
        s = f"{v:,.2f}".rstrip("0").rstrip(".") if not v.is_integer() else f"{int(v):,}"
    else:
        s = str(v)
    return f"{s} {unit}".strip()


def _norm_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(co|company|ltd|limited|llc|inc|gmbh|sas|srl|s\.a|corp|corporation)\b\.?", "", s)
    return re.sub(r"[^a-z0-9一-鿿]", "", s)


def _same(a, b, rel=0.005) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(0.01, rel * max(abs(a), abs(b)))
    return a == b


class Checker:
    def __init__(self, docs: list[Doc]):
        self.docs = docs
        self.issues: dict[str, dict] = {}
        self.checked = 0

    def _issue(self, key: str, title: str, field_label: str, values: list[tuple[Doc, str]], *,
               suspect: Doc | None = None, note: str = "", severity: str = "error"):
        cur = self.issues.get(key)
        if cur:
            if note and note not in cur["notes"]:
                cur["notes"].append(note)
            if suspect and not cur.get("_suspect_forced"):
                cur["likely_wrong"] = suspect.label
                cur["_suspect_forced"] = True
            return
        self.issues[key] = {"key": key, "title": title, "field": field_label, "severity": severity,
                            "values": [{"doc": d.label, "file": d.name, "value": v} for d, v in values],
                            "likely_wrong": suspect.label if suspect else "", "notes": [note] if note else [],
                            "_suspect_forced": bool(suspect)}

    def _compare(self, key: str, title: str, field_label: str, pairs: list[tuple[Doc, object]], unit: str = "",
                 hint=None):
        pairs = [(d, v) for d, v in pairs if v not in (None, "")]
        if len(pairs) < 2:
            return
        self.checked += 1
        groups: list[tuple[object, list[Doc]]] = []
        for d, v in pairs:
            for g in groups:
                if _same(g[0], v):
                    g[1].append(d)
                    break
            else:
                groups.append((v, [d]))
        if len(groups) == 1:
            return
        groups.sort(key=lambda g: -len(g[1]))
        suspect = None
        if len(groups[0][1]) > len(groups[1][1]) and sum(len(g[1]) for g in groups[1:]) == 1:
            suspect = groups[1][1][0]
            others = "、".join(d.label for d in groups[0][1])
            note = f"{others}都是 {_fmt(groups[0][0], unit)}，{suspect.label}可能写错了"
        else:
            note = ""
        if hint:
            s2, n2 = hint(pairs)
            if s2:
                suspect, note = s2, n2
        self._issue(key, title, field_label, [(d, _fmt(v, unit)) for d, v in pairs], suspect=suspect, note=note)

    def run(self) -> list[dict]:
        docs = [d for d in self.docs if not d.error]
        # 单据内部自检（先做，用来辅助判断谁写错）
        self.self_flags: dict[tuple[str, str], tuple[Doc, str]] = {}
        for d in docs:
            self._self_check(d)
        # 型号逐项比对
        models: list[str] = []
        for d in docs:
            for it in d.items:
                if it["model"] not in models:
                    models.append(it["model"])
        for m in models:
            rows = [(d, next((it for it in d.items if it["model"] == m), None)) for d in docs]
            present = [(d, it) for d, it in rows if it]
            missing = [d for d, it in rows if not it and d.items]
            if missing and len(present) >= 1:
                self.checked += 1
                self._issue(f"missing:{m}", f"{m} 在部分单据里没有", "型号",
                            [(d, "有") for d, _ in present] + [(d, "缺少") for d in missing],
                            suspect=missing[0] if len(missing) == 1 and len(present) >= 2 else None,
                            note="漏写了一行，或者型号写法不一致")
            self._compare(f"qty:{m}", f"{m} 数量对不上", "数量", [(d, it.get("qty")) for d, it in present], "PCS")
            self._compare(f"price:{m}", f"{m} 单价对不上", "单价", [(d, it.get("unit_price")) for d, it in present])
            self._compare(f"amount:{m}", f"{m} 金额对不上", "金额", [(d, it.get("amount")) for d, it in present])
            self._compare(f"hs:{m}", f"{m} HS 编码对不上", "HS 编码", [(d, it.get("hs")) for d, it in present],
                          hint=self._hint_for(f"hs:{m}"))
        # 合计
        for k, label, unit in (("amount", "总金额", ""), ("ctns", "总箱数", "CTNS"), ("gw", "总毛重", "KG"),
                               ("nw", "总净重", "KG"), ("cbm", "总体积", "CBM")):
            self._compare(f"total:{k}", f"{label}对不上", label, [(d, d.totals.get(k)) for d in docs], unit,
                          hint=self._hint_for(f"total:{k}"))
        # 抬头信息
        self._compare("consignee", "收货人名称对不上", "收货人",
                      [(d, _norm_name(d.consignee) and d.consignee) for d in docs])
        if "consignee" in self.issues:  # 名字只差标点 / 公司后缀不算错
            names = {_norm_name(v["value"]) for v in self.issues["consignee"]["values"]}
            if len(names) == 1:
                del self.issues["consignee"]
        self._compare("currency", "币种对不上", "币种", [(d, d.currency) for d in docs])
        self._compare("incoterm", "成交方式对不上", "成交方式", [(d, d.incoterm) for d in docs])
        # 没有跨单据冲突的自检问题，单独列出来
        for (key, _), (d, note) in self.self_flags.items():
            if key not in self.issues:
                self._issue(key, note.split("：")[0], "单据自检", [(d, note.split("：", 1)[-1])], suspect=d, note=note,
                            severity="warn")
        out = list(self.issues.values())
        for x in out:
            x.pop("_suspect_forced", None)
        order = {"qty": 0, "price": 1, "amount": 2, "total": 3, "hs": 4, "missing": 5}
        out.sort(key=lambda x: (x["severity"] != "error", order.get(x["key"].split(":")[0], 6), x["key"]))
        return out

    def _hint_for(self, key: str):
        def hint(pairs):
            for (k, _), (d, note) in self.self_flags.items():
                if k == key and any(d is p[0] for p in pairs):
                    return d, note
            return None, ""
        return hint

    def _flag(self, key: str, d: Doc, note: str):
        self.self_flags[(key, d.name)] = (d, note)

    def _self_check(self, d: Doc):
        for it in d.items:
            m = it["model"]
            q, p, a = it.get("qty"), it.get("unit_price"), it.get("amount")
            if q is not None and p is not None and a is not None:
                self.checked += 1
                if not _same(q * p, a, rel=0.002):
                    self._flag(f"amount:{m}", d, f"{m} 金额算错：{_fmt(q)} × {_fmt(p)} 应为 {_fmt(q * p)}，单据上写的是 {_fmt(a)}")
            if q is not None and it.get("per_ctn") and it.get("ctns"):
                self.checked += 1
                if not _same(it["per_ctn"] * it["ctns"], q, rel=0.0):
                    self._flag(f"qty:{m}", d, f"{m} 数量和装箱对不上：每箱 {_fmt(it['per_ctn'])} × {_fmt(it['ctns'])} 箱 = {_fmt(it['per_ctn'] * it['ctns'])}，单据上写的是 {_fmt(q)}")
            if it.get("nw") is not None and it.get("gw") is not None:
                self.checked += 1
                if it["nw"] > it["gw"]:
                    self._flag(f"weight:{m}", d, f"{m} 净重比毛重还大：净重 {_fmt(it['nw'])} KG，毛重 {_fmt(it['gw'])} KG")
            if it.get("hs") and d.kind == "CD":
                self.checked += 1
                if len(it["hs"]) != 10:
                    self._flag(f"hs:{m}", d, f"{m} HS 编码位数不对：中国报关用 10 位，这里是 {len(it['hs'])} 位（{it['hs']}）")
        t = d.totals
        if t.get("nw") is not None and t.get("gw") is not None:
            self.checked += 1
            if t["nw"] > t["gw"]:
                self._flag("total:gw", d, f"{d.label}的毛重比净重还小：毛重 {_fmt(t['gw'])} KG，净重 {_fmt(t['nw'])} KG")
        for k, unit in (("qty", "PCS"), ("amount", ""), ("ctns", "CTNS"), ("gw", "KG"), ("nw", "KG")):
            if k in t and d.items and all(k in it for it in d.items):
                self.checked += 1
                s = sum(it[k] for it in d.items)
                if not _same(s, t[k], rel=0.002):
                    self._flag(f"total:{k}", d, f"{d.label}的明细加起来是 {_fmt(s, unit)}，合计行写的是 {_fmt(t[k], unit)}")


# --------------------------------------------------------------------- 入口
def decode_files(files: list) -> list[tuple[str, bytes]]:
    if not isinstance(files, list) or not files:
        raise ValueError("请至少上传 2 份单据")
    if len(files) > MAX_FILES:
        raise ValueError(f"一次最多核对 {MAX_FILES} 份单据")
    out = []
    for f in files:
        name = Path(str((f or {}).get("name") or "单据")).name[:120]
        try:
            data = base64.b64decode(str(f.get("data") or ""), validate=False)
        except Exception:  # noqa: BLE001
            raise ValueError(f"{name} 读取失败")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"{name} 超过 5MB")
        if Path(name).suffix.lower() not in SUPPORTED_EXT:
            raise ValueError(f"{name}：暂不支持这种格式，请上传 PDF、Excel、Word 或 CSV")
        out.append((name, data))
    if len(out) < 2:
        raise ValueError("请至少上传 2 份单据，才能交叉核对")
    return out


def run_check(llm, files: list[tuple[str, bytes]]) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(4, len(files))) as ex:
        docs = list(ex.map(lambda f: extract(llm, f[0], f[1]), files))
    docs.sort(key=lambda d: DOC_ORDER.index(d.kind) if d.kind in DOC_ORDER else 9)
    checker = Checker(docs)
    issues = checker.run()
    report = {
        "docs": [{"name": d.name, "kind": d.kind, "label": d.label, "number": d.number, "items": len(d.items),
                  "via": d.via, "error": d.error} for d in docs],
        "issues": issues,
        "checked": checker.checked,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
    report["email"] = fix_email(llm, report) if issues else ""
    report["elapsed_ms"] = int((time.time() - t0) * 1000)
    return report


def fix_email(llm, report: dict) -> str:
    lines = []
    for i, x in enumerate(report["issues"], 1):
        vals = "；".join(f"{v['doc']} {v['value']}" for v in x["values"])
        lines.append(f"{i}. {x['title']}（{vals}）" + (f" —— {x['notes'][0]}" if x["notes"] else ""))
    issues_text = "\n".join(lines)
    try:
        text = llm.chat(prompts.DOC_FIX_SYSTEM, prompts.DOC_FIX_USER.format(issues=issues_text), json_mode=False)
        if text and text.strip():
            return text.strip()
    except Exception:  # noqa: BLE001
        pass
    return default_fix_email(report)


def default_fix_email(report: dict) -> str:
    wrong = []
    for x in report["issues"]:
        if x["likely_wrong"] and x["likely_wrong"] not in wrong:
            wrong.append(x["likely_wrong"])
    body = [f"您好，这票货的单据核对后发现 {len(report['issues'])} 处不一致，麻烦安排更正：", ""]
    for i, x in enumerate(report["issues"], 1):
        line = f"{i}. {x['title']}：" + "；".join(f"{v['doc']} {v['value']}" for v in x["values"])
        if x["likely_wrong"]:
            line += f"。请核对{x['likely_wrong']}"
        body.append(line)
    body += ["", f"更正后请把新版{'、'.join(wrong) or '单据'}发我确认，确认无误再报关 / 寄单，谢谢！"]
    return "\n".join(body)


def report_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False)
