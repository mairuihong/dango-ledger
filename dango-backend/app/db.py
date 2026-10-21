"""SQLite 访问层。

- 只用标准库 sqlite3，不引入 ORM；
- 每个请求/事务使用独立连接，写操作显式 BEGIN IMMEDIATE；
- 删除一律写 deleted_at 墓碑，不做物理 DELETE；
- 金额全部为整数「分」。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 系统分类的归属用户。系统分类对所有用户只读。
SYSTEM_USER_ID = "__system__"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL DEFAULT 'cash',
    balance         INTEGER NOT NULL DEFAULT 0,
    initial_balance INTEGER NOT NULL DEFAULT 0,
    sort            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- 系统分类的 user_id 是 '__system__'，不对应 users 表，因此这里不建外键。
CREATE TABLE IF NOT EXISTS categories (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    icon       TEXT NOT NULL DEFAULT '',
    color      TEXT NOT NULL DEFAULT '',
    parent_id  TEXT,
    sort       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    to_account_id TEXT,
    category_id   TEXT,
    amount        INTEGER NOT NULL,
    type          TEXT NOT NULL,
    occurred_at   TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id),
    FOREIGN KEY (to_account_id) REFERENCES accounts (id),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TABLE IF NOT EXISTS budgets (
    user_id    TEXT NOT NULL,
    month      TEXT NOT NULL,
    amount     INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, month),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_user
    ON accounts (user_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_categories_user_kind
    ON categories (user_id, kind, sort);
CREATE INDEX IF NOT EXISTS idx_transactions_user_occurred
    ON transactions (user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_user_account
    ON transactions (user_id, account_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_transactions_pair
    ON transactions (user_id, type, account_id, to_account_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_budgets_user
    ON budgets (user_id);
"""

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def now_iso() -> str:
    """服务端时间戳，统一 UTC、秒级 ISO8601。"""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now_iso() -> str:
    """记账发生时间默认值：使用服务器本地时间，不写时区，方便按月归类。"""

    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def current_month() -> str:
    """当前月份，格式 YYYY-MM。"""

    return datetime.now().strftime("%Y-%m")


def is_valid_month(value: str | None) -> bool:
    return bool(value and _MONTH_RE.match(value))


def shift_month(month: str, delta: int) -> str:
    """在 YYYY-MM 上前后移动 delta 个月。"""

    year, mon = (int(part) for part in month.split("-", 1))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_range(month: str) -> tuple[str, str]:
    """返回左闭右开的 occurred_at 字符串范围。

    发生时间允许存 "YYYY-MM-DD" 或 "YYYY-MM-DDTHH:MM:SS"，
    因此用 "YYYY-MM-01" ~ "下月-01" 的字符串比较即可覆盖整月。
    """

    return f"{month}-01", f"{shift_month(month, 1)}-01"


def escape_like(value: str) -> str:
    """转义 SQLite LIKE 中的通配符，配合 ESCAPE '\\' 使用。"""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Database:
    """轻量数据库封装，不持有长连接。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def initialize(self) -> None:
        """建表 + 开启 WAL。可重复执行。"""

        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """只读连接；调用方负责关闭（由本上下文负责）。"""

        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """写事务：BEGIN IMMEDIATE，异常整体回滚，正常提交。"""

        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            if conn.in_transaction:
                conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.fetchone(sql, params)
        return row[0] if row is not None else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """独立的写语句（自带事务），返回受影响行数。"""

        with self.transaction() as conn:
            return conn.execute(sql, params).rowcount
