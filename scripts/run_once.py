"""手动触发一次任务（调试或录屏时用）。

    python scripts/run_once.py mail        # 立即收一次邮件
    python scripts/run_once.py check       # 立即处理表格里的勾选（生成报价单 / 已跟进）
    python scripts/run_once.py daily       # 立即生成今天的跟进提醒并推送到飞书群
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import build_assistant  # noqa: E402
from app.worker import Worker  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    a = build_assistant()
    if what == "mail":
        print("新询盘：", Worker(a).check_mail())
    elif what == "check":
        print(a.process_checkboxes())
    elif what == "daily":
        for x in a.daily_followups(push=True):
            print(f"- {x['company']}（{x['level']}级，第{x['count'] + 1}次）{x['action']}\n  {x['message']}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
