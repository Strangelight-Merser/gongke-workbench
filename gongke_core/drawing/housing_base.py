"""箱座零件图（二级圆柱齿轮减速器）：主视图（外形 + 右端壁局部剖）、俯视图（剖分面）、A-A 剖视（过低速轴轴承孔）。

结构尺寸全部来自 `layout.housing_detail`，与三维模型（`geometry.parts.housing_base`）和装配图一致。
坐标与布置计算相同：x 沿箱体长度，y 向上（剖分面 y = 0），z 沿轴线（内壁 z = 0～W）。
视图按第一角投影配置：俯视图在主视图下方（下方为前，即 +z），左视图在主视图右方（右方为前）。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.calc import tolerance as tol
from gongke_core.drawing import hidden
from gongke_core.drawing.assembly import PIN_D, _std
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout.housing_detail import HousingDetail, detail

MM = 1e3

# 螺栓通孔（GB/T 5277-1985 中等装配）和沉孔锪平直径（GB/T 152.4-1988，用于六角头螺栓和螺母），mm
CLEARANCE = {6: 6.6, 8: 9, 10: 11, 12: 13.5, 16: 17.5, 20: 22, 24: 26, 30: 33}
SPOT_FACE = {6: 13, 8: 18, 10: 22, 12: 26, 16: 33, 20: 40, 24: 48, 30: 61}
# 普通螺纹小径（GB/T 196-2003）：d − 1.0825P
MINOR = {12: 10.106, 16: 14.376}  # M12（粗牙）、M16×1.5


def _wavy(v: View, p, q, amp: float):
    """波浪线（局部剖视的分界线，细实线），从 p 到 q。"""
    L = math.dist(p, q)
    n = max(int(L / (8 * amp)), 2)
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    pts = [(p[0] + ux * L * k / (4 * n) - uy * amp * math.sin(math.pi * k / 2),
            p[1] + uy * L * k / (4 * n) + ux * amp * math.sin(math.pi * k / 2)) for k in range(4 * n + 1)]
    v.poly(pts, "细实线")


def tolerances(d) -> dict:
    """箱座图上的公差（mm）：各级中心距偏差 ±fa，相邻轴承孔轴线的平行度 fΣδ / fΣβ，各轴承孔圆柱度。"""
    lays = [s.layout for s in d.shafts]
    pairs = [d.high, d.low]
    out = {"fa": [], "parallel": [], "cyl": []}
    for k, pair in enumerate(pairs):
        q = pair.inp.grade
        out["fa"].append(tol.center_distance_fa(q, pair.a) * MM)
        lay = lays[k + 1]
        L = abs(lay.bearing_z[1] - lay.bearing_z[0])
        Fb = tol.helix_total_Fbeta(q, pair.d2, pair.b2)
        f_d, f_b = tol.axis_parallelism(L, pair.b2, Fb)
        out["parallel"].append((f_d * MM, f_b * MM))
    for lay in lays:
        out["cyl"].append(tol.housing_bore_cylindricity(lay.bearing.D) * MM)
    return out


def _fmt(v: float) -> str:
    """公差值写法：保留到 μm，去掉末尾的 0。"""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def draw(d, path: str | Path, drawing_no: str = "GK-04-01") -> Sheet:
    t = detail(d)
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    xo0, xo1 = (v * MM for v in t.x_outer)
    yb = t.y_bottom * MM
    xs = [x * MM for x in t.shaft_x]
    hook_out = 0.9 * fw

    # ------------------------------------------------ 图幅与比例
    x_min = xo0 - fw - (hook_out if t.hooks and min(t.hooks) * MM < xo0 + 1 else 0)
    x_max = xo1 + fw + (hook_out if t.hooks and max(t.hooks) * MM > xo1 - 1 else 0)
    z_min, z_max = -max(L1, delta + fw), W + max(L1, delta + fw)
    front_w, front_h = x_max - x_min, -yb
    top_h = z_max - z_min
    left_w = z_max - z_min
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
            if (w_need <= x1 - x0 and h_need <= y1 - y0
                    and (top_right <= x1 - 185 or top_bottom >= y0 + 60)):
                chosen = sc
                break
        if chosen is not None and (chosen >= 1 / 2.5 or size == "A0"):
            break
    s = chosen or 1 / 5
    ox = x0 + 45 - x_min * s
    oy_f = y1 - 40  # 剖分面
    front_bottom = oy_f + yb * s
    oy_t = front_bottom - 45 + z_min * s  # 俯视图：图上 Y = oy_t − z·s
    front_right = ox + x_max * s
    ox_l = front_right + 60 - z_min * s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s)  # 用 (x, −z) 作图
    lv = View(sh, (ox_l, oy_f), s)

    tl = tolerances(d)
    _front(d, t, fv, sh, tl)
    _top(d, t, tv, sh, tl)
    _left(d, t, lv, sh)
    # 剖切符号 A-A：在俯视图上沿低速轴轴线，从左向右看（箭头指向 +x）
    xc = xs[-1]
    for zz, sg in ((z_min - 6, -1), (z_max + 6, 1)):
        p0, p1 = tv.P(xc, -zz), tv.P(xc, -(zz + sg * 5))
        sh.line(p0, p1, "图框")
        sh.arrow(p1, (p1[0] + 8, p1[1]), 2.5, "细实线")
        sh.text(p1[0] + 2, p1[1] + (1.5 if sg < 0 else -6.5), "A", 5)
    sh.section_label(lv.P(W / 2, 0)[0], oy_f + 12, "A")

    # ------------------------------------------------ 技术要求
    reqs = [
        "铸件应进行时效处理，消除内应力。",
        "铸件不得有砂眼、气孔、缩松、裂纹等缺陷。",
        "箱座与箱盖合箱后，先配作定位销孔并装入定位销，再一同镗轴承孔。",
        "合箱后剖分面用 0.05 mm 塞尺检查，塞入深度不大于剖分面宽度的 1/3。",
        "未注铸造圆角 R3～R5，未注拔模斜度 1:20。",
        "加工面未注倒角 C2；未注尺寸公差：加工面按 GB/T 1804-m，铸造面按 GB/T 6414-2017 DCTG10。",
        "箱座内表面清理后涂耐油油漆，外表面涂底漆。",
    ]
    # 放在俯视图右侧、标题栏上方
    tx = max(ox + x_max * s + 30, lv.P(z_min, 0)[0] - 20)
    ty = front_bottom - 40
    sh.tech_requirements(reqs, min(tx, x1 - 175), ty)
    sh.frame(TitleInfo("箱座", "HT200", s, "1", drawing_no), None, "毛坯")
    sh.save(path)
    return sh


# ====================================================================== 主视图

def _front(d, t: HousingDetail, v: View, sh: Sheet, tl: dict):
    h = d.housing
    s = v.s
    delta = h.delta * MM
    fw = t.flange_w * MM
    b, b2 = h.flange_base * MM, h.flange_foot * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xi0, xi1 = (val * MM for val in h.x_range)
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    xs = [x * MM for x in t.shaft_x]
    Ds = [c.D * MM for c in t.caps]
    rbs = [r * MM for r in t.boss_r]
    occ = [(x, 0.0, rb) for x, rb in zip(xs, rbs)]

    def seg(p, q, layer="粗实线", circles=None):
        for a_, b_ in hidden.visible_segments(p, q, occ if circles is None else circles):
            v.line(a_, b_, layer)

    # ---------------- 轴承座凸台（前侧，伸出凸缘外，最靠近观察者）与轴承孔
    for i, (x, D, rb) in enumerate(zip(xs, Ds, rbs)):
        others = [c for j, c in enumerate(occ) if j != i]
        for a0, a1 in hidden.visible_arcs(x, 0, rb, 180, 360, others):
            v.arc((x, 0), rb, a0, a1)
        v.arc((x, 0), D / 2, 180, 360)
        v.centerline((x, 0), (x, -rb), 3)
    # 剖分面（上缘）：轴承孔处断开
    cuts = sorted((x - D / 2, x + D / 2) for x, D in zip(xs, Ds))
    xa = xo0 - fw
    for c0, c1 in cuts:
        v.line((xa, 0), (c0, 0))
        xa = c1
    v.line((xa, 0), (xo1 + fw, 0))
    # 凸缘、箱壁、底座
    seg((xo0 - fw, 0), (xo0 - fw, -b))
    seg((xo1 + fw, 0), (xo1 + fw, -b))
    seg((xo0 - fw, -b), (xo1 + fw, -b))
    seg((xo0, -b), (xo0, yb + b2))
    # 右端壁在局部剖视范围以上的部分
    dip = t.dipstick
    (dx_, dy_), ang = dip
    dy_ *= MM
    r_dip = 11.0
    y_sec = dy_ + r_dip * math.sqrt(2) + 3  # 局部剖视上边界（吊钩下端在其上方）
    seg((xo1, -b), (xo1, y_sec))
    xw0 = xi1 - 2 * delta  # 局部剖视左边界
    seg((xo0 - fw, yb + b2), (xw0, yb + b2))
    seg((xo0 - fw, yb), (xw0, yb))
    seg((xo0 - fw, yb), (xo0 - fw, yb + b2))
    # 吊钩（箱座两端铸出）
    for xe in t.hooks:
        pts, (hx, hy), hr = t.hook_shape(xe)
        pts = [(px * MM, py * MM) for px, py in pts]
        for p, q in zip(pts, pts[1:]):
            seg(p, q)
        v.circle((hx * MM, hy * MM), hr * MM)

    # ---------------- 连接螺栓孔、定位销孔、地脚螺栓孔（不可见，虚线）
    def hidden_hole(x, r, y0, y1):
        v.line((x - r, y0), (x - r, y1), "虚线")
        v.line((x + r, y0), (x + r, y1), "虚线")
        v.centerline((x, y0), (x, y1), 2)

    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    for xb in t.bearing_bolts:
        hidden_hole(xb * MM, CLEARANCE[d1] / 2, -b, 0)
    for xb in t.flange_bolts:
        hidden_hole(xb * MM, CLEARANCE[d2] / 2, -b, 0)
    pin = _std(t.pin_d * MM, PIN_D)
    for px, _ in t.pins:
        hidden_hole(px * MM, pin / 2, -b, 0)
    df = round(h.bolt_foot * MM)
    xf_ = sorted({round(x * MM, 3) for x, _ in t.foot_bolts})
    for xf in xf_:
        hidden_hole(xf, CLEARANCE[df] / 2, yb, yb + b2)
        sp = SPOT_FACE[df] / 2
        v.line((xf - sp, yb + b2 - 2), (xf + sp, yb + b2 - 2), "虚线")
    tx, ty = v.P(xf_[0] + CLEARANCE[df] / 2, yb + b2 / 2)
    n_foot = len(t.foot_bolts)
    sh.leader_text((tx, ty), (tx + 8, ty - 12), f"{n_foot}×Ø{CLEARANCE[df]:g} 上面锪平Ø{SPOT_FACE[df]:g}", 3.0)

    # ---------------- 右端壁局部剖视：放油螺塞孔、油标孔
    yd = t.drain[1] * MM
    rd_min, rd_maj = MINOR[16] / 2, 8.0
    ri_min, ri_maj = MINOR[12] / 2, 6.0
    c45 = math.cos(math.radians(ang))
    sn45 = math.sin(math.radians(ang))
    ox_ = xo1

    def P(s_, n_):  # 油标孔局部坐标：s 沿孔轴向外，n 垂直于孔轴
        return (ox_ + c45 * s_ - sn45 * n_, dy_ + sn45 * s_ + c45 * n_)

    def s_at_x(x, n_):  # 孔轴方向的直线 n = n_ 与竖直线 x 的交点
        return (x - ox_ + sn45 * n_) / c45

    boss_s = 14.0  # 与装配图中的油标座一致
    p1 = [(xw0, yb), (xo1 + fw, yb), (xo1 + fw, yb + b2), (xo1, yb + b2), (xo1, yd - rd_min), (xi1, yd - rd_min),
          (xi1, y_floor), (xw0, y_floor)]
    p2 = [(xi1, yd + rd_min), (xo1, yd + rd_min), P(s_at_x(xo1, -r_dip), -r_dip), P(boss_s, -r_dip), P(boss_s, -ri_min),
          P(s_at_x(xi1, -ri_min), -ri_min)]
    p3 = [P(s_at_x(xi1, ri_min), ri_min), P(boss_s, ri_min), P(boss_s, r_dip), P(s_at_x(xo1, r_dip), r_dip),
          (xo1, y_sec), (xi1, y_sec)]
    for lp in (p1, p2, p3):
        v.poly(lp, close=True)
    v.hatch([p1, p2, p3], 45)
    # 内螺纹大径（细实线）
    v.line((xi1, yd - rd_maj), (xo1, yd - rd_maj), "细实线")
    v.line((xi1, yd + rd_maj), (xo1, yd + rd_maj), "细实线")
    v.line(P(s_at_x(xi1, -ri_maj), -ri_maj), P(boss_s, -ri_maj), "细实线")
    v.line(P(s_at_x(xi1, ri_maj), ri_maj), P(boss_s, ri_maj), "细实线")
    v.line((xi1 - 4, yd), (xo1 + 6, yd), "点画线")
    v.line(P(s_at_x(xi1, 0) - 4, 0), P(boss_s + 6, 0), "点画线")
    _wavy(v, (xw0, yb), (xw0, y_floor), 1.0 / s)
    _wavy(v, (xi1, y_sec), (xo1, y_sec), 1.0 / s)
    # 放油孔外端面的沉孔锪平
    tx, ty = v.P(xo1, yd - rd_min)
    sh.leader_text((tx, ty), (tx + 10, ty - 10), "M16×1.5", 3.0)
    tx, ty = v.P(*P(boss_s, r_dip * 0.5))
    sh.leader_text((tx, ty), (tx + 10, ty + 8), "M12", 3.0)

    # ---------------- 尺寸
    top = 12 / s
    for k, (xa_, xb_) in enumerate(zip(xs, xs[1:])):
        v.dim((xa_, 0), (xb_, 0), (xa_, top), 0, f"<>±{_fmt(tl['fa'][k])}", 0)
    v.dim((xo0 - fw, 0), (xs[0], 0), (xo0 - fw, top), 0, "<>", 1)
    v.dim((xo0 - fw, yb), (xo1 + fw, yb), (xo0 - fw, yb - 14 / s), 0, "<>", 0)
    xr = xo1 + fw + (0.9 * fw if t.hooks else 0)
    v.dim((xo1 + fw, 0), (xo1 + fw, yb), (xr + 12 / s, 0), 90, "<>", 0)
    v.dim((xo1 + fw, -b), (xo1 + fw, 0), (xr + 4 / s, 0), 90, "<>", 0)
    v.dim((xo0 - fw, yb), (xo0 - fw, yb + b2), (xo0 - fw - 8 / s, yb), 90, "<>", 0)
    # 轴承孔直径
    for i, (x, D) in enumerate(zip(xs, Ds)):
        a = math.radians(-60)
        px, py = v.P(x + D / 2 * math.cos(a), D / 2 * math.sin(a))
        sh.leader_text((px, py), (px + 6, py - 14 - 4 * (i % 2)), f"Ø{D:g}H7", 3.0)
    # 表面结构：剖分面、轴承孔、底面
    xr_ = (xs[0] + xs[1]) / 2
    sh.roughness(*v.P(xr_, 0), "Ra 3.2", 0, 3.0)
    tx, ty = v.P((xo0 + xi0) / 2 + 20, yb)
    sh.roughness_leader((tx, ty), (tx - 12, ty - 10), "Ra 12.5", 3.0)
    # 剖分面平面度
    px, py = v.P(xo1 + fw / 2, 0)
    sh.arrow((px, py + 14), (px, py), 2.5, "细实线")
    sh.gtol(px - 4, py + 14, "flatness", "0.03")


# ====================================================================== 俯视图（剖分面）

def _top(d, t: HousingDetail, v: View, sh: Sheet, tl: dict):
    h = d.housing
    s = v.s
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xi0, xi1 = (val * MM for val in h.x_range)
    xs = [x * MM for x in t.shaft_x]
    Ds = [c.D * MM for c in t.caps]
    rbs = [r * MM for r in t.boss_r]

    def L(p, q, layer="粗实线"):  # 以 (x, z) 作图
        v.line((p[0], -p[1]), (q[0], -q[1]), layer)

    def C(c, r, layer="粗实线"):
        v.circle((c[0], -c[1]), r, layer)

    zf0, zf1 = -delta - fw, W + delta + fw
    # 轴承座凸台伸出凸缘外的部分（按 x 区间合并相邻凸台）
    spans = sorted((x - rb, x + rb) for x, rb in zip(xs, rbs))
    merged: list[list[float]] = []
    for a, b_ in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b_)
        else:
            merged.append([a, b_])
    protrude = L1 > delta + fw + 1e-6
    for z_edge, z_end in ((zf0, -L1), (zf1, W + L1)):
        xa = xo0 - fw
        for a, b_ in merged if protrude else []:
            L((xa, z_edge), (a, z_edge))
            L((a, z_edge), (a, z_end))
            L((b_, z_edge), (b_, z_end))
            # 凸台端面，轴承孔处断开
            xa2 = a
            for x, D in sorted(zip(xs, Ds)):
                if a <= x <= b_:
                    L((xa2, z_end), (x - D / 2, z_end))
                    xa2 = x + D / 2
            L((xa2, z_end), (b_, z_end))
            xa = b_
        L((xa, z_edge), (xo1 + fw, z_edge))
    L((xo0 - fw, zf0), (xo0 - fw, zf1))
    L((xo1 + fw, zf0), (xo1 + fw, zf1))
    # 内腔开口与轴承孔
    for z_wall in (0.0, W):
        xa = xi0
        for x, D in sorted(zip(xs, Ds)):
            L((xa, z_wall), (x - D / 2, z_wall))
            xa = x + D / 2
        L((xa, z_wall), (xi1, z_wall))
    L((xi0, 0), (xi0, W))
    L((xi1, 0), (xi1, W))
    for x, D in zip(xs, Ds):
        for zz0, zz1 in ((-L1 if protrude else zf0, 0.0), (W, W + L1 if protrude else zf1)):
            L((x - D / 2, zz0), (x - D / 2, zz1))
            L((x + D / 2, zz0), (x + D / 2, zz1))
        L((x, -L1 - 4), (x, W + L1 + 4), "点画线")
    L((xo0 - fw - 4, W / 2), (xo1 + fw + 4, W / 2), "点画线")
    # 螺栓孔、销孔、地脚螺栓孔（被凸缘挡住，虚线）
    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    zr = (-delta - fw / 2, W + delta + fw / 2)
    for xb in t.bearing_bolts:
        for z in zr:
            C((xb * MM, z), CLEARANCE[d1] / 2)
            sh.cross(v.P(xb * MM, -z), CLEARANCE[d1] / 2 * s, 1.5)
    for xb in t.flange_bolts:
        for z in zr:
            C((xb * MM, z), CLEARANCE[d2] / 2)
            sh.cross(v.P(xb * MM, -z), CLEARANCE[d2] / 2 * s, 1.5)
    pin = _std(t.pin_d * MM, PIN_D)
    for px, pz in t.pins:
        C((px * MM, pz * MM), pin / 2)
        sh.cross(v.P(px * MM, -pz * MM), pin / 2 * s, 1.5)
    df = round(h.bolt_foot * MM)
    for fx, fz in t.foot_bolts:
        C((fx * MM, fz * MM), CLEARANCE[df] / 2, "虚线")
    # 孔的标注
    n1, n2 = 2 * len(t.bearing_bolts), 2 * len(t.flange_bolts)
    xb = t.bearing_bolts[0] * MM
    px, py = v.P(xb, -zr[1])
    sh.leader_text((px, py - CLEARANCE[d1] / 2 * s), (px + 6, py - 16),
                   f"{n1}×Ø{CLEARANCE[d1]:g} 下面锪平Ø{SPOT_FACE[d1]:g}", 3.0)
    if t.flange_bolts:
        xb = t.flange_bolts[-1] * MM
        px, py = v.P(xb, -zr[1])
        px, py = v.P(xb, -zr[0])
        sh.leader_text((px, py + CLEARANCE[d2] / 2 * s), (px + 8, py + 22),
                       f"{n2}×Ø{CLEARANCE[d2]:g} 下面锪平Ø{SPOT_FACE[d2]:g}", 3.0)
    px_, pz_ = t.pins[0]
    px, py = v.P(px_ * MM, -pz_ * MM)
    sh.leader_text((px, py), (px + 8, py + 10), f"2×锥销孔Ø{pin:g} 配作", 3.0)

    # ---------------- 尺寸
    x_l = xo0 - fw - 10 / s
    v.dim((xo0 - fw, -zf0), (xo0 - fw, -zf1), (x_l, 0), 90, "<>", 0)
    v.dim((xi0, 0), (xi0, -W), (xi0 + 8 / s, 0), 90, "<>", 0)
    if protrude:
        x_r = xo1 + fw + 10 / s
        x1b = xs[-1] + rbs[-1]
        v.dim((x1b, L1), (x1b, -W - L1), (x_r, 0), 90, "<>", 0)
    # 轴承旁螺栓相对轴承孔中心的位置
    for x, cap in zip(xs, t.caps):
        near = [xb * MM for xb in t.bearing_bolts if abs(xb * MM - x) < cap.D2 * MM]
        if len(near) == 2:
            v.dim((near[0], -zr[0]), (near[1], -zr[0]), (near[0], -zf0 + 8 / s), 0, "<>", 0)
    # 表面结构：凸台端面（轴承盖贴合面）
    if protrude:
        x_ = xs[-1] + (Ds[-1] / 2 + rbs[-1]) / 2
        sh.roughness(*v.P(x_, L1), "Ra 3.2", 0, 3.0)
    # 轴承孔的基准与几何公差：第一根轴孔为基准 A，其余轴孔对前一根标平行度（垂直平面内 fΣβ）
    letters = "ABC"
    for i, (x, D) in enumerate(zip(xs, Ds)):
        z_ = W + 0.5 * (delta + fw / 2 - CLEARANCE[round(h.bolt_bearing * MM)] / 2)  # 内壁与螺栓孔之间
        px, py = v.P(x - D / 2, -z_)
        if i < len(xs) - 1:
            sh.datum(px, py, letters[i], "left", 3.0)
        if i > 0:
            fx, fy = v.P(x + D / 2, -(W + L1 if protrude else zf1))
            sh.arrow((fx + 8, fy - 12), (fx, fy), 2.5, "细实线")
            sh.gtol(fx + 8, fy - 19, "parallel", _fmt(tl["parallel"][i - 1][1]), letters[i - 1], 3.0)
            sh.gtol(fx + 8, fy - 26, "cylindricity", _fmt(tl["cyl"][i]), "", 3.0)
        else:
            fx, fy = v.P(x + D / 2, -(W + L1 if protrude else zf1))
            sh.arrow((fx + 8, fy - 12), (fx, fy), 2.5, "细实线")
            sh.gtol(fx + 8, fy - 19, "cylindricity", _fmt(tl["cyl"][0]), "", 3.0)


# ====================================================================== A-A 剖视（过低速轴轴承孔中心，从左向右看）

def _left(d, t: HousingDetail, v: View, sh: Sheet):
    h = d.housing
    s = v.s
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    b2 = h.flange_foot * MM
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    D = t.caps[-1].D * MM
    rb = t.boss_r[-1] * MM
    zl = -max(L1, delta + fw)
    base = [(-L1, -D / 2), (0, -D / 2), (0, y_floor), (W, y_floor), (W, -D / 2), (W + L1, -D / 2),
            (W + L1, -rb), (W + delta, -rb), (W + delta, yb + b2), (W + delta + fw, yb + b2), (W + delta + fw, yb),
            (-delta - fw, yb), (-delta - fw, yb + b2), (-delta, yb + b2), (-delta, -rb), (-L1, -rb)]
    v.poly(base, close=True)
    v.hatch([base], 45)
    # 剖切面后方：轴承孔孔壁两端、凸台端面、剖分面
    for z in (-L1, 0.0, W, W + L1):
        v.line((z, -D / 2), (z, 0))
    v.line((-L1, 0), (W + L1, 0))
    v.line((W / 2, yb - 4), (W / 2, 4), "点画线")
    # 右端壁内表面上的放油孔（正对观察者，螺纹孔画法：小径粗实线圆，大径细实线 3/4 圆）
    yd = t.drain[1] * MM
    v.circle((W / 2, yd), MINOR[16] / 2)
    v.arc((W / 2, yd), 8.0, 0, 270, "细实线")
    sh.cross(v.P(W / 2, yd), 8.0 * s, 1.5)
    # 油标孔与内壁的交线（斜孔，椭圆）
    (_, dy_), ang = t.dipstick
    yi = dy_ * MM - h.delta * MM * math.tan(math.radians(ang))
    ri = MINOR[12] / 2
    e = [(W / 2 + ri * math.cos(2 * math.pi * k / 48), yi + ri / math.cos(math.radians(ang)) * math.sin(2 * math.pi * k / 48))
         for k in range(49)]
    v.poly(e)
    # 尺寸
    v.dim((0, y_floor), (W, y_floor), (0, -D / 2 - 10 / s), 0, "<>", 0)
    v.dim((W, -rb), (W + delta, -rb), (W, -rb - 8 / s), 0, "<>", 0)
    v.dim((W, -D / 2), (W + L1, -D / 2), (W, 8 / s), 0, "<>", 0)
    v.dim((-delta - fw, yb), (W + delta + fw, yb), (-delta - fw, yb - 10 / s), 0, "<>", 0)
    v.dim((zl, 0), (zl, y_floor), (zl - 8 / s, 0), 90, "<>", 0)
    v.dim((zl, y_floor), (zl, yb), (zl - 8 / s, 0), 90, "<>", 0)
    tx, ty = v.P(W + L1, -(D / 2 + rb) / 2)
    sh.roughness_leader((tx, ty), (tx + 10, ty + 10), "Ra 3.2", 3.0)
