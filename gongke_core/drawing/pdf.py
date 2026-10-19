"""DXF → PDF（矢量，可直接打印）。

借用 ezdxf drawing 插件的前端（与 SVG 预览相同的渲染设置，文字转成轮廓曲线），自己写一个很小的 PDF 后端，
不依赖其他库（常见的 PDF 库 PyMuPDF 是 AGPL 许可，不适合本项目）。每张图一页，页面尺寸等于图幅。
"""

from __future__ import annotations

import copy
import zlib
from pathlib import Path
from typing import Iterable

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, recorder
from ezdxf.addons.drawing.backend import BackendInterface, BkPath2d, BkPoints2d, ImageData
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
from ezdxf.addons.drawing.properties import BackendProperties
from ezdxf.math import Vec2
from ezdxf.path import Command

from gongke_core.drawing.render import _cjk_font

PT_PER_MM = 72 / 25.4
COORD_SPACE = 100_000  # 输出坐标空间（长边），再用 cm 矩阵缩放到 pt


def _rgb(color: str) -> str:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return f"{r:.3f} {g:.3f} {b:.3f}"


class _PdfRender(BackendInterface):
    def __init__(self, page: layout.Page):
        self.vb_w, self.vb_h = ((COORD_SPACE, round(COORD_SPACE * page.height / page.width)) if page.width >= page.height
                                else (round(COORD_SPACE * page.width / page.height), COORD_SPACE))
        self.mm_to_vb = self.vb_w / page.width_in_mm
        self.ops: list[str] = []
        self.min_lw = 0.05
        self.lw_scale = 1.0
        self._state = (None, None, None)  # (线宽, 描边色, 填充色)

    # ---- 图形状态
    def _stroke_state(self, p: BackendProperties):
        w = max(self.min_lw, p.lineweight) * self.lw_scale if self.lw_scale else self.min_lw
        w *= self.mm_to_vb
        col = _rgb(p.color)
        lw, sc, fc = self._state
        if lw != w:
            self.ops.append(f"{w:.1f} w")
        if sc != col:
            self.ops.append(f"{col} RG")
        self._state = (w, col, fc)

    def _fill_state(self, p: BackendProperties):
        col = _rgb(p.color)
        lw, sc, fc = self._state
        if fc != col:
            self.ops.append(f"{col} rg")
        self._state = (lw, sc, col)

    # ---- 路径
    def _poly(self, pts, close=False):
        pts = list(pts)
        if len(pts) < 2:
            return
        self.ops.append(f"{pts[0].x:.1f} {pts[0].y:.1f} m")
        self.ops += [f"{q.x:.1f} {q.y:.1f} l" for q in pts[1:]]
        if close:
            self.ops.append("h")

    def _path(self, path: BkPath2d, close=False):
        cur = path.start
        self.ops.append(f"{cur.x:.1f} {cur.y:.1f} m")
        for cmd in path.commands():
            e = cmd.end
            if cmd.type == Command.MOVE_TO:
                self.ops.append(f"{e.x:.1f} {e.y:.1f} m")
            elif cmd.type == Command.LINE_TO:
                self.ops.append(f"{e.x:.1f} {e.y:.1f} l")
            elif cmd.type == Command.CURVE3_TO:  # 二次 → 三次贝塞尔
                c1 = cur + (cmd.ctrl - cur) * (2 / 3)
                c2 = e + (cmd.ctrl - e) * (2 / 3)
                self.ops.append(f"{c1.x:.1f} {c1.y:.1f} {c2.x:.1f} {c2.y:.1f} {e.x:.1f} {e.y:.1f} c")
            elif cmd.type == Command.CURVE4_TO:
                a, b = cmd.ctrl1, cmd.ctrl2
                self.ops.append(f"{a.x:.1f} {a.y:.1f} {b.x:.1f} {b.y:.1f} {e.x:.1f} {e.y:.1f} c")
            cur = e
        if close:
            self.ops.append("h")

    # ---- BackendInterface
    def configure(self, config: Configuration) -> None:
        if config.min_lineweight:
            self.min_lw = max(0.05, config.min_lineweight * 25.4 / 300)
        self.lw_scale = config.lineweight_scaling

    def set_background(self, color) -> None:
        self.ops[:0] = [f"{_rgb(color)} rg", f"0 0 {self.vb_w} {self.vb_h} re f"]
        self._state = (None, None, _rgb(color))

    def draw_point(self, pos: Vec2, properties: BackendProperties) -> None:
        self.draw_line(pos, pos, properties)

    def draw_line(self, start: Vec2, end: Vec2, properties: BackendProperties) -> None:
        self._stroke_state(properties)
        self._poly([start, end])
        self.ops.append("S")

    def draw_solid_lines(self, lines: Iterable[tuple[Vec2, Vec2]], properties: BackendProperties) -> None:
        lines = list(lines)
        if not lines:
            return
        self._stroke_state(properties)
        for a, b in lines:
            self._poly([a, b])
        self.ops.append("S")

    def draw_path(self, path: BkPath2d, properties: BackendProperties) -> None:
        if len(path) == 0:
            return
        self._stroke_state(properties)
        self._path(path)
        self.ops.append("S")

    def draw_filled_paths(self, paths: Iterable[BkPath2d], properties: BackendProperties) -> None:
        paths = [p for p in paths if len(p)]
        if not paths:
            return
        self._fill_state(properties)
        for p in paths:
            self._path(p, close=True)
        self.ops.append("f*")

    def draw_filled_polygon(self, points: BkPoints2d, properties: BackendProperties) -> None:
        v = points.vertices()
        if len(v) < 3:
            return
        self._fill_state(properties)
        self._poly(v, close=True)
        self.ops.append("f*")

    def draw_image(self, image_data: ImageData, properties: BackendProperties) -> None:
        pass

    def clear(self) -> None:
        pass

    def finalize(self) -> None:
        pass

    def enter_entity(self, entity, properties) -> None:
        pass

    def exit_entity(self, entity) -> None:
        pass


