"""后台循环：定时收邮件、处理表格里的勾选、每天定点推送跟进提醒。"""
from __future__ import annotations

import logging
import threading
import time

from . import mailbox
from .pipeline import Assistant

log = logging.getLogger(__name__)


class Worker(threading.Thread):
    def __init__(self, assistant: Assistant):
        super().__init__(daemon=True, name="worker")
        self.a = assistant
        self.cfg = assistant.cfg
        self._stop = threading.Event()
        self._last_mail = 0.0
        self.lock = threading.Lock()  # 和 HTTP 接口共用，避免同一条记录被同时处理

    def stop(self) -> None:
        self._stop.set()

    def check_mail(self) -> int:
        if not self.cfg.mail_enabled:
            return 0
        msgs = mailbox.fetch_recent(self.cfg.imap_host, self.cfg.imap_port, self.cfg.imap_user,
                                    self.cfg.imap_password, self.cfg.imap_folder, self.cfg.imap_lookback_days,
                                    skip_ids=self.a.state.seen_ids())
        n = 0
        for m in sorted(msgs, key=lambda x: x.get("date") or 0):
            try:
                if self.a.ingest(m, source="邮箱"):
                    n += 1
            except Exception:
                log.exception("处理邮件失败：%s", m.get("subject"))
        return n

    def maybe_daily_push(self) -> bool:
        now = self.a.now()
        today = now.strftime("%Y-%m-%d")
        if self.a.state.get("last_followup_push") == today:
            return False
        if now.strftime("%H:%M") < self.cfg.followup_time:
            return False
        self.a.daily_followups(push=True)
        self.a.state.set("last_followup_push", today)
        return True

    def tick(self) -> None:
        with self.lock:
            if time.time() - self._last_mail >= self.cfg.mail_poll_seconds:
                self._last_mail = time.time()
                try:
                    self.check_mail()
                except Exception:
                    log.exception("收邮件失败")
            try:
                self.a.process_checkboxes()
            except Exception:
                log.exception("处理勾选失败")
            try:
                self.maybe_daily_push()
            except Exception:
                log.exception("每日跟进推送失败")

    def run(self) -> None:
        log.info("后台任务已启动：每 %ss 检查表格，每 %ss 收一次邮件，每天 %s 推送跟进提醒",
                 self.cfg.poll_seconds, self.cfg.mail_poll_seconds, self.cfg.followup_time)
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.cfg.poll_seconds)
