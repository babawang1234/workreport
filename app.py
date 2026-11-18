"""汇报官 · 工作汇报智能 Agent（Streamlit 单页应用）"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

from core import payments, store
from core.config import get_settings
from core.exporter import ensure_title, md_to_docx, md_to_plain
from core.llm import LLMError, stream_chat
from core.payments import CHANNELS, PLANS, check_paid, create_payment, gateway_ready, plan_by_id, yuan
from core.prompts import (
    AUDIENCES,
    LENGTHS,
    POSITIONS,
    QUICK_ACTIONS,
    REPORT_TYPES,
    SAMPLES,
    build_generation_prompt,
    build_refine_prompt,
)
from core.ui import CSS

ss = st.session_state
settings = get_settings()

st.set_page_config(
    page_title="汇报官 · 5 分钟搞定周报",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)
store.init_db()

for key, value in {
    "token": None,
    "report": "",
    "versions": [],
    "refine_count": 0,
    "meta": {},
    "pending": None,
    "report_type": "周报",
    "position": "产品经理",
    "audience": "直属上级",
    "length_key": "标准（约600-800字）",
    "brief": "",
    "extra": "",
    "refine_text": "",
    "admin_unlocked": False,
    "page": "use",
    "order_no": "",
    "pay_url": "",
    "pay_channel": "alipay",
    "pay_error": "",
    "report_id": None,
    "last_code": "",
    "buy_plan": "",
    "manual_order_no": "",
}.items():
    ss.setdefault(key, value)


# ---------------------------------------------------------------- 工具函数
def qp_get(key: str) -> str | None:
    try:
        value = st.query_params.get(key)
        return value if isinstance(value, str) else None
    except Exception:
        values = st.experimental_get_query_params().get(key)
        return values[0] if values else None


def qp_set(key: str, value: str) -> None:
    try:
        st.query_params[key] = value
    except Exception:
        st.experimental_set_query_params(**{key: value})


def default_period(report_type: str) -> str:
    today = datetime.now()
    if report_type == "日报":
        return today.strftime("%Y-%m-%d（%a）").replace("Mon", "周一").replace("Tue", "周二").replace(
            "Wed", "周三"
        ).replace("Thu", "周四").replace("Fri", "周五").replace("Sat", "周六").replace("Sun", "周日")
    if report_type == "周报":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        return f"{start:%Y.%m.%d} - {end:%m.%d}"
    if report_type == "月报":
        return f"{today.year}年{today.month}月"
    quarter = (today.month - 1) // 3 + 1
    return f"{today.year}年 Q{quarter}"


def trigger(action: dict) -> None:
    ss.pending = action
    st.rerun()


def goto(page: str) -> None:
    ss["_goto"] = page
    st.rerun()


def return_url() -> str:
    base = (settings.site_url or "http://localhost:8501").rstrip("/")
    token = f"&k={ss.token}" if ss.token else ""
    return f"{base}/?pay=return{token}"


def quota_html(remaining: int, used: int, total: int) -> str:
    return (
        '<div class="quota"><div><b>'
        + str(remaining)
        + '</b><span class="quota-unit">次可用</span></div>'
        + f'<div class="quota-sub">累计 {total} 次 · 已用 {used} 次</div></div>'
    )


def word_count(text: str) -> int:
    return len([c for c in text if not c.isspace()])


# ---------------------------------------------------------------- 会话授权
if not ss.token:
    candidate = qp_get("k")
    if candidate and store.session_info(candidate):
        ss.token = candidate
if ss.token and not store.session_info(ss.token):
    ss.token = None

session = store.session_info(ss.token) if ss.token else None


# ---------------------------------------------------------------- 侧边栏
def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px;">'
            '<div style="width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#4F46E5,#A855F7);'
            'display:flex;align-items:center;justify-content:center;color:#fff;font-size:19px;">报</div>'
            '<div><div style="font-weight:700;font-size:16px;color:#1B2130;">汇报官</div>'
            '<div style="font-size:12px;color:#6B7280;">WorkBrief Agent</div></div></div>',
            unsafe_allow_html=True,
        )

        quota_placeholder = st.empty()
        if session:
            quota_placeholder.markdown(
                quota_html(session["remaining"], session["used"], session["total"]), unsafe_allow_html=True
            )
            st.caption(f"兑换码：{session['code']}")
            if session.get("expires_at"):
                st.caption(f"有效期至：{session['expires_at'][:10]}")
        else:
            quota_placeholder.markdown(
                quota_html(0, 0, 0), unsafe_allow_html=True
            )

        st.radio(
            "导航",
            ["use", "reports", "buy"],
            key="page",
            format_func=lambda v: {"use": "✍️ 写汇报", "reports": "📁 我的报告", "buy": "💳 购买次数"}[v],
            label_visibility="collapsed",
        )

        with st.expander("🎟️ 激活 / 更换兑换码", expanded=not bool(session)):
            code_input = st.text_input("兑换码", key="activate_code", placeholder="例如 RP-8F3K2Q")
            if st.button("激活", width="stretch"):
                result = store.activate(code_input, ss.token or "")
                if result.ok:
                    ss.token = result.token
                    qp_set("k", result.token)
                    st.success(f"激活成功，可用 {result.remaining} 次")
                    st.rerun()
                else:
                    st.error(result.message)

        st.markdown("---")
        st.markdown(
            '<div class="muted"><b style="color:#1B2130;">怎么用最省力</b><br/>'
            "1. 把聊天记录、待办、口语描述整段粘进去，越真实越好<br/>"
            "2. 选岗位和汇报类型，点生成<br/>"
            "3. 不满意直接用大白话让它改，改到满意再导出</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown(f'<div class="muted">{settings.support_text}</div>', unsafe_allow_html=True)

        with st.expander("🔐 管理后台"):
            if ss.admin_unlocked:
                if st.button("退出后台", width="stretch"):
                    ss.admin_unlocked = False
                    st.rerun()
            else:
                pwd = st.text_input("管理密码", type="password", key="admin_pwd")
                if st.button("进入后台", width="stretch"):
                    if pwd and pwd == settings.admin_password:
                        ss.admin_unlocked = True
                        st.rerun()
                    else:
                        st.error("密码错误")
            if settings.admin_password == "admin888":
                st.caption("⚠️ 当前为默认密码，上线前请修改 .env 中的 ADMIN_PASSWORD")
        return quota_placeholder


if ss.get("_goto"):
    ss.page = ss["_goto"]
    ss["_goto"] = None

quota_ph = render_sidebar()


# ---------------------------------------------------------------- 主视图
def render_hero() -> None:
    st.markdown(
        '<div class="hero"><div class="hero-left">'
        '<div class="hero-logo">📝</div>'
        '<div><div class="hero-title">工作汇报智能 Agent</div>'
        '<div class="hero-sub">粘贴零散工作碎片 · 一键生成可直接提交的日报 / 周报 / 月报</div></div></div>'
        '<div class="hero-tags"><span class="hero-tag">5 分钟搞定 1 小时周报</span>'
        '<span class="hero-tag">13 个岗位风格</span><span class="hero-tag">支持多轮微调</span></div></div>',
        unsafe_allow_html=True,
    )


def render_samples() -> None:
    with st.expander("👀 先看看生成效果（示例，无需激活）"):
        tabs = st.tabs(list(SAMPLES.keys()))
        for tab, text in zip(tabs, SAMPLES.values()):
            with tab:
                st.markdown(text)


def render_landing() -> None:
    steps = st.columns(3)
    step_data = [
        ("1", "粘贴工作碎片", "聊天记录、待办，整段粘贴"),
        ("2", "选择岗位类型", "13 个岗位，自动匹配重点"),
        ("3", "导出提交", "微调满意后导出 Word"),
    ]
    for col, (num, title, desc) in zip(steps, step_data):
        with col:
            st.markdown(
                f'<div class="step"><span class="step-num">{num}</span>'
                f'<div><div class="step-title">{title}</div><div class="step-desc">{desc}</div></div></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="sec-title">选择套餐</div>', unsafe_allow_html=True)
    render_plan_cards()

    left, right = st.columns([1, 1.1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="card-title"><span class="dot"></span>已有兑换码？直接激活</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="muted">兑换码就是你的账号：手机和电脑输入同一个码，'
                "剩余次数和历史报告都会自动同步。</div>",
                unsafe_allow_html=True,
            )
            code = st.text_input("兑换码", key="lock_code", placeholder="例如 RP-8F3K2Q")
            if st.button("立即激活", type="primary", width="stretch"):
                result = store.activate(code, "")
                if result.ok:
                    ss.token = result.token
                    qp_set("k", result.token)
                    ss.page = "use"
                    st.rerun()
                else:
                    st.error(result.message)
            st.markdown(
                f'<div class="muted" style="margin-top:10px;">{settings.support_text}</div>', unsafe_allow_html=True
            )
    with right:
        with st.container(border=True):
            st.markdown('<div class="card-title"><span class="dot"></span>效果示例（无需购买）</div>', unsafe_allow_html=True)
            sample_name = st.radio("示例", list(SAMPLES.keys()), horizontal=True, label_visibility="collapsed")
            st.markdown(SAMPLES[sample_name])

    with st.expander("❓ 常见问题"):
        st.markdown(
            "**手机上能用吗？** 能，页面自适应手机；输入同一个兑换码即可看到全部历史报告和剩余次数。\n\n"
            "**次数怎么算？** 每生成一份报告扣 1 次；同一份报告的微调不扣次数（单份最多 20 轮）。\n\n"
            "**报告会保存吗？** 会保存在你的兑换码下，换设备登录也能找回；可随时在「我的报告」里删除。\n\n"
            "**付款后没收到兑换码？** 支付成功会自动发放并激活；也可在「购买次数」页点「我已完成支付」手动确认，或联系客服。"
        )


# ---------------------------------------------------------------- 购买 / 充值
def render_plan_cards() -> None:
    with st.container(key="plan_row"):
        cols = st.columns(len(PLANS), gap="small")
        for col, plan in zip(cols, PLANS):
            with col:
                with st.container(border=True):
                    badge_text = plan["badge"] or "占位"
                    hidden = "" if plan["badge"] else "visibility:hidden;"
                    st.markdown(
                        f'<div class="plan-card">'
                        f'<div class="plan-badge" style="{hidden}">{badge_text}</div>'
                        f'<div class="plan-name">{plan["name"]}</div>'
                        f'<div class="plan-price"><span class="rmb">¥</span>{yuan(plan["price"])}</div>'
                        f'<div class="plan-uses">{plan["uses"]} 次生成</div>'
                        f'<div class="plan-desc">{plan["desc"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    if gateway_ready():
                        label = "立即购买"
                    elif settings.alipay_qr:
                        label = "扫码购买"
                    else:
                        label = "联系客服"
                    if st.button(
                        label,
                        key=f"buy_{plan['id']}",
                        type="primary" if plan["badge"] else "secondary",
                        width="stretch",
                    ):
                        if gateway_ready():
                            start_order(plan)
                        elif settings.alipay_qr:
                            ss["buy_plan"] = plan["id"]
                            goto("buy")
                        else:
                            st.info(settings.support_text)


def start_order(plan: dict) -> None:
    order_no = store.create_order(plan["id"], plan["name"], plan["price"], plan["uses"], ss.pay_channel)
    ss.order_no = order_no
    ss.pay_url = ""
    ss.pay_error = ""
    ss.last_code = ""
    result = create_payment(order_no, plan["name"], plan["price"], ss.pay_channel, return_url())
    if result.ok:
        ss.pay_url = result.pay_url
    else:
        ss.pay_error = result.message
    st.rerun()


def finish_order(order_no: str) -> None:
    ok, code, message = store.mark_order_paid(order_no, "auto")
    if not ok:
        st.error(message)
        return
    result = store.activate(code, ss.token or "")
    if result.ok:
        ss.token = result.token
        qp_set("k", result.token)
        info = store.session_info(result.token)
        if info:
            quota_ph.markdown(
                quota_html(info["remaining"], info["used"], info["total"]), unsafe_allow_html=True
            )
    ss.last_code = code
    ss.order_no = ""
    ss.pay_url = ""


def _app_rerun() -> None:
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()


def _order_age_minutes(created_at: str) -> float:
    try:
        created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0.0
    return (datetime.now() - created).total_seconds() / 60


def render_payment_panel(order_no: str) -> None:
    order = store.get_order(order_no)
    if not order:
        ss.order_no = ""
        return
    with st.container(border=True):
        st.markdown(
            '<div class="card-title"><span class="dot"></span>最后一步：完成支付</div>', unsafe_allow_html=True
        )
        st.markdown(
            f'<div class="muted">订单号 {order["order_no"]}　·　{order["plan_name"]}　·　'
            f'<b style="color:#4F46E5;">¥{yuan(order["amount"])}</b>　·　'
            f'{CHANNELS.get(order["channel"], "")}</div>',
            unsafe_allow_html=True,
        )
        if ss.pay_error:
            st.warning(ss.pay_error)
        if ss.pay_url:
            st.link_button("👉 打开支付页面完成付款", ss.pay_url, type="primary", width="stretch")
        st.caption("支付成功后本页会自动刷新并发放兑换码，无需返回。")
        if st.button("我已支付，立即确认", width="stretch"):
            with st.spinner("正在向支付平台确认…"):
                paid = check_paid(order_no)
            if paid:
                finish_order(order_no)
                _app_rerun()
            else:
                st.warning("暂未查到支付结果。若已扣款，请等 10 秒再点一次，或联系客服处理。")
        if st.button("取消这个订单", width="stretch"):
            ss.order_no = ""
            ss.pay_url = ""
            st.rerun()


@st.fragment(run_every=8)
def payment_watcher(order_no: str) -> None:
    order = store.get_order(order_no)
    if not order:
        return
    if order["status"] == "paid":
        finish_order(order_no)
        _app_rerun()
        return
    if _order_age_minutes(order["created_at"]) > 60:
        return
    if check_paid(order_no):
        finish_order(order_no)
        _app_rerun()


def render_manual_pay() -> None:
    """支付宝个人收款码：扫码付款 → 提交订单 → 后台补单发码 → 用户凭订单号查询。"""
    plans = {p["id"]: p for p in PLANS}
    ids = list(plans)
    chosen = ss.get("buy_plan") or ids[0]
    index = ids.index(chosen) if chosen in ids else 0

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>支付宝扫码付款</div>', unsafe_allow_html=True)
        left, right = st.columns([1, 1.35], gap="large")
        with left:
            qr = settings.alipay_qr
            if qr.startswith("http"):
                st.image(qr, width=210)
            elif Path(qr).exists():
                st.image(qr, width=210)
            else:
                st.warning("收款码未就绪：请把图片放到 assets/alipay_qr.png，或在 Secrets 配置 ALIPAY_QR")
            st.caption("付款时在备注里写上你的微信名或手机尾号，方便对账")
        with right:
            plan_id = st.selectbox(
                "选择套餐",
                ids,
                index=index,
                format_func=lambda x: f"{plans[x]['name']} · ¥{yuan(plans[x]['price'])} · {plans[x]['uses']} 次",
            )
            unpaid_note = st.text_input(
                "付款备注 / 联系方式", placeholder="例如：微信 wxid_abc 或 手机尾号 8899", key="manual_contact"
            )
            st.caption(f"扫码支付 ¥{yuan(plans[plan_id]['price'])}，金额与所选套餐保持一致")
            if st.button("我已付款，提交订单", type="primary", width="stretch"):
                note = unpaid_note.strip()
                if not note:
                    st.error("请先填写付款备注或联系方式，方便客服核对")
                else:
                    plan = plans[plan_id]
                    no = store.create_order(plan["id"], plan["name"], plan["price"], plan["uses"], "alipay_qr", note)
                    ss["manual_order_no"] = no
                    st.rerun()

        if ss.get("manual_order_no"):
            st.success("订单已提交，客服核对到账后会自动发码")
            st.code(ss["manual_order_no"], language=None)
            if settings.support_wechat:
                st.caption(
                    f"把订单号和付款截图发微信 {settings.support_wechat}，一般几分钟内处理完成"
                )
            else:
                st.caption("把订单号和付款截图发给客服，一般几分钟内处理完成")

        st.markdown("---")
        st.markdown('<div class="card-title"><span class="dot"></span>已付款？用订单号查兑换码</div>', unsafe_allow_html=True)
        query = st.text_input("订单号", key="order_query", placeholder="粘贴订单号，例如 R20261117XXXX")
        if st.button("查询订单", width="stretch"):
            ss["order_lookup"] = query.strip()

        looked_up = ss.get("order_lookup") or ""
        order = store.get_order(looked_up) if looked_up else None
        if looked_up and not order:
            st.error("订单号不存在，请检查后重试")
        elif order and order["status"] == "paid" and order["code"]:
            st.success("已确认到账，兑换码如下")
            st.code(order["code"], language=None)
            if st.button("激活并开始使用", type="primary", width="stretch", key="activate_from_order"):
                result = store.activate(order["code"], ss.token or "")
                if result.ok:
                    ss.token = result.token
                    qp_set("k", result.token)
                    ss.last_code = order["code"]
                    goto("use")
                else:
                    st.error(result.message)
        elif order:
            if settings.support_wechat:
                st.info(f"订单还在等待确认，可加微信 {settings.support_wechat} 催单")
            else:
                st.info("订单还在等待确认，付款后请联系客服催单")


def render_buy_page() -> None:
    st.markdown('<div class="sec-title">购买次数</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="muted">兑换码就是你的账号：手机、电脑输入同一个码，剩余次数和历史报告实时同步。'
        "付款后系统自动发码并激活。</div>",
        unsafe_allow_html=True,
    )
    if session:
        st.markdown(
            f'<div class="pill">当前账号 {session["code"]}</div>'
            f'<span class="muted">剩余 {session["remaining"]} 次</span>',
            unsafe_allow_html=True,
        )

    if not gateway_ready():
        if settings.alipay_qr:
            render_manual_pay()
        else:
            st.warning("在线支付通道尚未开通，可直接联系客服购买兑换码。")
    else:
        st.radio(
            "支付方式",
            list(CHANNELS),
            key="pay_channel",
            format_func=CHANNELS.get,
            horizontal=True,
            label_visibility="collapsed",
        )

    render_plan_cards()

    if ss.last_code:
        with st.container(border=True):
            st.success("支付成功，兑换码已自动激活")
            st.code(ss.last_code, language=None)
            st.caption("换设备时输入这个兑换码即可同步全部数据，请截图或复制保存")
            if st.button("开始写汇报", type="primary", width="stretch"):
                goto("use")
    elif ss.order_no:
        render_payment_panel(ss.order_no)
        payment_watcher(ss.order_no)


# ---------------------------------------------------------------- 我的报告（多端同步）
def open_report(report_id: int) -> None:
    record = store.get_report(report_id, session["code"])
    if not record:
        st.error("报告不存在或已删除")
        return
    ss.report = record["content"]
    ss.report_id = record["id"]
    ss.meta = {
        "position": record["position"],
        "report_type": record["report_type"],
        "period": record["period"],
        "audience": ss.get("audience", "直属上级"),
        "created_at": record["created_at"],
    }
    try:
        versions = json.loads(record["versions"]) or []
    except (json.JSONDecodeError, TypeError):
        versions = []
    ss.versions = versions or [{"label": "初稿", "text": record["content"]}]
    ss.refine_count = 0
    goto("use")


def render_reports_page() -> None:
    st.markdown('<div class="sec-title">我的报告</div>', unsafe_allow_html=True)
    st.caption(f"账号 {session['code']} · 在手机或电脑输入同一个兑换码，可看到全部历史报告")
    reports = store.list_reports(session["code"])
    if not reports:
        st.markdown(
            '<div class="empty"><span class="big">📁</span>还没有保存的报告<br/>去「写汇报」生成第一份吧</div>',
            unsafe_allow_html=True,
        )
        if st.button("去写汇报", type="primary"):
            goto("use")
        return

    for record in reports:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.markdown(f"**{record['title']}**")
            col1.caption(f"{record['position']} · {record['report_type']} · 更新于 {record['updated_at'][:16]}")
            if col2.button("打开", key=f"open_{record['id']}", width="stretch"):
                open_report(record["id"])
            if col3.button("删除", key=f"del_{record['id']}", width="stretch"):
                store.delete_report(record["id"], session["code"])
                if ss.report_id == record["id"]:
                    ss.report = ""
                    ss.report_id = None
                st.rerun()


# ---------------------------------------------------------------- 输入区
def render_input_card() -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="card-title"><span class="dot"></span>① 粘贴你的工作碎片</div>', unsafe_allow_html=True
        )
        st.text_area(
            "工作记录",
            key="brief",
            height=250,
            placeholder=(
                "随便写，越真实越好。例如：\n"
                "周一开产品评审会，方案改了 3 版；周二对接运营确认活动排期；\n"
                "周三处理 5 个客诉；周四输出 Q4 规划初稿；周五和技术对齐开发排期……"
            ),
            label_visibility="collapsed",
        )
        used = word_count(ss.brief)
        st.caption(f"已输入 {used} 字" + ("（超出上限，将自动截断）" if used > settings.max_input_chars else ""))

        col_a, col_b = st.columns(2)
        position = col_a.selectbox("岗位", list(POSITIONS), key="position")
        report_type = col_b.selectbox("汇报类型", REPORT_TYPES, key="report_type")

        if ss.get("_period_type") != report_type:
            ss.period_input = default_period(report_type)
            ss._period_type = report_type
            st.rerun()

        col_c, col_d = st.columns(2)
        col_c.text_input("汇报周期", key="period_input")
        audience = col_d.selectbox("汇报对象", AUDIENCES, key="audience")

        length_key = st.selectbox("篇幅", list(LENGTHS), key="length_key")
        st.text_input(
            "补充要求（选填）",
            key="extra",
            placeholder="例如：这次重点体现降本增效 / 少提问题、多写成果",
        )

        disabled = not ss.brief.strip()
        if st.button("✨ 一键生成汇报", type="primary", width="stretch", disabled=disabled):
            if session and session["remaining"] <= 0:
                st.error("可用次数已用完，请激活新的兑换码")
            else:
                trigger(
                    {
                        "kind": "generate",
                        "position": position,
                        "report_type": report_type,
                        "audience": audience,
                        "length_key": length_key,
                        "period": ss.period_input or default_period(report_type),
                        "brief": ss.brief.strip()[: settings.max_input_chars],
                        "extra": ss.extra,
                    }
                )
        if not disabled and not session:
            st.caption("尚未激活，生成前请先在左侧输入兑换码")


# ---------------------------------------------------------------- 输出区
def run_stream(messages: list[dict[str, str]]):
    placeholder = st.empty()
    text = ""
    try:
        for chunk in stream_chat(messages):
            text += chunk
            placeholder.markdown(text + " ▍")
    except LLMError as exc:
        placeholder.empty()
        st.error(str(exc))
        return None
    if not text.strip():
        placeholder.empty()
        st.error("模型没有返回内容，请调整输入后重试")
        return None
    placeholder.markdown(text.strip())
    return text.strip()


def handle_generate(action: dict) -> None:
    info = store.session_info(ss.token)
    if not info:
        st.error("登录状态失效，请重新激活兑换码")
        return
    if info["remaining"] <= 0:
        st.error("可用次数已用完，请激活新的兑换码")
        return

    messages = build_generation_prompt(
        report_type=action["report_type"],
        position=action["position"],
        audience=action["audience"],
        length_key=action["length_key"],
        period=action["period"],
        brief=action["brief"],
        extra=action["extra"],
    )
    with st.spinner("正在梳理你的工作碎片，整理成汇报…"):
        text = run_stream(messages)
    if not text:
        return

    ok, left = store.consume(ss.token)
    if ok:
        quota_ph.markdown(quota_html(left, info["used"] + 1, info["total"]), unsafe_allow_html=True)
    else:
        st.warning("生成成功，但次数扣减异常，请联系客服处理")

    ss.report = text
    ss.versions = [{"label": "初稿", "text": text}]
    ss.refine_count = 0
    ss.meta = {
        "position": action["position"],
        "report_type": action["report_type"],
        "period": action["period"],
        "audience": action["audience"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if session:
        ss.report_id = store.save_report(
            session["code"],
            title=f"{action['position']}{action['report_type']}（{action['period']}）",
            position=action["position"],
            report_type=action["report_type"],
            period=action["period"],
            content=text,
            versions=ss.versions,
        )


def handle_refine(action: dict) -> None:
    if not ss.report:
        return
    if ss.refine_count >= settings.max_refines:
        st.warning(f"单份报告最多微调 {settings.max_refines} 轮，建议先生成一份新报告")
        return

    messages = build_refine_prompt(
        ss.report, action["instruction"], ss.meta.get("position", ss.position), ss.meta.get("report_type", "周报")
    )
    with st.spinner("正在按你的要求修改…"):
        text = run_stream(messages)
    if not text:
        return

    ss.versions = ss.versions + [{"label": f"微调 {ss.refine_count + 1}", "text": text}]
    ss.report = text
    ss.refine_count += 1
    store.log_event(ss.token, "refine", action["instruction"][:80])
    if session:
        meta = ss.meta or {}
        ss.report_id = store.save_report(
            session["code"],
            title=f"{meta.get('position', '')}{meta.get('report_type', '')}（{meta.get('period', '')}）",
            position=meta.get("position", ""),
            report_type=meta.get("report_type", ""),
            period=meta.get("period", ""),
            content=text,
            versions=ss.versions,
            report_id=ss.report_id,
        )


def render_toolbar() -> None:
    meta = ss.meta or {}
    st.markdown(
        '<div style="margin:2px 0 10px;">'
        f'<span class="pill">{meta.get("position", "通用白领")}</span>'
        f'<span class="pill">{meta.get("report_type", "周报")}</span>'
        f'<span class="pill">{meta.get("period", "")}</span>'
        f'<span class="muted">{word_count(ss.report)} 字</span></div>',
        unsafe_allow_html=True,
    )

    title = f"{meta.get('position', '')}{meta.get('report_type', '')}（{meta.get('period', '')}）".strip()
    stem = f"{meta.get('position', '汇报')}{meta.get('report_type', '')}_{datetime.now():%Y%m%d}"
    markdown_text = ensure_title(ss.report, title)
    plain_text = md_to_plain(markdown_text)
    try:
        docx_bytes = md_to_docx(markdown_text, title)
    except Exception:
        docx_bytes = b""

    c1, c2, c3, c4 = st.columns(4)
    if docx_bytes:
        c1.download_button("⬇️ Word", docx_bytes, file_name=f"{stem}.docx", width="stretch")
    c2.download_button("⬇️ Markdown", markdown_text.encode("utf-8"), file_name=f"{stem}.md", width="stretch")
    c3.download_button("⬇️ 纯文本", plain_text.encode("utf-8"), file_name=f"{stem}.txt", width="stretch")
    if c4.button("↩️ 撤销上一步", width="stretch", disabled=len(ss.versions) <= 1):
        ss.versions = ss.versions[:-1]
        ss.report = ss.versions[-1]["text"]
        ss.refine_count = max(0, ss.refine_count - 1)
        if session and ss.report_id:
            store.save_report(
                session["code"],
                title=title,
                position=meta.get("position", ""),
                report_type=meta.get("report_type", ""),
                period=meta.get("period", ""),
                content=ss.report,
                versions=ss.versions,
                report_id=ss.report_id,
            )
        st.rerun()

    with st.expander("📋 复制到飞书 / 企微 / 邮件（纯文本）"):
        st.code(plain_text, language=None)


def render_refine_panel() -> None:
    st.markdown("---")
    st.markdown(
        '<div class="card-title" style="margin-bottom:6px;"><span class="dot"></span>③ 不满意？直接说，我改</div>',
        unsafe_allow_html=True,
    )
    feedback = st.text_input(
        "修改要求",
        key="refine_text",
        placeholder="例如：把第二点拆得更详细 / 改成国企正式文风 / 压缩成 300 字",
        label_visibility="collapsed",
    )

    rows = [QUICK_ACTIONS[i : i + 3] for i in range(0, len(QUICK_ACTIONS), 3)]
    for row in rows:
        cols = st.columns(len(row))
        for col, label in zip(cols, row):
            if col.button(label, key=f"qa_{label}", width="stretch"):
                trigger({"kind": "refine", "instruction": label})

    col1, col2 = st.columns([1, 1.6])
    if col1.button("应用修改", type="primary", width="stretch"):
        if feedback.strip():
            trigger({"kind": "refine", "instruction": feedback.strip()})
        else:
            st.info("先写一句修改要求，或点上面的快捷指令")
    col2.markdown(
        f'<div class="muted" style="padding-top:8px;">微调不额外扣次数，'
        f"本份报告还可改 {max(0, settings.max_refines - ss.refine_count)} 轮</div>",
        unsafe_allow_html=True,
    )


def render_output_card() -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>② 汇报正文</div>', unsafe_allow_html=True)

        pending = ss.pending
        ss.pending = None
        if pending:
            if pending["kind"] == "generate":
                handle_generate(pending)
            elif pending["kind"] == "refine":
                handle_refine(pending)

        if ss.report:
            if not pending:
                st.markdown(ss.report)
            render_toolbar()
            render_refine_panel()
        else:
            st.markdown(
                '<div class="empty"><span class="big">🗂️</span>'
                "左侧粘贴工作碎片，选好岗位与汇报类型<br/>点「一键生成汇报」，30 秒拿走可直接提交的成稿"
                "</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------- 管理后台
def render_admin() -> None:
    st.markdown("## 🔐 管理后台")
    stats = store.admin_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("兑换码", stats["codes"])
    c2.metric("总次数", stats["total_uses"])
    c3.metric("已用次数", stats["used_uses"])
    c4.metric("激活用户", stats["users"])
    c5.metric("今日生成", stats["today"])

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>生成兑换码</div>', unsafe_allow_html=True)
        with st.form("create_codes"):
            a, b, c, d = st.columns(4)
            count = a.number_input("数量", min_value=1, max_value=200, value=10)
            uses = b.number_input("每个可用次数", min_value=1, max_value=10000, value=20)
            prefix = c.text_input("前缀", value="RP")
            days = d.number_input("有效天数（0=永久）", min_value=0, max_value=3650, value=0)
            note = st.text_input("备注", placeholder="例如：抖音渠道 / 双十一活动")
            if st.form_submit_button("生成", type="primary"):
                codes = store.create_codes(int(count), int(uses), prefix, int(days), note)
                st.success(f"已生成 {len(codes)} 个兑换码，可直接复制发给用户：")
                st.code("\n".join(codes), language=None)

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>兑换码列表</div>', unsafe_allow_html=True)
        keyword = st.text_input("搜索", placeholder="输入兑换码或备注关键词", label_visibility="collapsed")
        rows = store.list_codes(keyword)
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

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>订单与收入</div>', unsafe_allow_html=True)
        order_stat = store.order_stats()
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("累计收入", f"¥{yuan(order_stat['revenue'])}")
        s2.metric("今日收入", f"¥{yuan(order_stat['today_revenue'])}")
        s3.metric("已付订单", order_stat["paid_count"])
        s4.metric("待支付", order_stat["pending"])
        keyword = st.text_input(
            "搜索订单", placeholder="订单号 / 兑换码", label_visibility="collapsed", key="order_search"
        )
        orders = store.list_orders(keyword)
        st.dataframe(
            [
                {
                    "订单号": o["order_no"],
                    "套餐": o["plan_name"],
                    "金额": yuan(o["amount"]),
                    "次数": o["uses"],
                    "状态": "已支付" if o["status"] == "paid" else "待支付",
                    "备注": o.get("remark") or "",
                    "兑换码": o["code"] or "",
                    "创建时间": o["created_at"],
                    "支付时间": o["paid_at"] or "",
                }
                for o in orders
            ],
            width="stretch",
            hide_index=True,
        )
        a, b = st.columns([3, 1])
        manual_no = a.text_input(
            "订单号", key="manual_order", placeholder="手动补单：粘贴订单号后可强制确认到账并发码", label_visibility="collapsed"
        )
        if b.button("确认到账并发码", width="stretch"):
            ok, code, message = store.mark_order_paid(manual_no.strip(), "manual")
            if ok:
                st.success(f"{message}：{code}")
            else:
                st.error(message)

    with st.container(border=True):
        st.markdown('<div class="card-title"><span class="dot"></span>最近记录</div>', unsafe_allow_html=True)
        st.dataframe(store.recent_logs(30), width="stretch", hide_index=True)


# ---------------------------------------------------------------- 页面组装
render_hero()

if ss.admin_unlocked:
    render_admin()
    st.stop()

if ss.page == "buy":
    render_buy_page()
    st.stop()

if not session:
    render_landing()
    st.stop()

if ss.page == "reports":
    render_reports_page()
    st.stop()

left, right = st.columns([1, 1.12], gap="large")
with left:
    render_input_card()
with right:
    render_output_card()
