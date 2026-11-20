"""单证核对：用演示单据生成器造两套单据，一套埋错、一套全对。"""
import subprocess
import sys
from pathlib import Path

import pytest

from app import doccheck
from app.llm import MockLLM

ROOT = Path(__file__).resolve().parent.parent


def make_docs(tmp_path: Path, clean: bool) -> list[tuple[str, bytes]]:
    out = tmp_path / ("clean" if clean else "bad")
    cmd = [sys.executable, str(ROOT / "scripts" / "make_demo_docs.py"), "--out", str(out)] + (["--clean"] if clean else [])
    subprocess.run(cmd, check=True, capture_output=True)
    return [(p.name, p.read_bytes()) for p in sorted(out.iterdir())]


def test_finds_three_planted_errors(tmp_path):
    r = doccheck.run_check(MockLLM(), make_docs(tmp_path, clean=False))
    assert [d["kind"] for d in r["docs"]] == ["PI", "CI", "PL", "CD"]
    assert all(d["items"] == 3 for d in r["docs"])
    keys = {x["key"]: x for x in r["issues"]}
    assert set(keys) == {"qty:DS-450", "total:gw", "hs:HG-304A"}
    assert keys["qty:DS-450"]["likely_wrong"] == "装箱单"
    assert keys["total:gw"]["likely_wrong"] == "报关资料"
    assert keys["hs:HG-304A"]["likely_wrong"] == "报关资料"
    assert "1,020" in r["email"] and "830210000" in r["email"]


def test_clean_documents_have_no_issues(tmp_path):
    r = doccheck.run_check(MockLLM(), make_docs(tmp_path, clean=True))
    assert r["issues"] == [] and r["email"] == ""
    assert r["checked"] > 30


def test_self_checks():
    d = doccheck.Doc(name="x.xlsx", kind="CI", items=[{"model": "AB-100", "qty": 100.0, "unit_price": 2.0, "amount": 210.0}],
                     totals={"nw": 50.0, "gw": 40.0})
    issues = doccheck.Checker([d]).run()
    titles = " ".join(x["notes"][0] for x in issues)
    assert "金额算错" in titles and "毛重比净重还小" in titles


def test_rejects_bad_uploads():
    with pytest.raises(ValueError):
        doccheck.decode_files([{"name": "a.pdf", "data": ""}])
    with pytest.raises(ValueError):
        doccheck.decode_files([{"name": "a.exe", "data": "AA=="}, {"name": "b.pdf", "data": "AA=="}])


def test_unreadable_file_reports_error():
    d = doccheck.extract(MockLLM(), "scan.pdf", b"not a pdf")
    assert d.error
