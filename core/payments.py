"""充值购买：套餐定义 + 易支付（epay 通用协议）对接。

支持任意兼容易支付协议的聚合支付平台（个人可申请，返回 payurl）。
未配置支付参数时，页面自动降级为「联系客服购买」，不影响正常使用。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from .config import get_settings

PLANS: list[dict] = [
    {"id": "starter", "name": "体验版", "price": 990, "uses": 10, "desc": "先试 10 份，够用两个月", "badge": ""},
    {"id": "standard", "name": "标准版", "price": 2900, "uses": 40, "desc": "最划算，长期写周报", "badge": "最受欢迎"},
    {"id": "pro", "name": "专业版", "price": 6900, "uses": 120, "desc": "日均一份，够用小半年", "badge": ""},
    {"id": "team", "name": "团队版", "price": 19900, "uses": 400, "desc": "小组共用，分摊更省", "badge": ""},
]

CHANNELS = {"alipay": "支付宝", "wxpay": "微信支付"}


@dataclass
class PaymentResult:
    ok: bool
    pay_url: str = ""
    message: str = ""


def plan_by_id(plan_id: str) -> dict | None:
    return next((p for p in PLANS if p["id"] == plan_id), None)


def yuan(cents: int) -> str:
    return f"{cents / 100:.2f}".rstrip("0").rstrip(".")


def gateway_ready() -> bool:
    s = get_settings()
    return bool(s.epay_url and s.epay_pid and s.epay_key)


def _sign(params: dict[str, str], key: str) -> str:
    items = sorted((k, v) for k, v in params.items() if k not in ("sign", "sign_type") and v not in ("", None))
    raw = "&".join(f"{k}={v}" for k, v in items)
    return hashlib.md5((raw + key).encode("utf-8")).hexdigest()


def verify_sign(params: dict[str, str]) -> bool:
    """校验易支付异步回调签名。"""
    s = get_settings()
    if not s.epay_key:
        return False
    sign = str(params.get("sign") or "")
    if not sign:
        return False
    return hmac.compare_digest(_sign(params, s.epay_key), sign.lower())


def _site_url() -> str:
    return (get_settings().site_url or "http://localhost:8501").rstrip("/")


def create_payment(
    order_no: str,
    plan_name: str,
    amount_cents: int,
    channel: str = "alipay",
    return_url: str = "",
) -> PaymentResult:
    """向支付平台下单，返回可跳转的收银台地址。"""
    s = get_settings()
    if not gateway_ready():
        return PaymentResult(False, message="支付通道未配置")
    try:
        import requests
    except ImportError:
        return PaymentResult(False, message="缺少 requests 依赖")

    params = {
        "pid": s.epay_pid,
        "type": channel,
        "out_trade_no": order_no,
        "notify_url": f"{_site_url()}/pay/notify",
        "return_url": return_url or f"{_site_url()}/?pay=return",
        "name": f"汇报官 {plan_name}",
        "money": f"{amount_cents / 100:.2f}",
        "sitename": "汇报官",
    }
    params["sign"] = _sign(params, s.epay_key)
    params["sign_type"] = "MD5"
    try:
        resp = requests.post(f"{s.epay_url.rstrip('/')}/mapi.php", data=params, timeout=10)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return PaymentResult(False, message=f"支付平台连接失败：{str(exc)[:80]}")

    if str(data.get("code")) == "1":
        url = data.get("payurl") or data.get("qrcode") or data.get("url") or ""
        if url:
            return PaymentResult(True, pay_url=url)
    return PaymentResult(False, message=str(data.get("msg") or "下单失败，请稍后重试")[:120])


def check_paid(order_no: str) -> bool:
    """主动查单（不依赖异步回调），已支付返回 True。"""
    s = get_settings()
    if not gateway_ready():
        return False
    try:
        import requests

        resp = requests.get(
            f"{s.epay_url.rstrip('/')}/api.php",
            params={"act": "order", "pid": s.epay_pid, "key": s.epay_key, "out_trade_no": order_no},
            timeout=8,
        )
        data = resp.json()
        return str(data.get("status")) == "1" or str(data.get("code")) == "1" and str(data.get("status")) == "1"
    except Exception:  # noqa: BLE001
        return False


def notify_url_hint() -> str:
    return f"{_site_url()}/pay/notify"


def wait_and_confirm(order_no: str, attempts: int = 3, interval: float = 1.5) -> bool:
    for i in range(attempts):
        if check_paid(order_no):
            return True
        if i < attempts - 1:
            time.sleep(interval)
    return False
