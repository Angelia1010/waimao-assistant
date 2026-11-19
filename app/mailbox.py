"""通过 IMAP 读取业务邮箱的新邮件（只读，不会把邮件标为已读）。"""
from __future__ import annotations

import email
import html
import imaplib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

log = logging.getLogger(__name__)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def _strip_quoted(text: str) -> str:
    """去掉回复邮件里引用的历史内容，减少噪音和 token。"""
    cut = re.split(r"\n(?:-{2,}\s*Original Message|On .{5,80} wrote:|From: .+\nSent: |发件人[:：])", text, maxsplit=1)
    return cut[0].strip()


def message_body(msg: email.message.Message) -> str:
    plain, rich = [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if part.get_content_type() == "text/plain":
            plain.append(text)
        elif part.get_content_type() == "text/html":
            rich.append(_html_to_text(text))
    body = "\n".join(plain) if plain else "\n".join(rich)
    return _strip_quoted(body)[:6000]


def parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    name, addr = parseaddr(_decode(msg.get("From")))
    try:
        dt = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    except Exception:
        dt = None
    return {
        "msg_id": (msg.get("Message-ID") or "").strip() or f"{addr}-{msg.get('Date')}",
        "sender": f"{name} <{addr}>" if name else addr,
        "sender_email": addr,
        "subject": _decode(msg.get("Subject")),
        "body": message_body(msg),
        "date": dt.timestamp() if dt else None,
    }


def fetch_recent(host: str, port: int, user: str, password: str, folder: str = "INBOX",
                 lookback_days: int = 3, skip_ids: set[str] | None = None) -> list[dict]:
    skip_ids = skip_ids or set()
    since = (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    out: list[dict] = []
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        # 网易/QQ 等邮箱要求登录后发送 ID 命令，否则 SELECT 会报 Unsafe Login
        try:
            imaplib.Commands["ID"] = ("AUTH", "SELECTED")
            conn._simple_command("ID", '("name" "waimao-assistant" "version" "1.0")')
        except Exception:
            pass
        typ, _ = conn.select(folder, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"无法打开邮箱文件夹 {folder}")
        typ, data = conn.search(None, "SINCE", since)
        ids = data[0].split() if data and data[0] else []
        for num in ids[-200:]:
            typ, hdr = conn.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            mid = ""
            if hdr and isinstance(hdr[0], tuple):
                mid = email.message_from_bytes(hdr[0][1]).get("Message-ID", "").strip()
            if mid and mid in skip_ids:
                continue
            typ, msg_data = conn.fetch(num, "(BODY.PEEK[])")
            if typ == "OK" and msg_data and isinstance(msg_data[0], tuple):
                out.append(parse_message(msg_data[0][1]))
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    log.info("邮箱检查完成：新邮件 %d 封", len(out))
    return out
