"""减速器装配图：主视图（外形）、俯视图（沿剖分面剖切、去掉箱盖）、左视图（外形）。

按 GB/T 4459.2、4459.7 和装配图规定画法：
- 实心轴沿轴线剖切按不剖处理，画外形；齿轮、套筒剖开画剖面线，相邻零件剖面线方向相反；
- 啮合区小齿轮轮齿画成可见，大齿轮被遮住的齿顶线画虚线；
- 深沟球轴承在轴线一侧用规定画法（内外圈剖面线、滚动体画圆），另一侧用通用画法（矩形线框加正十字），
  圆锥滚子轴承两侧都用通用画法（GB/T 4459.7）；
- 轴承盖按一个零件剖开：凸缘和伸入座孔的止口画同一方向的剖面线；
- 主视图、左视图画外形，被轴承盖、轴承座等挡住的线不画（见 `hidden`）；
- 零件序号沿图形四周按逆时针顺次排列，配明细栏、技术特性表和技术要求。

视图按第一角投影配置：俯视图在主视图下方（下方为前），左视图在主视图右方（右方为前）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from gongke_core import standards
from gongke_core.calc.tolerance import center_distance_fa
from gongke_core.design import ReducerDesign
from gongke_core.drawing import hidden, material_name
from gongke_core.drawing.gear import dms
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout.gear_blank import blank
from gongke_core.layout.housing_detail import Arc, HousingDetail, detail, envelope_height

MM = 1e3  # m → mm

PIN_D = [6, 8, 10, 12, 16]
MINOR = {12: 10.106, 16: 14.376}  # 螺纹小径：M12（粗牙）、M16×1.5
CLEARANCE = {6: 6.6, 8: 9, 10: 11, 12: 13.5, 16: 17.5, 20: 22, 24: 26, 30: 33}  # 螺栓通孔（GB/T 5277 中等装配）
SPOT_FACE = {6: 13, 8: 18, 10: 22, 12: 26, 16: 33, 20: 40, 24: 48, 30: 61}  # 沉孔锪平直径
# 课程设计装配图技术要求的最后两条：试运转
TRIAL_RUN = ["装配后作空载试运转，正、反转各 1 h，运转平稳、无冲击和异常噪声，各连接处不松动。",
             "负载试运转时油池温升不超过 35 ℃，轴承温升不超过 40 ℃。"]
PIN_L = [20, 24, 26, 28, 30, 32, 35, 40, 45, 50, 55, 60]
SCREW_L = [10, 12, 16, 20, 25, 30, 35, 40, 45, 50]


def _std(v: float, table: list[int]) -> int:
    return next((x for x in table if x >= v - 1e-9), table[-1])


def _zshafts(d) -> list:
    """轴线沿 z（垂直于主视图）的各轴；圆锥-圆柱减速器的Ⅰ轴沿 x，单独画。"""
    return d.shafts[1:] if getattr(d, "bevel", None) is not None else d.shafts


def _bearing_bodies(lay, backs=(+1, -1)) -> list[tuple[float, float]]:
    """两轴承的 (中面位置, 宽度)（mm）。圆锥滚子轴承的 bearing_z 是压力中心，按内圈背面朝向 backs 换算到中面。"""
    brg = lay.bearing
    if isinstance(brg, standards.TaperedBearing):
        off = brg.a - brg.T / 2
        return [((z - b * off) * MM, brg.T * MM) for z, b in zip(lay.bearing_z, backs)]
    return [(z * MM, brg.B * MM) for z in lay.bearing_z]


def _bearing_name(brg) -> tuple[str, str]:
    if isinstance(brg, standards.TaperedBearing):
        return f"圆锥滚子轴承 {brg.designation}", "GB/T 297-2015"
    return f"深沟球轴承 {brg.designation}", "GB/T 276-2013"


def draw_bearing(v: View, zc: float, B: float, x: float, dd: float, Dd: float, ang: float,
                 detail: bool = True) -> None:
    """轴线沿 z 的滚动轴承（mm）。detail=True 时 +x 一侧用深沟球轴承规定画法：
    内外圈画剖面线（同一方向），滚动体为直径 A/2 的圆（A = (D − d)/2），−x 一侧用通用画法。"""
    A = (Dd - dd) / 2
    rm = (dd + Dd) / 4  # 滚动体中心半径
    for sgn in (1, -1):
        y_in, y_out = x + sgn * dd / 2, x + sgn * Dd / 2
        v.rect(zc - B / 2, min(y_in, y_out), zc + B / 2, max(y_in, y_out))
        if detail and sgn > 0:
            rb = A / 4
            v.circle((zc, x + rm), rb)
            # 内、外圈的分界线在滚动体中心两侧 A/6 处，与滚动体圆相交；剖面线区域绕开滚动体
            h = A / 6
            w = math.sqrt(max(rb**2 - h**2, 0.0))
            n = 12
            for side in (1, -1):  # 1：外圈，−1：内圈
                yb = rm + side * h
                v.line((zc - B / 2, x + yb), (zc - w, x + yb))
                v.line((zc + w, x + yb), (zc + B / 2, x + yb))
                # 从左交点沿滚动体圆弧（外圈经上方、内圈经下方）到右交点
                a0, a1 = math.atan2(side * h, -w), math.atan2(side * h, w)
                arc = [a0 + (a1 - a0) * k / n for k in range(n + 1)]
                pts = [(zc - B / 2, x + yb), (zc - w, x + yb)]
                pts += [(zc + rb * math.cos(t), x + rm + rb * math.sin(t)) for t in arc]
                y_edge = Dd / 2 if side > 0 else dd / 2
                pts += [(zc + w, x + yb), (zc + B / 2, x + yb), (zc + B / 2, x + y_edge), (zc - B / 2, x + y_edge)]
                v.hatch([pts], ang, 1.2)
        else:
            ym = (y_in + y_out) / 2
            v.line((zc - B * 0.3, ym), (zc + B * 0.3, ym), "细实线")
            v.line((zc, ym - abs(y_out - y_in) * 0.3), (zc, ym + abs(y_out - y_in) * 0.3), "细实线")


def cap_section(v: View, z_out: float, z_in: float, z_brg: float, x: float, r_cap: float, r_bore: float,
                r_seal: float, ang: float) -> None:
    """轴承盖剖面（mm）：凸缘在 z_out～z_in（z_in 为贴箱体的面），止口从 z_in 伸到轴承外圈端面 z_brg，
    止口壁厚 8 mm。r_seal > 0 为透盖（中间有轴孔），否则为闷盖（整块剖面）。"""
    r_sp = max(r_bore - 8, r_seal + 2)
    spig = abs(z_brg - z_in) > 0.5

    def half(sgn):
        pts = [(z_out, x + sgn * r_cap), (z_in, x + sgn * r_cap)]
        if spig:
            pts += [(z_in, x + sgn * r_bore), (z_brg, x + sgn * r_bore), (z_brg, x + sgn * r_sp), (z_in, x + sgn * r_sp)]
        return pts

    if r_seal > 0:
        loops = []
        for sgn in (1, -1):
            pts = [(z_out, x + sgn * r_seal)] + half(sgn) + [(z_in, x + sgn * r_seal)]
            loops.append(pts)
    else:
        up, dn = half(1), half(-1)
        loops = [up + list(reversed(dn))]
    for pts in loops:
        v.poly(pts, close=True)
    v.hatch(loops, ang, 2.0)


@dataclass
class Part:
    name: str
    qty: str
    material: str
    note: str
    target: tuple[float, float] | None = None  # 图纸坐标
    group: str = ""  # 序号所在的一排：FL/FT/FR（主视图左、上、右），TL/TR（俯视图左、右）


def draw(d: ReducerDesign, path: str | Path, drawing_no: str = "GK-00") -> Sheet:
    t = detail(d)
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    zsh = _zshafts(d)
    xs = [s.layout.x * MM for s in zsh]
    xo0, xo1 = (v * MM for v in t.x_outer)
    bevel = getattr(d, "bevel", None)

    # ------------------------------------------------ 各视图的模型范围（mm）
    z_min = min(s.layout.segments[0].z0 for s in zsh) * MM - 5
    z_max = max(s.layout.segments[-1].z1 for s in zsh) * MM + 5
    x_left = xo0 - fw - 2
    if bevel is not None:  # Ⅰ轴从左端壁伸出，套杯凸缘在 z_apex 两侧
        from gongke_core.layout.bevel_reducer import cup

        c = cup(d.pinion)
        za = d.positions.z_apex * MM
        z_min = min(z_min, za - c.flange_D * MM / 2 - 5)
        z_max = max(z_max, za + c.flange_D * MM / 2 + 5)
        x_left = min(x_left, -d.pinion.segments[-1].z1 * MM - 5)
    eye_top = max(envelope_height(t.cover_outer, x) for x in t.eyebolts) * MM + 4.6 * t.eyebolt_d * MM
    fy0, fy1 = t.y_bottom * MM, max(eye_top, t.cover_top * MM + 30)
    cx0, cx1 = x_left, xo1 + fw + 40  # 右端有油标、放油螺塞
    front_w, front_h = cx1 - cx0, fy1 - fy0
    top_h = z_max - z_min
    left_w = z_max - z_min
    n_rows = 42  # 明细栏行数的估计上限
    n_cont = 18  # 标题栏左方续表的最多行数

    for size in ("A1", "A0"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        s = None
        for sc in reversed(SCALES):
            if sc > 1:
                continue
            w_need = 48 + front_w * sc + 40 + left_w * sc + 30
            h_need = 25 + front_h * sc + 32 + top_h * sc + 30
            right_free = (x1 - x0) - 180 - (48 + front_w * sc + 45)  # 俯视图右侧放技术特性表、技术要求
            front_bottom = y1 - 25 - front_h * sc
            left_right = x0 + 48 + front_w * sc + 40 + left_w * sc + 30
            first_rows = int((front_bottom - 22 - (y0 + 56)) / 7) - 1 if left_right > x1 - 180 else 99
            if (w_need <= x1 - x0 and h_need <= y1 - y0 and right_free >= 135
                    and first_rows + n_cont >= n_rows and front_bottom - 30 - 130 >= y0 + 7 * (n_cont + 1)):
                s = sc
                break
        if s is not None or size == "A0":
            s = s or 1 / 5
            break
    sh.parts_first_rows = max(first_rows, 10) if s is not None else None

    ox = x0 + 48 - cx0 * s  # 模型 x = 0 在图纸上的 X（主视图、俯视图共用）
    oy_f = y1 - 25 - fy1 * s  # 模型 y = 0（剖分面）在主视图中的 Y
    front_bottom = oy_f + fy0 * s
    oy_t = front_bottom - 32 + z_min * s  # 俯视图：图上 Y = oy_t − z·s
    front_right = ox + cx1 * s
    ox_l = front_right + 40 - z_min * s  # 左视图：图上 X = ox_l + z·s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s, rotate=True)  # 模型 (z, x) → 图上 (x, −z)
    lv = View(sh, (ox_l, oy_f), s)

    parts: list[Part] = []
    by_name: dict[str, Part] = {}

    def add(name, qty, mat, note="", target=None, group=""):
        if name in by_name:
            p = by_name[name]
            if p.target is None and target is not None:
                p.target, p.group = target, group
            return p
        p = Part(name, str(qty), mat, note, target, group)
        parts.append(p)
        by_name[name] = p
        return p

    _top_view(d, t, tv, sh, add)
    _front_view(d, t, fv, sh, add)
    _left_view(d, t, lv, sh)
    _standard_parts(d, t, add)

    # ------------------------------------------------ 零件序号与明细栏
    col_fl = min(ox + cx0 * s, ox + (h.x_range[0] * MM - delta - fw) * s) - 30  # 俯视图左侧有宽度、总宽两道尺寸
    col_tr = ox + (xo1 + fw) * s + 30
    col_fr = front_right + 14
    row_ft = oy_f + fy1 * s + 12
    _place_balloons(sh, parts, {
        "FL": ("col", col_fl, (front_bottom - 5, y1 - 8)),
        "TL": ("col", col_fl, (y0 + 10, front_bottom - 12)),
        "TR": ("col", col_tr, (y0 + 10, front_bottom - 12)),
        "FR": ("col", col_fr, (front_bottom + 2, y1 - 8)),
        "FT": ("row", row_ft, (ox + cx0 * s, front_right)),
    })

    # ------------------------------------------------ 尺寸
    zr = z_min - 5
    mesh = [d.low] if getattr(d, "bevel", None) is not None else [d.high, d.low]
    for (xa, xb), pair in zip(zip(xs, xs[1:]), mesh):
        fa = center_distance_fa(pair.inp.grade, pair.a) * MM
        tv.dim((zr, xa), (zr, xb), (zr - 10 / s, xa), 90, f"<>±{fa:.3f}".rstrip("0"), 0)
    tv.dim((-delta - fw, xo0 - fw), (W + delta + fw, xo0 - fw), (-delta - fw, xo0 - fw - 14 / s), 0, "<>", 0)
    tv.dim((z_max - 5, xo0 - fw), (z_max - 5, xo1 + fw), (z_max + 2 / s, xo0 - fw), 90, "<>", 0)
    # 安装尺寸：地脚螺栓孔的孔距（横向在凸缘上方，纵向在右侧）和孔径
    from gongke_core.drawing.housing_base import CLEARANCE
    fxs = sorted({fx * MM for fx, _ in t.foot_bolts})
    fzs = sorted({fz * MM for _, fz in t.foot_bolts})
    z_caps = -h.bearing_seat_length * MM - h.cap_thickness * MM  # 轴承盖外端面，孔距尺寸放在它的上方
    tv.dim((fzs[0], fxs[0]), (fzs[0], fxs[-1]), (z_caps - 8 / s, fxs[0]), 90, "<>", 0)
    tv.dim((fzs[0], fxs[-1]), (fzs[-1], fxs[-1]), (fzs[0], xo1 + fw + 14 / s), 0, "<>", 0)
    dfh = CLEARANCE[round(h.bolt_foot * MM)]
    px, py = tv.P(fzs[0], fxs[-1])
    sh.leader_text((px + dfh / 2 * s * 0.7, py + dfh / 2 * s * 0.7), (px + 8, py + 14), f"{len(t.foot_bolts)}×Ø{dfh:g}", 3.0)
    # 外伸轴段的配合长度（联轴器、带轮的安装尺寸）
    for sr_ in zsh:
        lay_ = sr_.layout
        if not lay_.extension:
            continue
        end = next(sg for sg in lay_.segments if sg.role == "端部")
        xx = lay_.x * MM + end.d * MM + 6 / s
        tv.dim((end.z0 * MM, xx - 6 / s), (end.z1 * MM, xx - 6 / s), (end.z0 * MM, xx), 0, "<>", 0)
    # 外形尺寸：两外伸轴端之间的总宽
    z_ends = [z_min + 5, z_max - 5]
    tv.dim((z_ends[0], xs[0]), (z_ends[1], xs[-1]), (z_ends[0], xo0 - fw - 22 / s), 0, "<>", 0)
    # 中心高、总高（左视图右侧）
    zl = z_max
    lv.dim((zl, fy0), (zl, 0), (zl + 10 / s, fy0), 90, "<>", 0)
    top_y = t.cover_top * MM
    lv.dim((zl, fy0), (zl, top_y), (zl + 20 / s, fy0), 90, "<>", 0)
    _fits(d, tv, sh)

    # ------------------------------------------------ 技术特性、技术要求
    k = d.kin
    rows = [["技术特性", ""],
            ["输入功率", f"{k.shafts[1].power / 1e3:.2f} kW"],
            ["输入转速", f"{k.shafts[1].speed_rpm:.0f} r/min"],
            ["传动比", f"{d.high.u * d.low.u:.2f}"]]
    ef = k.task.efficiencies
    if bevel is not None:
        rows.append(["效率", f"{ef.bearing_pair ** 3 * ef.bevel_pair * ef.gear_pair:.3f}"])
        rows.append([bevel.inp.name, f"m={bevel.m * MM:g}  z={bevel.z1}/{bevel.z2}  δ1={dms(bevel.delta1)}  {bevel.inp.grade}级"])
    else:
        rows.append(["效率", f"{ef.bearing_pair ** 3 * ef.gear_pair ** 2:.3f}"])
        rows.append([d.high.inp.name, f"mn={d.high.mn * MM:g}  z={d.high.z1}/{d.high.z2}  β={dms(d.high.beta)}  {d.high.inp.grade}级"])
    p = d.low
    rows.append([p.inp.name, f"mn={p.mn * MM:g}  z={p.z1}/{p.z2}  β={dms(p.beta)}  {p.inp.grade}级"])
    tx = col_tr + 22
    sh.table(tx, front_bottom - 30, rows, [30, 95], 8)
    reqs = [
        "装配前所有零件用煤油清洗，箱体内壁涂耐油油漆。",
        "啮合侧隙用铅丝检验，高速级不小于 0.14 mm，低速级不小于 0.16 mm。",
        "用涂色法检验接触斑点，沿齿高不小于 40%，沿齿长不小于 50%。",
        *(["圆锥滚子轴承用垫片调整轴向游隙（Ⅰ轴 0.04～0.07 mm，Ⅱ轴 0.05～0.10 mm）。",
           "深沟球轴承两端固定，轴向游隙 0.25～0.4 mm。"] if bevel is not None
          else ["深沟球轴承两端固定，用调整垫片调整轴向游隙为 0.25～0.4 mm。"]),
        *(["锥齿轮啮合位置用套杯与轴承座间的垫片调整，使两锥顶重合。"] if bevel is not None else []),
        "剖分面、各接触面及密封处不允许漏油，剖分面允许涂密封胶，不允许使用垫片。",
        f"箱内装 L-CKC 220 工业闭式齿轮油至油标规定高度（大齿轮浸油约 {(t.oil_level + d.low.da2 / 2) * MM:.0f} mm）。",
        "外表面涂灰色油漆。",
        *TRIAL_RUN,
    ]
    sh.tech_requirements(reqs, tx, front_bottom - 30 - 8 * len(rows) - 22 - 0)
    for i, p in enumerate(parts, 1):
        sh.add_part(i, p.name, p.qty, p.material, p.note)
    sh.frame(TitleInfo("圆锥-圆柱齿轮减速器" if bevel is not None else "二级圆柱齿轮减速器", "", s, "1", drawing_no))
    sh.save(path)
    return sh


# ====================================================================== 俯视图

def _top_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet, add):
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    zsh = _zshafts(d)
    xs = [s.layout.x * MM for s in zsh]
    ylo, yhi = h.x_range[0] * MM, h.x_range[1] * MM
    y_min, y_max = ylo - delta - fw, yhi + delta + fw
    group_of = lambda x: "TL" if x < (xs[0] + xs[-1]) / 2 else "TR"  # noqa: E731

    def tadd(name, qty, mat, note, at):
        add(name, qty, mat, note, v.P(*at), group_of(at[1]))

    # 箱座（剖分面俯视）；左端壁有Ⅰ轴轴承座时，凸缘外缘在凸台处、内壁在座孔处断开
    sb = t.side_bore
    def xline(z, x0, x1, skip, layer):
        """z 为常数的线，跳过 skip 中的 x 区间（被轴承座孔或轴承座凸台断开）。"""
        xa = x0
        for a, b_ in sorted(skip):
            if b_ <= xa or a >= x1:
                continue
            if a > xa:
                v.line((z, xa), (z, a), layer)
            xa = max(xa, b_)
        if xa < x1:
            v.line((z, xa), (z, x1), layer)

    def rect_gap(z0, x0, z1, x1, r_gap, layer="粗实线", skip=()):
        v.line((z0, x1), (z1, x1), layer)
        xline(z0, x0, x1, skip, layer)
        xline(z1, x0, x1, skip, layer)
        if sb is None:
            v.line((z0, x0), (z1, x0), layer)
        else:
            zc = sb.z * MM
            v.line((z0, x0), (zc - r_gap, x0), layer)
            v.line((zc + r_gap, x0), (z1, x0), layer)

    rb_side = sb.boss_r * MM if sb else 0
    rd_side = sb.D * MM / 2 if sb else 0
    bores = [(x - c.D * MM / 2, x + c.D * MM / 2) for x, c in zip(xs, t.caps)]
    spans = boss_spans(t)
    rect_gap(-delta - fw, y_min, W + delta + fw, y_max, rb_side, skip=spans)
    rect_gap(0, ylo, W, yhi, rd_side, skip=bores)
    rect_gap(-delta, ylo - delta, W + delta, yhi + delta, rd_side, "细实线", skip=bores)
    # 轴承座和轴承旁凸台伸出凸缘外的部分（按 x 区间合并），与凸缘连成一体，凸缘外缘在此不画线；座孔处端面断开
    for a, b_ in spans:
        for za, zb in ((-L1, -delta - fw), (W + delta + fw, W + L1)):
            v.line((za, a), (zb, a))
            v.line((za, b_), (zb, b_))
            xline(-L1 if za == -L1 else W + L1, a, b_, bores, "粗实线")
    for x, cap in zip(xs, t.caps):
        D = cap.D * MM
        for sgn in (1, -1):
            v.line((-L1, x + sgn * D / 2), (0, x + sgn * D / 2))
            v.line((W, x + sgn * D / 2), (W + L1, x + sgn * D / 2))
    # 凸缘上的螺栓孔、定位销
    zf = (-delta - fw / 2, W + delta + fw / 2)
    for xb, dd in [(x, h.bolt_bearing) for x in t.bearing_bolts] + [(x, h.bolt_flange) for x in t.flange_bolts]:
        for zc in zf:
            v.circle((zc, xb * MM), dd * MM / 2 + 1, "细实线")
            sh.cross(v.P(zc, xb * MM), (dd * MM / 2 + 1) * v.s, 1.5)
    pin_d = _std(t.pin_d * MM, PIN_D)
    for px, pz in t.pins:
        v.circle((pz * MM, px * MM), pin_d / 2)
        sh.cross(v.P(pz * MM, px * MM), pin_d / 2 * v.s, 1.5)
    # 地脚螺栓孔（在凸缘下方，不可见，画虚线），供标注安装尺寸
    from gongke_core.drawing.housing_base import CLEARANCE
    df = CLEARANCE[round(h.bolt_foot * MM)]
    for fx, fz in t.foot_bolts:
        v.circle((fz * MM, fx * MM), df / 2, "虚线")
        sh.cross(v.P(fz * MM, fx * MM), df / 2 * v.s, 1.5)
    pin_l = _std(b_total(h) + 8, PIN_L)
    px, pz = t.pins[0]
    tadd(f"圆锥销 A{pin_d}×{pin_l}", len(t.pins), "35", "GB/T 117-2000", (pz * MM, px * MM))
    tadd("箱座", "1", "HT200", "", (W / 2, ylo - delta / 2))

    hatch_angle = [45]

    def next_angle():
        hatch_angle[0] = 135 if hatch_angle[0] == 45 else 45
        return hatch_angle[0]

    pairs = {"high": d.high, "low": d.low, "bevel": getattr(d, "bevel", None)}
    key_count: dict[str, int] = {}
    key_at: dict[str, tuple[float, float]] = {}
    sleeves = 0
    sleeve_at = None
    for sr, x, cap in zip(zsh, xs, t.caps):
        lay = sr.layout
        brg = lay.bearing
        Dd, dd = brg.D * MM, brg.d * MM
        bodies = _bearing_bodies(lay)
        # 轴（外形）
        prev = None
        for seg in lay.segments:
            a, bb = seg.z0 * MM, seg.z1 * MM
            if seg.role == "齿轮轴":
                g = next(g for g in lay.gears if g.integral)
                pair = pairs[g.pair]
                ra, rf, rp = g.tip_d * MM / 2, g.root_d * MM / 2, pair.d1 * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * ra), (bb, x + sgn * ra))
                    v.line((a, x + sgn * rf), (bb, x + sgn * rf), "细实线")
                    v.line((a - 2, x + sgn * rp), (bb + 2, x + sgn * rp), "点画线")
                r = ra
            else:
                r = seg.d * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * r), (bb, x + sgn * r))
            if prev is not None:
                rr = max(prev, r)
                v.line((a, x - rr), (a, x + rr))
            prev = r
        v.line((lay.segments[-1].z1 * MM, x - prev), (lay.segments[-1].z1 * MM, x + prev))
        v.line((lay.segments[0].z0 * MM, x - lay.segments[0].d * MM / 2), (lay.segments[0].z0 * MM, x + lay.segments[0].d * MM / 2))
        v.centerline((lay.segments[0].z0 * MM, x), (lay.segments[-1].z1 * MM, x), 5)
        ig = next((g for g in lay.gears if g.integral), None)
        shaft_name = lay.name.split("（")[0] + ("（齿轮轴）" if ig else "")
        mat = material_name(pairs[ig.pair].inp.material1) if ig else "45"
        first = lay.segments[0]
        tadd(shaft_name, "1", mat, "", (first.z0 * MM + 5, x))

        # 轴承：深沟球轴承一侧规定画法、一侧通用画法
        ball = not isinstance(brg, standards.TaperedBearing)
        for zc, B in bodies:
            draw_bearing(v, zc, B, x, dd, Dd, next_angle(), ball)
        tadd(*_bearing_name(brg)[:1], "2", "", _bearing_name(brg)[1], (bodies[1][0], x + (dd + Dd) / 4))

        # 轴承盖（凸缘式）、调整垫片、毡圈
        r_cap = cap.D2 * MM / 2
        for side, zb_face in (("left", -L1), ("right", W + L1)):
            is_open = lay.extension == side
            sgn_z = -1 if side == "left" else 1
            za, zb = sorted((zb_face, zb_face + sgn_z * e))
            seal_r = (lay.diameters["密封"] or dd) * MM / 2 + 1 if is_open else 0
            # 凸缘 + 伸入轴承座孔、顶住轴承外圈的止口，作为一个零件剖开
            bz, B = bodies[0 if side == "left" else 1]
            face = bz - B / 2 if side == "left" else bz + B / 2
            cap_section(v, zb_face + sgn_z * e, zb_face, face, x, r_cap, Dd / 2, seal_r, next_angle())
            if is_open:
                # 毡圈：嵌在透盖的梯形槽内（简化为矩形，交叉细线表示）
                sd = lay.diameters["密封"] * MM
                fz0, fz1 = za + e * 0.25, zb - e * 0.25
                for sgn in (1, -1):
                    v.rect(fz0, x + sgn * sd / 2, fz1, x + sgn * (sd / 2 + 5), "细实线")
                    v.line((fz0, x + sgn * sd / 2), (fz1, x + sgn * (sd / 2 + 5)), "细实线")
                tadd(f"毡圈 {sd:g}", "1", "半粗羊毛毡", "JB/ZQ 4606-1997", ((fz0 + fz1) / 2, x - sd / 2 - 2.5))
            tadd("轴承透盖" if is_open else "轴承闷盖", "", "HT200", "", ((za + zb) / 2, x + (seal_r + r_cap) / 2 + 2))
            if side == "right" and sr is d.shafts[1]:
                tadd("调整垫片", "6组", "08F", "", (zb_face, x - r_cap + 3))

        # 齿轮（剖开）与套筒
        for gg in lay.gears:
            pair = pairs[gg.pair]
            if gg.integral:
                continue
            if gg.pair == "bevel":
                _top_bevel_gear(d, v, gg, x, next_angle(), tadd)
                s0, s1 = bodies[0][0] + bodies[0][1] / 2, gg.z * MM - gg.width * MM / 2
                sleeve = _top_sleeve(v, lay, x, s0, s1, next_angle)
                if sleeve:
                    sleeves += 1
                    sleeve_at = sleeve_at or sleeve
                continue
            gb = blank(pair, gg.member, gg.seat_d)
            zc = gg.z * MM
            bw = gb.b * MM
            rb_, rf, ra, rp = gb.bore * MM / 2, gb.df * MM / 2, gb.da * MM / 2, gb.d * MM / 2
            ang = next_angle()
            for sgn in (1, -1):
                if gb.web:
                    rh, r2, c = gb.hub_d * MM / 2, gb.rim_inner_d * MM / 2, gb.web_thickness * MM / 2
                    loop = [(-bw / 2, rb_), (bw / 2, rb_), (bw / 2, rh), (c, rh), (c, r2), (bw / 2, r2), (bw / 2, rf),
                            (-bw / 2, rf), (-bw / 2, r2), (-c, r2), (-c, rh), (-bw / 2, rh)]
                else:
                    loop = [(-bw / 2, rb_), (bw / 2, rb_), (bw / 2, rf), (-bw / 2, rf)]
                pts = [(zc + px, x + sgn * py) for px, py in loop]
                v.poly(pts, close=True)
                v.hatch([pts], ang, 2.5)
                # 轮齿：大齿轮朝向啮合小齿轮一侧的齿顶线被遮住，画虚线
                mate_dir = 0
                if gg.member == 2:
                    mate_x = xs[zsh.index(sr) - 1]
                    mate_dir = 1 if mate_x > x else -1
                hid = gg.member == 2 and sgn == mate_dir
                v.line((zc - bw / 2, x + sgn * rf), (zc - bw / 2, x + sgn * ra))
                v.line((zc + bw / 2, x + sgn * rf), (zc + bw / 2, x + sgn * ra))
                v.line((zc - bw / 2, x + sgn * ra), (zc + bw / 2, x + sgn * ra), "虚线" if hid else "粗实线")
                v.line((zc - bw / 2 - 2, x + sgn * rp), (zc + bw / 2 + 2, x + sgn * rp), "点画线")
            label = f"{pair.inp.name}{'小' if gg.member == 1 else '大'}齿轮"
            gm = material_name(pair.inp.material1 if gg.member == 1 else pair.inp.material2)
            z = pair.z1 if gg.member == 1 else pair.z2
            tadd(label, "1", gm, f"mn={pair.mn * MM:g}，z={z}", (zc, x + (rf + rb_) / 2))
            # 套筒：齿轮装入一侧与轴承之间
            if gg.mount == "left":
                s0, s1 = bodies[0][0] + bodies[0][1] / 2, zc - bw / 2
            else:
                s0, s1 = zc + bw / 2, bodies[1][0] - bodies[1][1] / 2
            sleeve = _top_sleeve(v, lay, x, s0, s1, next_angle)
            if sleeve:
                sleeves += 1
                sleeve_at = sleeve_at or sleeve
        for k in sr.keys:
            name = f"键 {k.size.b * MM:g}×{k.length * MM:g}"
            key_count[name] = key_count.get(name, 0) + k.count
        for seg in lay.segments:
            if seg.keyway:
                kb, _, kl = (v_ * MM for v_ in seg.keyway)
                key_at.setdefault(f"键 {kb:g}×{kl:g}", ((seg.z0 + seg.z1) / 2 * MM + kl / 4, x))

        # 联轴器或大带轮的轮毂（相邻零件，细实线画外形）
        if lay.extension:
            end = next(sg for sg in lay.segments if sg.role == "端部")
            a, bb = end.z0 * MM, end.z1 * MM
            rh = end.d * MM
            for sgn in (1, -1):
                v.line((a, x + sgn * rh), (bb, x + sgn * rh), "细实线")
            v.line((a, x - rh), (a, x + rh), "细实线")
            v.line((bb, x - rh), (bb, x + rh), "细实线")

    if getattr(d, "bevel", None) is not None:
        _top_pinion_shaft(d, t, v, sh, tadd, next_angle, key_count, key_at)
    if sleeve_at:
        tadd("套筒", str(sleeves), "Q235", "", sleeve_at)
    for name, n in key_count.items():
        tadd(name, str(n), "45", "GB/T 1096-2003", key_at.get(name, (0, 0)))
    n_open = sum(1 for s in zsh if s.layout.extension)
    by_count = {"轴承透盖": n_open, "轴承闷盖": 2 * len(zsh) - n_open}
    return by_count


def _top_sleeve(v: View, lay, x: float, s0: float, s1: float, next_angle):
    """齿轮与轴承之间的套筒（mm），返回序号引线目标点。"""
    if s1 - s0 <= 1:
        return None
    sd_in = lay.diameters["轴承"] * MM / 2
    sd_out = sd_in + max(0.08 * sd_in * 2, 4)
    ang = next_angle()
    for sgn in (1, -1):
        pts = [(s0, x + sgn * sd_in), (s1, x + sgn * sd_in), (s1, x + sgn * sd_out), (s0, x + sgn * sd_out)]
        v.poly(pts, close=True)
        v.hatch([pts], ang, 1.5)
    return ((s0 + s1) / 2, x + (sd_in + sd_out) / 2)


def _bevel_section(v: View, g, P, ang: float, integral: bool = False):
    """锥齿轮通过轴线剖切：轮体画剖面线，轮齿不剖（齿顶线、齿根线粗实线，分度线点画线）。

    g 为 `bevel_blank.BevelBlank`，P(t, r) 把齿轮坐标（m）换算到视图模型坐标（mm）。"""
    prof = g.profile()
    for sgn in (1, -1):
        f = lambda p: P(p[0], sgn * p[1])  # noqa: E731
        tooth = [g.root_small, g.tip_small, g.tip_large, g.root_large]
        v.poly([f(p) for p in tooth])
        if not integral:
            body = [f(p) for p in prof[2:]]
            v.poly(body, close=True)
            v.hatch([body], ang, 2.5)
        else:
            v.line(f(g.root_small), f(g.root_large))
        c, sn = math.cos(g.delta), math.sin(g.delta)
        r0, r1 = g.R - g.b - 0.002, g.R + 0.002
        v.line(f((r0 * c, r0 * sn)), f((r1 * c, r1 * sn)), "点画线")


def _top_bevel_gear(d, v: View, gg, x: float, ang: float, tadd):
    """俯视图中Ⅱ轴上的大锥齿轮（大端朝 −z，锥顶在 z_apex）。"""
    from gongke_core.layout.bevel_blank import blank as bevel_blank

    g = bevel_blank(d.bevel, 2, gg.seat_d, d.positions.hub)
    za = d.positions.z_apex
    _bevel_section(v, g, lambda t_, r_: ((za - t_) * MM, x + r_ * MM), ang)
    rp = (g.root_large[1] + g.bore / 2) / 2 * MM
    tadd("大锥齿轮", "1", material_name(d.bevel.inp.material2), f"m={d.bevel.m * MM:g}，z={d.bevel.z2}",
         ((za - g.t_back) * MM + 3, x + rp))


def _top_pinion_shaft(d, t: HousingDetail, v: View, sh: Sheet, tadd, next_angle, key_count, key_at):
    """俯视图中的Ⅰ轴（沿 −x，轴线在剖分面上 z = z_apex）：轴、小锥齿轮、反装的圆锥滚子轴承、套杯、透盖、
    轴承座和联轴器。模型坐标 (z, x)，Ⅰ轴上一点 (u, r) 对应 (z_apex + r, −u)。"""
    from gongke_core.layout.bevel_blank import blank as bevel_blank
    from gongke_core.layout.bevel_reducer import cup

    ps, h = d.pinion, d.housing
    za = d.positions.z_apex * MM
    U = lambda u, r: (za + r, -u)  # noqa: E731  u、r 单位 mm
    Um = lambda u, r: U(u * MM, r * MM)  # noqa: E731  u、r 单位 m
    segs = ps.segments
    # 轴（外形）
    prev = None
    for seg in segs:
        a, bb = seg.z0 * MM, seg.z1 * MM
        if seg.role == "齿轮轴":
            r = None
        else:
            r = seg.d * MM / 2
            for sgn in (1, -1):
                v.line(U(a, sgn * r), U(bb, sgn * r))
        if prev is not None and r is not None:
            rr = max(prev, r)
            v.line(U(a, -rr), U(a, rr))
        prev = r
    v.line(U(segs[-1].z1 * MM, -prev), U(segs[-1].z1 * MM, prev))
    if segs[0].role != "齿轮轴":
        r0 = segs[0].d * MM / 2
        v.line(U(segs[0].z0 * MM, -r0), U(segs[0].z0 * MM, r0))
    v.centerline(U(segs[0].z0 * MM - 3, 0), U(segs[-1].z1 * MM, 0), 5)
    # 小锥齿轮
    g = bevel_blank(d.bevel, 1, ps.seat_d or ps.diameters["齿轮"], ps.pinion_length)
    _bevel_section(v, g, Um, next_angle(), ps.integral)
    if ps.integral:
        rh = g.hub_r
        for sgn in (1, -1):
            v.poly([Um(*g.root_large), Um(*g.back_point), Um(g.back_point[0], rh), Um(g.hub_span[1], rh)]
                   if sgn > 0 else [Um(g.root_large[0], -g.root_large[1]), Um(g.back_point[0], -g.back_point[1]),
                                    Um(g.back_point[0], -rh), Um(g.hub_span[1], -rh)])
        v.line(Um(g.root_small[0], -g.root_small[1]), Um(g.root_small[0], g.root_small[1]))
        tadd("Ⅰ轴（齿轮轴）", "1", material_name(d.bevel.inp.material1), "", U(segs[-1].z1 * MM - 5, 0))
    else:
        tadd("Ⅰ轴", "1", "45", "", U(segs[-1].z1 * MM - 5, 0))
        rp = (g.root_large[1] + g.bore / 2) / 2
        tadd("小锥齿轮", "1", material_name(d.bevel.inp.material1), f"m={d.bevel.m * MM:g}，z={d.bevel.z1}",
             Um((g.t_front + g.back_point[0]) / 2, -rp))
    # 轴承（反装）
    brg = ps.bearing
    Dd, dd = brg.D * MM, brg.d * MM
    off = brg.a - brg.T / 2
    bodies = [((u - b * off) * MM, brg.T * MM) for u, b in zip(ps.bearing_u, (-1, +1))]
    for uc, B in bodies:
        for sgn in (1, -1):
            r_in, r_out = sgn * dd / 2, sgn * Dd / 2
            v.poly([U(uc - B / 2, r_in), U(uc + B / 2, r_in), U(uc + B / 2, r_out), U(uc - B / 2, r_out)], close=True)
            rm = (r_in + r_out) / 2
            v.line(U(uc - B * 0.3, rm), U(uc + B * 0.3, rm), "细实线")
            v.line(U(uc, rm - abs(r_out - r_in) * 0.3), U(uc, rm + abs(r_out - r_in) * 0.3), "细实线")
    name, std = _bearing_name(brg)
    tadd(name, "2", "", std, U(bodies[0][0], -(dd + Dd) / 4))
    # 套杯（剖开）
    c = cup(ps)
    ro, ri, rr, rf = (c.D_out * MM / 2, c.D * MM / 2, c.rib_d * MM / 2, c.flange_D * MM / 2)
    u0, uf, ft = c.u0 * MM, c.u_flange * MM, c.flange_t * MM
    k0, k1 = c.rib[0] * MM, c.rib[1] * MM
    ang = next_angle()
    for sgn in (1, -1):
        loop = [U(u0, sgn * ri), U(k0, sgn * ri), U(k0, sgn * rr), U(k1, sgn * rr), U(k1, sgn * ri),
                U(uf + ft, sgn * ri), U(uf + ft, sgn * rf), U(uf, sgn * rf), U(uf, sgn * ro), U(u0, sgn * ro)]
        v.poly(loop, close=True)
        v.hatch([loop], ang, 2.0)
    tadd("套杯", "1", "HT150", "", U((u0 + k0) / 2, (ri + ro) / 2))
    # 套杯凸缘与轴承座之间的调整垫片
    for sgn in (1, -1):
        v.line(U(uf - 1, sgn * ro), U(uf - 1, sgn * rf), "细实线")
    tadd("调整垫片", "2组", "08F", "", U(uf - 1, -(ro + rf) / 2))
    # 透盖（剖开）与毡圈
    e = h.cap_thickness * MM
    seal_d = ps.diameters["密封"] * MM
    ua, ub = uf + ft, uf + ft + e
    ang = next_angle()
    for sgn in (1, -1):
        loop = [U(ua, sgn * (seal_d / 2 + 1)), U(ub, sgn * (seal_d / 2 + 1)), U(ub, sgn * rf), U(ua, sgn * rf)]
        v.poly(loop, close=True)
        v.hatch([loop], ang, 2.0)
        fz0, fz1 = ua + e * 0.25, ub - e * 0.25
        v.poly([U(fz0, sgn * seal_d / 2), U(fz1, sgn * seal_d / 2), U(fz1, sgn * (seal_d / 2 + 5)),
                U(fz0, sgn * (seal_d / 2 + 5))], "细实线", close=True)
        v.line(U(fz0, sgn * seal_d / 2), U(fz1, sgn * (seal_d / 2 + 5)), "细实线")
    tadd("轴承透盖", "", "HT200", "", U((ua + ub) / 2, (seal_d / 2 + rf) / 2 + 2))
    tadd(f"毡圈 {seal_d:g}", "1", "半粗羊毛毡", "JB/ZQ 4606-1997", U((ua + ub) / 2, -seal_d / 2 - 2.5))
    # 轴承座（左端壁凸台）与座孔
    sb = t.side_bore
    xo0 = t.x_outer[0] * MM
    br = sb.boss_r * MM
    for sgn in (1, -1):
        v.line(U(-sb.x_face * MM, sgn * br), U(-xo0, sgn * br))
        v.line(U(-sb.x_face * MM, sgn * ro), U(-h.x_range[0] * MM, sgn * ro))
    v.line(U(-sb.x_face * MM, -br), U(-sb.x_face * MM, br))
    # 联轴器轮毂（相邻零件，细实线）
    end = next(sg for sg in segs if sg.role == "端部")
    a, bb = end.z0 * MM, end.z1 * MM
    rh = end.d * MM
    for sgn in (1, -1):
        v.line(U(a, sgn * rh), U(bb, sgn * rh), "细实线")
    v.line(U(a, -rh), U(a, rh), "细实线")
    v.line(U(bb, -rh), U(bb, rh), "细实线")
    # 键
    for k in d.shafts[0].keys:
        name = f"键 {k.size.b * MM:g}×{k.length * MM:g}"
        key_count[name] = key_count.get(name, 0) + k.count
    for seg in segs:
        if seg.keyway:
            kb, _, kl = (v_ * MM for v_ in seg.keyway)
            key_at.setdefault(f"键 {kb:g}×{kl:g}", U((seg.z0 + seg.z1) / 2 * MM - kl / 4, 0))


def boss_spans(t: HousingDetail) -> list[tuple[float, float]]:
    """轴承座凸台（x ± rb）与轴承旁凸台的 x 区间合并后的结果，mm。"""
    spans = sorted([((x - r) * MM, (x + r) * MM) for x, r in zip(t.shaft_x, t.boss_r)]
                   + [(a * MM, b * MM) for a, b in t.side_bosses])
    out: list[list[float]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def b_total(h) -> float:
    return (h.flange_base + h.flange_cover) * MM


# ====================================================================== 主视图

def _front_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet, add):
    h = d.housing
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    zsh = _zshafts(d)
    xs = [s.layout.x * MM for s in zsh]
    xo0, xo1 = (val * MM for val in t.x_outer)
    yb = t.y_bottom * MM
    b2 = h.flange_foot * MM
    mid_x = (xo0 + xo1) / 2

    def fadd(name, qty, mat, note, at):
        if at[1] > b1 + 2:
            g = "FT"
        else:
            g = "FL" if at[0] < mid_x else "FR"
        add(name, qty, mat, note, v.P(*at), g)

    caps = [(x, 0.0, c.D2 * MM / 2) for x, c in zip(xs, t.caps)]
    bosses = [(x, 0.0, r * MM) for x, r in zip(xs, t.boss_r)]
    occ = caps + bosses
    hb = t.boss_h * MM
    blocks = [(a * MM, -hb, b_ * MM, hb) for a, b_ in t.side_bosses]  # 轴承旁凸台（箱座 + 箱盖），与轴承座端面平齐

    def seg(p, q, layer="粗实线", circles=None, rects=None):
        for a, bb in hidden.visible_segments(p, q, occ if circles is None else circles, blocks if rects is None else rects):
            v.line(a, bb, layer)

    def arc(cx, cy, r, a0, a1, layer="粗实线", circles=None, rects=None):
        for a, bb in hidden.visible_arcs(cx, cy, r, a0, a1, occ if circles is None else circles,
                                         blocks if rects is None else rects):
            v.arc((cx, cy), r, a, bb, layer)

    def rect(x0, y0, x1, y1, layer="粗实线"):
        for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            seg(p, q, layer)

    # ---------------- 轴承盖（最前面）
    for k, (sr, x, cap) in enumerate(zip(zsh, xs, t.caps)):
        r2 = cap.D2 * MM / 2
        v.circle((x, 0), r2)
        r0 = cap.D0 * MM / 2
        d3 = cap.d3 * MM
        for j in range(cap.n):
            a = math.radians(45 + 360 * j / cap.n if cap.n == 4 else 30 + 360 * j / cap.n)
            c = (x + r0 * math.cos(a), r0 * math.sin(a))
            v.circle(c, 0.85 * d3)
            v.circle(c, 0.5 * d3, "细实线")
        v.centerline((x - r2, 0), (x + r2, 0), 3)
        v.centerline((x, -r2), (x, r2), 3)
        lay = sr.layout
        if lay.extension == "right":  # 伸出端朝向观察者：画轴端和联轴器
            end = next(sg for sg in lay.segments if sg.role == "端部")
            v.circle((x, 0), end.d * MM / 2)
            v.circle((x, 0), end.d * MM, "细实线")
        tag = "轴承透盖" if lay.extension == "right" else "轴承闷盖"
        fadd(tag, "", "HT200", "", (x + r2 * 0.75, -r2 * 0.55))
        fadd(f"螺钉 M{d3:g}×{_std(h.cap_thickness * MM + 1.5 * d3, SCREW_L)}", "", "Q235", "GB/T 5783-2016",
             (x + r0 * math.cos(math.radians(-45 if cap.n == 4 else -30)) * 1.0,
              r0 * math.sin(math.radians(-45 if cap.n == 4 else -30))))
    # ---------------- 轴承座（被轴承盖挡住一部分）与轴承旁凸台（端面平齐，只画合成外形）
    for x, rb in zip(xs, t.boss_r):
        arc(x, 0, rb * MM, 0, 360, circles=caps)
    for x0_, y0_, x1_, y1_ in blocks:
        for p, q in (((x0_, y0_), (x1_, y0_)), ((x1_, y0_), (x1_, y1_)), ((x1_, y1_), (x0_, y1_)), ((x0_, y1_), (x0_, y0_))):
            seg(p, q, rects=[])
        seg((x0_, 0), (x1_, 0), circles=caps, rects=[])  # 剖分面
    # 右端壁下部的局部剖视（过中间平面 z = W/2，剖出放油螺塞和油标）范围：x ≥ xw0，y ≤ y_sec
    xi1 = h.x_range[1] * MM
    xw0 = xi1 - 2 * h.delta * MM
    (_, dip_y), _ = t.dipstick
    y_sec = dip_y * MM + 11 * math.sqrt(2) + 3
    # 箱座侧壁外的加强肋（轴承座正下方）
    m = t.rib_t * MM
    for x, rb in zip(xs, t.boss_r):
        y_top = -math.sqrt((rb * MM) ** 2 - (m / 2) ** 2)
        for sx in (-1, 1):
            xr = x + sx * m / 2
            seg((xr, y_top), (xr, yb + b2 if xr < xw0 else max(y_sec, yb + b2)))

    # ---------------- 凸缘、箱壁、底座
    rect(xo0 - fw, -b, xo1 + fw, 0)
    rect(xo0 - fw, 0, xo1 + fw, b1)
    seg((xo0, yb + b2), (xo0, -b))
    seg((xo1, y_sec), (xo1, -b))
    seg((xo0 - fw, yb), (xw0, yb))
    seg((xo0 - fw, yb + b2), (xw0, yb + b2))
    seg((xo0 - fw, yb), (xo0 - fw, yb + b2))
    # 箱盖外形：凸缘以上部分
    for e in t.cover_outer:
        if isinstance(e, Arc):
            r = e.r * MM
            cut = math.degrees(math.asin(min(b1 / r, 1.0)))
            a0, a1 = max(e.a0, cut), min(e.a1, 180 - cut)
            if a1 > a0:
                arc(e.cx * MM, 0, r, a0, a1)
        else:
            p_, q_ = (e.p[0] * MM, e.p[1] * MM), (e.q[0] * MM, e.q[1] * MM)
            gap = _inspection_gap(t, p_, q_)
            if gap:
                seg(p_, gap[0])
                seg(gap[1], q_)
            else:
                seg(p_, q_)
    xc = (xs[-2] + t.caps[-2].D2 * MM / 2 + xs[-1] - t.caps[-1].D2 * MM / 2) / 2
    fadd("箱盖", "1", "HT200", "", (xc, 0.55 * envelope_height(t.cover_outer, xc / MM) * MM))

    if t.side_bore is not None:
        _front_pinion_side(d, t, v, fadd)

    # ---------------- 吊钩（箱座两端铸出，在中间平面上；前侧凸缘下的螺母、垫圈在它前面）
    dn = h.bolt_flange * MM
    nuts = blocks + [(xb * MM - dn, -b - 1.05 * dn, xb * MM + dn, -b) for xb in t.flange_bolts]
    for xe in t.hooks:
        pts, (hx, hy), hr = t.hook_shape(xe)
        pts = [(px * MM, py * MM) for px, py in pts]
        for p, q in zip(pts, pts[1:]):
            seg(p, q, rects=nuts)
        arc(hx * MM, hy * MM, hr * MM, 0, 360, rects=nuts)

    # ---------------- 连接螺栓（前侧凸缘一排）、起盖螺钉
    def bolt(x, dd, length, head_only=False, top=b1, bot=b):  # 螺栓头支承面 y = top，螺母支承面 y = −bot
        seg((x, top + 0.7 * dd + 3), (x, top - length - 3), "点画线")
        rect(x - dd, top, x + dd, top + 0.7 * dd)
        seg((x - dd / 2, top), (x - dd / 2, top + 0.7 * dd), "粗实线")
        seg((x + dd / 2, top), (x + dd / 2, top + 0.7 * dd), "粗实线")
        if head_only:
            return
        yw = -bot - 0.25 * dd
        rect(x - 0.75 * dd, yw, x + 0.75 * dd, -bot)
        yn = yw - 0.8 * dd
        rect(x - dd, yn, x + dd, yw)
        seg((x - dd / 2, yn), (x - dd / 2, yw))
        seg((x + dd / 2, yn), (x + dd / 2, yw))
        y_end = top - length
        if y_end < yn:
            rect(x - dd / 2, y_end, x + dd / 2, yn)

    d1, d2 = h.bolt_bearing * MM, h.bolt_flange * MM
    L1b, L2b = t.bolt_length_d1 * MM, t.bolt_length_d2 * MM
    for xb in t.bearing_bolts:
        bolt(xb * MM, d1, L1b, top=hb, bot=hb)
    for xb in t.flange_bolts:
        bolt(xb * MM, d2, L2b)
    xj = t.jack_screw[0] * MM
    lj = _std(b1 + d2, SCREW_L)
    bolt(xj, d2, lj, head_only=True)
    n1 = 2 * len(t.bearing_bolts)
    n2 = 2 * len(t.flange_bolts)
    xb1 = t.bearing_bolts[0] * MM
    fadd(f"螺栓 M{d1:g}×{L1b:g}", n1, "Q235", "GB/T 5782-2016", (xb1 - d1 * 0.6, hb + 0.35 * d1))
    fadd(f"螺母 M{d1:g}", n1, "Q235", "GB/T 6170-2015", (xb1 - d1 * 0.6, -hb - 0.65 * d1))
    fadd(f"弹簧垫圈 {d1:g}", n1, "65Mn", "GB/T 93-1987", (xb1 + d1 * 0.5, -hb - 0.12 * d1))
    if t.flange_bolts:
        xb2 = t.flange_bolts[-1] * MM
        fadd(f"螺栓 M{d2:g}×{L2b:g}", n2, "Q235", "GB/T 5782-2016", (xb2 + d2 * 0.6, b1 + 0.35 * d2))
        fadd(f"螺母 M{d2:g}", n2, "Q235", "GB/T 6170-2015", (xb2 + d2 * 0.6, -b - 0.65 * d2))
        fadd(f"弹簧垫圈 {d2:g}", n2, "65Mn", "GB/T 93-1987", (xb2 - d2 * 0.5, -b - 0.12 * d2))
    fadd(f"起盖螺钉 M{d2:g}×{lj}", 1, "Q235", "GB/T 5783-2016", (xj, b1 + 0.35 * d2))
    # 选一个两侧最空的连接螺栓，作局部剖视表示箱盖、箱座凸缘和螺栓连接
    half = 2.4 * d2
    keep = [(x, r) for x, _, r in caps] + [((a_ + b_) / 2, (b_ - a_) / 2) for a_, _, b_, _ in blocks] + [(xj, d2)]
    best = max(t.flange_bolts, key=lambda xb: min(abs(xb * MM - x) - r for x, r in keep), default=None)
    if best is not None and min(abs(best * MM - x) - r for x, r in keep) > half:
        _bolt_section(v, best * MM, d2, b, b1, half, (xo0 - fw, xo1 + fw))

    # ---------------- 视孔盖、通气器（视孔处局部剖视）
    _inspection_section(t, v, fadd)

    # ---------------- 吊环螺钉
    ed = t.eyebolt_d * MM
    for k, xe in enumerate(t.eyebolts):
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        v.rect(xe - 1.1 * ed, ye - 2, xe + 1.1 * ed, ye + 0.4 * ed)  # 凸台
        v.rect(xe - 0.9 * ed, ye + 0.4 * ed, xe + 0.9 * ed, ye + 0.9 * ed)  # 台肩
        rc = ye + 0.9 * ed + 1.6 * ed
        v.circle((xe, rc), 1.6 * ed)
        v.circle((xe, rc), 0.8 * ed)
        v.line((xe, ye - 4), (xe, rc + 1.6 * ed + 3), "点画线")
        if k == 0:
            fadd(f"吊环螺钉 M{ed:g}", len(t.eyebolts), "20", "GB/T 825-1988", (xe - 1.2 * ed, rc))

    # ---------------- 右端壁局部剖视：油标（杆式，45° 斜插）、放油螺塞
    _drain_dipstick_section(t, v, fadd, xw0, y_sec)


def _bolt_section(v: View, xb: float, dd: float, b: float, b1: float, half: float, lim: tuple[float, float]):
    """连接螺栓处的局部剖视：箱盖、箱座凸缘剖开（剖面线方向相反），螺栓按不剖画出穿过通孔的杆部。
    lim 为凸缘两端，剖视范围到凸缘端面为止（端面处不画波浪线）。"""
    r0 = CLEARANCE.get(round(dd), 1.1 * dd) / 2
    xl, xr = max(xb - half, lim[0]), min(xb + half, lim[1])
    cover = [[(xl, 0), (xb - r0, 0), (xb - r0, b1), (xl, b1)], [(xb + r0, 0), (xr, 0), (xr, b1), (xb + r0, b1)]]
    base = [[(xl, -b), (xb - r0, -b), (xb - r0, 0), (xl, 0)], [(xb + r0, -b), (xr, -b), (xr, 0), (xb + r0, 0)]]
    for lp in cover + base:
        v.poly(lp, close=True)
    v.hatch(cover, 135)
    v.hatch(base, 45)
    for x in (xb - dd / 2, xb + dd / 2):
        v.line((x, -b), (x, b1))
    for x in (xl, xr):
        if lim[0] < x < lim[1]:
            v.wavy((x, -b), (x, b1))


def _inspection_gap(t: HousingDetail, p, q):
    """箱盖外形线 p–q 若是视孔所在的那段公切线，返回视孔两端（局部剖视里那段外形线断开）。"""
    ins = t.inspection
    if ins.pad > 0:
        return None
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    L = math.dist(p, q)
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    s0 = (cx - p[0]) * ux + (cy - p[1]) * uy
    if abs((cx - p[0]) * uy - (cy - p[1]) * ux) > 0.5 or not 0 < s0 < L:
        return None
    hl = ins.hole_length * MM / 2
    return (p[0] + ux * (s0 - hl), p[1] + uy * (s0 - hl)), (p[0] + ux * (s0 + hl), p[1] + uy * (s0 + hl))


def _inspection_section(t: HousingDetail, v: View, fadd):
    """视孔处的局部剖视（剖切面 z = W/2）：箱盖壁、视孔盖、垫片剖开，螺钉和通气器按不剖画外形。
    视孔盖在圆弧顶部的平台上时（蜗杆减速器，主视图另有画法）只画外形。"""
    h = t.h
    ins = t.inspection
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    a = math.radians(ins.angle)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    L, th = ins.length * MM, ins.thickness * MM
    hl = ins.hole_length * MM / 2
    g = 1.5  # 垫片厚
    d1 = h.delta1 * MM
    sd, vd = ins.screw_d * MM, ins.vent_d * MM
    P = lambda s_, n_: (cx + ux * s_ + nx * n_, cy + uy * s_ + ny * n_)  # noqa: E731
    rect = lambda s0, n0, s1, n1: [P(s0, n0), P(s1, n0), P(s1, n1), P(s0, n1)]  # noqa: E731
    screws = (-L / 2 + 10, L / 2 - 10)
    rs = sd / 2  # 螺钉大径（箱盖上的螺孔按旋合画到大径）
    rc = rs + 0.6  # 盖板上的通孔
    t0, t1 = g, g + th  # 盖板上下表面
    section = ins.pad == 0
    if section:
        Ls = L / 2 + 12
        wall, plate = [], []
        for (s0, s1) in ((-Ls, screws[0] - rs), (screws[0] + rs, -hl), (hl, screws[1] - rs), (screws[1] + rs, Ls)):
            wall.append(rect(s0, -d1, s1, 0))
        cuts = [(-L / 2, screws[0] - rc), (screws[0] + rc, -vd / 2), (vd / 2, screws[1] - rc), (screws[1] + rc, L / 2)]
        for s0, s1 in cuts:
            plate.append(rect(s0, t0, s1, t1))
        # 垫片只在视孔四周（视孔范围内没有），按螺钉孔分段
        gasket = [rect(-L / 2, 0, screws[0] - rc, g), rect(screws[0] + rc, 0, -hl, g),
                  rect(hl, 0, screws[1] - rc, g), rect(screws[1] + rc, 0, L / 2, g)]
        for lp in wall + plate + gasket:
            v.poly(lp, close=True)
        v.hatch(wall, 45)
        v.hatch(plate, 135, 2.0)
        v.hatch(gasket, 45, 0.5)
        for s_ in (-Ls, Ls):
            v.wavy(P(s_, -d1), P(s_, 0))
    else:
        v.poly(rect(-L / 2, t0, L / 2, t1), close=True)
        v.poly(rect(-L / 2, 0, L / 2, g), close=True)
    # 螺钉（不剖）：头部、穿过盖板和垫片旋入箱盖的杆部
    for s_ in screws:
        v.poly(rect(s_ - 0.85 * sd, t1, s_ + 0.85 * sd, t1 + 0.7 * sd), close=True)
        if section:
            n_end = t1 - 16
            v.poly(rect(s_ - rs, n_end, s_ + rs, t1), close=True)
            for k in (-1, 1):
                v.line(P(s_ + k * 0.85 * rs, n_end), P(s_ + k * 0.85 * rs, 0), "细实线")
        v.line(P(s_, -d1 - 2 if section else t1 - 2), P(s_, t1 + 0.7 * sd + 2), "点画线")
    # 通气器（不剖）：旋在盖板上
    stack = [(0.6 * vd, t1, t1 + 0.5 * vd), (0.9 * vd, t1 + 0.5 * vd, t1 + 0.9 * vd), (0.45 * vd, t1 + 0.9 * vd, t1 + 1.4 * vd)]
    if section:
        stack.insert(0, (vd / 2, t0 - 2, t1))
    for hw, n0, n1_ in stack:
        v.poly(rect(-hw, n0, hw, n1_), close=True)
    v.line(P(0, -3), P(0, t1 + 1.4 * vd + 3), "点画线")
    fadd("视孔盖", "1", "Q235", "", P(-L / 2 + 22, (t0 + t1) / 2))
    fadd("视孔盖垫片", "1", "石棉橡胶纸", "", P(-L / 2 + 30, g / 2))
    fadd(f"螺钉 M{sd:g}×16", "4", "Q235", "GB/T 5783-2016", P(L / 2 - 10, t1 + 0.35 * sd))
    fadd(f"通气器 M{vd:g}×1.5", "1", "Q235", "", P(0.3 * vd, t1 + 1.15 * vd))


def _drain_dipstick_section(t: HousingDetail, v: View, fadd, xw0: float, y_sec: float):
    """主视图右下角的局部剖视（剖切面为中间平面 z = W/2，波浪线为界）：右端壁、箱底和油标座剖开，
    螺塞、油标按不剖画外形；剖切面正好通过底座凸缘的缺口，凸缘只剩缺口侧面的外形。"""
    h = t.h
    fw = t.flange_w * MM
    b2 = h.flange_foot * MM
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    xo1 = t.x_outer[1] * MM
    xi1 = h.x_range[1] * MM
    (ox_, oy_), ang = t.dipstick
    ox_, oy_ = ox_ * MM, oy_ * MM
    a = math.radians(ang)
    c, sn = math.cos(a), math.sin(a)
    dy, ddr = t.drain[1] * MM, t.drain_d * MM
    rd = ddr / 2  # 螺塞大径（旋合部分按外螺纹画，箱体剖面线画到大径）
    ri = 6.0  # 油标 M12 大径
    r_dip = 11.0  # 油标座半径
    boss_s = 14.0

    def P(s_, n_):  # 油标局部坐标：s 沿孔轴向外，n 垂直于孔轴
        return (ox_ + c * s_ - sn * n_, oy_ + sn * s_ + c * n_)

    def s_at_x(x, n_):
        return (x - ox_ + sn * n_) / c

    # 箱体剖面
    p1 = [(xw0, yb), (xo1, yb), (xo1, dy - rd), (xi1, dy - rd), (xi1, y_floor), (xw0, y_floor)]
    p2 = [(xi1, dy + rd), (xo1, dy + rd), P(s_at_x(xo1, -r_dip), -r_dip), P(boss_s, -r_dip), P(boss_s, -ri),
          P(s_at_x(xi1, -ri), -ri)]
    p3 = [P(s_at_x(xi1, ri), ri), P(boss_s, ri), P(boss_s, r_dip), P(s_at_x(xo1, r_dip), r_dip),
          (xo1, y_sec), (xi1, y_sec)]
    for lp in (p1, p2, p3):
        v.poly(lp, close=True)
    v.hatch([p1, p2, p3], 135)  # 与 45° 油标孔垂直，剖面线不与孔壁平行
    v.wavy((xw0, yb), (xw0, max(y_floor, yb + b2)))
    v.wavy((xi1, y_sec), (xo1, y_sec))
    # 底座凸缘缺口的侧面（在剖切面后方），被螺塞挡住的一段不画
    head = 14.0
    v.line((xo1, yb), (xo1 + fw, yb))
    v.line((xo1 + fw, yb), (xo1 + fw, yb + b2))
    top_hidden = dy - 0.9 * ddr < yb + b2
    v.line((xo1 + head if top_hidden else xo1, yb + b2), (xo1 + fw, yb + b2))

    # 放油螺塞（不剖）：螺纹杆伸入箱内，封油垫剖开（涂黑画成密剖面线），六角头
    L_th = 14.0
    v.rect(xo1 - L_th, dy - rd, xo1, dy + rd)
    for n_ in (-1, 1):
        v.line((xo1 - L_th, dy + n_ * 0.45 * ddr), (xo1, dy + n_ * 0.45 * ddr), "细实线")
    gasket = [(xo1, dy - 0.9 * ddr), (xo1 + 4, dy - 0.9 * ddr), (xo1 + 4, dy + 0.9 * ddr), (xo1, dy + 0.9 * ddr)]
    gasket_hi, gasket_lo = gasket[:], gasket[:]
    gasket_hi[0], gasket_hi[1] = (xo1, dy + rd), (xo1 + 4, dy + rd)
    gasket_lo[2], gasket_lo[3] = (xo1 + 4, dy - rd), (xo1, dy - rd)
    v.poly(gasket, close=True)
    v.hatch([gasket_hi, gasket_lo], 45, 1.0)
    v.rect(xo1 + 4, dy - 0.8 * ddr, xo1 + head, dy + 0.8 * ddr)
    v.line((xo1 + 4, dy - 0.4 * ddr), (xo1 + head, dy - 0.4 * ddr))
    v.line((xo1 + 4, dy + 0.4 * ddr), (xo1 + head, dy + 0.4 * ddr))
    v.line((xo1 - L_th - 3, dy), (xo1 + head + 4, dy), "点画线")
    fadd(f"放油螺塞 M{ddr:g}×1.5", "1", "Q235", "JB/ZQ 4450-2006", (xo1 + 9, dy + 0.6 * ddr))
    fadd(f"封油垫 {ddr:g}", "1", "石棉橡胶纸", "", (xo1 + 2, dy + 0.75 * ddr))

    # 杆式油标（不剖）：螺纹段旋在油标座里，油标杆斜插到油面以下，杆上刻最高、最低油面线
    s_in = s_at_x(xi1, 0) - 2
    v.poly([P(s_in, -ri), P(boss_s, -ri), P(boss_s, ri), P(s_in, ri)], close=True)
    for n_ in (-1, 1):
        v.line(P(s_in, n_ * 0.84 * ri), P(boss_s, n_ * 0.84 * ri), "细实线")
    oil = t.oil_level * MM
    s_tip = (oil - 12 - oy_) / sn
    rr = 3.0
    v.poly([P(s_in, -rr), P(s_tip, -rr), P(s_tip, rr), P(s_in, rr)])
    for dy_mark in (-8.0, 8.0):  # 最低、最高油面刻线
        s_m = (oil + dy_mark - oy_) / sn
        v.line(P(s_m, -rr - 1.5), P(s_m, rr + 1.5), "细实线")
    v.poly([P(boss_s, -6), P(26, -6), P(26, 6), P(boss_s, 6)])
    v.poly([P(26, -10), P(34, -10), P(34, 10), P(26, 10)], close=True)
    v.line(P(s_tip - 4, 0), P(38, 0), "点画线")
    fadd("杆式油标 M12", "1", "Q235", "组合件", P(30, 4))
    # 油面（细实线），在油标杆处断开
    x_rod = ox_ + (oil - oy_) / sn * c
    v.line((xw0 + 3, oil), (x_rod - rr / sn - 1, oil), "细实线")
    v.line((x_rod + rr / sn + 1, oil), (xi1, oil), "细实线")


def _front_pinion_side(d, t: HousingDetail, v: View, fadd):
    """主视图中左端壁外的Ⅰ轴部分（外形）：轴承座凸台（剖分面分开）、套杯凸缘、透盖、轴伸和联轴器轮毂。"""
    from gongke_core.layout.bevel_reducer import cup

    ps, h = d.pinion, d.housing
    sb = t.side_bore
    c = cup(ps)
    xo0 = t.x_outer[0] * MM
    xf = sb.x_face * MM
    br = sb.boss_r * MM
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    # 凸台：左端在凸缘以外的部分可见，凸缘范围内被凸缘挡住
    for y in (br, -br):
        v.line((xf, y), (xo0 - fw, y) if abs(y) <= max(b, b1) else (xo0, y))
    v.line((xf, -br), (xf, br))
    v.line((xf, 0), (xo0 - fw, 0))
    rf = c.flange_D * MM / 2
    ft, e = c.flange_t * MM, h.cap_thickness * MM
    v.rect(xf - ft, -rf, xf, rf)
    v.rect(xf - ft - e, -rf, xf - ft, rf)
    # 螺钉头（上下各一）
    d3 = c.screw_d * MM
    r0 = (c.D_out + 2.5 * c.screw_d) * MM / 2
    for y in (r0, -r0):
        v.rect(xf - ft - e - 0.7 * d3, y - 0.85 * d3, xf - ft - e, y + 0.85 * d3)
    # 轴伸与联轴器轮毂
    x_cap = xf - ft - e
    for seg in ps.segments:
        u0, u1 = seg.z0 * MM, seg.z1 * MM
        if -u0 <= x_cap:
            v.rect(-u1, -seg.d * MM / 2, -u0, seg.d * MM / 2)
        elif -u1 < x_cap:
            v.rect(-u1, -seg.d * MM / 2, x_cap, seg.d * MM / 2)
    end = next(sg for sg in ps.segments if sg.role == "端部")
    v.rect(-end.z1 * MM, -end.d * MM, -end.z0 * MM, end.d * MM, "细实线")
    v.centerline((-ps.segments[-1].z1 * MM - 3, 0), (xo0 - fw, 0), 3)
    fadd("轴承透盖", "", "HT200", "", (xf - ft - e / 2, -rf * 0.7))
    fadd("套杯", "1", "HT150", "", (xf - ft / 2, rf * 0.7))


# ====================================================================== 左视图

def _left_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet):
    """从左向右看：图上 X = z，Y = y。各零件投影为矩形，按离观察者（−x 方向）由近到远绘制并消隐。"""
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    zsh = _zshafts(d)
    xs = [s.layout.x * MM for s in zsh]
    xo0, xo1 = (val * MM for val in t.x_outer)
    yb = t.y_bottom * MM
    b2 = h.flange_foot * MM
    top = t.cover_top * MM

    items: list[tuple[float, tuple[float, float, float, float], str]] = []  # (深度 x, 矩形 (z0,y0,z1,y1), 图层)
    items.append((xo0 - fw, (-delta - fw, yb, W + delta + fw, yb + b2), "粗实线"))
    items.append((xo0 - fw, (-delta - fw, -b, W + delta + fw, 0), "粗实线"))
    items.append((xo0 - fw, (-delta - fw, 0, W + delta + fw, b1), "粗实线"))
    items.append((xo0, (-delta, yb + b2, W + delta, -b), "粗实线"))
    cover_near = min(x - r * MM for x, r in zip(xs, t.cover_r))
    items.append((cover_near, (-delta, b1, W + delta, top), "粗实线"))
    hb = t.boss_h * MM
    for a_, b_ in t.side_bosses:  # 轴承旁凸台
        items.append((a_ * MM, (-L1, -hb, -delta, hb), "粗实线"))
        items.append((a_ * MM, (W + delta, -hb, W + L1, hb), "粗实线"))
    for xe in t.hooks[:1]:
        pts = t.hook_shape(xe)[0]
        items.append((xe * MM - fw, (W / 2 - delta, pts[-1][1] * MM, W / 2 + delta, pts[0][1] * MM), "粗实线"))
    for sr, x, rb, cap in zip(zsh, xs, t.boss_r, t.caps):
        rb = rb * MM
        r2 = cap.D2 * MM / 2
        items.append((x - rb, (-L1, -rb, -delta, rb), "粗实线"))
        items.append((x - rb, (W + delta, -rb, W + L1, rb), "粗实线"))
        items.append((x - r2, (-L1 - e, -r2, -L1, r2), "粗实线"))
        items.append((x - r2, (W + L1, -r2, W + L1 + e, r2), "粗实线"))
        m, dep = t.rib_t * MM, t.rib_depth * MM  # 加强肋（侧面看为一窄条）
        items.append((x - m / 2, (-delta - dep, yb + b2, -delta, -rb), "粗实线"))
        items.append((x - m / 2, (W + delta, yb + b2, W + delta + dep, -rb), "粗实线"))
        lay = sr.layout
        if lay.extension:
            for seg in lay.segments:
                z0, z1 = seg.z0 * MM, seg.z1 * MM
                if lay.extension == "left" and z1 <= -L1 - e + 1e-6 or lay.extension == "right" and z0 >= W + L1 + e - 1e-6:
                    r = seg.d * MM / 2
                    items.append((x - r, (z0, -r, z1, r), "粗实线"))
                elif lay.extension == "left" and z0 < -L1 - e:
                    r = seg.d * MM / 2
                    items.append((x - r, (z0, -r, -L1 - e, r), "粗实线"))
                elif lay.extension == "right" and z1 > W + L1 + e:
                    r = seg.d * MM / 2
                    items.append((x - r, (W + L1 + e, -r, z1, r), "粗实线"))
    # 吊环螺钉、视孔盖、通气器
    ed = t.eyebolt_d * MM
    for xe in t.eyebolts:
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        items.append((xe - 1.1 * ed, (W / 2 - 1.1 * ed, ye - 2, W / 2 + 1.1 * ed, ye + 0.4 * ed), "粗实线"))
        items.append((xe - 0.9 * ed, (W / 2 - 0.9 * ed, ye + 0.4 * ed, W / 2 + 0.9 * ed, ye + 0.9 * ed), "粗实线"))
        items.append((xe - 1.6 * ed, (W / 2 - 0.4 * ed, ye + 0.9 * ed, W / 2 + 0.4 * ed, ye + 0.9 * ed + 3.2 * ed), "粗实线"))
    ins = t.inspection
    a = math.radians(ins.angle)
    L, Bw, th = ins.length * MM, ins.width * MM, ins.thickness * MM
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    y_lo = cy - L / 2 * abs(math.sin(a))
    y_hi = cy + L / 2 * abs(math.sin(a)) + th * math.cos(a)
    items.append((cx - L / 2, (W / 2 - Bw / 2, y_lo, W / 2 + Bw / 2, y_hi), "粗实线"))
    vd = ins.vent_d * MM
    yv = cy + th
    items.append((cx - 0.9 * vd, (W / 2 - 0.9 * vd, yv + 0.5 * vd, W / 2 + 0.9 * vd, yv + 0.9 * vd), "粗实线"))
    items.append((cx - 0.6 * vd, (W / 2 - 0.6 * vd, yv, W / 2 + 0.6 * vd, yv + 0.5 * vd), "粗实线"))
    items.append((cx - 0.45 * vd, (W / 2 - 0.45 * vd, yv + 0.9 * vd, W / 2 + 0.45 * vd, yv + 1.4 * vd), "粗实线"))

    items.sort(key=lambda it: it[0])
    circ: list[tuple[float, float, float]] = []
    if t.side_bore is not None:
        circ = _left_pinion_side(d, t, v)
    drawn: list[tuple[float, float, float, float]] = []
    for _, (z0, y0, z1, y1), layer in items:
        for p, q in (((z0, y0), (z1, y0)), ((z1, y0), (z1, y1)), ((z1, y1), (z0, y1)), ((z0, y1), (z0, y0))):
            for a_, b_ in hidden.visible_segments(p, q, circles=circ, rects=drawn):
                v.line(a_, b_, layer)
        drawn.append((z0, y0, z1, y1))
    # 轴线、对称中心线
    zl = [min(s.layout.segments[0].z0 for s in zsh) * MM, max(s.layout.segments[-1].z1 for s in zsh) * MM]
    v.centerline((zl[0], 0), (zl[1], 0), 4)
    v.centerline((W / 2, yb), (W / 2, top + 4.6 * ed), 4)


def _left_pinion_side(d, t: HousingDetail, v: View) -> list[tuple[float, float, float]]:
    """左视图中正对观察者的Ⅰ轴：联轴器轮毂、轴端、透盖和套杯凸缘（带螺钉）、轴承座凸台，都是同心圆。
    返回这些圆（作为后面零件的遮挡体）。"""
    from gongke_core.layout.bevel_reducer import cup

    ps = d.pinion
    c = cup(ps)
    zc = t.side_bore.z * MM
    end = next(sg for sg in ps.segments if sg.role == "端部")
    rf = c.flange_D * MM / 2
    br = t.side_bore.boss_r * MM
    v.circle((zc, 0), end.d * MM, "细实线")  # 联轴器轮毂
    v.circle((zc, 0), end.d * MM / 2)
    v.circle((zc, 0), rf)
    d3 = c.screw_d * MM
    r0 = (c.D_out + 2.5 * c.screw_d) * MM / 2
    for j in range(c.screws):
        a = math.radians(360 * (j + 0.5) / c.screws)
        p = (zc + r0 * math.cos(a), r0 * math.sin(a))
        v.circle(p, 0.85 * d3)
    v.circle((zc, 0), br)
    v.centerline((zc - br, 0), (zc + br, 0), 3)
    v.centerline((zc, -br), (zc, br), 3)
    return [(zc, 0.0, br)]


# ====================================================================== 标准件、配合、序号

def _standard_parts(d: ReducerDesign, t: HousingDetail, add):
    """补齐没有画出序号引线的数量（轴承盖、螺钉的总数等）。"""
    zsh = _zshafts(d)
    n_open = sum(1 for s in zsh if s.layout.extension)
    n_side = 1 if t.side_bore is not None else 0  # Ⅰ轴套杯外的透盖
    for name, qty in (("轴承透盖", n_open + n_side), ("轴承闷盖", 2 * len(zsh) - n_open)):
        p = add(name, qty, "HT200")
        p.qty = str(qty)
    # 轴承盖螺钉按规格汇总
    counts: dict[str, int] = {}
    for cap in t.caps:
        d3 = cap.d3 * MM
        name = f"螺钉 M{d3:g}×{_std(d.housing.cap_thickness * MM + 1.5 * d3, SCREW_L)}"
        counts[name] = counts.get(name, 0) + 2 * cap.n
    if t.side_bore is not None:  # 透盖和套杯凸缘用同一组螺钉固定在轴承座上
        from gongke_core.layout.bevel_reducer import cup

        c = cup(d.pinion)
        d3 = c.screw_d * MM
        name = f"螺钉 M{d3:g}×{_std((d.housing.cap_thickness + c.flange_t) * MM + 1.5 * d3, SCREW_L)}"
        counts[name] = counts.get(name, 0) + c.screws
    for name, n in counts.items():
        p = add(name, n, "Q235", "GB/T 5783-2016")
        p.qty = str(n)


def _fits(d: ReducerDesign, v: View, sh: Sheet):
    fits = []
    for sr in _zshafts(d):
        lay = sr.layout
        x = lay.x * MM
        zb = _bearing_bodies(lay)[0][0]
        D, dd = lay.bearing.D * MM, lay.bearing.d * MM
        fits.append(((zb, x - D / 2), f"%%c{D:g}H7", True))
        # 轴承盖止口与座孔：间隙配合（课程设计手册推荐 H7/d11）
        zr = _bearing_bodies(lay)[1]
        fits.append(((zr[0] + zr[1] / 2 + 3, x + D / 2), f"%%c{D:g}H7/d11"))
        fits.append(((zb - _bearing_bodies(lay)[0][1] / 2 - 1, x - dd / 2), f"%%c{dd:g}k6"))
        for gg in lay.gears:
            if not gg.integral:
                fits.append(((gg.z * MM, x - gg.seat_d * MM / 2), f"%%c{gg.seat_d * MM:g}H7/r6"))
        if lay.extension:
            end = next(sg for sg in lay.segments if sg.role == "端部")
            fits.append((((end.z0 + end.z1) / 2 * MM, x - end.d * MM / 2), f"%%c{end.d * MM:g}k6"))
    if getattr(d, "bevel", None) is not None:
        from gongke_core.layout.bevel_reducer import cup

        ps = d.pinion
        za = d.positions.z_apex * MM
        c = cup(ps)
        ua = ps.bearing_u[0] * MM
        fits.append(((za - c.D_out * MM / 2, -ua), f"%%c{c.D_out * MM:g}H7/js6"))
        fits.append(((za - c.D * MM / 2, -ps.bearing_u[1] * MM), f"%%c{c.D * MM:g}H7"))
        if not ps.integral:
            seg = next(s_ for s_ in ps.segments if s_.role == "齿轮")
            fits.append(((za - seg.d * MM / 2, -(seg.z0 + seg.z1) / 2 * MM), f"%%c{seg.d * MM:g}H7/r6"))
        end = next(s_ for s_ in ps.segments if s_.role == "端部")
        fits.append(((za - end.d * MM / 2, -(end.z0 + end.z1) / 2 * MM), f"%%c{end.d * MM:g}k6"))
    for pt, txt, *left in fits:
        tx, ty = v.P(*pt)
        if left and left[0]:  # 座孔标注向外侧（远离轴）引出，避免压在轴和轴承上
            sh.leader_text((tx, ty), (tx - 4, ty - 9), txt.replace("%%c", "Ø"), 3.0, left=True)
        else:
            sh.leader_text((tx, ty), (tx + 6, ty - 9), txt.replace("%%c", "Ø"), 3.0)


def _place_balloons(sh: Sheet, parts: list[Part], lanes: dict):
    """按 FL（上→下）、TL（上→下）、TR（下→上）、FR（下→上）、FT（右→左）的顺序编号，即沿图形四周逆时针。"""
    groups: dict[str, list[Part]] = {k: [] for k in lanes}
    for p in parts:
        if p.target is not None and p.group in groups:
            groups[p.group].append(p)
    placed: dict[str, list[tuple[Part, tuple[float, float]]]] = {}
    for g, items in groups.items():
        kind, pos, (lo, hi) = lanes[g]
        if kind == "col":
            items.sort(key=lambda p: -p.target[1])
            ys = []
            for p in items:
                y = min(p.target[1], hi) if not ys else min(p.target[1], ys[-1] - 10)
                ys.append(y)
            if ys and ys[-1] < lo:  # 超出下边界：整体上移
                shift = lo - ys[-1]
                ys = [y + shift for y in ys]
                for k in range(len(ys) - 2, -1, -1):
                    ys[k] = max(ys[k], ys[k + 1] + 10)
            placed[g] = [(p, (pos, y)) for p, y in zip(items, ys)]
        else:
            items.sort(key=lambda p: p.target[0])
            xs_: list[float] = []
            for p in items:
                xs_.append(max(p.target[0], lo) if not xs_ else max(p.target[0], xs_[-1] + 12))
            if xs_ and xs_[-1] > hi:
                shift = xs_[-1] - hi
                xs_ = [x - shift for x in xs_]
                for k in range(1, len(xs_)):
                    xs_[k] = max(xs_[k], xs_[k - 1] + 12)
            placed[g] = [(p, (x, pos)) for p, x in zip(items, xs_)]
    order: list[tuple[Part, tuple[float, float]]] = []
    order += placed.get("FL", [])
    order += placed.get("TL", [])
    order += list(reversed(placed.get("TR", [])))
    order += list(reversed(placed.get("FR", [])))
    order += list(reversed(placed.get("FT", [])))
    ballooned = [p for p, _ in order]
    rest = [p for p in parts if p not in ballooned]
    parts[:] = ballooned + rest
    for i, (p, at) in enumerate(order, 1):
        sh.balloon(p.target, at, i)
