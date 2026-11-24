"""汇报官 Web 版：FastAPI + Jinja2 服务端模板 + 原生 JS。

与 Streamlit 版并存，复用 core/ 下的业务能力，不修改 core/ 任何文件。
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import markdown as md
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import llm, payments, store
from core.config import ROOT_DIR, get_settings
from core.db import connection
from core.exporter import ensure_title, md_to_docx
from core.llm import LLMError
from core.payments import PLANS, yuan
from core.prompts import (
    AUDIENCES,
    LENGTHS,
    POSITIONS,
    QUICK_ACTIONS,
    REPORT_TYPES,
    build_generation_prompt,
    build_refine_prompt,
)

BASE_DIR = Path(__file__).resolve().parent
MARKETING_DIR = ROOT_DIR / "docs"
COOKIE_NAME = "k"
VISITOR_COOKIE = "vid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60 天
DEFAULT_LENGTH = "标准（约450-550字）"

# 简单的单 IP 生成限流：防止清 cookie 刷免费试用把大模型额度刷爆
_GEN_WINDOW = 3600
_GEN_LIMIT = 30
_GEN_HITS: dict[str, list[float]] = {}

store.init_db()

app = FastAPI(title="智报", docs_url=None, redoc_url=None, openapi_url=None)

_assets_dir = ROOT_DIR / "assets"
if _assets_dir.is_dir():
    app.mount("/static/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
settings = get_settings()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ------------------------------------------------------------------ 通用工具
@app.middleware("http")
async def ensure_visitor(request: Request, call_next):
    """给每个浏览器发一个访客标识，用于统计免费试用次数。"""
    visitor = request.cookies.get(VISITOR_COOKIE) or ""
    is_new = not visitor
    if is_new:
        visitor = secrets.token_hex(16)
    request.state.visitor = visitor
    response = await call_next(request)
    if is_new:
        response.set_cookie(
            VISITOR_COOKIE,
            visitor,
            max_age=COOKIE_MAX_AGE * 3,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response


def _visitor(request: Request) -> str:
    return getattr(request.state, "visitor", "") or request.cookies.get(VISITOR_COOKIE, "")


def _session(request: Request) -> tuple[dict | None, str | None]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None, None
    return store.session_info(token), token


def _page_auth(request: Request) -> tuple[dict | None, str | None, RedirectResponse | None]:
    info, token = _session(request)
    if not info:
        return None, None, RedirectResponse("/activate", status_code=303)
    return info, token, None


def _api_auth(request: Request) -> tuple[dict, str]:
    info, token = _session(request)
    if not info or not token:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新激活兑换码")
    return info, token


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _page(info: dict, request: Request, active: str, template: str, context: dict | None = None, **kwargs):
    data = {
        "request": request,
        "info": info,
        "active": active,
        "settings": settings,
        "site_url": (settings.site_url or "").rstrip("/"),
    }
    if context:
        data.update(context)
    return templates.TemplateResponse(request, template, data, **kwargs)


def default_period(report_type: str) -> str:
    today = datetime.now()
    if report_type == "日报":
        week = "一二三四五六日"[today.weekday()]
        return f"{today:%Y-%m-%d}（周{week}）"
    if report_type == "周报":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        return f"{start:%Y.%m.%d} - {end:%m.%d}"
    if report_type == "月报":
        return f"{today.year}年{today.month}月"
    quarter = (today.month - 1) // 3 + 1
    return f"{today.year}年 Q{quarter}"


def _period_defaults() -> dict[str, str]:
    return {t: default_period(t) for t in REPORT_TYPES}


def _load_versions(record: dict) -> list[dict]:
    try:
        versions = json.loads(record.get("versions") or "[]")
    except (TypeError, ValueError):
        versions = []
    if not isinstance(versions, list) or not versions:
        versions = [{"label": "初稿", "text": record.get("content", "")}]
    return [v for v in versions if isinstance(v, dict)]


def _render_markdown(text: str) -> str:
    # 先转义 HTML，避免模型输出里的原始标签被浏览器执行
    return md.markdown(html.escape(text or "", quote=False), extensions=["extra", "sane_lists"])


def _qr_url(value: str = "") -> str:
    qr = (value or "").strip()
    if not qr:
        return ""
    if qr.startswith("http://") or qr.startswith("https://"):
        return qr
    path = Path(qr)
    if not path.is_absolute():
        path = ROOT_DIR / qr
    if path.is_file():
        return f"/static/assets/{quote(path.name)}"
    return ""


def _title_of(record: dict) -> str:
    return f"{record.get('position', '')}{record.get('report_type', '')}（{record.get('period', '')}）".strip()


# ------------------------------------------------------------------ 管理后台（人工确认到账）
ADMIN_COOKIE = "zb_adm"
ADMIN_BASE = "/zb-manage-2026"
ADMIN_MAX_AGE = 60 * 60 * 12


def _admin_sig(user: str, ts: str) -> str:
    key = (settings.admin_password or "zhibao").encode("utf-8")
    return hmac.new(key, f"{user}|{ts}".encode("utf-8"), hashlib.sha256).hexdigest()


def _admin_authed(request: Request) -> bool:
    parts = (request.cookies.get(ADMIN_COOKIE) or "").split("|")
    if len(parts) != 3:
        return False
    user, ts, sig = parts
    if not hmac.compare_digest(user, settings.admin_user):
        return False
    if not hmac.compare_digest(sig, _admin_sig(user, ts)):
        return False
    try:
        issued = int(ts)
    except ValueError:
        return False
    return time.time() - issued <= ADMIN_MAX_AGE


def _orders_snapshot(limit: int = 80) -> tuple[list[dict], dict]:
    conn = connection()
    with conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        stats = conn.execute(
            "SELECT status, COUNT(*) AS c, COALESCE(SUM(amount), 0) AS total FROM orders GROUP BY status"
        ).fetchall()
    summary = {"pending": 0, "paid": 0, "pending_amount": 0, "paid_amount": 0}
    for row in stats:
        key = "paid" if row["status"] == "paid" else "pending"
        summary[key] += int(row["c"] or 0)
        summary[key + "_amount"] += int(row["total"] or 0)
    orders = []
    for row in rows:
        item = dict(row)
        item["amount_label"] = yuan(item["amount"])
        item["channel_label"] = payments.CHANNELS.get(item.get("channel") or "", "扫码支付")
        item["status_text"] = "已到账" if item["status"] == "paid" else "待确认"
        item["claimed"] = (item.get("remark") or "").startswith("用户已点付款")
        orders.append(item)
    return orders, summary


# ------------------------------------------------------------------ 首页 / 认证
_MARKETING_EXT = (".html", ".css", ".js", ".svg", ".png", ".jpg", ".ico", ".xml", ".txt")


def _marketing_file(name: str) -> Path | None:
    """把 docs/ 里的静态营销页映射成站点根路径，防止目录穿越。"""
    if not name:
        name = "index.html"
    if not name.endswith(_MARKETING_EXT):
        return None
    base = MARKETING_DIR.resolve()
    path = (base / name).resolve()
    if path != base and base not in path.parents:
        return None
    return path if path.is_file() else None


@app.api_route("/", methods=["GET", "HEAD"])
def index():
    page = _marketing_file("index.html")
    if page:
        return FileResponse(page)
    return RedirectResponse("/activate", status_code=302)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    base = (settings.site_url or "").rstrip("/")
    return f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {base}/sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap_xml():
    base = (settings.site_url or "").rstrip("/")
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        ("/", "1.0"),
        ("/gongzuo-zongjie.html", "1.0"),
        ("/zhoubao-moban.html", "0.9"),
        ("/zhoubao-fanwen.html", "0.9"),
        ("/yuebao-fanwen.html", "0.9"),
        ("/shuzhi-baogao.html", "0.9"),
        ("/shixi-zhoubao-fanwen.html", "0.9"),
        ("/jidu-zongjie.html", "0.8"),
        ("/zhoubao-kaitou.html", "0.8"),
        ("/ribao-fanwen.html", "0.8"),
        ("/zongjie-kaitou-jiewei.html", "0.8"),
        ("/activate", "0.8"),
        ("/buy", "0.8"),
        ("/guide", "0.6"),
    ]
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, priority in urls:
        body.append(
            f"<url><loc>{base}{path}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>{priority}</priority></url>"
        )
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")


@app.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request):
    info, _ = _session(request)
    return _page(info, request, "guide", "guide.html")



@app.get("/activate", response_class=HTMLResponse)
def activate_page(request: Request, code: str = ""):
    info, _ = _session(request)
    if info and not code:
        return RedirectResponse("/write", status_code=302)
    trial_left = store.trial_left(_visitor(request), settings.trial_uses)
    return _page(
        info,
        request,
        "activate",
        "activate.html",
        {
            "code_value": code.strip(),
            "trial_left": trial_left,
            "plans": [{**plan, "price_label": yuan(plan["price"])} for plan in PLANS],
        },
    )


@app.post("/activate", response_class=HTMLResponse)
def activate_submit(request: Request, code: str = Form("")):
    info, token = _session(request)
    result = store.activate(code, token or "")
    if not result.ok:
        return _page(
            info,
            request,
            "activate",
            "activate.html",
            {"error": result.message, "code_value": (code or "").strip(),
             "trial_left": store.trial_left(_visitor(request), settings.trial_uses),
             "plans": [{**plan, "price_label": yuan(plan["price"])} for plan in PLANS]},
            status_code=400,
        )
    response = RedirectResponse("/write", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        result.token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/activate", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ------------------------------------------------------------------ 写汇报
@app.get("/write", response_class=HTMLResponse)
def write_page(request: Request):
    info, _token = _session(request)
    trial_left = store.trial_left(_visitor(request), settings.trial_uses)
    if not info and trial_left <= 0:
        return RedirectResponse("/activate", status_code=303)
    return _page(
        info,
        request,
        "write",
        "write.html",
        {
            "positions": list(POSITIONS),
            "report_types": REPORT_TYPES,
            "audiences": AUDIENCES,
            "lengths": list(LENGTHS),
            "default_length": DEFAULT_LENGTH,
            "period_defaults": _period_defaults(),
            "trial_mode": not info,
            "trial_left": trial_left,
        },
    )


@app.post("/api/generate")
async def api_generate(request: Request):
    info, token = _session(request)
    trial_mode = not info
    visitor = _visitor(request)

    ip = (request.headers.get("x-real-ip") or (request.client.host if request.client else "")).strip()
    now_ts = time.time()
    hits = [t for t in _GEN_HITS.get(ip, []) if now_ts - t < _GEN_WINDOW]
    if len(hits) >= _GEN_LIMIT:
        raise HTTPException(status_code=429, detail="生成太频繁，请稍后再试")
    hits.append(now_ts)
    _GEN_HITS[ip] = hits

    if trial_mode and store.trial_left(visitor, settings.trial_uses) <= 0:
        raise HTTPException(status_code=402, detail="免费试用已用完，激活兑换码后可继续使用")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    brief = str(body.get("brief") or "").strip()[: settings.max_input_chars]
    position = str(body.get("position") or "")
    report_type = str(body.get("report_type") or "")
    audience = str(body.get("audience") or "")
    length_key = str(body.get("length_key") or DEFAULT_LENGTH)
    period = str(body.get("period") or "").strip()
    extra = str(body.get("extra") or "")

    if not brief:
        raise HTTPException(status_code=400, detail="请先粘贴你的工作碎片")
    if position not in POSITIONS:
        raise HTTPException(status_code=400, detail="请选择有效的岗位")
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="请选择有效的汇报类型")
    if audience not in AUDIENCES:
        audience = AUDIENCES[0]
    if length_key not in LENGTHS:
        length_key = DEFAULT_LENGTH
    if not period:
        period = default_period(report_type)
    if not trial_mode and info["remaining"] == 0:
        raise HTTPException(status_code=400, detail="可用次数已用完，请激活新的兑换码")

    messages = build_generation_prompt(
        report_type=report_type,
        position=position,
        audience=audience,
        length_key=length_key,
        period=period,
        brief=brief,
        extra=extra,
    )
    code = info["code"] if info else ""

    def stream():
        chunks: list[str] = []
        try:
            for chunk in llm.stream_chat(messages):
                if chunk:
                    chunks.append(chunk)
                    yield _sse({"type": "chunk", "text": chunk})
        except LLMError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return
        except Exception:
            yield _sse({"type": "error", "message": "生成失败，请稍后重试"})
            return

        content = "".join(chunks).strip()
        if not content:
            yield _sse({"type": "error", "message": "模型没有返回内容，请调整输入后重试"})
            return

        guess = f"{position}{report_type}（{period}）"
        title = ensure_title(content, guess).splitlines()[0].lstrip("# ").strip() or guess

        if trial_mode:
            ok, left = store.consume_trial(visitor, settings.trial_uses)
            if not ok:
                yield _sse({"type": "error", "message": "免费试用已用完，激活兑换码后可继续使用"})
                return
            yield _sse(
                {
                    "type": "done",
                    "trial": True,
                    "report_id": None,
                    "title": title,
                    "remaining": left,
                    "code": "",
                }
            )
            return

        try:
            report_id = store.save_report(
                code,
                title=title,
                position=position,
                report_type=report_type,
                period=period,
                content=content,
                versions=[{"label": "初稿", "text": content}],
            )
        except Exception:
            yield _sse({"type": "error", "message": "报告保存失败，请稍后重试"})
            return

        ok, left = store.consume(token)
        yield _sse(
            {
                "type": "done",
                "report_id": report_id,
                "title": title,
                "remaining": left if ok else info["remaining"],
                "code": code,
            }
        )

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/api/refine/{report_id}")
async def api_refine(report_id: int, request: Request):
    info, token = _api_auth(request)
    record = store.get_report(report_id, info["code"])
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在或已删除")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    instruction = str(body.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="请填写修改要求")
    position = str(body.get("position") or record["position"] or "")
    report_type = str(body.get("report_type") or record["report_type"] or "")
    if position not in POSITIONS:
        position = record["position"] or "通用白领"
    if report_type not in REPORT_TYPES:
        report_type = record["report_type"] or "周报"

    versions = _load_versions(record)
    if len(versions) - 1 >= settings.max_refines:
        raise HTTPException(
            status_code=400,
            detail=f"单份报告最多微调 {settings.max_refines} 轮，建议先生成一份新报告",
        )

    messages = build_refine_prompt(record["content"], instruction, position, report_type)
    code = info["code"]
    title = record["title"] or _title_of(record)
    period = record["period"]

    def stream():
        chunks: list[str] = []
        try:
            for chunk in llm.stream_chat(messages):
                if chunk:
                    chunks.append(chunk)
                    yield _sse({"type": "chunk", "text": chunk})
        except LLMError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return
        except Exception:
            yield _sse({"type": "error", "message": "微调失败，请稍后重试"})
            return

        content = "".join(chunks).strip()
        if not content:
            yield _sse({"type": "error", "message": "模型没有返回内容，请换个说法再试"})
            return

        new_versions = versions + [{"label": f"微调{len(versions)}", "text": content}]
        try:
            store.save_report(
                code,
                title=title,
                position=position,
                report_type=report_type,
                period=period,
                content=content,
                versions=new_versions,
                report_id=report_id,
            )
        except Exception:
            yield _sse({"type": "error", "message": "修改保存失败，请稍后重试"})
            return

        store.log_event(token, "refine", instruction[:80])
        yield _sse(
            {
                "type": "done",
                "report_id": report_id,
                "title": title,
                "versions": len(new_versions),
            }
        )

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/api/reports/{report_id}/edit")
async def api_edit_report(report_id: int, request: Request):
    """手动改标题/正文：不调用模型、不扣次数，保存后记入历史版本。"""
    info, _token = _api_auth(request)
    record = store.get_report(report_id, info["code"])
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在或已删除")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    title = str(body.get("title") or "").strip()[:80]
    content = str(body.get("content") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="正文太短，至少写 10 个字")

    if title == (record["title"] or "") and content == record["content"]:
        return {"ok": True, "unchanged": True}

    versions = _load_versions(record)
    versions.append({"label": "手动修改", "text": content})
    if len(versions) > 30:
        versions = versions[-30:]

    store.save_report(
        info["code"],
        title=title,
        position=record["position"],
        report_type=record["report_type"],
        period=record["period"],
        content=content,
        versions=versions,
        report_id=report_id,
    )
    return {"ok": True, "report_id": report_id}


# ------------------------------------------------------------------ 我的报告
@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, q: str = "", start: str = "", end: str = ""):
    info, _token, redirect = _page_auth(request)
    if redirect:
        return redirect

    keyword = (q or "").strip()
    reports = store.list_reports(info["code"])
    filtered = []
    for record in reports:
        day = (record.get("updated_at") or "")[:10]
        if keyword and keyword not in (record["title"] + record["content"]):
            continue
        if start and day < start:
            continue
        if end and day > end:
            continue
        filtered.append(record)

    return _page(
        info,
        request,
        "reports",
        "reports.html",
        {
            "reports": filtered,
            "total": len(reports),
            "q": keyword,
            "start": start,
            "end": end,
        },
    )


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request):
    info, _token, redirect = _page_auth(request)
    if redirect:
        return redirect
    record = store.get_report(report_id, info["code"])
    if not record:
        return RedirectResponse("/reports", status_code=303)

    versions = _load_versions(record)
    return _page(
        info,
        request,
        "reports",
        "report_detail.html",
        {
            "record": record,
            "content_html": _render_markdown(record["content"]),
            "versions": versions,
            "quick_actions": QUICK_ACTIONS,
            "can_refine": len(versions) - 1 < settings.max_refines,
        },
    )


@app.get("/reports/{report_id}/docx")
def report_docx(report_id: int, request: Request):
    info, _token, redirect = _page_auth(request)
    if redirect:
        return redirect
    record = store.get_report(report_id, info["code"])
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在或已删除")

    title = _title_of(record)
    data = md_to_docx(ensure_title(record["content"], title), title)
    filename = f"{record['position'] or '汇报'}{record['report_type']}_{(record['updated_at'] or '')[:10]}.docx"
    headers = {
        "Content-Disposition": f"attachment; filename=\"report.docx\"; filename*=UTF-8''{quote(filename)}"
    }
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@app.post("/reports/{report_id}/delete")
def report_delete(report_id: int, request: Request):
    info, _token, redirect = _page_auth(request)
    if redirect:
        return redirect
    store.delete_report(report_id, info["code"])
    return RedirectResponse("/reports", status_code=303)


# ------------------------------------------------------------------ 购买次数
@app.get("/buy", response_class=HTMLResponse)
def buy_page(request: Request):
    info, _token = _session(request)
    plan_cards = [{**plan, "price_label": yuan(plan["price"])} for plan in PLANS]
    return _page(
        info,
        request,
        "buy",
        "buy.html",
        {
            "plans": plan_cards,
            "alipay_qr_url": _qr_url(settings.alipay_qr),
            "wechat_qr_url": _qr_url(settings.wechat_qr),
            "support_wechat": settings.support_wechat,
            "support_text": settings.support_text,
            "auto_confirm": payments.gateway_ready(),
        },
    )


@app.post("/api/orders")
async def api_create_order(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    plan_id = str(body.get("plan_id") or "")
    channel = str(body.get("channel") or "alipay").strip().lower()
    if channel not in payments.CHANNELS:
        channel = "alipay"
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=400, detail="请选择有效的套餐")

    order_no = store.create_order(
        plan["id"], plan["name"], plan["price"], plan["uses"], channel, ""
    )

    pay_url = ""
    if payments.gateway_ready():
        result = payments.create_payment(
            order_no, plan["name"], plan["price"], channel, f"{request.base_url}buy?order={order_no}"
        )
        pay_url = result.pay_url if result.ok else ""

    qr = _qr_url(settings.alipay_qr if channel == "alipay" else settings.wechat_qr)
    return JSONResponse(
        {
            "order_no": order_no,
            "plan_name": plan["name"],
            "amount": yuan(plan["price"]),
            "uses": plan["uses"],
            "status": "pending",
            "channel": channel,
            "channel_label": payments.CHANNELS[channel],
            "qr_url": qr,
            "pay_url": pay_url,
            "auto_confirm": payments.gateway_ready(),
            "support_wechat": settings.support_wechat,
            "support_text": settings.support_text,
        }
    )


@app.get("/api/orders/{order_no}")
def api_get_order(order_no: str, request: Request):
    order = store.get_order((order_no or "").strip())
    if not order:
        raise HTTPException(status_code=404, detail="订单号不存在，请检查后重试")

    # 配置了支付网关时，主动查单，到账即自动发码（无需人工确认）
    if order["status"] != "paid" and payments.gateway_ready():
        if payments.check_paid(order["order_no"]):
            store.mark_order_paid(order["order_no"], "epay")
            order = store.get_order(order["order_no"]) or order

    paid = order["status"] == "paid" and bool(order["code"])
    channel = order.get("channel") or "alipay"
    qr = _qr_url(settings.alipay_qr if channel == "alipay" else settings.wechat_qr)
    return {
        "order_no": order["order_no"],
        "plan_name": order["plan_name"],
        "amount": yuan(order["amount"]),
        "uses": order["uses"],
        "status": order["status"],
        "status_text": "已支付" if order["status"] == "paid" else "待确认到账",
        "created_at": order["created_at"],
        "channel": channel,
        "channel_label": payments.CHANNELS.get(channel, "扫码支付"),
        "qr_url": qr,
        "auto_confirm": payments.gateway_ready(),
        "claimed": (order.get("remark") or "").startswith("用户已点付款"),
        "code": order["code"] if paid else "",
        "activate_url": f"/activate?code={quote(order['code'])}" if paid else "",
    }


@app.post("/api/orders/{order_no}/claim")
def api_claim_order(order_no: str):
    """用户点「我已付款」：记录催单，管理后台可优先核对。"""
    order = store.get_order((order_no or "").strip())
    if not order:
        raise HTTPException(status_code=404, detail="订单号不存在，请检查后重试")
    if order["status"] == "paid" and order["code"]:
        return {"ok": True, "paid": True, "code": order["code"]}
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connection()
    with conn:
        conn.execute(
            "UPDATE orders SET remark = ? WHERE order_no = ?",
            (f"用户已点付款 {stamp}", order["order_no"]),
        )
    return {"ok": True, "paid": False, "claimed_at": stamp}


# ------------------------------------------------------------------ 管理后台
@app.get(ADMIN_BASE, response_class=HTMLResponse)
def admin_page(request: Request, ok: str = "", err: str = ""):
    authed = _admin_authed(request)
    orders: list[dict] = []
    summary = {"pending": 0, "paid": 0, "pending_amount": 0, "paid_amount": 0}
    if authed:
        orders, summary = _orders_snapshot()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "request": request,
            "authed": authed,
            "orders": orders,
            "summary": summary,
            "ok": ok,
            "err": err,
            "site_url": settings.site_url,
            "admin_base": ADMIN_BASE,
        },
    )


@app.post(ADMIN_BASE + "/login")
def admin_login(request: Request, username: str = Form(""), password: str = Form("")):
    if username.strip() == settings.admin_user and password == settings.admin_password:
        ts = str(int(time.time()))
        token = f"{settings.admin_user}|{ts}|{_admin_sig(settings.admin_user, ts)}"
        response = RedirectResponse(ADMIN_BASE, status_code=303)
        response.set_cookie(
            ADMIN_COOKIE, token, max_age=ADMIN_MAX_AGE, httponly=True, samesite="lax", path="/"
        )
        return response
    return RedirectResponse(ADMIN_BASE + "?err=用户名或密码错误", status_code=303)


@app.get(ADMIN_BASE + "/logout")
def admin_logout():
    response = RedirectResponse(ADMIN_BASE, status_code=303)
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return response


@app.post(ADMIN_BASE + "/orders/{order_no}/confirm")
def admin_confirm(order_no: str, request: Request):
    if not _admin_authed(request):
        return RedirectResponse(ADMIN_BASE, status_code=303)
    ok, code, message = store.mark_order_paid(order_no, "manual")
    tip = f"已确认 {order_no}，兑换码 {code}" if ok else message
    return RedirectResponse(ADMIN_BASE + "?ok=" + quote(tip), status_code=303)


@app.api_route("/pay/notify", methods=["GET", "POST"])
async def pay_notify(request: Request):
    """易支付异步回调：验签 + 金额校验，通过后自动发码。"""
    if not payments.gateway_ready():
        return PlainTextResponse("fail", status_code=400)
    params = dict(request.query_params) if request.method == "GET" else dict(await request.form())
    order_no = str(params.get("out_trade_no") or "").strip()
    order = store.get_order(order_no)
    if not order:
        return PlainTextResponse("fail", status_code=404)
    if not payments.verify_sign(params):
        return PlainTextResponse("fail", status_code=400)
    if str(params.get("trade_status") or "") != "TRADE_SUCCESS":
        return PlainTextResponse("fail", status_code=400)
    try:
        paid_cents = round(float(params.get("money") or 0) * 100)
    except (TypeError, ValueError):
        return PlainTextResponse("fail", status_code=400)
    if paid_cents != int(order["amount"]):
        return PlainTextResponse("fail", status_code=400)

    store.mark_order_paid(order_no, "epay")
    return PlainTextResponse("success")


# ------------------------------------------------------------------ 营销页兜底
# 必须放在所有业务路由之后，保证 /write、/admin、/api 等不会被这里拦截。
@app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
def marketing_page(full_path: str):
    page = _marketing_file(full_path)
    if page is None:
        raise HTTPException(status_code=404, detail="页面不存在")
    return FileResponse(page)