class _Recorder(recorder.Recorder):
    def page_content(self, page: layout.Page) -> tuple[float, float, bytes]:
        """返回 (页宽 pt, 页高 pt, 内容流)。"""
        settings = layout.Settings(output_coordinate_space=COORD_SPACE)
        player = self.player()
        out = layout.Layout(player.bbox(), flip_y=False)
        page = out.get_final_page(page, settings)
        player.transform(out.get_placement_matrix(page, settings=copy.copy(settings), top_origin=False))
        be = _PdfRender(page)
        player.replay(be)
        w_pt, h_pt = page.width_in_mm * PT_PER_MM, page.height_in_mm * PT_PER_MM
        s = w_pt / be.vb_w
        body = f"q {s:.8f} 0 0 {s:.8f} 0 0 cm 1 J 1 j\n" + "\n".join(be.ops) + "\nQ\n"
        return w_pt, h_pt, body.encode("ascii")


def _render(dxf_path: Path, width_mm: float | None, height_mm: float | None):
    doc = ezdxf.readfile(str(dxf_path))
    font = _cjk_font()
    if font:
        for st in doc.styles:
            if st.dxf.name.upper() == "GB":
                st.dxf.font = font
    msp = doc.modelspace()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_policy=LineweightPolicy.ABSOLUTE)
    rec = _Recorder()
    Frontend(RenderContext(doc), rec, config=cfg).draw_layout(msp)
    if width_mm is None:
        ext = ezdxf.bbox.extents(msp)
        width_mm, height_mm = ext.size.x, ext.size.y
    return rec.page_content(layout.Page(width_mm, height_mm, layout.Units.mm, margins=layout.Margins.all(0)))


def write_pdf(pages: list[tuple[float, float, bytes]], pdf_path: Path, title: str = "") -> None:
    """把若干页（页宽 pt、页高 pt、内容流）写成一个 PDF 文件。"""
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    catalog = add(b"")  # 占位
    pages_id = add(b"")
    kids = []
    for w, h, content in pages:
        data = zlib.compress(content, 6)
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] "
                        f"/Contents {cid} 0 R /Resources << >> >>".encode()))
    objs[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    objs[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>").encode()
    info = add(b"<< /Producer (GongKe Workbench) /Title <FEFF" + title.encode("utf-16-be").hex().upper().encode() + b"> >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, b in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + b + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(pdf_path).write_bytes(bytes(out))


def to_pdf(dxf_paths: list[tuple[Path, float | None, float | None]], pdf_path: Path, title: str = "") -> None:
    """dxf_paths 为 (DXF 文件, 图幅宽 mm, 图幅高 mm)，按顺序每张一页。"""
    write_pdf([_render(Path(p), w, h) for p, w, h in dxf_paths], pdf_path, title)
