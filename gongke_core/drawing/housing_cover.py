"""箱盖零件图（二级圆柱齿轮减速器）：主视图（外形）、俯视图、A-A 剖视（过低速轴轴承孔中心）。

结构尺寸来自 `layout.housing_detail`，与三维模型（`geometry.housing.cover`）、装配图和箱座零件图一致。
坐标：x 沿箱体长度，y 向上（剖分面 y = 0），z 沿轴线（内壁 z = 0～W）。视图按第一角投影配置。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.drawing import hidden
from gongke_core.drawing.assembly import PIN_D, _std
from gongke_core.drawing.housing_base import CLEARANCE, SPOT_FACE, _fmt, tolerances
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout.housing_detail import Arc, HousingDetail, detail, envelope_height

MM = 1e3
# 普通螺纹小径（GB/T 196-2003，粗牙）
MINOR = {6: 4.917, 8: 6.647, 10: 8.376, 12: 10.106, 16: 13.835}


def _tapped(v: View, sh: Sheet, c, d: float):
    """螺纹孔（端视）：小径粗实线圆，大径约 3/4 细实线圆，加十字中心线。"""
    v.circle(c, MINOR[round(d)] / 2)
    v.arc(c, d / 2, 0, 270, "细实线")
    sh.cross(v.P(*c), d / 2 * v.s, 1.5)


def draw(d, path: str | Path, drawing_no: str = "GK-04-02") -> Sheet:
    t = detail(d)
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    xo0, xo1 = (v * MM for v in t.x_outer)
    xs = [x * MM for x in t.shaft_x]
    ed = t.eyebolt_d * MM
    top = max(t.cover_top * MM, max(envelope_height(t.cover_outer, x) * MM + 0.4 * ed for x in t.eyebolts))
    ins = t.inspection
    top = max(top, ins.center[1] * MM + 5)

    x_min, x_max = xo0 - fw, xo1 + fw
    z_min, z_max = -max(L1, delta + fw), W + max(L1, delta + fw)
    front_w, front_h = x_max - x_min, top
    top_h = left_w = z_max - z_min
    chosen = None
    for size in ("A2", "A1", "A0"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        for sc in reversed(SCALES):
            if sc > 1:
                continue
            w_need = 45 + front_w * sc + 60 + left_w * sc + 45
            h_need = 40 + front_h * sc + 45 + top_h * sc + 30
            top_right = x0 + 45 + front_w * sc
            top_bottom = y1 - 40 - front_h * sc - 45 - top_h * sc - 20
            if w_need <= x1 - x0 and h_need <= y1 - y0 and (top_right <= x1 - 185 or top_bottom >= y0 + 60):
                chosen = sc
                break
        if chosen is not None and (chosen >= 1 / 2.5 or size == "A0"):
            break
    s = chosen or 1 / 5
    ox = x0 + 45 - x_min * s
    oy_f = y1 - 40 - top * s  # 剖分面
    front_bottom = oy_f - 22  # 剖分面以下留出尺寸位置
    oy_t = front_bottom - 25 + z_min * s
    front_right = ox + x_max * s
    ox_l = front_right + 60 - z_min * s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s)  # 用 (x, −z) 作图
    lv = View(sh, (ox_l, oy_f), s)

    tl = tolerances(d)
    _front(d, t, fv, sh, tl)
    _top(d, t, tv, sh)
    _left(d, t, lv, sh)
    xc = xs[-1]
    for zz, sg in ((z_min - 6, -1), (z_max + 6, 1)):
        p0, p1 = tv.P(xc, -zz), tv.P(xc, -(zz + sg * 5))
        sh.line(p0, p1, "图框")
        sh.arrow(p1, (p1[0] + 8, p1[1]), 2.5, "细实线")
        sh.text(p1[0] + 2, p1[1] + (1.5 if sg < 0 else -6.5), "A", 5)
    sh.section_label(lv.P(W / 2, 0)[0], oy_f + top * s + 8, "A")

    reqs = [
        "铸件应进行时效处理，消除内应力。",
        "铸件不得有砂眼、气孔、缩松、裂纹等缺陷。",
        "箱盖与箱座合箱后，先配作定位销孔并装入定位销，再一同镗轴承孔。",
        "合箱后剖分面用 0.05 mm 塞尺检查，塞入深度不大于剖分面宽度的 1/3。",
        "未注铸造圆角 R3～R5，未注拔模斜度 1:20。",
        "加工面未注倒角 C2；未注尺寸公差：加工面按 GB/T 1804-m，铸造面按 GB/T 6414-2017 DCTG10。",
        "箱盖内表面清理后涂耐油油漆，外表面涂底漆。",
    ]
    tx = max(ox + x_max * s + 30, lv.P(z_min, 0)[0] - 20)
    sh.tech_requirements(reqs, min(tx, x1 - 175), oy_f - 50)
    sh.frame(TitleInfo("箱盖", "HT200", s, "1", drawing_no), None, "毛坯")
    sh.save(path)
    return sh


# ====================================================================== 主视图（外形）

def _front(d, t: HousingDetail, v: View, sh: Sheet, tl: dict):
    h = d.housing
    s = v.s
    fw = t.flange_w * MM
    b1 = h.flange_cover * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xs = [x * MM for x in t.shaft_x]
    Ds = [c.D * MM for c in t.caps]
    rbs = [r * MM for r in t.boss_r]
    occ = [(x, 0.0, rb) for x, rb in zip(xs, rbs)]
    ed = t.eyebolt_d * MM

    def seg(p, q, layer="粗实线", circles=None):
        for a_, b_ in hidden.visible_segments(p, q, occ if circles is None else circles):
            v.line(a_, b_, layer)

    # 轴承座凸台（上半）与轴承孔
    for i, (x, D, rb) in enumerate(zip(xs, Ds, rbs)):
        others = [c for j, c in enumerate(occ) if j != i]
        for a0, a1 in hidden.visible_arcs(x, 0, rb, 0, 180, others):
            v.arc((x, 0), rb, a0, a1)
        v.arc((x, 0), D / 2, 0, 180)
        v.centerline((x, 0), (x, rb), 3)
    # 剖分面（下缘），轴承孔处断开
    xa = xo0 - fw
    for c0, c1 in sorted((x - D / 2, x + D / 2) for x, D in zip(xs, Ds)):
        v.line((xa, 0), (c0, 0))
        xa = c1
    v.line((xa, 0), (xo1 + fw, 0))
    seg((xo0 - fw, 0), (xo0 - fw, b1))
    seg((xo1 + fw, 0), (xo1 + fw, b1))
    seg((xo0 - fw, b1), (xo1 + fw, b1))
    # 箱盖外形（凸缘以上）
    for e in t.cover_outer:
        if isinstance(e, Arc):
            r = e.r * MM
            cut = math.degrees(math.asin(min(b1 / r, 1.0)))
            a0, a1 = max(e.a0, cut), min(e.a1, 180 - cut)
            if a1 > a0:
                for p0, p1 in hidden.visible_arcs(e.cx * MM, 0, r, a0, a1, occ):
                    v.arc((e.cx * MM, 0), r, p0, p1)
        else:
            seg((e.p[0] * MM, max(e.p[1] * MM, b1)), (e.q[0] * MM, max(e.q[1] * MM, b1)))
    # 吊环螺钉座（凸台）与螺纹孔（不可见）
    for xe in t.eyebolts:
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        v.rect(xe - 1.1 * ed, ye - 2, xe + 1.1 * ed, ye + 0.4 * ed)
        depth = 1.5 * ed
        for sg in (-1, 1):
            v.line((xe + sg * ed / 2, ye + 0.4 * ed), (xe + sg * ed / 2, ye + 0.4 * ed - depth), "虚线")
        v.centerline((xe, ye + 0.4 * ed), (xe, ye + 0.4 * ed - depth), 3)
    # 视孔（在倾斜的顶面上，孔壁不可见）
    ins = t.inspection
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    a = math.radians(ins.angle)
    ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    d1w = h.delta1 * MM
    for s_ in (-ins.hole_length * MM / 2, ins.hole_length * MM / 2):
        p = (cx + ux * s_, cy + uy * s_)
        v.line(p, (p[0] - nx * d1w, p[1] - ny * d1w), "虚线")
    # 连接螺栓孔、定位销孔、起盖螺钉孔（不可见，虚线）
    def hidden_hole(x, r):
        v.line((x - r, 0), (x - r, b1), "虚线")
        v.line((x + r, 0), (x + r, b1), "虚线")
        v.centerline((x, 0), (x, b1), 2)

    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    for xb in t.bearing_bolts:
        hidden_hole(xb * MM, CLEARANCE[d1] / 2)
    for xb in t.flange_bolts:
        hidden_hole(xb * MM, CLEARANCE[d2] / 2)
    pin = _std(t.pin_d * MM, PIN_D)
    for px, _ in t.pins:
        hidden_hole(px * MM, pin / 2)
    hidden_hole(t.jack_screw[0] * MM, MINOR[d2] / 2)

    # 尺寸
    yb_ = -10 / s
    for k, (xa_, xb_) in enumerate(zip(xs, xs[1:])):
        v.dim((xa_, 0), (xb_, 0), (xa_, yb_), 0, f"<>±{_fmt(tl['fa'][k])}", 0)
    v.dim((xo0 - fw, 0), (xs[0], 0), (xo0 - fw, yb_), 0, "<>", 1)
    top = t.cover_top * MM
    v.dim((xo1 + fw, 0), (xo1 + fw, b1), (xo1 + fw + 5 / s, 0), 90, "<>", 0)
    v.dim((xo1 + fw, 0), (xs[-1], top), (xo1 + fw + 14 / s, 0), 90, "<>", 0)
    # 各段圆弧半径
    for k, e in enumerate(t.cover_outer):
        if isinstance(e, Arc):
            r = e.r * MM
            am = math.radians((e.a0 + e.a1) / 2 if k else max(e.a0, 100))
            p = (e.cx * MM + r * math.cos(am), r * math.sin(am))
            P = v.P(*p)
            sh.leader_text(P, (P[0] + 10 * math.cos(am), P[1] + 10 * math.sin(am)), f"R{r:.0f}", 3.0)
    for i, (x, D) in enumerate(zip(xs, Ds)):
        a_ = math.radians(60)
        px, py = v.P(x + D / 2 * math.cos(a_), D / 2 * math.sin(a_))
        sh.leader_text((px, py), (px + 4, py - 8 - 4 * (i % 2)), f"Ø{D:g}H7", 3.0)
    # 表面结构：剖分面
    sh.roughness(*v.P(xo1 + fw * 0.6, 0), "Ra 3.2", 180, 3.0)


# ====================================================================== 俯视图

def _top(d, t: HousingDetail, v: View, sh: Sheet):
    h = d.housing
    s = v.s
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    b1 = h.flange_cover * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xs = [x * MM for x in t.shaft_x]
    rbs = [r * MM for r in t.boss_r]

    def L(p, q, layer="粗实线"):
        v.line((p[0], -p[1]), (q[0], -q[1]), layer)

    def C(c, r, layer="粗实线"):
        v.circle((c[0], -c[1]), r, layer)

    zf0, zf1 = -delta - fw, W + delta + fw
    # 凸缘外缘；轴承座凸台伸出凸缘的部分
    spans = []
    for x, rb in zip(xs, rbs):
        if spans and x - rb <= spans[-1][1]:
            spans[-1][1] = x + rb
        else:
            spans.append([x - rb, x + rb])
    protrude = L1 > delta + fw + 1e-6
    for z_edge, z_end in ((zf0, -L1), (zf1, W + L1)):
        xa = xo0 - fw
        for a, b_ in spans if protrude else []:
            L((xa, z_edge), (a, z_edge))
            xa = b_
        L((xa, z_edge), (xo1 + fw, z_edge))
    L((xo0 - fw, zf0), (xo0 - fw, zf1))
    L((xo1 + fw, zf0), (xo1 + fw, zf1))
    # 箱盖壳体两侧面（z = −δ、W + δ），被凸台盖住的地方断开
    left = min(xs[0] - math.sqrt(max((t.cover_r[0] * MM) ** 2 - b1**2, 0)), xs[0] - rbs[0])
    right = max(xs[-1] + math.sqrt(max((t.cover_r[-1] * MM) ** 2 - b1**2, 0)), xs[-1] + rbs[-1])
    for z in (-delta, W + delta):
        L((left, z), (right, z))
    L((left, -delta), (left, W + delta))
    L((right, -delta), (right, W + delta))
    # 凸台（从壳体侧面伸到凸台端面），轴承孔在剖分面上不可见
    for a, b_ in spans:
        for z0_, z1_ in ((-delta, -L1), (W + delta, W + L1)):
            L((a, z0_), (a, z1_))
            L((b_, z0_), (b_, z1_))
            L((a, z1_), (b_, z1_))
    for x in xs:
        L((x, -L1 - 4), (x, W + L1 + 4), "点画线")
    L((xo0 - fw - 4, W / 2), (xo1 + fw + 4, W / 2), "点画线")
    # 视孔与盖板螺钉孔
    ins = t.inspection
    cx = ins.center[0] * MM
    a = math.radians(ins.angle)
    hl = ins.hole_length * MM * math.cos(a) / 2
    hw = ins.hole_width * MM / 2
    for p, q in (((cx - hl, W / 2 - hw), (cx + hl, W / 2 - hw)), ((cx + hl, W / 2 - hw), (cx + hl, W / 2 + hw)),
                 ((cx + hl, W / 2 + hw), (cx - hl, W / 2 + hw)), ((cx - hl, W / 2 + hw), (cx - hl, W / 2 - hw))):
        L(p, q)
    Lc, Bw, sd = ins.length * MM, ins.width * MM, ins.screw_d * MM
    holes = [(cx + s_ * math.cos(a), W / 2 + zz) for s_ in (-Lc / 2 + 10, Lc / 2 - 10)
             for zz in (-(Bw / 2 - 8), Bw / 2 - 8)]
    for hx, hz in holes:
        _tapped(v, sh, (hx, -hz), sd)
    px, py = v.P(holes[-1][0], -holes[-1][1])
    sh.leader_text((px, py), (px + 10, py - 10), f"4×M{sd:g}-7H 深 {1.5 * sd + 3:g}", 3.0)
    px, py = v.P(cx + hl, -(W / 2 + hw))
    sh.leader_text((px, py), (px + 8, py - 24), f"视孔 {ins.hole_length * MM:g}×{ins.hole_width * MM:g}", 3.0)
    # 吊环螺钉孔
    ed = t.eyebolt_d * MM
    for xe in t.eyebolts:
        C((xe * MM, W / 2), 1.1 * ed)
        _tapped(v, sh, (xe * MM, -W / 2), ed)
    px, py = v.P(t.eyebolts[0] * MM, -W / 2)
    sh.leader_text((px + 1.1 * ed * s * 0.7, py + 1.1 * ed * s * 0.7), (px + 10, py + 14), f"2×M{ed:g}-7H 深 {1.5 * ed:g}", 3.0)
    # 连接螺栓孔（上面锪平）、定位销孔、起盖螺钉孔
    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    zr = (-delta - fw / 2, W + delta + fw / 2)
    for xb in t.bearing_bolts:
        for z in zr:
            C((xb * MM, z), CLEARANCE[d1] / 2)
            C((xb * MM, z), SPOT_FACE[d1] / 2, "细实线")
            sh.cross(v.P(xb * MM, -z), CLEARANCE[d1] / 2 * s, 1.5)
    for xb in t.flange_bolts:
        for z in zr:
            C((xb * MM, z), CLEARANCE[d2] / 2)
            C((xb * MM, z), SPOT_FACE[d2] / 2, "细实线")
            sh.cross(v.P(xb * MM, -z), CLEARANCE[d2] / 2 * s, 1.5)
    pin = _std(t.pin_d * MM, PIN_D)
    for px_, pz_ in t.pins:
        C((px_ * MM, pz_ * MM), pin / 2)
        sh.cross(v.P(px_ * MM, -pz_ * MM), pin / 2 * s, 1.5)
    jx, jz = (val * MM for val in t.jack_screw)
    _tapped(v, sh, (jx, -jz), d2)
    n1, n2 = 2 * len(t.bearing_bolts), 2 * len(t.flange_bolts)
    xb = t.bearing_bolts[0] * MM
    px, py = v.P(xb, -zr[1])
    sh.leader_text((px, py - CLEARANCE[d1] / 2 * s), (px + 6, py - 16), f"{n1}×Ø{CLEARANCE[d1]:g} 上面锪平Ø{SPOT_FACE[d1]:g}", 3.0)
    if t.flange_bolts:
        xb = t.flange_bolts[-1] * MM
        px, py = v.P(xb, -zr[0])
        sh.leader_text((px, py + CLEARANCE[d2] / 2 * s), (px + 8, py + 22),
                       f"{n2}×Ø{CLEARANCE[d2]:g} 上面锪平Ø{SPOT_FACE[d2]:g}", 3.0)
    px_, pz_ = t.pins[0]
    px, py = v.P(px_ * MM, -pz_ * MM)
    sh.leader_text((px, py), (px + 8, py + 10), f"2×锥销孔Ø{pin:g} 配作", 3.0)
    px, py = v.P(jx, -jz)
    sh.leader_text((px, py - MINOR[d2] / 2 * s), (px + 6, py - 14), f"M{d2:g}-7H 通（起盖螺钉）", 3.0)

    # 尺寸
    v.dim((xo0 - fw, -zf0), (xo0 - fw, -zf1), (xo0 - fw - 10 / s, 0), 90, "<>", 0)
    if protrude:
        x1b = xs[-1] + rbs[-1]
        v.dim((x1b, L1), (x1b, -W - L1), (xo1 + fw + 10 / s, 0), 90, "<>", 0)
    for x, cap in zip(xs, t.caps):
        near = [xb_ * MM for xb_ in t.bearing_bolts if abs(xb_ * MM - x) < cap.D2 * MM]
        if len(near) == 2:
            v.dim((near[0], -zr[0]), (near[1], -zr[0]), (near[0], -zf0 + 8 / s), 0, "<>", 0)


# ====================================================================== A-A 剖视

def _left(d, t: HousingDetail, v: View, sh: Sheet):
    h = d.housing
    s = v.s
    W = h.inner_width * MM
    delta = h.delta * MM
    L1 = h.bearing_seat_length * MM
    D = t.caps[-1].D * MM
    rb = t.boss_r[-1] * MM
    xc = t.shaft_x[-1]
    R = envelope_height(t.cover_outer, xc) * MM
    Ri = envelope_height(t.cover_inner, xc) * MM
    ed = t.eyebolt_d * MM
    eye = next((xe for xe in t.eyebolts if abs(xe - xc) < 1e-6), None)
    sec = [(-L1, D / 2), (0, D / 2), (0, Ri), (W, Ri), (W, D / 2), (W + L1, D / 2), (W + L1, rb), (W + delta, rb),
           (W + delta, R), (-delta, R), (-delta, rb), (-L1, rb)]
    loops = [sec]
    if eye is not None:
        # 剖切面通过吊环螺钉孔：顶部壁在孔处断开（按小径画剖面区域）
        r_in = MINOR[round(ed)] / 2
        top = R + 0.4 * ed
        sec = [(-L1, D / 2), (0, D / 2), (0, Ri), (W / 2 - r_in, Ri), (W / 2 - r_in, top), (W / 2 - 1.1 * ed, top),
               (W / 2 - 1.1 * ed, R), (-delta, R), (-delta, rb), (-L1, rb)]
        sec2 = [(W / 2 + r_in, Ri), (W, Ri), (W, D / 2), (W + L1, D / 2), (W + L1, rb), (W + delta, rb),
                (W + delta, R), (W / 2 + 1.1 * ed, R), (W / 2 + 1.1 * ed, top), (W / 2 + r_in, top)]
        loops = [sec, sec2]
        for sg in (-1, 1):
            v.line((W / 2 + sg * ed / 2, top), (W / 2 + sg * ed / 2, Ri), "细实线")
        sh.leader_text(v.P(W / 2 + ed / 2, top), (v.P(W / 2 + ed / 2, top)[0] + 8, v.P(0, top)[1] + 10),
                       f"M{ed:g}-7H", 3.0)
    for lp in loops:
        v.poly(lp, close=True)
    v.hatch(loops, 135)
    for z in (-L1, 0.0, W, W + L1):
        v.line((z, 0), (z, D / 2))
    v.line((-L1, 0), (W + L1, 0))
    v.line((W / 2, -4), (W / 2, R + 0.4 * ed + 4), "点画线")
    # 尺寸
    v.dim((0, Ri), (W, Ri), (0, Ri - 8 / s), 0, "<>", 0)
    v.dim((W, R), (W + delta, R), (W, R + 8 / s), 0, "<>", 0)
    v.dim((W, D / 2), (W + L1, D / 2), (W, -8 / s), 0, "<>", 0)
    v.dim((-L1, 0), (-L1, R), (-L1 - 10 / s, 0), 90, "<>", 0)
    tx, ty = v.P(W + L1, (D / 2 + rb) / 2)
    sh.roughness_leader((tx, ty), (tx + 10, ty + 10), "Ra 3.2", 3.0)
    tx, ty = v.P(W + L1 * 0.4, D / 2)
    sh.roughness_leader((tx, ty), (tx + 8, ty - 12), "Ra 1.6", 3.0)
