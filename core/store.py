"""授权与计费：兑换码 + 次数扣减。本地 SQLite，云端 Postgres（设 DATABASE_URL 即切换）。"""

from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS codes (
    code        TEXT PRIMARY KEY,
    total       INTEGER NOT NULL DEFAULT 10,
    used        INTEGER NOT NULL DEFAULT 0,
    note        TEXT    NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    expires_at  TEXT,
    created_at  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    code        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    code        TEXT,
    action      TEXT,
    detail      TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    order_no    TEXT PRIMARY KEY,
    code        TEXT,
    plan_id     TEXT NOT NULL,
    plan_name   TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    uses        INTEGER NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'alipay',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    paid_at     TEXT,
    remark      TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    position    TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT '',
    period      TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    versions    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_code ON sessions(code);
CREATE INDEX IF NOT EXISTS idx_reports_code ON reports(code);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conn():
    return connection()


_ready = False


def init_db() -> None:
    global _ready
    if _ready:
        return
    conn = _conn()
    schema = SCHEMA
    if conn.backend != "sqlite":
        schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    with conn:
        conn.executescript(schema)
    _ready = True


def _normalize(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


def _log(code: str | None, action: str, detail: str = "") -> None:
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO usage_log (ts, code, action, detail) VALUES (?,?,?,?)",
                (_now(), code, action, detail),
            )
    except Exception:
        pass


@dataclass
class CodeInfo:
    code: str
    total: int
    used: int
    remaining: int
    active: bool
    expires_at: str | None
    note: str
    created_at: str


def create_codes(
    count: int = 1,
    uses: int = 10,
    prefix: str = "RP",
    expires_days: int = 0,
    note: str = "",
) -> list[str]:
    """批量生成兑换码。"""
    count = max(1, min(int(count), 200))
    uses = max(1, min(int(uses), 100000))
    prefix = (_normalize(prefix) or "RP")[:8]
    expires_at = None
    if expires_days and expires_days > 0:
        expires_at = (datetime.now() + timedelta(days=expires_days)).strftime("%Y-%m-%d %H:%M:%S")

    created: list[str] = []
    with _conn() as conn:
        for _ in range(count):
            for _try in range(20):
                suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
                code = f"{prefix}-{suffix}"
                exists = conn.execute("SELECT 1 FROM codes WHERE code = ?", (code,)).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO codes (code, total, used, note, active, expires_at, created_at)"
                    " VALUES (?,?,?,?,1,?,?)",
                    (code, uses, 0, note, expires_at, _now()),
                )
                created.append(code)
                break
    _log(None, "create_codes", f"生成 {len(created)} 个，每个 {uses} 次")
    return created


def _code_row(conn, code: str) -> dict | None:
    return conn.execute("SELECT * FROM codes WHERE code = ?", (_normalize(code),)).fetchone()


def _is_expired(row) -> bool:
    if not row["expires_at"]:
        return False
    try:
        return datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now()
    except ValueError:
        return False


@dataclass
class ActivateResult:
    ok: bool
    message: str
    remaining: int = 0
    token: str = ""


def activate(raw_code: str, token: str) -> ActivateResult:
    """用兑换码激活当前会话，返回会话 token。"""
    code = _normalize(raw_code)
    if not code:
        return ActivateResult(False, "请输入兑换码")

    with _conn() as conn:
        row = _code_row(conn, code)
        if not row:
            return ActivateResult(False, "兑换码不存在，请核对后重试")
        if not row["active"]:
            return ActivateResult(False, "该兑换码已被停用，请联系客服")
        if _is_expired(row):
            return ActivateResult(False, "该兑换码已过期，请联系客服续费")
        remaining = int(row["total"]) - int(row["used"])
        if remaining <= 0:
            return ActivateResult(False, "该兑换码次数已用完，请联系客服续费")

        if not token:
            token = secrets.token_urlsafe(18)
        conn.execute(
            "INSERT INTO sessions (token, code, created_at, last_seen) VALUES (?,?,?,?)"
            " ON CONFLICT(token) DO UPDATE SET code = excluded.code, last_seen = excluded.last_seen",
            (token, code, _now(), _now()),
        )
    _log(code, "activate")
    return ActivateResult(True, "激活成功", remaining, token)


