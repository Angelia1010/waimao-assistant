"""自带数据库（SQLite）。

SqliteStore 的方法和 FeishuClient 完全一致（search / create_record / update_record / get_record /
upload_attachment / send_card），所以 pipeline 里的业务逻辑不用改就能跑在本地数据库上。
另外还管理：用户、登录会话、系统设置、站内提醒。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY, tbl TEXT NOT NULL, fields TEXT NOT NULL,
  created REAL NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_tbl ON records(tbl);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, markdown TEXT NOT NULL,
  template TEXT, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'sales', pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL
);
"""

SESSION_DAYS = 14


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 200_000).hex()
    return h, salt


class SqliteStore:
    def __init__(self, data_dir: str, bot_sender=None):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "files").mkdir(exist_ok=True)
        self.path = self.dir / "waimao.db"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self.bot_sender = bot_sender  # 可选：FeishuClient 实例，只用它的群机器人推送

    # ------------------------------------------------------------- 内部工具
    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    # ======================================================================
    # 与 FeishuClient 相同的接口
    # ======================================================================
    def table_id(self, name: str) -> str:
        return name

    def list_tables(self) -> dict[str, str]:
        from . import schema as S
        return {t: t for t in S.TABLES}

    def search(self, table: str, conditions=None, conjunction: str = "and",
               field_names: list[str] | None = None) -> list[dict]:
        rows = self._query("SELECT id, fields FROM records WHERE tbl=? ORDER BY created", (table,))
        out = []
        for r in rows:
            f = json.loads(r["fields"])
            if field_names:
                f = {k: v for k, v in f.items() if k in field_names}
            out.append({"record_id": r["id"], "fields": f})
        return out

    def create_record(self, table: str, fields: dict) -> str:
        rid = "rec" + uuid.uuid4().hex[:12]
        clean = {k: v for k, v in fields.items() if v is not None and v != ""}
        now = time.time()
        self._exec("INSERT INTO records (id, tbl, fields, created, updated) VALUES (?,?,?,?,?)",
                   (rid, table, json.dumps(clean, ensure_ascii=False), now, now))
        return rid

    def batch_create(self, table: str, rows: list[dict]) -> list[str]:
        return [self.create_record(table, r) for r in rows]

    def update_record(self, table: str, record_id: str, fields: dict) -> None:
        with self._lock:
            row = self._conn.execute("SELECT fields FROM records WHERE id=? AND tbl=?", (record_id, table)).fetchone()
            if not row:
                raise KeyError(f"记录不存在：{record_id}")
            cur = json.loads(row["fields"])
            for k, v in fields.items():
                if v is None or v == "":
                    cur.pop(k, None)
                else:
                    cur[k] = v
            self._conn.execute("UPDATE records SET fields=?, updated=? WHERE id=?",
                               (json.dumps(cur, ensure_ascii=False), time.time(), record_id))
            self._conn.commit()

    def get_record(self, table: str, record_id: str) -> dict:
        row = self._query("SELECT id, fields, created, updated FROM records WHERE id=? AND tbl=?", (record_id, table))
        if not row:
            raise KeyError(f"记录不存在：{record_id}")
        r = row[0]
        return {"record_id": r["id"], "fields": json.loads(r["fields"]), "created": r["created"],
                "updated": r["updated"]}

    def delete_record(self, table: str, record_id: str) -> None:
        self._exec("DELETE FROM records WHERE id=? AND tbl=?", (record_id, table))

    def upload_attachment(self, path) -> str:
        p = Path(path)
        fid = "file" + uuid.uuid4().hex[:16]
        dest = self.dir / "files" / f"{fid}{p.suffix}"
        shutil.copyfile(p, dest)
        self._exec("INSERT INTO files (id, name, path, created) VALUES (?,?,?,?)",
                   (fid, p.name, str(dest), time.time()))
        return fid

    def get_file(self, fid: str) -> dict | None:
        rows = self._query("SELECT id, name, path FROM files WHERE id=?", (fid,))
        return dict(rows[0]) if rows else None

    def send_card(self, title: str, markdown: str, template: str = "blue", button=None) -> None:
        """站内提醒一定保存；配置了飞书群机器人就同时推送过去。"""
        self._exec("INSERT INTO notifications (title, markdown, template, created) VALUES (?,?,?,?)",
                   (title, markdown, template, time.time()))
        if self.bot_sender is not None and getattr(self.bot_sender, "bot_webhook", ""):
            self.bot_sender.send_card(title, markdown, template=template, button=button)

    def notifications(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT id, title, markdown, template, created FROM notifications ORDER BY id DESC LIMIT ?", (limit,))]

    # ======================================================================
    # 设置
    # ======================================================================
    def get_settings(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value"]) for r in self._query("SELECT key, value FROM settings")}

    def set_settings(self, values: dict[str, Any]) -> None:
        with self._lock:
            for k, v in values.items():
                self._conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                   (k, json.dumps(v, ensure_ascii=False)))
            self._conn.commit()

    # ======================================================================
    # 用户与会话
    # ======================================================================
    def user_count(self) -> int:
        return self._query("SELECT COUNT(*) AS n FROM users")[0]["n"]

    def create_user(self, username: str, name: str, password: str, role: str = "sales") -> int:
        if role not in ("admin", "sales"):
            raise ValueError("角色只能是 admin 或 sales")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        h, salt = hash_password(password)
        try:
            cur = self._exec("INSERT INTO users (username, name, role, pw_hash, salt, created) VALUES (?,?,?,?,?,?)",
                             (username.strip(), name.strip() or username.strip(), role, h, salt, time.time()))
        except sqlite3.IntegrityError:
            raise ValueError("用户名已存在")
        return cur.lastrowid

    def list_users(self) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT id, username, name, role, active, created FROM users ORDER BY id")]

    def get_user(self, uid: int) -> dict | None:
        rows = self._query("SELECT id, username, name, role, active FROM users WHERE id=?", (uid,))
        return dict(rows[0]) if rows else None

    def update_user(self, uid: int, *, name: str | None = None, role: str | None = None,
                    active: bool | None = None, password: str | None = None) -> None:
        if role is not None and role not in ("admin", "sales"):
            raise ValueError("角色只能是 admin 或 sales")
        sets, args = [], []
        if name is not None:
            sets.append("name=?"); args.append(name.strip())
        if role is not None:
            sets.append("role=?"); args.append(role)
        if active is not None:
            sets.append("active=?"); args.append(1 if active else 0)
        if password:
            if len(password) < 6:
                raise ValueError("密码至少 6 位")
            h, salt = hash_password(password)
            sets += ["pw_hash=?", "salt=?"]; args += [h, salt]
        if sets:
            self._exec(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*args, uid))
        if active is False or password:
            self._exec("DELETE FROM sessions WHERE user_id=?", (uid,))

    def authenticate(self, username: str, password: str) -> dict | None:
        rows = self._query("SELECT id, username, name, role, active, pw_hash, salt FROM users WHERE username=?",
                           (username.strip(),))
        if not rows:
            hash_password(password, "x" * 32)  # 统一耗时，避免通过响应时间探测用户名
            return None
        u = rows[0]
        h, _ = hash_password(password, u["salt"])
        if not hmac.compare_digest(h, u["pw_hash"]) or not u["active"]:
            return None
        return {"id": u["id"], "username": u["username"], "name": u["name"], "role": u["role"]}

    def create_session(self, uid: int) -> str:
        token = secrets.token_urlsafe(32)
        self._exec("INSERT INTO sessions (token, user_id, expires) VALUES (?,?,?)",
                   (token, uid, time.time() + SESSION_DAYS * 86400))
        self._exec("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        return token

    def session_user(self, token: str) -> dict | None:
        if not token:
            return None
        rows = self._query("SELECT u.id, u.username, u.name, u.role, u.active, s.expires FROM sessions s "
                           "JOIN users u ON u.id = s.user_id WHERE s.token=?", (token,))
        if not rows or rows[0]["expires"] < time.time() or not rows[0]["active"]:
            return None
        r = rows[0]
        return {"id": r["id"], "username": r["username"], "name": r["name"], "role": r["role"]}

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM sessions WHERE token=?", (token,))
