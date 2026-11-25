"""把报告推送到飞书 / 钉钉 / 企业微信群机器人（官方 Webhook，零成本）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from .extract import _ssl_context

CHANNELS = {"feishu": "飞书", "dingtalk": "钉钉", "wecom": "企业微信"}
HOSTS = {
    "feishu": {"open.feishu.cn", "open.larksuite.com"},
    "dingtalk": {"oapi.dingtalk.com"},
    "wecom": {"qyapi.weixin.qq.com"},
}
MAX_BYTES = 3800


class PushError(RuntimeError):
    """对外暴露的可读错误。"""


def _plain(text: str) -> str:
    """飞书文本消息不渲染 Markdown，先把标记去掉。"""
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[>*]\s*", "", line)
        lines.append(line)
    return "\n".join(lines)


def _clip_bytes(text: str) -> str:
    data = (text or "").encode("utf-8")
    if len(data) <= MAX_BYTES:
        return text
    cut = data[:MAX_BYTES].decode("utf-8", errors="ignore").rstrip()
    return cut + "\n…（内容较长，已截断，完整报告请在智报查看）"


def _check_webhook(channel: str, webhook: str):
    host = (urlparse(webhook).hostname or "").lower()
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or host not in HOSTS[channel]:
        raise PushError("Webhook 地址不正确，请粘贴对应群机器人的官方地址")
    return webhook


def _sign_feishu(secret: str) -> dict:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return {"timestamp": timestamp, "sign": base64.b64encode(digest).decode()}


def _sign_dingtalk(webhook: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(secret.encode(), string_to_sign, digestmod=hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest))
    joiner = "&" if "?" in webhook else "?"
    return f"{webhook}{joiner}timestamp={timestamp}&sign={sign}"


def _post_json(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raise PushError(f"群机器人返回 {exc.code}，请检查 Webhook 是否有效") from exc
    except (URLError, OSError) as exc:
        raise PushError("连接群机器人失败，请检查网络后重试") from exc
    try:
        return json.loads(raw or "{}")
    except ValueError as exc:
        raise PushError("群机器人返回了无法识别的内容") from exc


def push(channel: str, webhook: str, title: str, content: str, secret: str = "") -> str:
    """发送报告，返回渠道中文名；失败抛 PushError。"""
    channel = (channel or "").strip()
    if channel not in CHANNELS:
        raise PushError("暂不支持这个渠道，可选飞书、钉钉、企业微信")
    url = _check_webhook(channel, (webhook or "").strip())
    title = (title or "工作汇报").strip()[:60]
    body = _clip_bytes((content or "").strip())
    if not body:
        raise PushError("报告内容为空，无法推送")

    if channel == "feishu":
        text = _clip_bytes(f"【{title}】\n\n{_plain(body)}")
        payload = {"msg_type": "text", "content": {"text": text}}
        if secret:
            payload.update(_sign_feishu(secret))
    elif channel == "dingtalk":
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": body}}
        if secret:
            url = _sign_dingtalk(url, secret)
    else:
        payload = {"msgtype": "markdown", "markdown": {"content": f"**【{title}】**\n\n{body}"}}

    data = _post_json(url, payload)
    code = data.get("errcode", data.get("code", data.get("StatusCode", 0)))
    if code not in (0, None):
        msg = data.get("errmsg") or data.get("msg") or "推送失败"
        raise PushError(str(msg)[:120])
    return CHANNELS[channel]
