"""数据库适配层：本地用 SQLite，云端设置 DATABASE_URL 即切到 Postgres。

对外只暴露 `connection()`，SQL 统一使用 `?` 占位符，行对象统一按字典取值，
所以上层 store.py 不需要关心后端差异。
"""

from __future__ import annotations

import sqlite3
import threading

from .config import DATA_DIR, get_settings

_local = threading.local()


class Cursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self) -> dict | None:
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict]:
        return [dict(row) for row in self._cur.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class Connection:
    """sqlite3 / psycopg2 的最小公共接口。"""

    def __init__(self, raw, backend: str, reconnect=None):
        self._raw = raw
        self.backend = backend
        self._reconnect_factory = reconnect

    # ------------------------------------------------------------ 内部
    def _sql(self, sql: str) -> str:
        return sql if self.backend == "sqlite" else sql.replace("?", "%s")

    def _run(self, sql: str, params) -> Cursor:
        cur = self._raw.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return Cursor(cur)

    # ------------------------------------------------------------ 对外
    def execute(self, sql: str, params=()) -> Cursor:
        try:
            return self._run(sql, params)
        except Exception:
            # 云端连接被回收（Neon 等会断开空闲连接）时重连一次
            if self.backend != "postgres" or self._reconnect_factory is None:
                raise
            self._raw = self._reconnect_factory()
            return self._run(sql, params)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def insert(self, sql: str, params=()) -> int:
        """执行 INSERT 并返回自增主键。"""
        if self.backend == "sqlite":
            cur = self._raw.cursor()
            cur.execute(sql, tuple(params))
            return int(cur.lastrowid or 0)
        cur = self._raw.cursor()
        cur.execute(self._sql(sql) + " RETURNING id", tuple(params))
        row = cur.fetchone()
        return int(row["id"])

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()
        if self.backend == "sqlite":
            self._raw.close()
        return False


def _sqlite_raw(path) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _pg_raw(url: str, fresh: bool = False):
    """Postgres 连接按线程复用，避免每次操作都握手。"""
    if not fresh:
        raw = getattr(_local, "pg", None)
        if raw is not None and getattr(_local, "pg_url", None) == url and not raw.closed:
            return raw

    import psycopg2
    from psycopg2.extras import RealDictCursor

    dsn = url
    if "sslmode" not in dsn:
        dsn = url + ("&" if "?" in url else "?") + "sslmode=require"
    try:
        raw = psycopg2.connect(dsn, cursor_factory=RealDictCursor, connect_timeout=10)
    except psycopg2.OperationalError:
        raw = psycopg2.connect(url, cursor_factory=RealDictCursor, connect_timeout=10)

    old = getattr(_local, "pg", None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    _local.pg = raw
    _local.pg_url = url
    return raw


def connection() -> Connection:
    settings = get_settings()
    if settings.database_url:
        url = settings.database_url
        return Connection(_pg_raw(url), "postgres", reconnect=lambda: _pg_raw(url, fresh=True))
    return Connection(_sqlite_raw(settings.db_path), "sqlite")


def is_postgres() -> bool:
    return bool(get_settings().database_url)
