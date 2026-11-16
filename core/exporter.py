"""导出：Markdown / 纯文本 / Word。"""

from __future__ import annotations

import io
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\d+[.、)]\s+.*$")


def md_to_plain(text: str) -> str:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = _HEADING.match(line)
        if m:
            out.append("")
            out.append(m.group(2).strip())
            out.append("")
            continue
        if line.strip() in ("---", "***", "___"):
            out.append("")
            continue
        line = _BOLD.sub(r"\1", line)
        line = line.replace("**", "").replace("`", "")
        line = _BULLET.sub(r"· \1", line)
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            line = " | ".join(cells)
        out.append(line)
    plain = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", plain).strip() + "\n"


def ensure_title(text: str, title: str) -> str:
    body = text.strip()
    if body.startswith("# "):
        return body + "\n"
    return f"# {title}\n\n{body}\n"


def _set_east_asia(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
    if rfonts is None:
        from docx.oxml import OxmlElement

        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", font_name)


def _add_inline(paragraph, text: str) -> None:
    text = text.replace("`", "")
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos : m.start()])
        run = paragraph.add_run(m.group(1))
        run.bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def _add_table(doc, rows: list[str]) -> None:
    parsed: list[list[str]] = []
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        parsed.append(cells)
    if not parsed:
        return
    cols = max(len(r) for r in parsed)
    table = doc.add_table(rows=0, cols=cols)
    try:
        table.style = "Light Grid Accent 1"
    except KeyError:
        table.style = "Table Grid"
    for idx, row in enumerate(parsed):
        cells = table.add_row().cells
        for j in range(cols):
            value = row[j] if j < len(row) else ""
            paragraph = cells[j].paragraphs[0]
            _add_inline(paragraph, value)
            for run in paragraph.runs:
                run.font.size = doc.styles["Normal"].font.size
                if idx == 0:
                    run.bold = True


def md_to_docx(text: str, title: str = "") -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.left_margin = Cm(2.6)
    section.right_margin = Cm(2.6)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体"
    )
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(2)

    lines = text.splitlines()
    i = 0
    first_heading_done = False

    while i < len(lines):
        raw = lines[i].rstrip()
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            _add_table(doc, block)
            doc.add_paragraph()
            continue

        heading = _HEADING.match(stripped)
        if heading and len(heading.group(1)) == 1:
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(heading.group(2).strip())
            run.bold = True
            run.font.size = Pt(17)
            _set_east_asia(run, "微软雅黑")
            run.font.color.rgb = RGBColor(0x1F, 0x24, 0x30)
            paragraph.paragraph_format.space_after = Pt(10)
            first_heading_done = True
            i += 1
            continue
        if heading:
            level = len(heading.group(1))
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(heading.group(2).strip())
            run.bold = True
            run.font.size = Pt(15 if level == 2 else 13)
            _set_east_asia(run, "微软雅黑")
            run.font.color.rgb = RGBColor(0x33, 0x39, 0x4A)
            paragraph.paragraph_format.space_before = Pt(12 if level == 2 else 10)
            paragraph.paragraph_format.space_after = Pt(4)
            i += 1
            continue

        bullet = _BULLET.match(stripped)
        if bullet:
            paragraph = doc.add_paragraph(style="List Bullet")
            _add_inline(paragraph, bullet.group(1))
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.space_after = Pt(3)
            i += 1
            continue

        if _NUMBERED.match(stripped):
            paragraph = doc.add_paragraph()
            _add_inline(paragraph, stripped)
            paragraph.paragraph_format.left_indent = Cm(0.6)
            i += 1
            continue

        paragraph = doc.add_paragraph()
        _add_inline(paragraph, stripped)
        i += 1

    if not first_heading_done and title:
        paragraph = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
        run = paragraph.add_run(title)
        run.bold = True
        run.font.size = Pt(17)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
