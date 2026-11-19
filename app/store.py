"""本地状态文件：已处理的邮件ID、报价单流水号、每日推送记录。"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class State:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text("utf-8"))
        except Exception:
            self.data = {}
        self.data.setdefault("seen_msg_ids", [])
        self.data.setdefault("quote_seq", {})
        self.data.setdefault("last_followup_push", "")

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.path)

    def seen(self, msg_id: str) -> bool:
        return msg_id in self.data["seen_msg_ids"]

    def mark_seen(self, msg_id: str) -> None:
        with self._lock:
            ids = self.data["seen_msg_ids"]
            if msg_id not in ids:
                ids.append(msg_id)
                self.data["seen_msg_ids"] = ids[-5000:]
                self.save()

    def seen_ids(self) -> set[str]:
        return set(self.data["seen_msg_ids"])

    def next_quote_no(self, day: str) -> str:
        with self._lock:
            n = int(self.data["quote_seq"].get(day, 0)) + 1
            self.data["quote_seq"] = {day: n}  # 只保留当天
            self.save()
        return f"Q{day}-{n:03d}"

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self.data[key] = value
            self.save()