def session_info(token: str | None) -> dict | None:
    """返回会话信息：code / remaining / total / used / expires_at。无效 token 返回 None。"""
    if not token:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT s.code AS code, s.created_at AS created_at, c.total AS total, c.used AS used,"
            " c.active AS active, c.expires_at AS expires_at"
            " FROM sessions s JOIN codes c ON c.code = s.code WHERE s.token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        if not row["active"] or _is_expired(row):
            return None
        conn.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (_now(), token))
    remaining = max(0, int(row["total"]) - int(row["used"]))
    return {
        "code": row["code"],
        "total": int(row["total"]),
        "used": int(row["used"]),
        "remaining": remaining,
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
    }


def remaining_of(token: str | None) -> int:
    info = session_info(token)
    return info["remaining"] if info else 0


def consume(token: str) -> tuple[bool, int]:
    """扣减 1 次。返回 (是否成功, 剩余次数)。"""
    info = session_info(token)
    if not info or info["remaining"] <= 0:
        return False, 0
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE codes SET used = used + 1"
            " WHERE code = ? AND active = 1 AND total - used > 0",
            (info["code"],),
        )
        if cur.rowcount == 0:
            return False, 0
        conn.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (_now(), token))
    _log(info["code"], "generate")
    left = info["remaining"] - 1
    return True, left


def log_event(token: str | None, action: str, detail: str = "") -> None:
    info = session_info(token)
    _log(info["code"] if info else None, action, detail)


def code_detail(raw_code: str) -> CodeInfo | None:
    with _conn() as conn:
        row = _code_row(conn, raw_code)
    if not row:
        return None
    return CodeInfo(
        code=row["code"],
        total=int(row["total"]),
        used=int(row["used"]),
        remaining=max(0, int(row["total"]) - int(row["used"])),
        active=bool(row["active"]),
        expires_at=row["expires_at"],
        note=row["note"],
        created_at=row["created_at"],
    )


