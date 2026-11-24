"""模型接入：OpenAI 兼容接口，流式输出，异常转成中文可读提示。"""

from __future__ import annotations

from collections.abc import Iterator

from .config import get_settings


class LLMError(RuntimeError):
    """对外暴露的可读错误。"""


def _client():
    settings = get_settings()
    if not settings.api_key:
        raise LLMError("尚未配置模型密钥：请在 .env 中填写 LLM_API_KEY 后重启应用")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("缺少 openai 依赖，请执行 pip install -r requirements.txt") from exc
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=120.0, max_retries=1)


def _friendly(exc: Exception) -> str:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    text = str(exc)
    if name == "AuthenticationError" or status == 401:
        return "模型密钥无效或已过期，请检查 .env 中的 LLM_API_KEY"
    if name == "RateLimitError" or status == 429:
        return "模型调用过于频繁或额度不足，请稍后再试"
    if name == "APIConnectionError" or name == "APITimeoutError":
        return "网络连接模型服务失败，请检查网络后重试"
    if name == "NotFoundError" or status == 404:
        return "模型名称不存在，请检查 .env 中的 LLM_MODEL"
    if status in (402, 403):
        return "模型账户余额不足或无权限，请检查模型服务商账户"
    if status and status >= 500:
        return "模型服务暂时不可用，请稍后重试"
    return f"生成失败：{text[:200]}"


def stream_chat(messages: list[dict[str, str]], *, temperature: float | None = None) -> Iterator[str]:
    settings = get_settings()
    client = _client()
    budget = settings.max_tokens
    # 推理模型（如 glm-5.3-flash）可能把预算全用在 reasoning 上，正文为空且 finish_reason=length。
    # 这种情况下自动加倍预算重试一次。
    for attempt in range(2):
        produced = False
        finish = None
        try:
            stream = client.chat.completions.create(
                model=settings.model,
                messages=messages,
                temperature=settings.temperature if temperature is None else temperature,
                max_tokens=budget,
                stream=True,
            )
            for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                choice = choices[0]
                if getattr(choice, "finish_reason", None):
                    finish = choice.finish_reason
                delta = getattr(choice, "delta", None)
                piece = getattr(delta, "content", None) if delta else None
                if piece:
                    produced = True
                    yield piece
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成可读提示
            raise LLMError(_friendly(exc)) from exc
        if produced or finish != "length" or attempt == 1:
            return
        budget = 16384


def transcribe(audio: bytes, filename: str = "audio.wav") -> str:
    """语音转文字（智谱 GLM-ASR，OpenAI 兼容 /audio/transcriptions 接口）。"""
    settings = get_settings()
    api_key = settings.asr_api_key or settings.api_key
    if not api_key:
        raise LLMError("尚未配置语音识别密钥：请在 .env 中填写 ASR_API_KEY 或 LLM_API_KEY")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("缺少 openai 依赖，请执行 pip install -r requirements.txt") from exc
    client = OpenAI(api_key=api_key, base_url=settings.asr_base_url, timeout=120.0, max_retries=1)
    try:
        resp = client.audio.transcriptions.create(
            model=settings.asr_model,
            file=(filename, audio),
        )
    except Exception as exc:  # noqa: BLE001 - 统一转成可读提示
        raise LLMError(_friendly(exc)) from exc
    return (getattr(resp, "text", "") or "").strip()
