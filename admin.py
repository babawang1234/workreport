"""汇报官 · 运营后台（独立应用，仅管理员账号可见）。

启动：streamlit run admin.py
数据与用户端共用同一个数据库（DATABASE_URL / 本地 SQLite）。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

import streamlit as st

from core import store
from core.config import get_settings
from core.payments import yuan
from core.ui import CSS

ss = st.session_state
settings = get_settings()

st.set_page_config(page_title="汇报官 · 运营后台", page_icon="📊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
store.init_db()

for key, value in {"authed": False, "issued_codes": []}.items():
    ss.setdefault(key, value)


def hero() -> None:
    st.markdown(
        '<div class="hero"><div class="hero-left"><div class="hero-logo">📊</div>'
        '<div><div class="hero-title">运营后台</div>'
        '<div class="hero-sub">营收 · 订单 · 兑换码 · 运营记录（仅管理员可见）</div></div></div></div>',
        unsafe_allow_html=True,
    )


def csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------- 登录
if not ss.authed:
    hero()
    st.caption("独立后台：普通用户页面不显示任何营收入口，只有管理员账号登录后可见")
    if settings.admin_password == "admin888":
        st.warning("当前使用默认密码，请在 Secrets 中设置 ADMIN_USER / ADMIN_PASSWORD 后重启应用")
    with st.form("admin_login"):
        user = st.text_input("管理员账号", placeholder="admin")
        pwd = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary", width="stretch")
    if submitted:
        if user.strip() == settings.admin_user and pwd == settings.admin_password:
            ss.authed = True
            st.rerun()
        else:
            st.error("账号或密码错误")
    st.stop()


# ---------------------------------------------------------------- 顶部
top_left, top_right = st.columns([5, 1])
top_left.markdown("## 📊 运营后台")
if top_right.button("退出登录", width="stretch"):
    ss.authed = False
    st.rerun()
st.caption(f"当前管理员：{settings.admin_user} · {datetime.now():%Y-%m-%d %H:%M}")


# ---------------------------------------------------------------- 经营看板
def render_dashboard() -> None:
    stats = store.order_stats()
    codes = store.admin_stats()
    all_orders = store.list_orders(limit=200)
    pending = [o for o in all_orders if o["status"] == "pending"]

    row1 = st.columns(4)
    row1[0].metric("今日收入", f"¥{yuan(stats['today_revenue'])}")
    row1[1].metric("今日成交", stats["today_count"])
    row1[2].metric("累计收入", f"¥{yuan(stats['revenue'])}")
    row1[3].metric("待发码订单", stats["pending"])

    row2 = st.columns(4)
    row2[0].metric("累计成交", stats["paid_count"])
    row2[1].metric("今日生成", codes["today"])
    row2[2].metric("兑换码数量", codes["codes"])
    row2[3].metric("剩余可用次数", codes["total_uses"] - codes["used_uses"])

    if pending:
        st.warning(f"有 {len(pending)} 笔订单等待发码，核对到账后到「订单管理」补单")
        st.dataframe(
            [
                {
                    "订单号": o["order_no"],
                    "套餐": o["plan_name"],
                    "金额": f"¥{yuan(o['amount'])}",
                    "备注": o.get("remark") or "",
                    "下单时间": o["created_at"],
                }
                for o in pending
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.success("没有待发码订单，当前无需处理")

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>最近订单</div>', unsafe_allow_html=True)
        st.dataframe(
            [
                {
                    "订单号": o["order_no"],
                    "套餐": o["plan_name"],
                    "金额": f"¥{yuan(o['amount'])}",
                    "状态": "已支付" if o["status"] == "paid" else "待支付",
                    "兑换码": o["code"] or "",
                    "备注": o.get("remark") or "",
                    "时间": o["paid_at"] or o["created_at"],
                }
                for o in all_orders[:10]
            ],
            width="stretch",
            hide_index=True,
        )


# ---------------------------------------------------------------- 订单管理
def render_orders() -> None:
    st.markdown('<div class="sec-title">订单管理</div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>手动补单</div>', unsafe_allow_html=True)
        st.caption("用户付款并把订单号发给你后，在这里确认到账并自动发放兑换码")
        a, b = st.columns([3, 1])
        manual_no = a.text_input(
            "订单号", key="manual_order", placeholder="粘贴用户订单号，例如 20261118XXXXXXXX", label_visibility="collapsed"
        )
        if b.button("确认到账并发码", type="primary", width="stretch"):
            ok, code, message = store.mark_order_paid(manual_no.strip(), "manual")
            if ok:
                st.success(f"{message}：{code}")
            else:
                st.error(message)

    with st.container(border=True):
        a, b = st.columns([2, 1])
        keyword = a.text_input(
            "搜索订单", placeholder="订单号 / 兑换码", label_visibility="collapsed"
        )
        status = b.selectbox("状态", ["全部", "待支付", "已支付"], label_visibility="collapsed")
        orders = store.list_orders(keyword.strip())
        if status != "全部":
            want = "pending" if status == "待支付" else "paid"
            orders = [o for o in orders if o["status"] == want]

        rows = [
            {
                "订单号": o["order_no"],
                "套餐": o["plan_name"],
                "金额(元)": yuan(o["amount"]),
                "次数": o["uses"],
                "状态": "已支付" if o["status"] == "paid" else "待支付",
                "备注": o.get("remark") or "",
                "兑换码": o["code"] or "",
                "下单时间": o["created_at"],
                "支付时间": o["paid_at"] or "",
            }
            for o in orders
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(f"共 {len(rows)} 条")
        if rows:
            st.download_button(
                "⬇️ 导出订单 CSV",
                csv_bytes(rows, list(rows[0])),
                file_name=f"orders_{datetime.now():%Y%m%d}.csv",
                width="stretch",
            )


# ---------------------------------------------------------------- 兑换码
def render_codes() -> None:
    st.markdown('<div class="sec-title">兑换码</div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>批量生成</div>', unsafe_allow_html=True)
        with st.form("create_codes"):
            a, b, c, d = st.columns(4)
            count = a.number_input("数量", min_value=1, max_value=200, value=10)
            uses = b.number_input("每个可用次数", min_value=1, max_value=10000, value=20)
            prefix = c.text_input("前缀", value="RP")
            days = d.number_input("有效天数（0=永久）", min_value=0, max_value=3650, value=0)
            note = st.text_input("备注", placeholder="例如：抖音渠道 / 双十一活动")
            if st.form_submit_button("生成", type="primary"):
                ss.issued_codes = store.create_codes(int(count), int(uses), prefix, int(days), note)
        if ss.issued_codes:
            st.success(f"已生成 {len(ss.issued_codes)} 个，复制发给用户即可：")
            st.code("\n".join(ss.issued_codes), language=None)

    with st.container(border=True):
        keyword = st.text_input("搜索", placeholder="兑换码或备注关键词", label_visibility="collapsed")
        rows = store.list_codes(keyword.strip())
        st.dataframe(
            [
                {
                    "兑换码": r.code,
                    "总次数": r.total,
                    "已用": r.used,
                    "剩余": r.remaining,
                    "状态": "正常" if r.active else "已停用",
                    "过期时间": r.expires_at or "永久",
                    "备注": r.note,
                    "创建时间": r.created_at,
                }
                for r in rows
            ],
            width="stretch",
            hide_index=True,
        )
        st.caption(f"共 {len(rows)} 条")

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>单码操作</div>', unsafe_allow_html=True)
        a, b, c, d = st.columns([2, 1, 1, 1])
        target = a.text_input("兑换码", placeholder="RP-XXXXXX", label_visibility="collapsed")
        delta = b.number_input("增加次数", min_value=0, max_value=10000, value=10)
        if c.button("加次数", width="stretch"):
            if target and store.add_uses(target, int(delta)):
                st.success("已增加次数")
            else:
                st.error("操作失败，请检查兑换码")
        if d.button("停用 / 启用", width="stretch"):
            info = store.code_detail(target) if target else None
            if not info:
                st.error("兑换码不存在")
            elif store.set_code_active(target, not info.active):
                st.success("已切换状态，刷新列表查看")
            else:
                st.error("操作失败")


# ---------------------------------------------------------------- 运营记录
def render_logs() -> None:
    st.markdown('<div class="sec-title">运营记录</div>', unsafe_allow_html=True)
    st.caption("下单、发码、激活、生成等关键动作都会记录在这里")
    logs = store.recent_logs(100)
    st.dataframe(logs, width="stretch", hide_index=True)
    if logs:
        st.download_button(
            "⬇️ 导出记录 CSV",
            csv_bytes(logs, ["ts", "code", "action", "detail"]),
            file_name=f"logs_{datetime.now():%Y%m%d}.csv",
            width="stretch",
        )


tab_dashboard, tab_orders, tab_codes, tab_logs = st.tabs(["📊 经营看板", "🧾 订单管理", "🎟️ 兑换码", "📜 运营记录"])
with tab_dashboard:
    render_dashboard()
with tab_orders:
    render_orders()
with tab_codes:
    render_codes()
with tab_logs:
    render_logs()