def list_codes(keyword: str = "", limit: int = 300) -> list[CodeInfo]:
    kw = f"%{_normalize(keyword)}%"
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM codes WHERE code LIKE ? OR note LIKE ? ORDER BY created_at DESC LIMIT ?",
            (kw, f"%{keyword.strip()}%", limit),
        ).fetchall()
    return [
        CodeInfo(
            code=r["code"],
            total=int(r["total"]),
            used=int(r["used"]),
            remaining=max(0, int(r["total"]) - int(r["used"])),
            active=bool(r["active"]),
            expires_at=r["expires_at"],
            note=r["note"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def set_code_active(raw_code: str, active: bool) -> bool:
    with _conn() as conn:
        cur = conn.execute("UPDATE codes SET active = ? WHERE code = ?", (1 if active else 0, _normalize(raw_code)))
    _log(_normalize(raw_code), "enable" if active else "disable")
    return cur.rowcount > 0


def add_uses(raw_code: str, delta: int) -> bool:
    if delta == 0:
        return False
    code = _normalize(raw_code)
    with _conn() as conn:
        row = conn.execute("SELECT total, used FROM codes WHERE code = ?", (code,)).fetchone()
        if not row:
            return False
        total = max(int(row["total"]) + int(delta), int(row["used"]))
        conn.execute("UPDATE codes SET total = ? WHERE code = ?", (total, code))
    _log(code, "add_uses", str(delta))
    return True


def admin_stats() -> dict:
    with _conn() as conn:
        codes = conn.execute("SELECT COUNT(*) c, SUM(total) t, SUM(used) u FROM codes").fetchone()
        users = conn.execute("SELECT COUNT(DISTINCT code) c FROM sessions").fetchone()
        today = datetime.now().strftime("%Y-%m-%d")
        today_gen = conn.execute(
            "SELECT COUNT(*) c FROM usage_log WHERE action = 'generate' AND ts LIKE ?", (f"{today}%",)
        ).fetchone()
    return {
        "codes": int(codes["c"] or 0),
        "total_uses": int(codes["t"] or 0),
        "used_uses": int(codes["u"] or 0),
        "users": int(users["c"] or 0),
        "today": int(today_gen["c"] or 0),
    }


def recent_logs(limit: int = 30) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, code, action, detail FROM usage_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ 订单（充值）
def _new_order_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + str(secrets.randbelow(9000) + 1000)


def create_order(
    plan_id: str, plan_name: str, amount_cents: int, uses: int, channel: str = "alipay", remark: str = ""
) -> str:
    order_no = _new_order_no()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO orders (order_no, plan_id, plan_name, amount, uses, channel, status, created_at, remark)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                order_no,
                plan_id,
                plan_name,
                int(amount_cents),
                int(uses),
                channel,
                "pending",
                _now(),
                remark,
            ),
        )
    _log(None, "create_order", f"{order_no} {plan_name} {amount_cents}")
    return order_no


def get_order(order_no: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
    return dict(row) if row else None


def mark_order_paid(order_no: str, remark: str = "auto") -> tuple[bool, str, str]:
    """订单支付成功后发放兑换码。返回 (成功, 兑换码, 提示)。幂等：已发过码直接返回原码。"""
    order = get_order(order_no)
    if not order:
        return False, "", "订单不存在"
    if order["status"] == "paid" and order["code"]:
        return True, order["code"], "订单已支付"

    code = create_codes(1, int(order["uses"]), "RP", 0, f"订单{order_no}")[0]
    with _conn() as conn:
        conn.execute(
            "UPDATE orders SET status = 'paid', code = ?, paid_at = ?, remark = ? WHERE order_no = ?",
            (code, _now(), remark, order_no),
        )
    _log(code, "order_paid", order_no)
    return True, code, "支付成功，兑换码已发放"


def order_stats() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM orders WHERE status = 'paid'"
        ).fetchone()
        today_row = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM orders WHERE status = 'paid' AND paid_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        pending = conn.execute("SELECT COUNT(*) c FROM orders WHERE status = 'pending'").fetchone()
    return {
        "paid_count": int(total["c"] or 0),
        "revenue": int(total["s"] or 0),
        "today_count": int(today_row["c"] or 0),
        "today_revenue": int(today_row["s"] or 0),
        "pending": int(pending["c"] or 0),
    }


def list_orders(keyword: str = "", limit: int = 200) -> list[dict]:
    with _conn() as conn:
        if keyword.strip():
            rows = conn.execute(
                "SELECT * FROM orders WHERE order_no LIKE ? OR code LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{keyword.strip()}%", f"%{keyword.strip()}%", limit),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ 云端报告（多端同步）
def save_report(
    code: str,
    *,
    title: str,
    position: str,
    report_type: str,
    period: str,
    content: str,
    versions: list[dict],
    report_id: int | None = None,
) -> int:
    payload = json.dumps(versions, ensure_ascii=False)
    with _conn() as conn:
        if report_id:
            row = conn.execute("SELECT code FROM reports WHERE id = ?", (report_id,)).fetchone()
            if row and row["code"] == code:
                conn.execute(
                    "UPDATE reports SET title=?, position=?, report_type=?, period=?, content=?, versions=?,"
                    " updated_at=? WHERE id=?",
                    (title, position, report_type, period, content, payload, _now(), report_id),
                )
                return report_id
        return conn.insert(
            "INSERT INTO reports (code, title, position, report_type, period, content, versions, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (code, title, position, report_type, period, content, payload, _now(), _now()),
        )


def list_reports(code: str, limit: int = 60) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, position, report_type, period, content, created_at, updated_at"
            " FROM reports WHERE code = ? ORDER BY updated_at DESC LIMIT ?",
            (code, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_report(report_id: int, code: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND code = ?", (report_id, code)
        ).fetchone()
    return dict(row) if row else None


def delete_report(report_id: int, code: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM reports WHERE id = ? AND code = ?", (report_id, code))
    return cur.rowcount > 0
