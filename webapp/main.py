"""汇报官 Web 版：FastAPI + Jinja2 服务端模板 + 原生 JS。

与 Streamlit 版并存，复用 core/ 下的业务能力，不修改 core/ 任何文件。
"""

from __future__ import annotations

import html
import json
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import markdown as md
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import llm, store
from core.config import ROOT_DIR, get_settings
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
COOKIE_NAME = "k"
VISITOR_COOKIE = "vid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60 天
DEFAULT_LENGTH = "标准（约600-800字）"

store.init_db()

app = FastAPI(title="汇报官", docs_url=None, redoc_url=None, openapi_url=None)

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
    data = {"request": request, "info": info, "active": active, "settings": settings}
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


def _qr_url() -> str:
    qr = (settings.alipay_qr or "").strip()
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


# ------------------------------------------------------------------ 首页 / 认证
@app.get("/")
def index(request: Request):
    info, _ = _session(request)
    return RedirectResponse("/write" if info else "/activate", status_code=302)


@app.get("/activate", response_class=HTMLResponse)
def activate_page(request: Request, code: str = ""):
    info, _ = _session(request)
    if info and not code:
        return RedirectResponse("/write", status_code=302)
    trial_left = store.trial_left(_visitor(request), settings.trial_uses)
    return _page(
        info, request, "activate", "activate.html", {"code_value": code.strip(), "trial_left": trial_left}
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
             "trial_left": store.trial_left(_visitor(request), settings.trial_uses)},
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
    if not trial_mode and info["remaining"] <= 0:
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
    info, _token, redirect = _page_auth(request)
    if redirect:
        return redirect
    plan_cards = [{**plan, "price_label": yuan(plan["price"])} for plan in PLANS]
    return _page(
        info,
        request,
        "buy",
        "buy.html",
        {
            "plans": plan_cards,
            "qr_url": _qr_url(),
            "support_wechat": settings.support_wechat,
            "support_text": settings.support_text,
        },
    )


@app.post("/api/orders")
async def api_create_order(request: Request):
    _api_auth(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    plan_id = str(body.get("plan_id") or "")
    remark = str(body.get("remark") or "").strip()[:200]
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=400, detail="请选择有效的套餐")
    if not remark:
        raise HTTPException(status_code=400, detail="请先填写付款备注或联系方式，方便客服核对")

    order_no = store.create_order(
        plan["id"], plan["name"], plan["price"], plan["uses"], "alipay_qr", remark
    )
    return JSONResponse(
        {
            "order_no": order_no,
            "plan_name": plan["name"],
            "amount": yuan(plan["price"]),
            "uses": plan["uses"],
            "status": "pending",
            "support_wechat": settings.support_wechat,
            "support_text": settings.support_text,
        }
    )


@app.get("/api/orders/{order_no}")
def api_get_order(order_no: str, request: Request):
    _api_auth(request)
    order = store.get_order((order_no or "").strip())
    if not order:
        raise HTTPException(status_code=404, detail="订单号不存在，请检查后重试")

    paid = order["status"] == "paid" and bool(order["code"])
    return {
        "order_no": order["order_no"],
        "plan_name": order["plan_name"],
        "amount": yuan(order["amount"]),
        "uses": order["uses"],
        "status": order["status"],
        "status_text": "已支付" if order["status"] == "paid" else "待确认",
        "created_at": order["created_at"],
        "code": order["code"] if paid else "",
        "activate_url": f"/activate?code={quote(order['code'])}" if paid else "",
    }
