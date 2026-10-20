"""工程图自动检查：文字与文字、文字与图线是否重叠。

GB/T 4458.4 要求尺寸数字不被任何图线通过，否则须将图线断开；技术要求、序号、表格文字同样不应压线。
这里读出图纸 DXF，把每段文字（含尺寸数字和极限偏差）按字高、字数估出外框，检查：

- 两段文字的外框相交；
- 粗实线、细实线、虚线、尺寸线、图框线穿过文字外框（点画线单列，通常只是提醒）。

文字宽度用预览和 PDF 实际使用的中文字体（宽度因子 0.7）量出，比 AutoCAD 里的仿宋略宽，偏于安全。外框四周各收进约 0.12 倍字高，
避免表格格线、引线水平线、尺寸线这些本来就贴着文字的线被误报。剖面线不检查。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

LINE_LAYERS = {"粗实线", "细实线", "虚线", "尺寸", "图框", "文字"}
CENTER_LAYERS = {"点画线"}
_STACK = re.compile(r"\\S([^^;]*)\^([^;]*);")


@dataclass
class TextBox:
    text: str
    x: float  # 外框左下角（文字自身坐标系），以及旋转角
    y: float
    w: float
    h: float
    rot: float
    owner: int  # 所属尺寸的编号（独立文字为 -1），同一尺寸自身的线不算压字

    def corners(self):
        c, s = math.cos(self.rot), math.sin(self.rot)
        return [(self.x + c * u - s * v, self.y + s * u + c * v) for u, v in ((0, 0), (self.w, 0), (self.w, self.h), (0, self.h))]

    def center(self):
        cs = self.corners()
        return (sum(p[0] for p in cs) / 4, sum(p[1] for p in cs) / 4)


@dataclass
class Issue:
    kind: str  # "text-text"、"line-text"、"centerline-text"
    text: str
    at: tuple[float, float]
    other: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "at": [round(self.at[0], 1), round(self.at[1], 1)], "other": self.other}


@dataclass
class LintResult:
    file: str
    issues: list[Issue] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for i in self.issues if i.kind == kind)


def _char_w(ch: str) -> float:
    return 1.0 if ord(ch) > 0x2E80 else 0.62


_FONTS: dict = {}


def text_width(s: str, h: float) -> float:
    """文字宽度（mm）：按预览和 PDF 实际使用的中文字体、宽度因子 0.7 量出；找不到字体时按每字估算。
    预览字体比 AutoCAD 里的仿宋宽，按它估计偏于安全。"""
    if "font" not in _FONTS:
        try:
            from ezdxf.fonts import fonts

            from gongke_core.drawing.render import _cjk_font

            name = _cjk_font()
            _FONTS["font"] = (lambda hh: fonts.make_font(name, cap_height=hh, width_factor=0.7)) if name else None
        except Exception:  # noqa: BLE001
            _FONTS["font"] = None
    mk = _FONTS["font"]
    if mk is None:
        return sum(_char_w(ch) for ch in s) * h
    key = round(h, 3)
    if key not in _FONTS:
        _FONTS[key] = mk(h)
    return _FONTS[key].text_width(s)


def _plain(s: str) -> str:
    """去掉 DXF 控制码（%%c、%%d、%%p 各算一个字符）。"""
    return s.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%p", "±")


def _text_box(e, owner: int) -> TextBox | None:
    t = e.dxftype()
    if t == "TEXT":
        s = _plain(e.dxf.text)
        h = e.dxf.height
        rot = math.radians(e.dxf.get("rotation", 0.0))
        w = text_width(s, h)
        halign, valign = e.dxf.get("halign", 0), e.dxf.get("valign", 0)
        if halign == 0 and valign == 0:
            px, py = e.dxf.insert.x, e.dxf.insert.y
        else:
            px, py = e.dxf.align_point.x, e.dxf.align_point.y
        du = {0: 0.0, 1: -w / 2, 2: -w, 4: -w / 2}.get(halign, 0.0)
        dv = {0: 0.0, 1: 0.0, 2: -h / 2, 3: -h}.get(valign, 0.0)
        if halign == 4:  # MIDDLE：水平、竖直都居中
            dv = -h / 2
    elif t == "MTEXT":
        s = e.plain_text().replace("\n", " ")
        h = e.dxf.char_height
        rot = math.radians(e.dxf.get("rotation", 0.0))
        raw = e.text
        w = 0.0
        for m_ in _STACK.finditer(raw):  # 极限偏差上下叠写：宽度取较长的一行，字高按 0.7
            w += max(text_width(m_.group(1), 0.7 * h), text_width(m_.group(2), 0.7 * h))
        rest = _STACK.sub("", raw)
        rest = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", rest)
        w += text_width(_plain(rest), h)
        att = e.dxf.get("attachment_point", 1)
        col, row = (att - 1) % 3, (att - 1) // 3
        px, py = e.dxf.insert.x, e.dxf.insert.y
        du = (0.0, -w / 2, -w)[col]
        dv = (-h, -h / 2, 0.0)[row]
    else:
        return None
    if not s.strip():
        return None
    m = 0.12 * h
    du, dv = du + m, dv + m
    c, sn = math.cos(rot), math.sin(rot)
    return TextBox(s, px + c * du - sn * dv, py + sn * du + c * dv, max(w - 2 * m, 0.1), max(h - 2 * m, 0.1), rot, owner)


def _segments(e) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    t = e.dxftype()
    if t == "LINE":
        return [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]
    if t == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        if e.closed and len(pts) > 2:
            pts.append(pts[0])
        return list(zip(pts, pts[1:]))
    if t in ("ARC", "CIRCLE"):
        cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
        a0, a1 = (e.dxf.start_angle, e.dxf.end_angle) if t == "ARC" else (0.0, 360.0)
        if a1 <= a0:
            a1 += 360
        n = max(int((a1 - a0) / 6), 2)
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
               for k in range(n + 1)]
        return list(zip(pts, pts[1:]))
    return []


def _clip(box: TextBox, p, q, grow: float = 0.0) -> tuple[float, float] | None:
    """线段 p–q 落在文字外框（四周放大 grow）内的参数区间 (t0, t1)，不相交时为 None（Liang–Barsky 裁剪）。"""
    c, s = math.cos(-box.rot), math.sin(-box.rot)

    def loc(pt):
        dx, dy = pt[0] - box.x, pt[1] - box.y
        return c * dx - s * dy, s * dx + c * dy

    (x0, y0), (x1, y1) = loc(p), loc(q)
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    g = grow
    for pp, qq in ((-dx, x0 + g), (dx, box.w + g - x0), (-dy, y0 + g), (dy, box.h + g - y0)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return None
        else:
            r = qq / pp
            if pp < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return None
    return t0, t1


def _hits(box: TextBox, p, q) -> bool:
    return _clip(box, p, q) is not None


def _boxes_overlap(a: TextBox, b: TextBox) -> bool:
    ca, cb = a.corners(), b.corners()
    for poly, other in ((ca, cb), (cb, ca)):
        for i in range(4):
            p, q = poly[i], poly[(i + 1) % 4]
            nx, ny = q[1] - p[1], p[0] - q[0]
            pa = [nx * x + ny * y for x, y in poly]
            pb = [nx * x + ny * y for x, y in other]
            if max(pa) <= min(pb) or max(pb) <= min(pa):
                return False
    return True


def text_boxes(msp) -> list[TextBox]:
    """图中全部文字（含尺寸数字）的外框。"""
    out = []
    for e in msp:
        if e.dxftype() == "DIMENSION":
            blk = e.get_geometry_block()
            for ve in blk or ():
                b = _text_box(ve, int(e.dxf.handle, 16))
                if b:
                    out.append(b)
        else:
            b = _text_box(e, -1)
            if b:
                out.append(b)
    return out


BREAK_LAYERS = ("点画线", "尺寸", "细实线")


def _break_in(layout, boxes, layers, gap, own=None) -> int:
    n = 0
    for e in list(layout.query("LINE")):
        if own is None and e.dxf.layer not in layers:  # 尺寸块里的线都断
            continue
        p, q = (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
        cuts = []
        for b in boxes:
            if own is not None and b.owner == own:
                continue
            if _clip(b, p, q) is None:  # 只断开真正穿过文字的线，贴着文字的引线、格线不动
                continue
            cuts.append(_clip(b, p, q, b.h * 0.12 + gap))
        if not cuts:
            continue
        cuts.sort()
        merged = []
        for a, b_ in cuts:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b_))
            else:
                merged.append((a, b_))
        keep, t = [], 0.0
        for a, b_ in merged:
            if a > t:
                keep.append((t, a))
            t = max(t, b_)
        if t < 1:
            keep.append((t, 1.0))
        L = math.dist(p, q)
        attrs = {k: v for k, v in e.dxfattribs().items() if k not in ("handle", "owner", "start", "end")}
        for a, b_ in keep:
            if (b_ - a) * L > 0.5:
                layout.add_line((p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a),
                                (p[0] + (q[0] - p[0]) * b_, p[1] + (q[1] - p[1]) * b_), dxfattribs=attrs)
        layout.delete_entity(e)
        n += len(merged)
    return n


def _in_box(b: TextBox, pt, grow: float) -> bool:
    c, s = math.cos(-b.rot), math.sin(-b.rot)
    dx, dy = pt[0] - b.x, pt[1] - b.y
    u, v = c * dx - s * dy, s * dx + c * dy
    return -grow <= u <= b.w + grow and -grow <= v <= b.h + grow


def _break_arcs(msp, boxes, gap) -> int:
    """点画线圆和圆弧（分度圆、孔的中心圆）遇文字断开：按 1° 取点，去掉落在文字外框内的部分。"""
    n = 0
    for e in list(msp.query("CIRCLE ARC")):
        if e.dxf.layer != "点画线":
            continue
        cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
        near = [b for b in boxes if _clip(b, (cx - r, cy), (cx + r, cy), r + 10) is not None]
        if not near:
            continue
        a0, a1 = (e.dxf.start_angle, e.dxf.end_angle) if e.dxftype() == "ARC" else (0.0, 360.0)
        if a1 <= a0:
            a1 += 360
        steps = max(int((a1 - a0) * 2), 2)
        angs = [a0 + (a1 - a0) * k / steps for k in range(steps + 1)]
        hidden = [any(_in_box(b, (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))), 0.12 * b.h + gap)
                      for b in near) for a in angs]
        if not any(hidden):
            continue
        runs, start = [], None
        for a, hd in zip(angs, hidden):
            if not hd and start is None:
                start = a
            if hd and start is not None:
                runs.append((start, a))
                start = None
        if start is not None:
            runs.append((start, angs[-1]))
        if e.dxftype() == "CIRCLE" and len(runs) > 1 and runs[0][0] == angs[0] and runs[-1][1] == angs[-1]:
            runs = [(runs[-1][0], runs[0][1] + 360)] + runs[1:-1]
        attrs = {k: v for k, v in e.dxfattribs().items() if k not in ("handle", "owner", "center", "radius", "start_angle", "end_angle")}
        for b0, b1 in runs:
            if (b1 - b0) * math.pi / 180 * r > 0.5:
                msp.add_arc((cx, cy), r, b0, b1, dxfattribs=attrs)
        msp.delete_entity(e)
        n += 1
    return n


def break_lines(msp, layers=BREAK_LAYERS, gap: float = 0.6) -> int:
    """按 GB/T 4458.4“尺寸数字不可被任何图线通过，否则应将该图线断开”，把穿过文字的点画线、细实线、
    尺寸线和尺寸界线断开（尺寸自身的线不对自身数字断开），断口比文字每边宽 gap（mm）。
    粗实线、虚线不断开，压字时应移动文字。返回断开的处数。"""
    boxes = text_boxes(msp)
    n = _break_in(msp, boxes, layers, gap) + _break_arcs(msp, boxes, gap)
    # 剖面线遇文字断开：文字整个落在某个剖面区域内时，把文字外框作为孤岛加进该剖面线的边界
    for hh in msp.query("HATCH"):
        if hh.dxf.layer != "剖面线":
            continue
        polys = [[(v[0], v[1]) for v in getattr(path, "vertices", [])] for path in hh.paths]
        for b in boxes:
            g = b.h * 0.12 + gap
            isl = TextBox(b.text, b.x - g * math.cos(b.rot) + g * math.sin(b.rot), b.y - g * math.sin(b.rot) - g * math.cos(b.rot),
                          b.w + 2 * g, b.h + 2 * g, b.rot, b.owner).corners()
            if any(len(pl) > 2 and all(_inside(p, pl) for p in isl) for pl in polys):
                hh.paths.add_polyline_path(isl, is_closed=True)
                n += 1
    for e in msp.query("DIMENSION"):
        blk = e.get_geometry_block()
        if blk is not None:
            n += _break_in(blk, boxes, layers, gap, own=int(e.dxf.handle, 16))
    return n


def check(dxf: str | Path) -> LintResult:
    doc = ezdxf.readfile(str(dxf))
    msp = doc.modelspace()
    texts: list[TextBox] = []
    segs: list[tuple[tuple, tuple, str, int]] = []  # (p, q, 图层, 所属尺寸)
    for e in msp:
        t = e.dxftype()
        if t == "DIMENSION":
            owner = int(e.dxf.handle, 16)
            blk = e.get_geometry_block()
            if blk is None:
                continue
            for ve in blk:
                b = _text_box(ve, owner)
                if b:
                    texts.append(b)
                else:
                    for p, q in _segments(ve):
                        segs.append((p, q, "尺寸", owner))
            continue
        b = _text_box(e, -1)
        if b:
            texts.append(b)
            continue
        layer = e.dxf.get("layer", "0")
        if layer in LINE_LAYERS or layer in CENTER_LAYERS:
            for p, q in _segments(e):
                segs.append((p, q, layer, -1))

    res = LintResult(str(dxf))
    # 文字之间
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a.owner == b.owner and a.owner != -1:
                continue  # 同一尺寸的数字和偏差
            if _boxes_overlap(a, b):
                res.issues.append(Issue("text-text", a.text, a.center(), b.text))
    # 图线穿过文字：先按外接矩形粗筛
    for a in texts:
        cs = a.corners()
        x0, x1 = min(p[0] for p in cs), max(p[0] for p in cs)
        y0, y1 = min(p[1] for p in cs), max(p[1] for p in cs)
        hit = {}
        for p, q, layer, owner in segs:
            if owner == a.owner and owner != -1:
                continue
            if max(p[0], q[0]) < x0 or min(p[0], q[0]) > x1 or max(p[1], q[1]) < y0 or min(p[1], q[1]) > y1:
                continue
            if _hits(a, p, q):
                kind = "centerline-text" if layer in CENTER_LAYERS else "line-text"
                hit.setdefault(kind, layer)
        for kind, layer in hit.items():
            res.issues.append(Issue(kind, a.text, a.center(), layer))
    return res


def check_dir(folder: str | Path) -> list[LintResult]:
    return [check(f) for f in sorted(Path(folder).glob("*.dxf"))]


# ---------------------------------------------------------------------- 引出标注自动避让

_COST = {"粗实线": 10.0, "虚线": 10.0, "细实线": 6.0, "尺寸": 6.0, "图框": 10.0, "文字": 6.0, "点画线": 2.0}


class _Grid:
    """按 10 mm 方格索引的图线和文字外框，用来快速找附近的障碍。"""

    def __init__(self, cell: float = 10.0):
        self.cell = cell
        self.cells: dict[tuple[int, int], list] = {}

    def _keys(self, x0, y0, x1, y1):
        c = self.cell
        for i in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for j in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
                yield i, j

    def add(self, item, bbox):
        for k in self._keys(*bbox):
            self.cells.setdefault(k, []).append(item)

    def near(self, bbox):
        seen, out = set(), []
        for k in self._keys(*bbox):
            for it in self.cells.get(k, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)
        return out


def _bbox_pts(pts, m=0.0):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def _seg_cross(p1, p2, q1, q2) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def obstacle_grid(msp) -> _Grid:
    g = _Grid()
    for b in text_boxes(msp):
        g.add(("text", b), _bbox_pts(b.corners()))
    for e in msp:
        t = e.dxftype()
        if t == "DIMENSION":
            for ve in e.get_geometry_block() or ():
                for p, q in _segments(ve):
                    g.add(("seg", (p, q, "尺寸")), _bbox_pts((p, q)))
            continue
        layer = e.dxf.get("layer", "0")
        if t == "HATCH" and layer == "剖面线":
            for path in e.paths:
                pts = [(v[0], v[1]) for v in getattr(path, "vertices", [])]
                if len(pts) > 2:
                    g.add(("hatch", pts), _bbox_pts(pts))
            continue
        if layer in _COST:
            for p, q in _segments(e):
                g.add(("seg", (p, q, layer)), _bbox_pts((p, q)))
    return g


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _rect(x0, y0, w, h, text="") -> TextBox:
    return TextBox(text, x0, y0, w, h, 0.0, -1)


def leader_shape(s: str, h: float):
    """引出标注（引线 + 水平线 + 文字，与 Sheet.leader_text 画法一致）的外形函数。"""
    tw = text_width(s, h)
    w = tw + 2
    m = 0.12 * h

    def shape(target, at, left):
        x0 = at[0] - w if left else at[0]
        box = _rect(x0 + 1 + m, at[1] + 0.8 + m, tw - 2 * m, h - 2 * m, s)
        return box, [(target, at), ((x0, at[1]), (x0 + w, at[1]))]
    return shape


def label_shape(s: str, h: float):
    """不带引线的文字，at 为左下角。"""
    tw = text_width(s, h)
    m = 0.12 * h

    def shape(target, at, left):
        return _rect(at[0] + m, at[1] + m, tw - 2 * m, h - 2 * m, s), []
    return shape


def frame_shape(w: float, hh: float, mid: bool = False):
    """带指引箭头的几何公差框格：left=False 时箭头从框格左下角（mid=True 时左边中点）引出，
    left=True 时从右下角（右边中点）引出。"""
    def shape(target, at, left):
        x0 = at[0] - w if left else at[0]
        return _rect(x0, at[1] - (hh / 2 if mid else 0), w, hh), [(target, at)]
    return shape


def roughness_shape(ra: str, h: float):
    """带引线的表面结构符号（与 Sheet.roughness_leader 一致）：符号尖端在 at 右侧 5 mm 的水平段上。"""
    h1 = 1.4 * h
    h2 = 2.1 * h1
    t = math.tan(math.radians(30))
    w = len(ra) * h * 0.6 + 4

    def shape(target, at, left):
        x, y = at[0] + 5, at[1]
        return _rect(x - h1 * t, y + 0.3, h1 * t + h2 * t + w, h2 - 0.3), [(target, at), (at, (at[0] + 10, at[1]))]
    return shape


def _place_cost(g: _Grid, shape, target, at, left, frame) -> float:
    box, conns = shape(target, at, left)
    cs = box.corners()
    bb = _bbox_pts(cs)
    if frame and (bb[0] < frame[0] or bb[2] > frame[2] or bb[1] < frame[1] or bb[3] > frame[3]):
        return 1e9
    cost = 0.0
    for kind, it in g.near(bb):
        if kind == "seg":
            p, q, layer = it
            if _hits(box, p, q):
                cost += _COST.get(layer, 6.0)
        elif kind == "hatch":  # 压在剖面线上（剖面线须断开，尽量避开）
            if any(_inside(p, it) for p in cs + [box.center()]):
                cost += 4.0
        elif _boxes_overlap(box, it):
            cost += 20.0
    for a, b in conns:
        for kind, it in g.near(_bbox_pts((a, b))):
            if kind == "text" and _hits(it, a, b):  # 引线或水平线穿过别的文字
                cost += 10.0
    return cost


def place(g: _Grid, shape, target, at, left: bool = False, frame=None, flip: bool = True):
    """在原定位置附近找不压线、不压字的位置，返回 (at, left)。原位置没有冲突时不动。
    flip=True 时在目标左侧的候选位置改为向左引出。"""
    base = _place_cost(g, shape, target, at, left, frame)
    if base == 0:
        return at, left
    vx, vy = at[0] - target[0], at[1] - target[1]
    L0 = max(math.hypot(vx, vy), 8.0)
    a0 = math.atan2(vy, vx)
    best = (base, at, left)
    for da in (0, 15, -15, 30, -30, 45, -45, 60, -60, 90, -90, 120, -120, 150, -150, 180):
        for f in (1.0, 1.4, 1.9, 2.5, 3.2):
            a = a0 + math.radians(da)
            cand = (target[0] + L0 * f * math.cos(a), target[1] + L0 * f * math.sin(a))
            lf = cand[0] < target[0] if flip else left
            c = _place_cost(g, shape, target, cand, lf, frame) + 0.04 * math.dist(cand, at) + (0.3 if lf != left else 0)
            if c < best[0] - 1e-9:
                best = (c, cand, lf)
    return best[1], best[2]


def place_sliding(g: _Grid, shape, options, frame=None):
    """只沿给定方向滑动的放置（例如键槽对称度框格的指引线须与尺寸线对齐）。
    options 为若干 (target, at, left)，每个都沿 target→at 方向试几个距离，返回代价最小的 (target, at, left)。"""
    best = None
    for k, (target, at, left) in enumerate(options):
        for f in (1.0, 1.5, 2.0, 3.0, 4.0, 5.5):
            cand = (target[0] + (at[0] - target[0]) * f, target[1] + (at[1] - target[1]) * f)
            c = _place_cost(g, shape, target, cand, left, frame) + 0.04 * math.dist(cand, at) + 0.5 * k
            if best is None or c < best[0] - 1e-9:
                best = (c, target, cand, left)
    return best[1], best[2], best[3]


def add_obstacles(g: _Grid, shape, target, at, left):
    box, conns = shape(target, at, left)
    g.add(("text", box), _bbox_pts(box.corners()))
    for p, q in conns:
        g.add(("seg", (p, q, "尺寸")), _bbox_pts((p, q)))
