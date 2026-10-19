"""图纸基础设施：DXF 文档、图层、文字和尺寸样式、图框、标题栏、明细栏、常用符号。

坐标一律为图纸上的 mm（不是零件的实际尺寸）。视图用 ``View`` 把零件尺寸按比例映射到图纸，
尺寸标注通过 DIMLFAC = 1/比例 显示零件的实际尺寸。

图幅（GB/T 14689）、比例（GB/T 14690）、字体（GB/T 14691，仿宋）、图线（GB/T 17450、GB/T 4457.4）
按国标规定的数值取用；标题栏、明细栏的格子划分为本项目自定的简化格式。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import ezdxf
from ezdxf.enums import TextEntityAlignment

# 图幅 B × L（GB/T 14689 基本幅面），以及装订边 a、周边 c
SIZES = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}
BIND_A = 25
MARGIN_C = {"A0": 10, "A1": 10, "A2": 10, "A3": 5, "A4": 5}
# 优先比例（GB/T 14690）：缩小、原值、放大
SCALES = [1 / 10, 1 / 5, 1 / 4, 1 / 3, 1 / 2.5, 1 / 2, 1 / 1.5, 1, 2, 2.5, 4, 5]  # 含第二系列 1:1.5、1:2.5、1:3、1:4

FONT = "simfang.ttf"  # 仿宋，Windows 自带；渲染预览时找不到会换成系统中文字体
TEXT_WIDTH = 0.7

LAYERS = {
    # 名称: (颜色, 线型, 线宽 1/100 mm)
    "粗实线": (7, "CONTINUOUS", 50),
    "细实线": (7, "CONTINUOUS", 25),
    "点画线": (1, "CENTER", 25),
    "虚线": (6, "DASHED", 25),
    "尺寸": (3, "CONTINUOUS", 25),
    "剖面线": (8, "CONTINUOUS", 18),
    "文字": (7, "CONTINUOUS", 25),
    "图框": (7, "CONTINUOUS", 70),
}


def scale_label(s: float) -> str:
    if s >= 1:
        return f"{s:g}:1"
    return f"1:{1 / s:g}"


def pick_scale(model_w: float, model_h: float, avail_w: float, avail_h: float) -> float:
    """在优先比例中取能放下视图的最大比例（单位均为 mm）。"""
    best = SCALES[0]
    for s in SCALES:
        if model_w * s <= avail_w and model_h * s <= avail_h:
            best = s
    return best


@dataclass
class TitleInfo:
    name: str  # 图名
    material: str = ""
    scale: float = 1.0
    quantity: str = "1"
    drawing_no: str = ""
    school: str = "（学校 班级）"
    designer: str = ""


class Sheet:
    def __init__(self, size: str = "A3", landscape: bool = True):
        self.size = size
        b, l = SIZES[size]
        self.w, self.h = (l, b) if landscape else (b, l)
        self.doc = ezdxf.new("R2018", setup=True, units=4)  # 4 = mm
        self.msp = self.doc.modelspace()
        for name, (color, lt, lw) in LAYERS.items():
            self.doc.layers.add(name, color=color, linetype=lt, lineweight=lw)
        self.doc.styles.new("GB", dxfattribs={"font": FONT, "width": TEXT_WIDTH})
        ds = self.doc.dimstyles.new("GB")
        ds.dxf.dimtxsty = "GB"
        ds.dxf.dimtxt = 3.5
        ds.dxf.dimasz = 3.0
        ds.dxf.dimexe = 2.0
        ds.dxf.dimexo = 0.0
        ds.dxf.dimgap = 1.0
        ds.dxf.dimtad = 1
        ds.dxf.dimtih = 0
        ds.dxf.dimtoh = 0
        ds.dxf.dimdec = 1
        ds.dxf.dimzin = 8  # 去掉小数末尾的 0
        ds.dxf.dimclrd = 3
        ds.dxf.dimclre = 3
        ds.dxf.dimclrt = 7
        c = MARGIN_C[size]
        self.inner = (BIND_A, c, self.w - c, self.h - c)  # x0, y0, x1, y1
        self.parts_rows: list[list[str]] = []
        self.parts_first_rows: int | None = None  # 标题栏上方明细栏的最多行数，其余续接在标题栏左方

    # ------------------------------------------------------------ 基本图元

    def line(self, p1, p2, layer="粗实线"):
        self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def poly(self, pts, layer="粗实线", close=False):
        self.msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})

    def rect(self, x0, y0, x1, y1, layer="粗实线"):
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, close=True)

    def circle(self, c, r, layer="粗实线"):
        self.msp.add_circle(c, r, dxfattribs={"layer": layer})

    def arc(self, c, r, a0, a1, layer="粗实线"):
        self.msp.add_arc(c, r, a0, a1, dxfattribs={"layer": layer})

    def text(self, x, y, s, h=3.5, align="LEFT", layer="文字", rotation=0.0):
        al = {
            "LEFT": TextEntityAlignment.BOTTOM_LEFT,
            "CENTER": TextEntityAlignment.BOTTOM_CENTER,
            "MIDDLE": TextEntityAlignment.MIDDLE_CENTER,
            "RIGHT": TextEntityAlignment.BOTTOM_RIGHT,
            "MIDDLE_LEFT": TextEntityAlignment.MIDDLE_LEFT,
        }[align]
        t = self.msp.add_text(s, height=h, rotation=rotation,
                              dxfattribs={"layer": layer, "style": "GB", "width": TEXT_WIDTH})
        t.set_placement((x, y), align=al)
        return t

    def hatch(self, loops: list[list[tuple[float, float]]], angle: float = 45, spacing: float = 3.0):
        h = self.msp.add_hatch(dxfattribs={"layer": "剖面线"})
        h.set_pattern_fill("ANSI31", scale=spacing / 3.175, angle=angle - 45)
        for loop in loops:
            h.paths.add_polyline_path(loop, is_closed=True)

    def centerline(self, p1, p2, ext=3.0):
        (x1, y1), (x2, y2) = p1, p2
        L = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        self.line((x1 - ux * ext, y1 - uy * ext), (x2 + ux * ext, y2 + uy * ext), "点画线")

    def cross(self, c, r, ext=3.0):
        """圆的中心线（十字点画线）。"""
        x, y = c
        self.centerline((x - r, y), (x + r, y), ext)
        self.centerline((x, y - r), (x, y + r), ext)

    # ------------------------------------------------------------ 尺寸

    def dim(self, p1, p2, base, angle=0.0, text="<>", scale=1.0, dec=1, location=None):
        """线性尺寸：angle=0 水平、90 竖直。scale 为视图比例，标注值显示实际尺寸。

        location 给定时把尺寸数字移到该处并画引线（用于狭窄或被遮挡的位置）。
        """
        ov = {"dimlfac": 1 / scale, "dimdec": dec}
        if location is not None:
            ov["dimtmove"] = 1
        d = self.msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, text=text, dimstyle="GB",
                                    location=location, override=ov, dxfattribs={"layer": "尺寸"})
        d.render()

    def dim_value(self, value_mm: float) -> str:
        return f"{value_mm:.2f}".rstrip("0").rstrip(".")

    def leader_text(self, target, at, s, h=3.5):
        """引出标注：带箭头的引线 + 水平线 + 文字。"""
        self.arrow(at, target)
        w = len(s) * h * 0.75 + 2
        self.line(at, (at[0] + w, at[1]), "尺寸")
        self.text(at[0] + 1, at[1] + 0.8, s, h)

    def arrow(self, frm, to, size=3.0, layer="尺寸"):
        self.line(frm, to, layer)
        ang = math.atan2(to[1] - frm[1], to[0] - frm[0])
        a1, a2 = ang + math.radians(165), ang - math.radians(165)
        tri = [to, (to[0] + size * math.cos(a1) * 1.0, to[1] + size * math.sin(a1)),
               (to[0] + size * math.cos(a2), to[1] + size * math.sin(a2))]
        h = self.msp.add_hatch(color=3, dxfattribs={"layer": layer})
        h.paths.add_polyline_path(tri, is_closed=True)

    # ------------------------------------------------------------ 技术符号

    def roughness(self, x, y, ra: str, angle: float = 0.0, h: float = 3.5):
        """表面结构符号（GB/T 131）：去除材料的基本符号，长边上方标 Ra 值。(x, y) 为符号尖端。"""
        h1 = 1.4 * h
        h2 = 2.1 * h1
        t = math.tan(math.radians(30))
        ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))

        def R(px, py):
            return (x + px * ca - py * sa, y + px * sa + py * ca)

        self.line(R(0, 0), R(-h1 * t, h1), "细实线")
        self.line(R(0, 0), R(h2 * t, h2), "细实线")
        self.line(R(-h1 * t, h1), R(h1 * t, h1), "细实线")
        w = len(ra) * h * 0.6 + 4
        self.line(R(h2 * t, h2), R(h2 * t + w, h2), "细实线")
        self.text(*R(h2 * t + 1, h2 - h - 1), ra, h, rotation=angle)

    def roughness_leader(self, target, at, ra: str, h: float = 3.0):
        """带引线的表面结构符号：箭头指向表面，符号站在引线的水平段上。"""
        self.arrow(at, target, 2.5, "细实线")
        self.line(at, (at[0] + 10, at[1]), "细实线")
        self.roughness(at[0] + 5, at[1], ra, 0, h)

    def gtol(self, x, y, kind: str, value: str, datum: str = "", h: float = 3.5):
        """几何公差框格（GB/T 1182），左下角在 (x, y)。kind：runout / symmetry / perpendicular / parallel。"""
        hh = 2 * h
        cells = [hh, len(value) * h * 0.6 + 4] + ([len(datum) * h * 0.6 + 4] if datum else [])
        cx = x
        for w in cells:
            self.rect(cx, y, cx + w, y + hh, "细实线")
            cx += w
        sx, sy, s = x + hh / 2, y + hh / 2, h * 0.9
        if kind == "runout":  # 圆跳动：斜向箭头
            self.arrow((sx - s * 0.5, sy - s * 0.6), (sx + s * 0.5, sy + s * 0.6), 1.6, "细实线")
        elif kind == "symmetry":  # 对称度：三条水平线，中间长
            self.line((sx - s * 0.7, sy), (sx + s * 0.7, sy), "细实线")
            self.line((sx - s * 0.45, sy + s * 0.4), (sx + s * 0.45, sy + s * 0.4), "细实线")
            self.line((sx - s * 0.45, sy - s * 0.4), (sx + s * 0.45, sy - s * 0.4), "细实线")
        elif kind == "perpendicular":
            self.line((sx - s * 0.6, sy - s * 0.5), (sx + s * 0.6, sy - s * 0.5), "细实线")
            self.line((sx, sy - s * 0.5), (sx, sy + s * 0.6), "细实线")
        elif kind == "parallel":
            self.line((sx - s * 0.5, sy - s * 0.5), (sx - s * 0.1, sy + s * 0.5), "细实线")
            self.line((sx + s * 0.1, sy - s * 0.5), (sx + s * 0.5, sy + s * 0.5), "细实线")
        self.text(x + hh + 2, y + h * 0.55, value, h)
        if datum:
            self.text(x + cells[0] + cells[1] + 2, y + h * 0.55, datum, h)
        return cx  # 框格右端 x

    def datum(self, x, y, letter: str, direction: str = "down", h: float = 3.5):
        """基准符号：实心三角形贴在要素上 (x, y)，连线到方框字母。direction 为方框相对三角形的方向。"""
        s = h * 0.9
        dx, dy = {"down": (0, -1), "up": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
        px, py = -dy, dx
        tri = [(x + px * s / 2, y + py * s / 2), (x - px * s / 2, y - py * s / 2), (x + dx * s * 0.8, y + dy * s * 0.8)]
        hch = self.msp.add_hatch(color=7, dxfattribs={"layer": "细实线"})
        hch.paths.add_polyline_path(tri, is_closed=True)
        L = 2 * h
        bx, by = x + dx * (s * 0.8 + L), y + dy * (s * 0.8 + L)
        self.line((x + dx * s * 0.8, y + dy * s * 0.8), (bx, by), "细实线")
        box = 2 * h
        cx, cy = bx + dx * box / 2, by + dy * box / 2
        self.rect(cx - box / 2, cy - box / 2, cx + box / 2, cy + box / 2, "细实线")
        self.text(cx, cy, letter, h, "MIDDLE")

    def balloon(self, target, at, n: int, h: float = 5.0):
        """零件序号：细实线引线，起点画小圆点，末端水平线上写序号。"""
        self.msp.add_circle(target, 0.6, dxfattribs={"layer": "细实线"})
        self.line(target, at, "细实线")
        sgn = 1 if at[0] >= target[0] else -1
        self.line(at, (at[0] + sgn * 8, at[1]), "细实线")
        self.text(at[0] + sgn * 4, at[1] + 0.8, str(n), h, "CENTER")

    def section_label(self, x, y, letter: str, h: float = 5.0):
        self.text(x, y, f"{letter}-{letter}", h, "CENTER")

    def cut_marks(self, x, y_top, y_bot, letter: str, h: float = 5.0):
        """剖切符号：两端粗短画 + 字母。"""
        for yy, sgn in ((y_top, 1), (y_bot, -1)):
            self.line((x, yy), (x, yy + sgn * 5), "图框")
            self.text(x + 2, yy + (sgn * 2 if sgn > 0 else -6), letter, h)

    # ------------------------------------------------------------ 图框、标题栏、明细栏

    def frame(self, info: TitleInfo, tech_reqs: list[str] | None = None, rest_ra: str | None = None):
        self.rect(0, 0, self.w, self.h, "细实线")
        x0, y0, x1, y1 = self.inner
        self.rect(x0, y0, x1, y1, "图框")
        self._title_block(info)
        if self.parts_rows:
            self._parts_list()
        if tech_reqs:
            self.tech_requirements(tech_reqs)
        if rest_ra:
            # 其余表面的表面结构要求，放在标题栏上方
            tx = x1 - 60
            ty = y0 + 56 + 8 + (7 * (len(self.parts_rows) + 1) if self.parts_rows else 0)
            self.text(tx, ty + 2, "其余", 5)
            self.roughness(tx + 18, ty, rest_ra, h=3.5)

    def _title_block(self, info: TitleInfo):
        x1, y0 = self.inner[2], self.inner[1]
        X, Y = x1 - 180, y0
        self.rect(X, Y, x1, Y + 56, "图框")
        # 左半：签字区 4 行 × 14
        for k in range(1, 4):
            self.line((X, Y + 14 * k), (X + 100, Y + 14 * k), "细实线")
        for xx in (X + 20, X + 60, X + 100):
            self.line((xx, Y), (xx, Y + 56), "细实线" if xx != X + 100 else "图框")
        for k, lab in enumerate(["日期", "审核", "校核", "设计"]):
            self.text(X + 10, Y + 14 * k + 7, lab, 3.5, "MIDDLE")
        self.text(X + 40, Y + 14 * 3 + 7, info.designer, 3.5, "MIDDLE")
        # 右半：图名、材料/比例/数量、图号/学校
        R = X + 100
        self.line((R, Y + 36), (x1, Y + 36), "细实线")
        self.line((R, Y + 20), (x1, Y + 20), "细实线")
        self.line((R, Y + 28), (x1, Y + 28), "细实线")
        self.text(R + 40, Y + 46, info.name, 7, "MIDDLE")
        for i, (lab, val) in enumerate([("材料", info.material), ("比例", scale_label(info.scale)), ("数量", info.quantity)]):
            cx = R + i * 80 / 3
            self.line((cx, Y + 20), (cx, Y + 36), "细实线")
            self.text(cx + 80 / 6, Y + 32, lab, 3.5, "MIDDLE")
            self.text(cx + 80 / 6, Y + 24, val, 3.5, "MIDDLE")
        self.text(R + 40, Y + 14, info.drawing_no, 5, "MIDDLE")
        self.line((R, Y + 8), (x1, Y + 8), "细实线")
        self.text(R + 40, Y + 4, info.school, 3.5, "MIDDLE")

    def add_part(self, no: int, name: str, qty: int | str, material: str, note: str = ""):
        self.parts_rows.append([str(no), name, str(qty), material, note])

    def _parts_list(self):
        """明细栏：画在标题栏上方，序号自下而上；行数超过 parts_first_rows 时续接在标题栏左方（GB/T 10609.2）。"""
        x1, y0 = self.inner[2], self.inner[1]
        n1 = self.parts_first_rows if self.parts_first_rows is not None else len(self.parts_rows)
        blocks = [(x1 - 180, y0 + 56, self.parts_rows[:n1])]
        if len(self.parts_rows) > n1:
            blocks.append((x1 - 360, y0, self.parts_rows[n1:]))
        cols = [10, 45, 12, 30, 83]
        for X, Y, body in blocks:
            rows = [["序号", "名称", "数量", "材料", "标准 / 备注"]] + body
            for i, row in enumerate(rows):
                yy = Y + 7 * i
                self.rect(X, yy, X + 180, yy + 7, "细实线")
                cx = X
                for w, v in zip(cols, row):
                    self.line((cx, yy), (cx, yy + 7), "细实线")
                    self.text(cx + w / 2, yy + 3.5, v, 3.5 if len(v) * 2.6 < w else 2.5, "MIDDLE")
                    cx += w

    def table(self, x, y_top, rows: list[list[str]], widths: list[float], row_h: float = 7.0, h: float = 3.5):
        """通用表格（如齿轮参数表、技术特性表），左上角 (x, y_top)。"""
        for i, row in enumerate(rows):
            yy = y_top - row_h * (i + 1)
            cx = x
            for w, v in zip(widths, row):
                self.rect(cx, yy, cx + w, yy + row_h, "细实线")
                self.text(cx + w / 2, yy + row_h / 2, v, h if len(v) * h * 0.72 < w else h * 0.75, "MIDDLE")
                cx += w
        self.rect(x, y_top - row_h * len(rows), x + sum(widths), y_top, "粗实线")

    def tech_requirements(self, lines: list[str], x: float | None = None, y: float | None = None):
        x = x if x is not None else self.inner[2] - 180 - 150
        y = y if y is not None else self.inner[1] + 10 + 7 * len(lines)
        self.text(x, y + 9, "技术要求", 5)
        for i, s in enumerate(lines):
            self.text(x + 4, y - i * 7, f"{i + 1}. {s}", 3.5)

    # ------------------------------------------------------------ 输出

    def save(self, path):
        self.doc.saveas(str(path))


class View:
    """把零件坐标（mm）按比例放到图纸上：P(x, y) = origin + s·(x, y)。

    rotate=True 时视图顺时针转 90°：P(x, y) = origin + s·(y, −x)。
    """

    def __init__(self, sheet: Sheet, origin: tuple[float, float], scale: float, rotate: bool = False):
        self.sh = sheet
        self.ox, self.oy = origin
        self.s = scale
        self.rot = rotate

    def P(self, x, y):
        if self.rot:
            x, y = y, -x
        return (self.ox + x * self.s, self.oy + y * self.s)

    def line(self, a, b, layer="粗实线"):
        self.sh.line(self.P(*a), self.P(*b), layer)

    def poly(self, pts, layer="粗实线", close=False):
        self.sh.poly([self.P(*p) for p in pts], layer, close)

    def rect(self, x0, y0, x1, y1, layer="粗实线"):
        self.sh.rect(*self.P(x0, y0), *self.P(x1, y1), layer)

    def circle(self, c, r, layer="粗实线"):
        self.sh.circle(self.P(*c), r * self.s, layer)

    def arc(self, c, r, a0, a1, layer="粗实线"):
        assert not self.rot
        self.sh.arc(self.P(*c), r * self.s, a0, a1, layer)

    def hatch(self, loops, angle=45, spacing=3.0):
        self.sh.hatch([[self.P(*p) for p in loop] for loop in loops], angle, spacing)

    def centerline(self, a, b, ext=3.0):
        self.sh.centerline(self.P(*a), self.P(*b), ext)

    def dim(self, a, b, base, angle=0.0, text="<>", dec=1):
        if self.rot:
            angle = 90.0 - angle
        self.sh.dim(self.P(*a), self.P(*b), self.P(*base), angle, text, self.s, dec)
