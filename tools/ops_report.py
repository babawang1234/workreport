"""每日经营巡检：读取线上库，输出当天订单 / 收入 / 待发码 / 生成量。

凭证放在仓库外的 ~/.workreport/ops.env（DATABASE_URL=...），不进 Git。
用法：python tools/ops_report.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = Path.home() / ".workreport" / "ops.env"


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

if not os.environ.get("DATABASE_URL"):
    print(f"缺少数据库凭证：请在 {ENV_FILE} 中写入一行")
    print("DATABASE_URL=postgresql://...（从 Streamlit Secrets 复制）")
    sys.exit(1)

from core import store  # noqa: E402

store.init_db()

today = datetime.now().strftime("%Y-%m-%d")
stats = store.order_stats()
codes = store.admin_stats()
orders = store.list_orders(limit=50)
pending = [o for o in orders if o["status"] == "pending"]
today_paid = [o for o in orders if o["status"] == "paid" and (o["paid_at"] or "").startswith(today)]

print(f"经营巡检 {datetime.now():%Y-%m-%d %H:%M}")
print(f"今日成交：{len(today_paid)} 单，收入 ¥{stats['today_revenue'] / 100:.2f}")
print(f"累计成交：{stats['paid_count']} 单，收入 ¥{stats['revenue'] / 100:.2f}")
print(f"今日生成：{codes['today']} 次；兑换码 {codes['codes']} 个，剩余 {codes['total_uses'] - codes['used_uses']} 次")

print(f"\n待发码订单：{len(pending)}")
for o in pending:
    print(f"  {o['order_no']} | {o['plan_name']} | ¥{o['amount'] / 100:.2f} | 备注：{o.get('remark') or '-'} | {o['created_at']}")

print("\n最近 10 条记录：")
for log in store.recent_logs(10):
    print(f"  {log['ts']} | {log['action']} | {log['code'] or '-'} | {log['detail'] or ''}")
