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
from ezdxf.render import dim_base as _dim_base


def _gb_tolerance_text(self, tol_upper: float, tol_lower: float):
    """极限偏差按 GB/T 4458.5 书写：偏差为零时只写“0”，不带正负号和小数。"""
    def fmt(v: float) -> str:
        if abs(v) < 5e-7:
            return "0"
        return _dim_base.sign_char(v) + self.format_text(abs(v))

    if tol_upper == tol_lower:
        self.text = _dim_base.PLUS_MINUS + self.format_text(abs(tol_upper))
    else:
        self.text_upper, self.text_lower = fmt(tol_upper), fmt(-tol_lower)


_dim_base.Tolerance.update_tolerance_text = _gb_tolerance_text


def _wrap_text(s: str, w_max: float, h: float, indent: str = "") -> list[str]:
    """把长句按文字外框宽度折行。中文可逐字断开；续行前加 indent。放不下哪怕一个字时也至少成一行。"""
    from gongke_core.drawing.lint import text_width

    if text_width(s, h) <= w_max:
        return [s]
    out, cur = [], ""
    for ch in s:
        if cur and text_width(cur + ch, h) > w_max:
            out.append(cur)
            cur = indent + ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out

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
    "虚线": (6, "GB_DASHED", 25),
    "尺寸": (3, "CONTINUOUS", 25),
    "剖面线": (8, "CONTINUOUS", 18),
    "文字": (7, "CONTINUOUS", 25),
    "图框": (7, "CONTINUOUS", 70),
}


