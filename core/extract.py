"""把上传的文档、截图、网页链接转成可继续加工的纯文本。"""

from __future__ import annotations

import html as html_lib
import io
import re

MAX_CHARS = 6000
MAX_BYTES = 10 * 1024 * 1024


class ExtractError(RuntimeError):
    """对外暴露的可读错误。"""


def _clip(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（内容较长，已截取前 6000 字）"
    return text


def _join(lines: list[str]) -> str:
    cleaned = [re.sub(r"[ \t]+", " ", str(x)).strip() for x in lines]
    return _clip("\n".join(x for x in cleaned if x))


def extract_docx(data: bytes) -> str:
    try:
        import docx  # type: ignore
    except ImportError as exc:
        raise ExtractError("服务端缺少 Word 解析依赖") from exc
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError("Word 文件无法解析，可能已损坏或加密") from exc
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return _join(lines)


def extract_xlsx(data: bytes) -> str:
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise ExtractError("服务端缺少 Excel 解析依赖") from exc
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ExtractError("Excel 文件无法解析，可能已损坏或加密") from exc
    lines: list[str] = []
    for sheet in wb.worksheets[:3]:
        lines.append(f"【工作表：{sheet.title}】")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= 120:
                lines.append("…（该表数据较多，仅取前 120 行）")
                break
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                lines.append(" | ".join(cells))
    wb.close()
    return _join(lines)


def extract_pptx(data: bytes) -> str:
    try:
        from pptx import Presentation  # type: ignore
    except ImportError as exc:
        raise ExtractError("服务端缺少 PPT 解析依赖") from exc
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError("PPT 文件无法解析，可能已损坏或加密") from exc
    lines: list[str] = []
    for idx, slide in enumerate(prs.slides, start=1):
        if idx > 40:
            lines.append("…（页数较多，仅取前 40 页）")
            break
        lines.append(f"【第 {idx} 页】")
        for shape in slide.shapes:
            text = getattr(shape, "text", "")
            if text and text.strip():
                lines.append(text)
    return _join(lines)


def extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise ExtractError("服务端缺少 PDF 解析依赖") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ExtractError("这个 PDF 有密码保护，无法读取") from exc
        pages = reader.pages[:20]
        if not pages:
            raise ExtractError("这个 PDF 没有可读取的页面")
        lines = [(p.extract_text() or "") for p in pages]
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError("PDF 文件无法解析，可能已损坏或加密") from exc
    if not any(x.strip() for x in lines):
        raise ExtractError("这个 PDF 是扫描件，文字无法直接读取，请改用截图上传")
    return _join(lines)


def extract_html_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return _clip(text)


def _ssl_context():
    """优先用 certifi 根证书，兼容部分缺少系统证书的环境。"""
    try:
        import ssl

        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _fetch_html(url: str) -> tuple[str, str]:
    """用标准库抓取网页，返回 (正文, content-type)。"""
    import gzip
    import zlib
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urlopen(req, timeout=15, context=_ssl_context()) as resp:
            ctype = (resp.headers.get("content-type") or "").lower()
            encoding = (resp.headers.get("content-encoding") or "").lower()
            raw = resp.read(4 * 1024 * 1024)
    except HTTPError as exc:
        raise ExtractError(f"这个链接返回 {exc.code}，无法读取内容") from exc
    except (URLError, OSError) as exc:
        raise ExtractError("打开这个链接失败，请确认地址可公开访问") from exc

    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass

    charset = ""
    m = re.search(r"charset=([\w-]+)", ctype)
    if m:
        charset = m.group(1)
    if charset:
        return raw.decode(charset, errors="ignore"), ctype
    try:
        return raw.decode("utf-8"), ctype
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="ignore"), ctype


def extract_link(url: str) -> str:
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise ExtractError("请填写以 http:// 或 https:// 开头的完整网址")
    body, ctype = _fetch_html(url)
    if not any(k in ctype for k in ("html", "text", "json")):
        raise ExtractError("这个链接不是网页内容，请下载后作为文件上传")
    if "html" in ctype:
        text = extract_html_text(body)
    else:
        text = _clip(body)
    if len(text) < 40:
        raise ExtractError("这个页面几乎读不到正文，可能由脚本动态渲染，请改用截图上传")
    return text


def extract_image(data: bytes, mime: str) -> str:
    from .llm import LLMError, vision_text

    try:
        text = vision_text(data, mime)
    except LLMError as exc:
        raise ExtractError(str(exc)) from exc
    if not text.strip():
        raise ExtractError("没有从截图里识别出文字，请换一张更清晰的图片")
    return _clip(text)


SUPPORTED = {
    ".docx": extract_docx,
    ".xlsx": extract_xlsx,
    ".pptx": extract_pptx,
    ".pdf": extract_pdf,
}


def extract_file(data: bytes, filename: str) -> str:
    if not data:
        raise ExtractError("文件是空的")
    if len(data) > MAX_BYTES:
        raise ExtractError("文件超过 10MB，请压缩或截取关键部分后再上传")
    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext in SUPPORTED:
        return SUPPORTED[ext](data)
    if ext in (".txt", ".md", ".csv"):
        return _clip(data.decode("utf-8", errors="ignore"))
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
        return extract_image(data, mime)
    raise ExtractError("暂不支持这种文件，请上传 Word、Excel、PPT、PDF、图片或纯文本")
