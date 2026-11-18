"""应用配置：优先读取 .env / 环境变量，其次读取 Streamlit secrets。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"


def _load_dotenv() -> None:
    path = ROOT_DIR / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def _secret(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return default


def _default_qr() -> str:
    """未配置 ALIPAY_QR 时，若仓库内有收款码图片则直接使用。"""
    for name in ("alipay_qr.png", "alipay_qr.jpg"):
        if (ROOT_DIR / "assets" / name).exists():
            return f"assets/{name}"
    return ""


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    admin_password: str
    db_path: Path
    database_url: str
    max_input_chars: int
    max_refines: int
    support_text: str
    support_wechat: str
    site_url: str
    epay_url: str
    epay_pid: str
    epay_key: str
    alipay_qr: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        api_key=_secret("LLM_API_KEY"),
        base_url=_secret("LLM_BASE_URL", "https://api.deepseek.com"),
        model=_secret("LLM_MODEL", "deepseek-chat"),
        temperature=float(_secret("LLM_TEMPERATURE", "0.5") or 0.5),
        max_tokens=int(_secret("LLM_MAX_TOKENS", "2400") or 2400),
        admin_password=_secret("ADMIN_PASSWORD", "admin888"),
        db_path=DATA_DIR / "app.db",
        database_url=_secret("DATABASE_URL"),
        max_input_chars=int(_secret("MAX_INPUT_CHARS", "8000") or 8000),
        max_refines=int(_secret("MAX_REFINES", "20") or 20),
        support_text=_secret("SUPPORT_TEXT", "如需购买或续费，请联系客服微信"),
        support_wechat=_secret("SUPPORT_WECHAT"),
        site_url=_secret("SITE_URL", "http://localhost:8501"),
        epay_url=_secret("EPAY_URL"),
        epay_pid=_secret("EPAY_PID"),
        epay_key=_secret("EPAY_KEY"),
        alipay_qr=_secret("ALIPAY_QR") or _default_qr(),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
