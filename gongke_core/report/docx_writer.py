"""把说明书渲染成 Word 文件（需要 python-docx）。"""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from gongke_core.report import Doc


def _font(run, size=None, bold=None, name="宋体"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold


def write(doc: Doc, path: str | Path) -> None:
    d = Document()
    sec = d.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.5)
    style = d.styles["Normal"]
    style.font.name = "宋体"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    style.font.size = Pt(12)

    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(p.add_run(doc.title), 18, True, "黑体")

    for b in doc.blocks:
        if b.kind in ("h1", "h2"):
            p = d.add_paragraph()
            p.paragraph_format.space_before = Pt(12 if b.kind == "h1" else 6)
            _font(p.add_run(b.text), 15 if b.kind == "h1" else 13, True, "黑体")
        elif b.kind == "p":
            p = d.add_paragraph()
            p.paragraph_format.first_line_indent = Pt(24)
            _font(p.add_run(b.text))
        elif b.kind == "eq":
            p = d.add_paragraph()
            p.paragraph_format.left_indent = Cm(1)
            _font(p.add_run(b.text), name="宋体")
        elif b.kind == "note":
            p = d.add_paragraph()
            _font(p.add_run("注：" + b.text), 10.5)
        elif b.kind == "table":
            t = d.add_table(rows=1, cols=len(b.headers))
            t.style = "Table Grid"
            for c, h in zip(t.rows[0].cells, b.headers):
                c.text = ""
                _font(c.paragraphs[0].add_run(h), 10.5, True)
            for row in b.rows:
                cells = t.add_row().cells
                for c, v in zip(cells, row):
                    c.text = ""
                    _font(c.paragraphs[0].add_run(v), 10.5)
        elif b.kind == "img":
            d.add_picture(io.BytesIO(b.image), width=Cm(15.5))
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _font(p.add_run(b.text), 10.5)
    d.save(str(path))
