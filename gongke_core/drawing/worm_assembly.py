"""蜗杆减速器（蜗杆下置）装配图：主视图（外形 + 沿蜗杆轴线的局部剖视）、左视图（沿蜗轮轴线全剖，B-B）、
俯视图（外形）。

画法按 GB/T 4459.2、4459.7 和装配图规定画法：
- 实心轴沿轴线剖切按不剖处理；横向剖切（左视图中的蜗杆）画剖面线；
- 蜗杆蜗轮啮合：在蜗轮投影为圆的主视图中，蜗轮画齿顶圆（粗实线）和分度圆（点画线），被蜗杆遮住的部分不画；
  在蜗杆投影为圆的左视图中，蜗轮齿圈、轮芯剖开（相邻零件剖面线方向相反），喉部被蜗杆遮住的齿顶线不画；
- 蜗杆的圆锥滚子轴承用通用画法（矩形线框加正十字），蜗轮轴的深沟球轴承一侧用规定画法；
- 零件序号沿图形四周逆时针排列，配明细栏、技术特性表和技术要求。

视图按第一角投影配置：俯视图在主视图下方（下方为前），左视图在主视图右方（右方为前）。
坐标与 `layout.worm_reducer` 一致：x 沿蜗杆轴线，y 向上（剖分面 y = 0），z 沿蜗轮轴线。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core import standards
from gongke_core.calc import worm as worm_calc
from gongke_core.drawing import hidden
from gongke_core.drawing.assembly import (PIN_D, PIN_L, SCREW_L, Part, _bearing_bodies, _bearing_name, _place_balloons, _std,
                                          TRIAL_RUN, b_total, cap_section, draw_bearing)
from gongke_core.drawing.gear import dms
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout import worm_blank
from gongke_core.layout.housing_detail import HousingDetail, detail, envelope_height

MM = 1e3
GAP = 80  # 主视图与左视图之间的间距（图纸 mm），中间放一列零件序号


def _circle_pts(cx, cy, r, n=72, a0=0.0, a1=360.0):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def _wavy(v: View, x0: float, x1: float, y: float, amp: float):
    """波浪线（局部剖视的分界线，细实线）。"""
    n = max(int((x1 - x0) / (8 * amp)), 4)
    pts = [(x0 + (x1 - x0) * k / (4 * n), y + amp * math.sin(math.pi * k / 2)) for k in range(4 * n + 1)]
    v.poly(pts, "细实线")


def draw(d, path: str | Path, drawing_no: str = "GK-00") -> Sheet:
    t = detail(d)
    h = d.housing
    w, ws = d.worm, d.worm_shaft
    s2 = d.shafts[1].layout
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    xo0, xo1 = (v * MM for v in t.x_outer)
    yb = t.y_bottom * MM
    ed = t.eyebolt_d * MM
    wb = t.worm_bore
    xf = wb.x_face * MM

    # ------------------------------------------------ 各视图的模型范围（mm）
    x_min = ws.segments[0].z0 * MM - 5
    x_max = max(xo1 + fw, xf + e) + 5
    eye_top = max(envelope_height(t.cover_outer, x) for x in t.eyebolts) * MM + 4.6 * ed
    y_top = max(eye_top, t.inspection.center[1] * MM + t.inspection.thickness * MM + 1.4 * t.inspection.vent_d * MM) + 5
    z_min = min(s2.segments[0].z0 * MM, -L1 - e) - 5
    z_max = s2.segments[-1].z1 * MM + 5
    z_max_l = max(z_max, W + delta + 50)  # 左视图右侧有油标
    front_w, front_h = x_max - x_min, y_top - yb
    left_w = z_max_l - z_min
    top_h = z_max - z_min
    n_rows = 40

    for size in ("A1", "A0"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        s = None
        for sc in reversed(SCALES):
            if sc > 1:
                continue
            w_need = 40 + front_w * sc + GAP + left_w * sc + 50
            h_need = 25 + front_h * sc + 35 + top_h * sc + 20
            front_bottom = y1 - 25 - front_h * sc
            left_right = x0 + 40 + front_w * sc + GAP + left_w * sc + 40
            parts_top = y0 + 56 + 7 * (n_rows + 1)
            right_free = x1 - 180 - (x0 + 40 + front_w * sc + GAP)
            if (w_need <= x1 - x0 and h_need <= y1 - y0 and right_free >= 140
                    and (left_right <= x1 - 180 or front_bottom - 5 >= parts_top or
                         front_bottom - 5 >= y0 + 56 + 7 * (n_rows // 2 + 1))):
                s = sc
                break
        if s is not None or size == "A0":
            s = s or 1 / 5
            break
    ox = x0 + 40 - x_min * s
    oy_f = y1 - 25 - y_top * s
    front_bottom = oy_f + yb * s
    oy_t = front_bottom - 35 + z_min * s  # 俯视图：图上 Y = oy_t − z·s
    front_right = ox + x_max * s
    ox_l = front_right + GAP - z_min * s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s, rotate=True)
    lv = View(sh, (ox_l, oy_f), s)
    if front_bottom - 5 < y0 + 56 + 7 * (n_rows + 1) and ox_l + z_max_l * s > x1 - 180:
        sh.parts_first_rows = max(int((front_bottom - 8 - (y0 + 56)) / 7) - 1, 10)

    parts: list[Part] = []
    by_name: dict[str, Part] = {}

    def add(name, qty, mat, note="", target=None, group=""):
        if name in by_name:
            p = by_name[name]
            if name.startswith("螺钉") and str(p.qty).isdigit() and str(qty).isdigit():
                p.qty = str(int(p.qty) + int(qty))  # 两种轴承盖螺钉规格相同时合并数量
            if p.target is None and target is not None:
                p.target, p.group = target, group
            return p
        p = Part(name, str(qty), mat, note, target, group)
        parts.append(p)
        by_name[name] = p
        return p

    hatch_angle = [45]

    def next_angle():
        hatch_angle[0] = 135 if hatch_angle[0] == 45 else 45
        return hatch_angle[0]

    _front(d, t, fv, sh, add, next_angle)
    _left(d, t, lv, sh, add, next_angle)
    _top(d, t, tv, sh, add)
    # 剖切符号与视图名称
    sh.section_label(lv.P(W / 2, 0)[0], oy_f + y_top * s + 3, "B")
    for zz, sg in ((-delta - fw - 6, -1), (W + delta + fw + 6, 1)):
        p0, p1 = tv.P(zz, 0), tv.P(zz + sg * 5, 0)
        sh.line(p0, p1, "图框")
        sh.text(p1[0] + 2, p1[1] + (1 if sg < 0 else -6), "B", 5)

    # ------------------------------------------------ 零件序号与明细栏
    col_fl = ox + x_min * s - 18
    col_lr = ox_l + z_max_l * s + 32
    col_mid = front_right + GAP / 2
    row_ft = oy_f + y_top * s + 12
    _place_balloons(sh, parts, {
        "FL": ("col", col_fl, (front_bottom - 5, y1 - 8)),
        "TL": ("col", col_fl, (y0 + 10, front_bottom - 12)),
        "TR": ("col", col_mid, (front_bottom - 5, y1 - 8)),
        "FR": ("col", col_lr, (front_bottom - 5 if col_lr < x1 - 180 else y0 + 56 + 7 * (len(parts) + 2), y1 - 8)),
        "FT": ("row", row_ft, (ox + x_min * s, front_right)),
    })

    # ------------------------------------------------ 尺寸
    za = z_min + 3
    lv.dim((za, 0), (za, -w.a * MM), (za - 8 / s, 0), 90, f"<>±{_fa(w):g}", 0)
    zr = z_max_l - 3
    lv.dim((zr, yb), (zr, 0), (zr + 6 / s, yb), 90, "<>", 0)
    lv.dim((zr, yb), (zr, t.cover_top * MM), (zr + 16 / s, yb), 90, "<>", 0)
    x_dim = min(xo0 - fw, ws.segments[0].z0 * MM) - 10 / s
    tv.dim((-delta - fw, xo0 - fw), (W + delta + fw, xo0 - fw), (-delta - fw, x_dim), 0, "<>", 0)
    tv.dim((z_max - 10, xo0 - fw), (z_max - 10, xo1 + fw), (z_max + 2 / s, xo0 - fw), 90, "<>", 0)
    # 安装尺寸：地脚螺栓孔（在凸缘下方，虚线）的孔距和孔径，两外伸轴段的配合长度
    from gongke_core.drawing.housing_base import CLEARANCE
    dfh = CLEARANCE[round(h.bolt_foot * MM)]
    for fx, fz in t.foot_bolts:
        tv.circle((fz * MM, fx * MM), dfh / 2, "虚线")
        sh.cross(tv.P(fz * MM, fx * MM), dfh / 2 * s, 1.5)
    fxs = sorted({fx * MM for fx, _ in t.foot_bolts})
    fzs = sorted({fz * MM for _, fz in t.foot_bolts})
    z_top = -h.bearing_seat_length * MM - h.cap_thickness * MM
    tv.dim((fzs[0], fxs[0]), (fzs[0], fxs[-1]), (z_top - 8 / s, fxs[0]), 90, "<>", 0)
    tv.dim((fzs[0], fxs[-1]), (fzs[-1], fxs[-1]), (fzs[0], xo1 + fw + 10 / s), 0, "<>", 0)
    px, py = tv.P(fzs[0], fxs[-1])
    sh.leader_text((px + dfh / 2 * s * 0.7, py + dfh / 2 * s * 0.7), (px + 8, py + 14), f"{len(t.foot_bolts)}×Ø{dfh:g}", 3.0)
    lay2 = d.shafts[1].layout
    end2 = next(sg for sg in lay2.segments if sg.role == "端部")
    xx = end2.d * MM + 6 / s
    tv.dim((end2.z0 * MM, end2.d * MM), (end2.z1 * MM, end2.d * MM), (end2.z0 * MM, xx), 0, "<>", 0)
    end1 = next(sg for sg in ws.segments if sg.role == "端部")
    zz = W / 2 + end1.d * MM + 6 / s  # 放在轴伸下方，上方有零件序号的引线
    tv.dim((W / 2 + end1.d * MM, end1.z0 * MM), (W / 2 + end1.d * MM, end1.z1 * MM), (zz, end1.z0 * MM), 90, "<>", 0)
    _fits(d, t, fv, lv, sh)

    # ------------------------------------------------ 技术特性、技术要求
    k = d.kin
    ef = d.task.conveyor.efficiencies
    rows = [["技术特性", ""],
            ["输入功率", f"{k.shafts[1].power / 1e3:.2f} kW"],
            ["输入转速", f"{k.shafts[1].speed_rpm:.0f} r/min"],
            ["传动比", f"{w.u:.2f}"],
            ["效率", f"{w.eta * ef.bearing_pair ** 2:.3f}"],
            ["蜗杆传动", f"m={w.m * MM:g}  q={w.q:g}  z={w.z1}/{w.z2}  x2={w.x2:+.2f}  γ={dms(w.gamma)}  {w.inp.grade}级"]]
    tx = ox + x_max * s + 30
    sh.table(tx, front_bottom - 25, rows, [26, 112], 8)
    oil_dip = (t.oil_level + w.a + w.da1 / 2) * MM
    reqs = [
        "装配前所有零件用煤油清洗，箱体内壁涂耐油油漆。",
        f"啮合侧隙用铅丝检验，不小于 {_jn_min(w):.3f} mm。",
        "用涂色法检验接触斑点，沿齿高不小于 55%，沿齿长不小于 50%，斑点应偏于蜗杆旋出一侧。",
        "蜗轮中间平面应通过蜗杆轴线，用蜗轮轴两端轴承盖下的垫片调整。",
        "圆锥滚子轴承用垫片调整轴向游隙：蜗杆轴 0.04～0.07 mm，蜗轮轴 0.05～0.10 mm。",
        "剖分面、各接触面及密封处不允许漏油，剖分面允许涂密封胶，不允许使用垫片。",
        f"箱内装 L-CKE 320 蜗轮蜗杆油至油标规定高度（蜗杆浸油约 {oil_dip:.0f} mm）。",
        "外表面涂灰色油漆。",
        TRIAL_RUN[0],
        f"负载试运转时油温不超过 {worm_calc.OIL_LIMIT:.0f} ℃，轴承温升不超过 40 ℃。",
    ]
    sh.tech_requirements(reqs, tx, front_bottom - 25 - 8 * len(rows) - 22)
    for i, p in enumerate(parts, 1):
        sh.add_part(i, p.name, p.qty, p.material, p.note)
    sh.frame(TitleInfo("蜗杆减速器", "", s, "1", drawing_no))
    sh.save(path)
    return sh


def _fa(w) -> float:
    """中心距极限偏差 ±fa（GB/T 10089，8 级，按中心距查表的近似值，mm）。"""
    a = w.a * MM
    for lim, fa in ((30, 0.026), (50, 0.031), (80, 0.037), (120, 0.044), (180, 0.050), (250, 0.058), (315, 0.065),
                    (400, 0.070), (500, 0.078)):
        if a <= lim:
            return fa
    return 0.087


def _jn_min(w) -> float:
    """最小法向侧隙（GB/T 10089 侧隙种类 c 的近似值，按中心距，mm）。"""
    a = w.a * MM
    for lim, j in ((30, 0.021), (50, 0.025), (80, 0.030), (120, 0.035), (180, 0.040), (250, 0.046), (315, 0.052),
                   (400, 0.057), (500, 0.063)):
        if a <= lim:
            return j
    return 0.070


# ====================================================================== 主视图

def _front(d, t: HousingDetail, v: View, sh: Sheet, add, next_angle):
    h = d.housing
    w, ws = d.worm, d.worm_shaft
    s2 = d.shafts[1].layout
    s1 = d.shafts[0].layout
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    b2 = h.flange_foot * MM
    e = h.cap_thickness * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xi0, xi1 = (val * MM for val in h.x_range)
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    a = w.a * MM
    wb = t.worm_bore
    rw, Dw = wb.boss_r * MM, wb.D * MM
    xbi, xf = wb.x_inner * MM, wb.x_face * MM
    y_w = -a + rw + 12  # 局部剖视的上边界

    def fadd(name, qty, mat, note, at):
        if at[1] > b1 + 2:
            g = "FT"
        elif at[0] > 0.3 * xo1:
            g = "TR"
        else:
            g = "FL"
        add(name, qty, mat, note, v.P(*at), g)

    cap2 = t.caps[0]
    occ = [(0.0, 0.0, cap2.D2 * MM / 2), (0.0, 0.0, t.boss_r[0] * MM)]
    hb = t.boss_h * MM
    blocks = [(a_ * MM, -hb, b_ * MM, hb) for a_, b_ in t.side_bosses]  # 轴承旁凸台

    def seg(p, q, layer="粗实线", circles=None, rects=None):
        for a_, b_ in hidden.visible_segments(p, q, occ if circles is None else circles, blocks if rects is None else rects):
            v.line(a_, b_, layer)

    def rect(x0, y0, x1, y1, layer="粗实线"):
        for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            seg(p, q, layer)

    # ---------------- 外形部分（局部剖视以上）
    # 蜗轮轴轴承盖（透盖，朝向观察者）与轴伸
    r2 = cap2.D2 * MM / 2
    v.circle((0, 0), r2)
    r0 = cap2.D0 * MM / 2
    d3 = cap2.d3 * MM
    for j in range(cap2.n):
        ang = math.radians(45 + 360 * j / cap2.n if cap2.n == 4 else 30 + 360 * j / cap2.n)
        c = (r0 * math.cos(ang), r0 * math.sin(ang))
        v.circle(c, 0.85 * d3)
        v.circle(c, 0.5 * d3, "细实线")
    v.centerline((-r2, 0), (r2, 0), 3)
    v.centerline((0, -r2), (0, r2), 3)
    end2 = next(sg for sg in s2.segments if sg.role == "端部")
    v.circle((0, 0), end2.d * MM / 2)
    v.circle((0, 0), end2.d * MM, "细实线")
    fadd("轴承透盖", "1", "HT200", "", (r2 * 0.75, -r2 * 0.55))
    fadd(f"螺钉 M{d3:g}×{_std(e + 1.5 * d3, SCREW_L)}", 2 * cap2.n, "Q235", "GB/T 5783-2016",
         (r0 * math.cos(math.radians(-45)), r0 * math.sin(math.radians(-45))))
    for a_, b_ in hidden.visible_arcs(0, 0, t.boss_r[0] * MM, 0, 360, [(0.0, 0.0, r2)], blocks):
        v.arc((0, 0), t.boss_r[0] * MM, a_, b_)
    for x0_, y0_, x1_, y1_ in blocks:
        for p, q in (((x0_, y0_), (x1_, y0_)), ((x1_, y0_), (x1_, y1_)), ((x1_, y1_), (x0_, y1_)), ((x0_, y1_), (x0_, y0_))):
            seg(p, q, rects=[])
        seg((x0_, 0), (x1_, 0), circles=occ[:1], rects=[])
    # 加强肋（局部剖视以上的部分）
    m = t.rib_t * MM
    for x in t.ribs:
        y_top = -math.sqrt((t.boss_r[0] * MM) ** 2 - (m / 2) ** 2)
        for sx in (-1, 1):
            seg((x * MM + sx * m / 2, y_top), (x * MM + sx * m / 2, y_w))
    # 凸缘、箱壁（局部剖视以上）、底座
    rect(xo0 - fw, -b, xo1 + fw, 0)
    rect(xo0 - fw, 0, xo1 + fw, b1)
    seg((xo0, y_w), (xo0, -b))
    seg((xo1, y_w), (xo1, -b))
    # 箱盖：半圆拱
    R = t.cover_r[0] * MM
    cut = math.degrees(math.asin(min(b1 / R, 1.0)))
    for a_, b_ in hidden.visible_arcs(0, 0, R, cut, 180 - cut, occ, blocks):
        v.arc((0, 0), R, a_, b_)
    fadd("箱盖", "1", "HT200", "", (-0.55 * R, 0.6 * R))
    # 吊钩（箱座两端铸出）
    for xe in t.hooks:
        pts, (hx, hy), hr = t.hook_shape(xe)
        pts = [(px * MM, py * MM) for px, py in pts]
        for p, q in zip(pts, pts[1:]):
            seg(p, q)
        for a_, b_ in hidden.visible_arcs(hx * MM, hy * MM, hr * MM, 0, 360, occ, blocks):
            v.arc((hx * MM, hy * MM), hr * MM, a_, b_)

    # 连接螺栓（前排）、起盖螺钉
    def bolt(x, dd, length, head_only=False, top=b1, bot=b):  # 螺栓头支承面 y = top，螺母支承面 y = −bot
        seg((x, top + 0.7 * dd + 3), (x, top - length - 3), "点画线")
        rect(x - dd, top, x + dd, top + 0.7 * dd)
        seg((x - dd / 2, top), (x - dd / 2, top + 0.7 * dd))
        seg((x + dd / 2, top), (x + dd / 2, top + 0.7 * dd))
        if head_only:
            return
        yw_ = -bot - 0.25 * dd
        rect(x - 0.75 * dd, yw_, x + 0.75 * dd, -bot)
        yn = yw_ - 0.8 * dd
        rect(x - dd, yn, x + dd, yw_)
        seg((x - dd / 2, yn), (x - dd / 2, yw_))
        seg((x + dd / 2, yn), (x + dd / 2, yw_))
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
    n1, n2 = 2 * len(t.bearing_bolts), 2 * len(t.flange_bolts)
    xb1 = t.bearing_bolts[0] * MM
    fadd(f"螺栓 M{d1:g}×{L1b:g}", n1, "Q235", "GB/T 5782-2016", (xb1 - d1 * 0.6, hb + 0.35 * d1))
    fadd(f"螺母 M{d1:g}", n1, "Q235", "GB/T 6170-2015", (xb1 - d1 * 0.6, -hb - 0.65 * d1))
    fadd(f"弹簧垫圈 {d1:g}", n1, "65Mn", "GB/T 93-1987", (xb1 + d1 * 0.5, -hb - 0.12 * d1))
    if t.flange_bolts:
        xb2 = t.flange_bolts[0] * MM
        fadd(f"螺栓 M{d2:g}×{L2b:g}", n2, "Q235", "GB/T 5782-2016", (xb2 + d2 * 0.6, b1 + 0.35 * d2))
        fadd(f"螺母 M{d2:g}", n2, "Q235", "GB/T 6170-2015", (xb2 + d2 * 0.6, -b - 0.65 * d2))
        fadd(f"弹簧垫圈 {d2:g}", n2, "65Mn", "GB/T 93-1987", (xb2 - d2 * 0.5, -b - 0.12 * d2))
    fadd(f"起盖螺钉 M{d2:g}×{lj}", 1, "Q235", "GB/T 5783-2016", (xj, b1 + 0.35 * d2))

    # 视孔盖、通气器
    ins = t.inspection
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    L, th = ins.length * MM, ins.thickness * MM
    v.rect(cx - L / 2, cy, cx + L / 2, cy + th)
    v.line((cx - L / 2, cy - 1.5), (cx + L / 2, cy - 1.5))
    if ins.pad > 0:  # 拱顶上的视孔平台
        for sx in (-1, 1):
            xp = cx + sx * L / 2
            v.line((xp, cy - 1.5), (xp, envelope_height(t.cover_outer, xp / MM) * MM))
    sd = ins.screw_d * MM
    for s_ in (-L / 2 + 10, L / 2 - 10):
        v.rect(cx + s_ - 0.85 * sd, cy + th, cx + s_ + 0.85 * sd, cy + th + 0.7 * sd)
    vd = ins.vent_d * MM
    for hw, n0, n1_ in ((0.6 * vd, th, th + 0.5 * vd), (0.9 * vd, th + 0.5 * vd, th + 0.9 * vd),
                        (0.45 * vd, th + 0.9 * vd, th + 1.4 * vd)):
        v.rect(cx - hw, cy + n0, cx + hw, cy + n1_)
    v.line((cx, cy - 3), (cx, cy + th + 1.4 * vd + 3), "点画线")
    fadd("视孔盖", "1", "Q235", "", (cx - L / 2 + 22, cy + th / 2))
    fadd("视孔盖垫片", "1", "石棉橡胶纸", "", (cx - L / 2 + 30, cy - 0.8))
    fadd(f"螺钉 M{sd:g}×16", "4", "Q235", "GB/T 5783-2016", (cx + L / 2 - 10, cy + th + 0.35 * sd))
    fadd(f"通气器 M{vd:g}×1.5", "1", "Q235", "", (cx + 0.3 * vd, cy + th + 1.15 * vd))
    # 吊环螺钉
    for k, xe in enumerate(t.eyebolts):
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        v.rect(xe - 1.1 * ed_(t), ye - 2, xe + 1.1 * ed_(t), ye + 0.4 * ed_(t))
        v.rect(xe - 0.9 * ed_(t), ye + 0.4 * ed_(t), xe + 0.9 * ed_(t), ye + 0.9 * ed_(t))
        rcy = ye + 0.9 * ed_(t) + 1.6 * ed_(t)
        v.circle((xe, rcy), 1.6 * ed_(t))
        v.circle((xe, rcy), 0.8 * ed_(t))
        v.line((xe, ye - 4), (xe, rcy + 1.6 * ed_(t) + 3), "点画线")
        if k == 0:
            fadd(f"吊环螺钉 M{ed_(t):g}", len(t.eyebolts), "20", "GB/T 825-1988", (xe - 1.2 * ed_(t), rcy))

    # ---------------- 局部剖视（剖切面通过蜗杆轴线，z = W/2）
    _wavy(v, xo0, xo1, y_w, 1.2 / v.s)
    yt_, yb_ = -a + rw, -a - rw  # 蜗杆轴承座的上下缘
    hD = Dw / 2
    # 箱座：两端壁（含轴承座）上部、底部（含两端轴承座下半、箱底、底座）
    for sg in (-1, 1):
        X = lambda x: sg * x  # noqa: E731
        up = [((xo0 if sg < 0 else xo1), y_w),
              ((xi0 if sg < 0 else xi1), y_w), ((xi0 if sg < 0 else xi1), yt_), (X(xbi), yt_), (X(xbi), -a + hD),
              (X(xf), -a + hD), (X(xf), yt_), ((xo0 if sg < 0 else xo1), yt_)]
        v.poly(up, close=True)
        v.hatch([up], 45)
    inner_lo = []
    if yb_ > y_floor:
        inner_lo = [(-xbi, yb_), (xi0, yb_), (xi0, y_floor), (xi1, y_floor), (xi1, yb_), (xbi, yb_)]
    else:
        inner_lo = [(-xbi, y_floor), (xbi, y_floor)]
    yfoot = yb + b2
    outer_r = [(xf, yb_), (xo1, yb_), (xo1, yfoot)] if yb_ > yfoot else [(xf, yfoot)]
    outer_l = [(xo0, yfoot), (xo0, yb_), (-xf, yb_)] if yb_ > yfoot else [(-xf, yfoot)]
    lo = ([(-xf, -a - hD), (-xbi, -a - hD)] + inner_lo + [(xbi, -a - hD), (xf, -a - hD)] + outer_r
          + [(xo1 + fw, yfoot), (xo1 + fw, yb), (xo0 - fw, yb), (xo0 - fw, yfoot)] + outer_l)
    v.poly(lo, close=True)
    v.hatch([lo], 45)
    fadd("箱座", "1", "HT200", "", (xo0 + 0.5 * (xi0 - xo0), y_w - 6))

    # 蜗轮（啮合画法：齿顶圆粗实线、分度圆点画线，被蜗杆遮住部分不画）
    worm_box = (-w.b1 * MM / 2, -a - w.da1 * MM / 2, w.b1 * MM / 2, -a + w.da1 * MM / 2)
    for r_, layer in ((w.de2 * MM / 2, "粗实线"), (w.d2 * MM / 2, "点画线")):
        y_lim = min(y_w, -1)
        if r_ <= -y_lim:
            continue
        a0 = math.degrees(math.asin(max(-1.0, y_lim / r_)))
        start, end = 180 - a0, 360 + a0
        arcpts = _circle_pts(0, 0, r_, 96, start, end)
        for p, q in zip(arcpts, arcpts[1:]):
            for a_, b_ in hidden.visible_segments(p, q, rects=[worm_box] if layer == "粗实线" else []):
                v.line(a_, b_, layer)

    # 蜗杆轴（不剖，画外形）
    prev = None
    segs = ws.segments
    for sg_ in segs:
        x_a, x_b = sg_.z0 * MM, sg_.z1 * MM
        if sg_.role == "齿轮轴":
            ra, rf, rp = w.da1 * MM / 2, w.df1 * MM / 2, w.d1 * MM / 2
            for sgn in (1, -1):
                v.line((x_a, -a + sgn * ra), (x_b, -a + sgn * ra))
                v.line((x_a, -a + sgn * rf), (x_b, -a + sgn * rf), "细实线")
                v.line((x_a - 3, -a + sgn * rp), (x_b + 3, -a + sgn * rp), "点画线")
            r_ = ra
        else:
            r_ = sg_.d * MM / 2
            for sgn in (1, -1):
                v.line((x_a, -a + sgn * r_), (x_b, -a + sgn * r_))
        if prev is not None:
            rr = max(prev, r_)
            v.line((x_a, -a - rr), (x_a, -a + rr))
        prev = r_
    v.line((segs[0].z0 * MM, -a - segs[0].d * MM / 2), (segs[0].z0 * MM, -a + segs[0].d * MM / 2))
    v.line((segs[-1].z1 * MM, -a - prev), (segs[-1].z1 * MM, -a + prev))
    v.centerline((segs[0].z0 * MM, -a), (max(segs[-1].z1 * MM, xf + e), -a), 5)
    fadd("蜗杆", "1", "45", f"m={w.m * MM:g}，z1={w.z1}", (w.b1 * MM * 0.3, -a + w.da1 * MM / 4))
    # 联轴器轮毂（相邻零件，细实线）
    end = next(sg_ for sg_ in segs if sg_.role == "端部")
    xa_, xb_ = end.z0 * MM, end.z1 * MM
    v.rect(xa_, -a - end.d * MM, xb_, -a + end.d * MM, "细实线")

    # 蜗杆轴承（通用画法）
    brg = ws.bearing
    Dd, dd = brg.D * MM, brg.d * MM
    T = brg.T * MM
    for xc in ws.bodies:
        xc *= MM
        for sgn in (1, -1):
            y_in, y_out = -a + sgn * dd / 2, -a + sgn * Dd / 2
            v.rect(xc - T / 2, min(y_in, y_out), xc + T / 2, max(y_in, y_out))
            ym = (y_in + y_out) / 2
            v.line((xc - T * 0.3, ym), (xc + T * 0.3, ym), "细实线")
            v.line((xc, ym - abs(y_out - y_in) * 0.3), (xc, ym + abs(y_out - y_in) * 0.3), "细实线")
    nm, std = _bearing_name(brg)
    fadd(nm, "2", "", std, (ws.bodies[1] * MM, -a + (dd + Dd) / 4))

    # 蜗杆轴承盖：凸缘 + 套筒形止口（剖开），输入端透盖装毡圈
    cap = wb.cap
    r_cap = cap.D2 * MM / 2
    seal_r = ws.diameters["密封"] * MM / 2 + 1
    for sg, xbody in ((-1, ws.bodies[0]), (1, ws.bodies[1])):
        x_brg = abs(xbody) * MM + T / 2
        f0, f1 = sorted((sg * xf, sg * (xf + e)))
        s0, s1 = sorted((sg * x_brg, sg * xf))
        is_open = sg < 0
        r_in = seal_r if is_open else 0.0
        ang = next_angle()
        # 透盖/闷盖的剖面：凸缘 + 止口套筒（上下两半）
        sec = []
        for sgn in (1, -1):
            if is_open:
                pts = [(f0, -a + sgn * r_in), (f1, -a + sgn * r_in), (f1, -a + sgn * (hD - 6)),
                       (s1, -a + sgn * (hD - 6)), (s1, -a + sgn * hD), (f1, -a + sgn * hD), (f1, -a + sgn * r_cap),
                       (f0, -a + sgn * r_cap)]
                if sg < 0:  # 止口在凸缘右侧（朝向箱内）
                    pts = [(f0, -a + sgn * r_in), (f1, -a + sgn * r_in), (f1, -a + sgn * (hD - 6)),
                           (s1, -a + sgn * (hD - 6)), (s1, -a + sgn * hD), (f1, -a + sgn * hD),
                           (f1, -a + sgn * r_cap), (f0, -a + sgn * r_cap)]
                sec.append(pts)
            else:
                pts = [(s0, -a + sgn * (hD - 6)), (f0, -a + sgn * (hD - 6)), (f0, -a), (f1, -a),
                       (f1, -a + sgn * r_cap), (f0, -a + sgn * r_cap), (f0, -a + sgn * hD), (s0, -a + sgn * hD)]
                sec.append(pts)
        for pts in sec:
            v.poly(pts, close=True)
        v.hatch(sec, ang, 2.0)
        if is_open:
            # 毡圈
            sdm = ws.diameters["密封"] * MM
            fz0, fz1 = f0 + e * 0.25, f1 - e * 0.25
            for sgn in (1, -1):
                v.rect(fz0, -a + sgn * sdm / 2, fz1, -a + sgn * (sdm / 2 + 5), "细实线")
                v.line((fz0, -a + sgn * sdm / 2), (fz1, -a + sgn * (sdm / 2 + 5)), "细实线")
            fadd(f"毡圈 {sdm:g}", "1", "半粗羊毛毡", "JB/ZQ 4606-1997", ((fz0 + fz1) / 2, -a - sdm / 2 - 2.5))
            fadd("蜗杆轴承透盖", "1", "HT200", "", ((f0 + f1) / 2, -a + (r_in + r_cap) / 2))
        else:
            fadd("蜗杆轴承闷盖", "1", "HT200", "", ((f0 + f1) / 2, -a + r_cap * 0.6))
            fadd("调整垫片", "2组", "08F", "", (f0, -a - r_cap + 3))
    # 蜗杆轴承盖螺钉（上下各画一个头部）
    d3w = cap.d3 * MM
    for sg in (-1, 1):
        xo_ = sg * (xf + e)
        for sgn in (1, -1):
            yc = -a + sgn * cap.D0 * MM / 2
            v.rect(min(xo_, xo_ + sg * 0.7 * d3w), yc - 0.85 * d3w, max(xo_, xo_ + sg * 0.7 * d3w), yc + 0.85 * d3w)
    fadd(f"螺钉 M{d3w:g}×{_std(e + 1.5 * d3w, SCREW_L)}", 2 * cap.n, "Q235", "GB/T 5783-2016",
         (xf + e + 0.35 * d3w, -a + cap.D0 * MM / 2))
    # 油面
    yo = t.oil_level * MM
    v.line((xi0 + 5, yo), (-w.b1 * MM / 2 - 5, yo), "点画线")
    v.line((w.b1 * MM / 2 + 5, yo), (xi1 - 5, yo), "点画线")


def ed_(t) -> float:
    return t.eyebolt_d * MM


# ====================================================================== 左视图（B-B）

def _left(d, t: HousingDetail, v: View, sh: Sheet, add, next_angle):
    h = d.housing
    w = d.worm
    sr2 = d.shafts[1]
    lay = sr2.layout
    W = h.inner_width * MM
    delta = h.delta * MM
    delta1 = h.delta1 * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    b2 = h.flange_foot * MM
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    a = w.a * MM
    R = t.cover_r[0] * MM
    Ri = R - delta1
    cap = t.caps[0]
    brg = lay.bearing
    D2b, d2b = brg.D * MM, brg.d * MM
    rb2 = t.boss_r[0] * MM
    ins = t.inspection
    hw = ins.hole_width * MM / 2

    def ladd(name, qty, mat, note, at):
        add(name, qty, mat, note, v.P(*at), "TR" if at[0] < W / 2 - 1 else "FR")

    # ---------------- 箱座、箱盖（剖开）
    base = [(-L1, -D2b / 2), (0, -D2b / 2), (0, y_floor), (W, y_floor), (W, -D2b / 2), (W + L1, -D2b / 2),
            (W + L1, -rb2), (W + delta, -rb2), (W + delta, yb + b2), (W + delta + fw, yb + b2), (W + delta + fw, yb),
            (-delta - fw, yb), (-delta - fw, yb + b2), (-delta, yb + b2), (-delta, -rb2), (-L1, -rb2)]
    v.poly(base, close=True)
    v.hatch([base], 45)
    # 加强肋：纵向剖切，按不剖画出轮廓
    dep = t.rib_depth * MM
    for z_ in (-delta - dep, W + delta + dep):
        v.line((z_, yb + b2), (z_, -rb2))
    covers = []
    yp, wp = ins.center[1] * MM, ins.width * MM / 2  # 视孔平台顶面与半宽（无平台时 yp = R）
    for mirror in (False, True):
        Z = (lambda z: W - z) if mirror else (lambda z: z)  # noqa: E731
        pts = [(Z(-L1), D2b / 2), (Z(0), D2b / 2), (Z(0), Ri), (Z(W / 2 - hw), Ri), (Z(W / 2 - hw), yp),
               (Z(W / 2 - wp), yp), (Z(W / 2 - wp), R), (Z(-delta), R), (Z(-delta), rb2), (Z(-L1), rb2)]
        covers.append(pts)
        v.poly(pts, close=True)
    v.hatch(covers, 135)
    # 视孔盖（剖开）、垫片、通气器（不剖）
    Bw, th = ins.width * MM / 2, ins.thickness * MM
    plate = [(W / 2 - Bw, yp), (W / 2 + Bw, yp), (W / 2 + Bw, yp + th), (W / 2 - Bw, yp + th)]
    v.poly(plate, close=True)
    v.hatch([plate], 45, 1.5)
    vd = ins.vent_d * MM
    for hw_, n0, n1_ in ((0.6 * vd, th, th + 0.5 * vd), (0.9 * vd, th + 0.5 * vd, th + 0.9 * vd),
                         (0.45 * vd, th + 0.9 * vd, th + 1.4 * vd)):
        v.rect(W / 2 - hw_, yp + n0, W / 2 + hw_, yp + n1_)
    v.centerline((W / 2, yp - 3), (W / 2, yp + th + 1.4 * vd + 3), 0)

    # ---------------- 蜗轮轴（不剖）
    prev = None
    for seg in lay.segments:
        z0, z1 = seg.z0 * MM, seg.z1 * MM
        r = seg.d * MM / 2
        for sgn in (1, -1):
            v.line((z0, sgn * r), (z1, sgn * r))
        if prev is not None:
            rr = max(prev, r)
            v.line((z0, -rr), (z0, rr))
        prev = r
    v.line((lay.segments[0].z0 * MM, -lay.segments[0].d * MM / 2), (lay.segments[0].z0 * MM, lay.segments[0].d * MM / 2))
    v.line((lay.segments[-1].z1 * MM, -prev), (lay.segments[-1].z1 * MM, prev))
    v.centerline((lay.segments[0].z0 * MM, 0), (lay.segments[-1].z1 * MM, 0), 5)
    ladd(lay.name.split("（")[0], "1", "45", "", (lay.segments[-1].z1 * MM - 10, 0))
    end = next(sg for sg in lay.segments if sg.role == "端部")
    v.rect(end.z0 * MM, -end.d * MM, end.z1 * MM, end.d * MM, "细实线")

    # ---------------- 轴承（通用画法）
    bodies = _bearing_bodies(lay)
    ball = not isinstance(brg, standards.TaperedBearing)
    for zc, B in bodies:
        draw_bearing(v, zc, B, 0.0, d2b, D2b, next_angle(), ball)
    nm, std = _bearing_name(brg)
    ladd(nm, "2", "", std, (bodies[1][0], (d2b + D2b) / 4))

    # ---------------- 轴承盖、毡圈、调整垫片
    r_cap = cap.D2 * MM / 2
    for side, face in (("left", -L1), ("right", W + L1)):
        is_open = lay.extension == side
        sgz = -1 if side == "left" else 1
        za, zb = sorted((face, face + sgz * e))
        seal_r = lay.diameters["密封"] * MM / 2 + 1 if is_open else 0
        bz, B = bodies[0 if side == "left" else 1]
        bface = bz - B / 2 if side == "left" else bz + B / 2
        cap_section(v, face + sgz * e, face, bface, 0.0, r_cap, D2b / 2, seal_r, next_angle())
        if is_open:
            sdm = lay.diameters["密封"] * MM
            fz0, fz1 = za + e * 0.25, zb - e * 0.25
            for sgn in (1, -1):
                v.rect(fz0, sgn * sdm / 2, fz1, sgn * (sdm / 2 + 5), "细实线")
                v.line((fz0, sgn * sdm / 2), (fz1, sgn * (sdm / 2 + 5)), "细实线")
            ladd(f"毡圈 {sdm:g}", "1", "半粗羊毛毡", "JB/ZQ 4606-1997", ((fz0 + fz1) / 2, -sdm / 2 - 2.5))
        ladd("轴承透盖" if is_open else "轴承闷盖", "1", "HT200", "", ((za + zb) / 2, (seal_r + r_cap) / 2 + 2))
        if not is_open:
            ladd("调整垫片", "2组", "08F", "", (face, -r_cap + 3))

    # ---------------- 套筒
    g = next(gg for gg in lay.gears if gg.pair == "worm")
    zc = g.z * MM
    hub = g.width * MM
    s0, s1 = bodies[0][0] + bodies[0][1] / 2, zc - hub / 2
    if s1 - s0 > 1:
        sd_in = lay.diameters["轴承"] * MM / 2
        sd_out = sd_in + max(0.16 * sd_in, 4)
        ang = next_angle()
        for sgn in (1, -1):
            pts = [(s0, sgn * sd_in), (s1, sgn * sd_in), (s1, sgn * sd_out), (s0, sgn * sd_out)]
            v.poly(pts, close=True)
            v.hatch([pts], ang, 1.5)
        ladd("套筒", "1", "Q235", "", ((s0 + s1) / 2, -(sd_in + sd_out) / 2))

    # ---------------- 蜗轮（齿圈、轮芯剖开）
    gb = worm_blank.blank(w, g.seat_d, g.width)
    t2 = gb.key_t2 * MM
    ring_ang, core_ang = next_angle(), next_angle()
    rb = gb.bore * MM / 2
    worm_c = (W / 2, -a, w.da1 * MM / 2)
    for sgn in (1, -1):
        core = [(zc + z * MM, sgn * (r * MM if abs(r * MM - rb) > 1e-6 or sgn < 0 else rb + t2))
                for z, r in gb.core_profile()]
        v.poly(core, close=True)
        v.hatch([core], core_ang)
        # 齿圈剖面只画到齿根（轮齿不剖）
        hb = gb.b2 * MM / 2
        R_root = (gb.a - gb.df2 / 2) * MM
        root = [(zc + (-hb + 2 * hb * k / 24), sgn * (a - math.sqrt(max(R_root**2 - (-hb + 2 * hb * k / 24) ** 2, 0))))
                for k in range(25)]
        ri = gb.ring_inner_d * MM / 2
        sec = [(zc - hb, sgn * ri), (zc + hb, sgn * ri)] + list(reversed(root))
        v.poly(sec, close=True)
        v.hatch([sec], ring_ang)
        # 轮齿：齿顶（喉圆弧 + 外圆），下半部分被蜗杆遮住的部分不画
        tip = [(zc + z, sgn * gb.tip_r(z / MM) * MM) for z in [(-hb + 2 * hb * k / 40) for k in range(41)]]
        circles = [worm_c] if sgn < 0 else []
        for p, q in zip(tip, tip[1:]):
            for a_, b_ in hidden.visible_segments(p, q, circles):
                v.line(a_, b_)
        v.line((zc - hb, root[0][1]), (zc - hb, tip[0][1]))
        v.line((zc + hb, root[-1][1]), (zc + hb, tip[-1][1]))
        pitch_R = (gb.a - gb.d2 / 2) * MM
        pz = hb + 3
        pitch = [(zc + z, sgn * (a - math.sqrt(max(pitch_R**2 - z**2, 0)))) for z in
                 [(-pz + 2 * pz * k / 24) for k in range(25)]]
        v.poly(pitch, "点画线")
    # 键（不剖）
    seat = next(sg for sg in lay.segments if sg.role == "齿轮")
    kb_, t1_, kl_ = (x * MM for x in seat.keyway)
    zm = (seat.z0 + seat.z1) / 2 * MM
    rs = seat.d * MM / 2
    v.rect(zm - kl_ / 2, rs - t1_, zm + kl_ / 2, rs + t2)
    ladd("蜗轮齿圈", "1", w.material.name.split()[0], "", (zc + hb * 0.5, ri + 3))
    ladd("蜗轮轮芯", "1", "HT200", "", (zc - gb.web_thickness * MM / 4, (gb.hub_d * MM / 2 + gb.core_inner_d * MM / 2) / 2))
    screw_len = math.floor(gb.screw_depth * MM / 2) * 2
    add(f"紧定螺钉 M{gb.screw_d * MM:g}×{screw_len:g}", str(gb.screws), "45", "GB/T 71-2018")

    # ---------------- 蜗杆（横向剖切，画剖面线）与远处的蜗杆轴承座
    ra = w.da1 * MM / 2
    cz, cy = W / 2, -a
    loop = _circle_pts(cz, cy, ra, 72)
    v.poly(loop, close=True)
    v.hatch([loop], next_angle(), 2.0)
    v.circle((cz, cy), w.d1 * MM / 2, "点画线")
    v.centerline((cz - ra - 3, cy), (cz + ra + 3, cy), 0)
    v.centerline((cz, cy - ra - 3), (cz, cy + ra + 3), 0)
    # 远处（+x 一侧）蜗杆轴承座内凸台端面：在两侧内壁之间可见
    wb = t.worm_bore
    rw = wb.boss_r * MM
    for r_ in (rw, wb.D * MM / 2):
        pts = _circle_pts(cz, cy, r_, 96)
        for p, q in zip(pts, pts[1:]):
            if 0 <= p[0] <= W and 0 <= q[0] <= W and p[1] >= y_floor and q[1] >= y_floor:
                for a_, b_ in hidden.visible_segments(p, q, [(cz, cy, ra)]):
                    v.line(a_, b_)
    # 油面
    yo = t.oil_level * MM
    for z0, z1 in ((0, cz - ra - 2), (cz + ra + 2, W)):
        if z1 - z0 > 2:
            v.line((z0 + 1, yo), (z1, yo), "点画线")

    # ---------------- 前侧壁上的油标、放油螺塞（在剖切面后方，外形）
    (_, oy_), ang = t.dipstick
    oy_ *= MM
    zw = W + delta
    al = math.radians(ang)
    ux, uy = math.cos(al), math.sin(al)
    nx, ny = -uy, ux
    P = lambda s_, n_: (zw + ux * s_ + nx * n_, oy_ + uy * s_ + ny * n_)  # noqa: E731
    v.poly([P(0, -11), P(14, -11), P(14, 11), P(0, 11)])
    v.poly([P(14, -6), P(34, -6), P(34, 6), P(14, 6)])
    v.poly([P(34, -10), P(42, -10), P(42, 10), P(34, 10)], close=True)
    v.line(P(-6, 0), P(46, 0), "点画线")
    ladd("杆式油标 M12", "1", "Q235", "组合件", P(38, 4))
    dy = t.drain[1] * MM
    ddr = t.drain_d * MM
    v.rect(zw, dy - 0.9 * ddr, zw + 4, dy + 0.9 * ddr)
    v.rect(zw + 4, dy - 0.8 * ddr, zw + 14, dy + 0.8 * ddr)
    v.line((zw + 4, dy - 0.4 * ddr), (zw + 14, dy - 0.4 * ddr))
    v.line((zw + 4, dy + 0.4 * ddr), (zw + 14, dy + 0.4 * ddr))
    v.line((zw - 4, dy), (zw + 18, dy), "点画线")
    ladd(f"放油螺塞 M{ddr:g}×1.5", "1", "Q235", "JB/ZQ 4450-2006", (zw + 9, dy + 0.6 * ddr))
    ladd(f"封油垫 {ddr:g}", "1", "石棉橡胶纸", "", (zw + 2, dy - 0.6 * ddr))

    # ---------------- 键（数量汇总）
    keys: dict[str, int] = {}
    for srx in d.shafts:
        for k in srx.keys:
            nm_ = f"键 {k.size.b * MM:g}×{k.length * MM:g}"
            keys[nm_] = keys.get(nm_, 0) + k.count
    first = True
    for nm_, n in keys.items():
        if first and abs(kb_ - float(nm_.split()[1].split("×")[0])) < 1e-6:
            ladd(nm_, str(n), "45", "GB/T 1096-2003", (zm, rs + (t2 - t1_) / 2))
            first = False
        else:
            add(nm_, str(n), "45", "GB/T 1096-2003")


# ====================================================================== 俯视图（外形）

def _top(d, t: HousingDetail, v: View, sh: Sheet, add):
    h = d.housing
    ws = d.worm_shaft
    lay = d.shafts[1].layout
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    b1 = h.flange_cover * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    R = t.cover_r[0] * MM
    cap = t.caps[0]

    def tadd(name, qty, mat, note, at):
        add(name, qty, mat, note, v.P(*at), "TL")

    # 凸缘外缘、箱盖拱顶的轮廓
    v.rect(-delta - fw, xo0 - fw, W + delta + fw, xo1 + fw)
    xr = math.sqrt(max(R**2 - b1**2, 0))
    v.rect(-delta, -xr, W + delta, xr)
    # 蜗轮轴轴承座和轴承盖、轴伸、联轴器
    from gongke_core.drawing.assembly import boss_spans

    for a_, b_ in boss_spans(t):  # 轴承座与轴承旁凸台伸出凸缘外的部分
        for za, zb in ((-L1, -delta - fw), (W + delta + fw, W + L1)):
            v.rect(za, a_, zb, b_)
    r_cap = cap.D2 * MM / 2
    v.rect(-L1 - e, -r_cap, -L1, r_cap)
    v.rect(W + L1, -r_cap, W + L1 + e, r_cap)
    for seg in lay.segments:
        if seg.z0 * MM >= W + L1 + e - 1e-6:
            v.rect(seg.z0 * MM, -seg.d * MM / 2, seg.z1 * MM, seg.d * MM / 2)
        elif seg.z1 * MM > W + L1 + e:
            v.rect(W + L1 + e, -seg.d * MM / 2, seg.z1 * MM, seg.d * MM / 2)
    end = next(sg for sg in lay.segments if sg.role == "端部")
    v.rect(end.z0 * MM, -end.d * MM, end.z1 * MM, end.d * MM, "细实线")
    v.centerline((-L1 - e, 0), (lay.segments[-1].z1 * MM, 0), 4)
    # 蜗杆轴伸出凸缘外的部分与联轴器
    zc = W / 2
    x_edge = xo0 - fw
    for seg in ws.segments:
        x_a, x_b = seg.z0 * MM, seg.z1 * MM
        if x_a < x_edge:
            v.rect(zc - seg.d * MM / 2, x_a, zc + seg.d * MM / 2, min(x_b, x_edge))
    endw = next(sg for sg in ws.segments if sg.role == "端部")
    v.rect(zc - endw.d * MM, endw.z0 * MM, zc + endw.d * MM, endw.z1 * MM, "细实线")
    v.centerline((zc, ws.segments[0].z0 * MM), (zc, x_edge), 3)
    # 螺栓（头部）、定位销
    zf = (-delta - fw / 2, W + delta + fw / 2)
    for xb, dd in [(x, h.bolt_bearing) for x in t.bearing_bolts] + [(x, h.bolt_flange) for x in t.flange_bolts]:
        for zc_ in zf:
            hx = dd * MM
            pts = [(zc_ + hx * math.cos(math.radians(30 + 60 * k)), xb * MM + hx * math.sin(math.radians(30 + 60 * k)))
                   for k in range(7)]
            v.poly(pts)
            v.circle((zc_, xb * MM), dd * MM / 2 * 0.85, "细实线")
    pin_d = _std(t.pin_d * MM, PIN_D)
    for px, pz in t.pins:
        v.circle((pz * MM, px * MM), pin_d / 2)
        sh.cross(v.P(pz * MM, px * MM), pin_d / 2 * v.s, 1.5)
    pin_l = _std(b_total(h) + 8, PIN_L)
    px, pz = t.pins[0]
    tadd(f"圆锥销 A{pin_d}×{pin_l}", len(t.pins), "35", "GB/T 117-2000", (pz * MM, px * MM))
    # 视孔盖和通气器、吊环螺钉
    ins = t.inspection
    L, Bw = ins.length * MM, ins.width * MM
    v.rect(W / 2 - Bw / 2, -L / 2, W / 2 + Bw / 2, L / 2)
    for s_ in (-L / 2 + 10, L / 2 - 10):
        for zz in (W / 2 - Bw / 2 + 8, W / 2 + Bw / 2 - 8):
            v.circle((zz, s_), ins.screw_d * MM * 0.85)
    vd = ins.vent_d * MM
    v.circle((W / 2, 0), 0.9 * vd)
    v.circle((W / 2, 0), 0.45 * vd)
    ed = t.eyebolt_d * MM
    for xe in t.eyebolts:
        xe *= MM
        v.rect(W / 2 - 0.4 * ed, xe - 2.4 * ed, W / 2 + 0.4 * ed, xe + 2.4 * ed)
        v.circle((W / 2, xe), 1.1 * ed)


# ====================================================================== 配合尺寸

def _fits(d, t: HousingDetail, fv: View, lv: View, sh: Sheet):
    w, ws = d.worm, d.worm_shaft
    lay = d.shafts[1].layout
    a = w.a * MM
    front, left = [], []
    brg = ws.bearing
    xb = ws.bodies[1] * MM
    front.append(((xb, -a - brg.D * MM / 2), f"Ø{brg.D * MM:g}H7"))
    front.append(((xb - brg.T * MM / 2 - 1, -a - brg.d * MM / 2), f"Ø{brg.d * MM:g}k6"))
    end = next(s for s in ws.segments if s.role == "端部")
    front.append((((end.z0 + end.z1) / 2 * MM, -a - end.d * MM / 2), f"Ø{end.d * MM:g}k6"))
    bodies = _bearing_bodies(lay)
    b2 = lay.bearing
    zb, B = bodies[1]
    left.append(((zb, -b2.D * MM / 2), f"Ø{b2.D * MM:g}H7"))
    left.append(((zb + B / 2 + 1, -b2.d * MM / 2), f"Ø{b2.d * MM:g}k6"))
    g = next(gg for gg in lay.gears if gg.pair == "worm")
    left.append(((g.z * MM - g.width * MM / 2 + 3, g.seat_d * MM / 2), f"Ø{g.seat_d * MM:g}H7/r6"))
    gb = worm_blank.blank(w, g.seat_d, g.width)
    left.append(((g.z * MM + gb.b2 * MM / 2 - 2, gb.ring_inner_d * MM / 2), f"Ø{gb.ring_inner_d * MM:g}H7/r6"))
    end = next(s for s in lay.segments if s.role == "端部")
    left.append((((end.z0 + end.z1) / 2 * MM, -end.d * MM / 2), f"Ø{end.d * MM:g}k6"))
    for v, fits in ((fv, front), (lv, left)):
        for pt, txt in fits:
            tx, ty = v.P(*pt)
            dy = 9 if pt[1] > 0 else -9
            sh.leader_text((tx, ty), (tx + 6, ty + dy), txt, 3.0)