def fit_height(s: str, h: float, max_w: float, h_min: float = 2.5) -> float:
    """表格格子里的文字：放不下时减小字高（不小于 h_min，GB/T 14691 最小字号 2.5）。"""
    from gongke_core.drawing.lint import text_width

    w = text_width(s, h)
    return h if w <= max_w else max(h * max_w / w, h_min)


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
        self.doc = ezdxf.new("R2007", setup=True, units=4)  # 4 = mm
        self.msp = self.doc.modelspace()
        # 虚线（GB/T 4457.4）：画长约 4 mm，间隔约 1.5 mm
        self.doc.linetypes.add("GB_DASHED", pattern=[5.5, 4.0, -1.5], description="GB 虚线 ____ ____ ____")
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
        ds.dxf.dimdsep = ord(".")  # 小数点（ezdxf 默认用逗号）
        ds.dxf.dimclrd = 3
        ds.dxf.dimclre = 3
        ds.dxf.dimclrt = 7
        c = MARGIN_C[size]
        self.inner = (BIND_A, c, self.w - c, self.h - c)  # x0, y0, x1, y1
        self.parts_rows: list[list[str]] = []
        self._leaders: list = []  # 待出图时定位的引出标注
        self._dims: list = []  # 待出图时选位置的尺寸
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

    def dim(self, p1, p2, base, angle=0.0, text="<>", scale=1.0, dec=1, location=None, tol=None):
        """线性尺寸：angle=0 水平、90 竖直。scale 为视图比例，标注值显示实际尺寸。

        location 给定时把尺寸数字移到该处并画引线（用于狭窄或被遮挡的位置）。
        tol = (上极限偏差, 下极限偏差)（m）时在尺寸数字后注极限偏差（GB/T 4458.5，偏差字高小一号）。
        """
        ov = {"dimlfac": 1 / scale, "dimdec": dec}
        if location is not None:
            ov["dimtmove"] = 1
        if tol is not None:
            up, lo = (round(v * 1e3, 3) for v in tol)
            ov.update({"dimtol": 1, "dimtp": up, "dimtm": -lo, "dimtfac": 0.7, "dimtdec": 3, "dimtzin": 0})
        d = self.msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, text=text, dimstyle="GB",
                                    location=location, override=ov, dxfattribs={"layer": "尺寸"})
        d.render()
        return d.dimension

    def dim_auto(self, p1, p2, bases, angle=0.0, text="<>", scale=1.0, dec=1, tol=None):
        """有几个候选尺寸线位置的线性尺寸：出图时选尺寸数字不压线、不压字的那个（按 bases 的先后优先）。"""
        self._dims.append((p1, p2, list(bases), angle, text, scale, dec, tol))

    def dim_best(self, p1, p2, bases, angle=0.0, text="<>", scale=1.0, dec=1, tol=None):
        """同 dim_auto，但立即画出并把采用的尺寸线位置（图纸坐标）返回给调用者。

        用于需要与尺寸线对齐的几何公差框格：框格的指引线必须落在尺寸线上，因此要先知道尺寸线最终在哪。
        候选按 bases 的先后优先（每往后一个加 0.5 的代价），所以够用时不外移。"""
        from gongke_core.drawing import lint

        g = lint.obstacle_grid(self.msp)
        best = None
        for k, base in enumerate(bases):
            d = self.dim(p1, p2, base, angle, text, scale, dec, tol=tol)
            boxes = [b for ve in d.get_geometry_block() if (b := lint._text_box(ve, -1))]
            c = sum(lint._place_cost(g, lambda t, a, lf, b=b: (b, []), None, None, False, self.inner)
                    for b in boxes) + 0.5 * k
            if best is None or c < best[0]:
                if best is not None:
                    self._drop_dim(best[1])
                best = (c, d, base)
            else:
                self._drop_dim(d)
        for ve in best[1].get_geometry_block():
            b = lint._text_box(ve, -1)
            if b:
                g.add(("text", b), lint._bbox_pts(b.corners()))
        return best[2]

    def _place_dims(self):
        from gongke_core.drawing import lint

        g = lint.obstacle_grid(self.msp)
        for p1, p2, bases, angle, text, scale, dec, tol in self._dims:
            best = None
            for k, base in enumerate(bases):
                d = self.dim(p1, p2, base, angle, text, scale, dec, tol=tol)
                boxes = [b for ve in d.get_geometry_block() if (b := lint._text_box(ve, -1))]
                c = sum(lint._place_cost(g, lambda t, a, lf, b=b: (b, []), None, None, False, self.inner) for b in boxes) + 0.5 * k
                if best is None or c < best[0]:
                    if best is not None:
                        self._drop_dim(best[1])
                    best = (c, d)
                else:
                    self._drop_dim(d)
                if c == 0 and k == 0:
                    break
            for ve in best[1].get_geometry_block():
                b = lint._text_box(ve, -1)
                if b:
                    g.add(("text", b), lint._bbox_pts(b.corners()))
        self._dims = []

    def _drop_dim(self, d):
        name = d.dxf.geometry
        self.msp.delete_entity(d)
        self.doc.blocks.delete_block(name, safe=False)

    def dim_value(self, value_mm: float) -> str:
        return f"{value_mm:.2f}".rstrip("0").rstrip(".")

    def label(self, near, at, s: str, h: float = 3.5):
        """不带引线的标注文字（如剖切符号旁的字母），at 为原定的左下角；出图时若压线则绕 near 另找位置。"""
        self._leaders.append(("label", near, at, False, (s, h)))

    def leader_text(self, target, at, s, h=3.5, left=False, fixed=False):
        """引出标注：带箭头的引线 + 水平线 + 文字。left=True 时水平线和文字在 at 的左边。

        默认在出图（save）时再画：若原定位置的文字压线或压字，在附近另找空位（`lint.place_leader`）。
        fixed=True 时立即按原位置画。"""
        if not fixed:
            self._leaders.append(("text", target, at, left, (s, h)))
            return
        from gongke_core.drawing.lint import text_width

        self.arrow(at, target)
        w = text_width(s, h) + 2
        x0 = at[0] - w if left else at[0]
        self.line((x0, at[1]), (x0 + w, at[1]), "尺寸")
        self.text(x0 + 1, at[1] + 0.8, s, h)

    def arrow(self, frm, to, size=3.0, layer="尺寸"):
        self.line(frm, to, layer)
        ang = math.atan2(to[1] - frm[1], to[0] - frm[0])
        a1, a2 = ang + math.radians(165), ang - math.radians(165)
        tri = [to, (to[0] + size * math.cos(a1) * 1.0, to[1] + size * math.sin(a1)),
               (to[0] + size * math.cos(a2), to[1] + size * math.sin(a2))]
        h = self.msp.add_hatch(color=3, dxfattribs={"layer": layer})
        h.paths.add_polyline_path(tri, is_closed=True)

    # ------------------------------------------------------------ 技术符号

    def roughness(self, x, y, ra: str, angle: float = 0.0, h: float = 3.5, keep: bool = False):
        """表面结构符号（GB/T 131）：去除材料的基本符号，长边上方标 Ra 值。(x, y) 为符号尖端。

        keep=True 时画不去除材料的符号（三角形内切圆，用于铸造毛坯面）。"""
        h1 = 1.4 * h
        h2 = 2.1 * h1
        t = math.tan(math.radians(30))
        ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))

        def R(px, py):
            return (x + px * ca - py * sa, y + px * sa + py * ca)

        self.line(R(0, 0), R(-h1 * t, h1), "细实线")
        self.line(R(0, 0), R(h2 * t, h2), "细实线")
        if keep:
            r = h1 / 3  # 符号短边与水平线构成的等边三角形（高 h1）的内切圆
            c = R(0, 2 * r)
            self.msp.add_circle(c, r, dxfattribs={"layer": "细实线"})
        else:
            self.line(R(-h1 * t, h1), R(h1 * t, h1), "细实线")
        if not ra:
            return
        w = len(ra) * h * 0.6 + 4
        self.line(R(h2 * t, h2), R(h2 * t + w, h2), "细实线")
        self.text(*R(h2 * t + 1, h2 - h - 1), ra, h, rotation=angle)

    def roughness_leader(self, target, at, ra: str, h: float = 3.0, fixed: bool = False):
        """带引线的表面结构符号：箭头指向表面，符号站在引线的水平段上。出图时自动避让（同 leader_text）。"""
        if not fixed:
            self._leaders.append(("ra", target, at, False, (ra, h)))
            return
        self.arrow(at, target, 2.5, "细实线")
        self.line(at, (at[0] + 10, at[1]), "细实线")
        self.roughness(at[0] + 5, at[1], ra, 0, h)

    @staticmethod
    def _gtol_size(value: str, datum: str = "", h: float = 3.5) -> tuple[float, float]:
        hh = 2 * h
        return hh + len(value) * h * 0.6 + 4 + (len(datum) * h * 0.6 + 4 if datum else 0), hh

    def gtol_leader(self, target, at, kind: str, value: str, datum: str = "", h: float = 3.5):
        """带指引箭头的几何公差框格：箭头从框格左下角（框格在目标左边时为右下角）指向目标。
        at 为原定的框格左下角，出图时若压线、压字则在附近另找位置。"""
        self._leaders.append(("gtol", target, at, False, (kind, value, datum, h)))

    def gtol_aligned(self, options, kind: str, value: str, datum: str = "", h: float = 3.5, arrow: float = 2.0):
        """指引线须与尺寸线对齐的几何公差框格（如键槽对称度）：options 为若干 (箭头尖, 框格侧边中点, 框格在左)，
        出图时选不压线的一个，并可沿指引线方向外移。"""
        t, a, lf = options[0]
        self._leaders.append(("gtol", t, a, lf, (kind, value, datum, h), {"options": options, "mid": True, "arrow": arrow}))

    def gtol(self, x, y, kind: str, value: str, datum: str = "", h: float = 3.5):
        """几何公差框格（GB/T 1182），左下角在 (x, y)。kind：runout / symmetry / perpendicular / parallel / cylindricity / flatness。"""
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
        elif kind == "cylindricity":  # 圆柱度：圆 + 两条斜切线
            self.msp.add_circle((sx, sy), s * 0.38, dxfattribs={"layer": "细实线"})
            self.line((sx - s * 0.65, sy - s * 0.5), (sx - s * 0.05, sy + s * 0.5), "细实线")
            self.line((sx + s * 0.05, sy - s * 0.5), (sx + s * 0.65, sy + s * 0.5), "细实线")
        elif kind == "flatness":  # 平面度：平行四边形
            self.poly([(sx - s * 0.6, sy - s * 0.3), (sx + s * 0.3, sy - s * 0.3), (sx + s * 0.6, sy + s * 0.3),
                       (sx - s * 0.3, sy + s * 0.3)], "细实线", close=True)
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
            if rest_ra == "毛坯":  # 铸件其余表面不加工
                self.roughness(tx + 18, ty, "", h=3.5, keep=True)
            else:
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
            self.text(cx + 80 / 6, Y + 24, val, fit_height(val, 3.5, 80 / 3 - 2), "MIDDLE")
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
                self.text(cx + w / 2, yy + row_h / 2, v, fit_height(v, h, w - 1.5), "MIDDLE")
                cx += w
        self.rect(x, y_top - row_h * len(rows), x + sum(widths), y_top, "粗实线")

    def tech_requirements(self, lines: list[str], x: float | None = None, y: float | None = None):
        """技术要求：编号逐条列出；比图框宽度还长的条目自动折行（折行后不再重编号）。"""
        x = x if x is not None else self.inner[2] - 180 - 150
        from gongke_core.drawing.lint import text_width

        rows: list[str] = []
        w_max = self.inner[2] - (x + 4) - 3  # 右侧留 3 mm，不压图框
        for i, s in enumerate(lines, 1):
            rows += _wrap_text(f"{i}. {s}", w_max, 3.5, indent="   ")
        y = y if y is not None else self.inner[1] + 10 + 7 * len(rows)
        self.text(x, y + 9, "技术要求", 5)
        for i, s in enumerate(rows):
            self.text(x + 4, y - i * 7, s, 3.5)

    # ------------------------------------------------------------ 输出

    def save(self, path):
        from gongke_core.drawing import lint

        if self._dims:
            self._place_dims()
        if self._leaders:
            g = lint.obstacle_grid(self.msp)
            for kind, target, at, left, args, *opt in self._leaders:
                opt = opt[0] if opt else {}
                if kind == "label":
                    shape = lint.label_shape(args[0], args[1])
                elif kind == "text":
                    shape = lint.leader_shape(args[0], args[1])
                elif kind == "gtol":
                    shape = lint.frame_shape(*self._gtol_size(args[1], args[2], args[3]), mid=opt.get("mid", False))
                else:
                    shape = lint.roughness_shape(args[0], args[1])
                if opt.get("options"):
                    target, at, left = lint.place_sliding(g, shape, opt["options"], self.inner)
                else:
                    at, left = lint.place(g, shape, target, at, left, self.inner, flip=kind != "ra")
                lint.add_obstacles(g, shape, target, at, left)
                if kind == "label":
                    self.text(at[0], at[1], args[0], args[1])
                elif kind == "text":
                    self.leader_text(target, at, args[0], args[1], left, fixed=True)
                elif kind == "gtol":
                    w, hh = self._gtol_size(args[1], args[2], args[3])
                    self.arrow(at, target, opt.get("arrow", 2.5), "细实线")
                    self.gtol(at[0] - w if left else at[0], at[1] - (hh / 2 if opt.get("mid") else 0), *args)
                else:
                    self.roughness_leader(target, at, args[0], args[1], fixed=True)
            self._leaders = []
        lint.break_lines(self.msp)  # 点画线、细实线、尺寸线在文字处断开
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

    def wavy(self, p, q, amp_mm: float = 1.0):
        """波浪线（局部剖视的分界线，细实线），从 p 到 q；amp_mm 为图纸上的波幅。"""
        amp = amp_mm / self.s
        L = math.dist(p, q)
        n = max(int(L / (8 * amp)), 2)
        ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
        pts = [(p[0] + ux * L * k / (4 * n) - uy * amp * math.sin(math.pi * k / 2),
                p[1] + uy * L * k / (4 * n) + ux * amp * math.sin(math.pi * k / 2)) for k in range(4 * n + 1)]
        self.poly(pts, "细实线")

    def dim_auto(self, a, b, bases, angle=0.0, text="<>", dec=1, tol=None):
        if self.rot:
            angle = 90.0 - angle
        self.sh.dim_auto(self.P(*a), self.P(*b), [self.P(*p) for p in bases], angle, text, self.s, dec, tol=tol)

    def dim(self, a, b, base, angle=0.0, text="<>", dec=1, tol=None):
        if self.rot:
            angle = 90.0 - angle
        self.sh.dim(self.P(*a), self.P(*b), self.P(*base), angle, text, self.s, dec, tol=tol)

    def dim_best(self, a, b, bases, angle=0.0, text="<>", dec=1, tol=None):
        """在几个候选尺寸线位置中自动选一个，返回采用的 base（图纸坐标）。见 Sheet.dim_best。"""
        if self.rot:
            angle = 90.0 - angle
        return self.sh.dim_best(self.P(*a), self.P(*b), [self.P(*p) for p in bases], angle, text, self.s, dec, tol=tol)
