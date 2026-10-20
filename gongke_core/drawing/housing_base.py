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
from gongke_core.drawing.assembly import CLEARANCE, MINOR, PIN_D, SPOT_FACE, _std
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout.housing_detail import HousingDetail, detail

MM = 1e3

# 螺栓通孔（GB/T 5277-1985 中等装配）和沉孔锪平直径（GB/T 152.4-1988，用于六角头螺栓和螺母），mm
# 普通螺纹小径（GB/T 196-2003）：d − 1.0825P


def _wavy(v: View, p, q, amp: float):
    """波浪线，amp 为视图坐标下的波幅。"""
    v.wavy(p, q, amp * v.s)


def tolerances(d) -> dict:
    """箱体图上的公差（mm）：轴线沿 z 的相邻轴承孔之间的中心距偏差 ±fa、平行度 (fΣδ, fΣβ)，各轴承孔圆柱度。
    圆锥-圆柱减速器的Ⅰ轴沿 x，只有一级圆柱齿轮副；其座孔（套杯孔）的圆柱度放在 "side"。"""
    from gongke_core.drawing.assembly import _zshafts

    worm = getattr(d, "worm_shaft", None) is not None
    lays = [d.shafts[1].layout] if worm else [s.layout for s in _zshafts(d)]
    if worm:
        pairs = []
    else:
        pairs = [d.low] if getattr(d, "bevel", None) is not None else [d.high, d.low]
    out = {"fa": [], "parallel": [], "cyl": [], "side": None, "worm": None}
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
    t = detail(d)
    if t.side_bore is not None:
        out["side"] = tol.housing_bore_cylindricity(t.side_bore.D) * MM
    if worm:  # 蜗杆传动中心距偏差（GB/T 10089）、蜗杆座孔圆柱度
        from gongke_core.drawing.worm_assembly import _fa

        out["worm"] = (_fa(d.worm), tol.housing_bore_cylindricity(t.worm_bore.D) * MM)
    return out


def _vgap(L, x, z0, z1, gaps):
    """俯视图中沿 z 的直线（x 为常数），在 gaps 各区间处断开。"""
    za = z0
    for g0, g1 in sorted(gaps):
        if g0 > za:
            L((x, za), (x, g0))
        za = max(za, g1)
    if z1 > za:
        L((x, za), (x, z1))


def _front_side(t: HousingDetail, v: View, sgn: int):
    """主视图中左端壁外的小锥齿轮轴承座（圆锥-圆柱减速器）：sgn = −1 为箱座（下半），+1 为箱盖（上半）。
    凸台在凸缘以外可见，座孔为虚线。"""
    sb = t.side_bore
    xo0 = t.x_outer[0] * MM
    fw = t.flange_w * MM
    xf, rb, D = sb.x_face * MM, sb.boss_r * MM, sb.D * MM
    xi0 = t.h.x_range[0] * MM
    v.line((xf, 0), (xo0 - fw, 0))
    v.line((xf, sgn * rb), (xo0, sgn * rb))
    v.line((xf, 0), (xf, sgn * rb))
    v.line((xf, sgn * D / 2), (xi0, sgn * D / 2), "虚线")


def _side_bosses_front(t: HousingDetail, v: View, sgn: int, occ) -> list[tuple[float, float, float, float]]:
    """主视图中的轴承旁凸台（与轴承座端面平齐，只画合成外形）：sgn = −1 为箱座，+1 为箱盖。返回遮挡矩形。"""
    hb = t.boss_h * MM
    rects = [(a * MM, min(0, sgn * hb), b * MM, max(0, sgn * hb)) for a, b in t.side_bosses]
    for x0, y0, x1, y1 in rects:
        yo = sgn * hb
        for p, q in (((x0, 0), (x0, yo)), ((x0, yo), (x1, yo)), ((x1, yo), (x1, 0))):
            for a_, b_ in hidden.visible_segments(p, q, occ):
                v.line(a_, b_)
    return rects


def _ribs_front(t: HousingDetail, v: View, y_bottom: float, rects):
    """主视图中箱座前侧壁外的加强肋（轴承座正下方，正对观察者）。"""
    m = t.rib_t * MM
    for x, rb in zip(t.ribs, t.boss_r):
        y_top = -math.sqrt((rb * MM) ** 2 - (m / 2) ** 2)
        for sx in (-1, 1):
            p, q = (x * MM + sx * m / 2, y_top), (x * MM + sx * m / 2, y_bottom)
            for a_, b_ in hidden.visible_segments(p, q, (), rects):
                v.line(a_, b_)


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
    gap_ft = 57 if t.worm_bore is not None else 45  # 主视图与俯视图的间距（蜗杆方案主视图下方多一道尺寸）

    # ------------------------------------------------ 图幅与比例
    x_min = xo0 - fw - (hook_out if t.hooks and min(t.hooks) * MM < xo0 + 1 else 0)
    if t.side_bore is not None:
        x_min = min(x_min, t.side_bore.x_face * MM)
    if t.worm_bore is not None:
        x_min = min(x_min, -t.worm_bore.x_face * MM)
    x_max = xo1 + fw + (hook_out if t.hooks and max(t.hooks) * MM > xo1 - 1 else 0)
    if t.worm_bore is not None:
        x_max = max(x_max, t.worm_bore.x_face * MM)
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
            h_need = 40 + front_h * sc + gap_ft + top_h * sc + 30
            top_right = x0 + 45 + front_w * sc
            top_bottom = y1 - 40 - front_h * sc - gap_ft - top_h * sc - 20
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
    oy_t = front_bottom - gap_ft + z_min * s  # 俯视图：图上 Y = oy_t − z·s
    front_right = ox + x_max * s
    ox_l = front_right + 60 - z_min * s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s)  # 用 (x, −z) 作图
    lv = View(sh, (ox_l, oy_f), s)

    tl = tolerances(d)
    (_front_worm if t.worm_bore is not None else _front)(d, t, fv, sh, tl)
    _top(d, t, tv, sh, tl)
    _left(d, t, lv, sh)
    # 剖切符号 A-A：在俯视图上沿低速轴轴线，从左向右看（箭头指向 +x）
    xc = xs[-1]
    za = max(-z_min, delta + fw + 14 / s) + 6  # 让开俯视图上方的螺栓间距尺寸
    for zz, sg in ((-za, -1), (W + za, 1)):
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
    if t.side_bore is not None:
        reqs.insert(3, "左端壁上的小锥齿轮轴承座孔与箱盖合箱后镗出，其轴线应与Ⅱ轴座孔轴线垂直相交。")
    if t.worm_bore is not None:
        reqs.insert(3, "两端蜗杆轴承座孔应一次镗出，其轴线对蜗轮轴座孔轴线的垂直度按 GB/T 10089 的轴交角极限偏差 fΣ 控制。")
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
    blocks = _side_bosses_front(t, v, -1, occ)

    def seg(p, q, layer="粗实线", circles=None):
        for a_, b_ in hidden.visible_segments(p, q, occ if circles is None else circles, blocks):
            v.line(a_, b_, layer)

    # ---------------- 轴承座凸台、轴承旁凸台（前侧，伸出凸缘外，最靠近观察者）与轴承孔
    for i, (x, D, rb) in enumerate(zip(xs, Ds, rbs)):
        others = [c for j, c in enumerate(occ) if j != i]
        for a0, a1 in hidden.visible_arcs(x, 0, rb, 180, 360, others, blocks):
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
    _ribs_front(t, v, yb + b2, blocks)
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

    if t.side_bore is not None:
        _front_side(t, v, -1)

    # ---------------- 连接螺栓孔、定位销孔、地脚螺栓孔（不可见，虚线）
    def hidden_hole(x, r, y0, y1):
        v.line((x - r, y0), (x - r, y1), "虚线")
        v.line((x + r, y0), (x + r, y1), "虚线")
        v.centerline((x, y0), (x, y1), 2)

    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    hb = t.boss_h * MM
    for xb in t.bearing_bolts:
        hidden_hole(xb * MM, CLEARANCE[d1] / 2, -hb, 0)
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
    # 剖切面（z = W/2）正好通过底座凸缘的缺口，凸缘只剩缺口侧面的外形（不画剖面线）
    p1 = [(xw0, yb), (xo1, yb), (xo1, yd - rd_min), (xi1, yd - rd_min), (xi1, y_floor), (xw0, y_floor)]
    v.rect(xo1, yb, xo1 + fw, yb + b2)
    p2 = [(xi1, yd + rd_min), (xo1, yd + rd_min), P(s_at_x(xo1, -r_dip), -r_dip), P(boss_s, -r_dip), P(boss_s, -ri_min),
          P(s_at_x(xi1, -ri_min), -ri_min)]
    p3 = [P(s_at_x(xi1, ri_min), ri_min), P(boss_s, ri_min), P(boss_s, r_dip), P(s_at_x(xo1, r_dip), r_dip),
          (xo1, y_sec), (xi1, y_sec)]
    for lp in (p1, p2, p3):
        v.poly(lp, close=True)
    v.hatch([p1, p2, p3], 135)  # 与 45° 油标孔垂直，剖面线不与孔壁平行
    # 内螺纹大径（细实线）
    v.line((xi1, yd - rd_maj), (xo1, yd - rd_maj), "细实线")
    v.line((xi1, yd + rd_maj), (xo1, yd + rd_maj), "细实线")
    v.line(P(s_at_x(xi1, -ri_maj), -ri_maj), P(boss_s, -ri_maj), "细实线")
    v.line(P(s_at_x(xi1, ri_maj), ri_maj), P(boss_s, ri_maj), "细实线")
    v.line((xi1 - 4, yd), (xo1 + 6, yd), "点画线")
    v.line(P(s_at_x(xi1, 0) - 4, 0), P(boss_s + 6, 0), "点画线")
    _wavy(v, (xw0, yb), (xw0, max(y_floor, yb + b2)), 1.0 / s)
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
    xa_ = blocks[0][0]
    v.dim((xa_, -hb), (xa_, 0), (xa_ - 6 / s, 0), 90, "<>", 0)  # 轴承旁凸台高度
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


def _front_worm(d, t: HousingDetail, v: View, sh: Sheet, tl: dict):
    """蜗杆减速器箱座主视图：蜗杆轴线以上画外形，以下为过蜗杆轴线（z = W/2）的局部剖视，剖出两端蜗杆轴承座。"""
    h = d.housing
    s = v.s
    fw = t.flange_w * MM
    b, b2 = h.flange_base * MM, h.flange_foot * MM
    xo0, xo1 = (val * MM for val in t.x_outer)
    xi0, xi1 = (val * MM for val in h.x_range)
    yb = t.y_bottom * MM
    y_floor = h.y_range[0] * MM
    wb = t.worm_bore
    a = -wb.y * MM
    rw, hD = wb.boss_r * MM, wb.D * MM / 2
    xbi, xf = wb.x_inner * MM, wb.x_face * MM
    y_w = -a + rw + 12  # 局部剖视的上边界
    D = t.caps[0].D * MM
    rb = t.boss_r[0] * MM
    occ = [(0.0, 0.0, rb)]
    blocks = _side_bosses_front(t, v, -1, occ)

    def seg(p, q, layer="粗实线"):
        for a_, b_ in hidden.visible_segments(p, q, occ, blocks):
            v.line(a_, b_, layer)

    # ---------------- 外形：蜗轮轴轴承座凸台下半与座孔、轴承旁凸台、剖分面、凸缘、端壁、吊钩、加强肋
    for a0, a1 in hidden.visible_arcs(0, 0, rb, 180, 360, (), blocks):
        v.arc((0, 0), rb, a0, a1)
    _ribs_front(t, v, y_w, blocks)
    v.arc((0, 0), D / 2, 180, 360)
    v.centerline((0, 0), (0, -rb), 3)
    v.line((xo0 - fw, 0), (-D / 2, 0))
    v.line((D / 2, 0), (xo1 + fw, 0))
    seg((xo0 - fw, 0), (xo0 - fw, -b))
    seg((xo1 + fw, 0), (xo1 + fw, -b))
    seg((xo0 - fw, -b), (xo1 + fw, -b))
    seg((xo0, -b), (xo0, y_w))
    seg((xo1, -b), (xo1, y_w))
    for xe in t.hooks:
        pts, (hx, hy), hr = t.hook_shape(xe)
        pts = [(px * MM, py * MM) for px, py in pts]
        for p, q in zip(pts, pts[1:]):
            seg(p, q)
        v.circle((hx * MM, hy * MM), hr * MM)

    def hidden_hole(x, r, y0, y1):
        v.line((x - r, y0), (x - r, y1), "虚线")
        v.line((x + r, y0), (x + r, y1), "虚线")
        v.centerline((x, y0), (x, y1), 2)

    d1, d2 = round(h.bolt_bearing * MM), round(h.bolt_flange * MM)
    hb = t.boss_h * MM
    for xb in t.bearing_bolts:
        hidden_hole(xb * MM, CLEARANCE[d1] / 2, -hb, 0)
    for xb in t.flange_bolts:
        hidden_hole(xb * MM, CLEARANCE[d2] / 2, -b, 0)
    pin = _std(t.pin_d * MM, PIN_D)
    for px, _ in t.pins:
        if all(abs(px - xb) > 1e-6 for xb in t.flange_bolts):
            hidden_hole(px * MM, pin / 2, -b, 0)

    # ---------------- 局部剖视：两端壁与蜗杆轴承座、箱底、底座
    yt_, yb_ = -a + rw, -a - rw
    for sg in (-1, 1):
        xo_, xi_ = (xo0, xi0) if sg < 0 else (xo1, xi1)
        up = [(xo_, y_w), (xi_, y_w), (xi_, yt_), (sg * xbi, yt_), (sg * xbi, -a + hD), (sg * xf, -a + hD),
              (sg * xf, yt_), (xo_, yt_)]
        v.poly(up, close=True)
        v.hatch([up], 45)
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
    # 剖切面后方的半个座孔：两端孔口的轮廓线
    for x_ in (-xf, -xbi, xbi, xf):
        v.line((x_, -a - hD), (x_, -a + hD))
    _wavy(v, (xo0, y_w), (xo1, y_w), 1.0 / s)
    v.centerline((-xf, -a), (xf, -a), 5)

    # ---------------- 尺寸
    xl = min(xo0 - fw - (0.9 * fw if t.hooks else 0), -xf) - 10 / s
    v.dim((xo0 - fw, 0), (-xf, -a), (xl, 0), 90, f"<>±{_fmt(tl['worm'][0])}", 0)
    v.dim((xo0 - fw, yb), (xo1 + fw, yb), (xo0 - fw, yb - 14 / s), 0, "<>", 0)
    v.dim((-xf, -a - hD), (xf, -a - hD), (-xf, yb - 26 / s), 0, "<>", 0)
    yi = (-a - hD + y_floor) / 2
    v.dim((-xbi, -a - hD), (xbi, -a - hD), (-xbi, yi), 0, "<>", 0)
    xr = max(xo1 + fw + (0.9 * fw if t.hooks else 0), xf)
    v.dim((xo1 + fw, 0), (xo1 + fw, yb), (xr + 12 / s, 0), 90, "<>", 0)
    v.dim((xo1 + fw, -b), (xo1 + fw, 0), (xr + 4 / s, 0), 90, "<>", 0)
    xa_ = blocks[0][0]
    v.dim((xa_, -hb), (xa_, 0), (xa_ - 6 / s, 0), 90, "<>", 0)  # 轴承旁凸台高度
    v.dim((xo0 - fw, yb), (xo0 - fw, yb + b2), (xo0 - fw - 8 / s, yb), 90, "<>", 0)
    ang = math.radians(-60)
    px, py = v.P(D / 2 * math.cos(ang), D / 2 * math.sin(ang))
    sh.leader_text((px, py), (px + 6, py - 14), f"Ø{D:g}H7", 3.0)
    # 蜗杆座孔直径，圆柱度框格接在尺寸引线下方（两端座孔一次镗出）
    px, py = v.P(xf - 0.4 * (xf - xbi), -a + hD)
    sh.leader_text((px, py), (px - 10, py - 14), f"Ø{2 * hD:g}H7", 3.0, fixed=True)
    sh.line((px - 10, py - 14), (px - 10, py - 18), "细实线")
    sh.gtol(px - 10, py - 24, "cylindricity", _fmt(tl["worm"][1]), "", 3.0)
    # 表面结构：剖分面、蜗杆座孔端面、底面
    sh.roughness(*v.P(xi0 / 2, 0), "Ra 3.2", 0, 3.0)
    tx, ty = v.P(xf, yt_ - 0.3 * (rw - hD))
    sh.roughness_leader((tx, ty), (tx + 10, ty + 10), "Ra 3.2", 3.0)
    tx, ty = v.P((xo0 + xi0) / 2 + 20, yb)
    sh.roughness_leader((tx, ty), (tx - 12, ty - 10), "Ra 12.5", 3.0)
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
    # 轴承座凸台、轴承旁凸台伸出凸缘外的部分（按 x 区间合并）
    from gongke_core.drawing.assembly import boss_spans

    merged = boss_spans(t)
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
    sb = t.side_bore
    gap_f = gap_i = []
    if sb is not None:  # 左端壁上的小锥齿轮轴承座（剖分面上可见半个凸台和座孔）
        zc, rbs_, Ds_ = sb.z * MM, sb.boss_r * MM, sb.D * MM
        xf = sb.x_face * MM
        gap_f, gap_i = [(zc - rbs_, zc + rbs_)], [(zc - Ds_ / 2, zc + Ds_ / 2)]
        for zz in (zc - rbs_, zc + rbs_):
            L((xf, zz), (xo0 - fw, zz))
        L((xf, zc - rbs_), (xf, zc - Ds_ / 2))
        L((xf, zc + Ds_ / 2), (xf, zc + rbs_))
        for zz in (zc - Ds_ / 2, zc + Ds_ / 2):
            L((xf, zz), (xi0, zz))
        L((xf - 4, zc), (xi1, zc), "点画线")
    wb = t.worm_bore
    if wb is not None:  # 两端的蜗杆轴承座在凸缘下方（不可见）；伸出凸缘外的端面部分可见
        zc, rw = wb.z * MM, wb.boss_r * MM
        xf = wb.x_face * MM
        for sg in (-1, 1):
            xo_ = xo0 if sg < 0 else xo1
            lay = "虚线" if xf <= xo1 + fw else "粗实线"
            L((sg * xf, zc - rw), (sg * xf, zc + rw), lay)
            for zz in (zc - rw, zc + rw):
                L((xo_, zz), (sg * min(xf, xo1 + fw), zz), "虚线")
        L((-xf - 4, zc), (xf + 4, zc), "点画线")
    _vgap(L, xo0 - fw, zf0, zf1, gap_f)
    L((xo1 + fw, zf0), (xo1 + fw, zf1))
    # 内腔开口与轴承孔
    for z_wall in (0.0, W):
        xa = xi0
        for x, D in sorted(zip(xs, Ds)):
            L((xa, z_wall), (x - D / 2, z_wall))
            xa = x + D / 2
        L((xa, z_wall), (xi1, z_wall))
    _vgap(L, xi0, 0, W, gap_i)
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
    if t.worm_bore is not None:  # 主视图为局部剖视，地脚螺栓孔在此标注
        fx, fz = t.foot_bolts[-1]
        px, py = v.P(fx * MM + CLEARANCE[df] / 2 * 0.7, -fz * MM - CLEARANCE[df] / 2 * 0.7)
        sh.leader_text((px, py), (px + 8, py - 12),
                       f"{len(t.foot_bolts)}×Ø{CLEARANCE[df]:g} 上面锪平Ø{SPOT_FACE[df]:g}", 3.0)
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
    # 加强肋：纵向剖切，按不剖画出轮廓
    dep = t.rib_depth * MM
    for z_ in (-delta - dep, W + delta + dep):
        v.line((z_, yb + b2), (z_, -rb))
    # 剖切面后方：轴承孔孔壁两端、凸台端面、剖分面
    for z in (-L1, 0.0, W, W + L1):
        v.line((z, -D / 2), (z, 0))
    v.line((-L1, 0), (W + L1, 0))
    v.line((W / 2, yb - 4), (W / 2, 4), "点画线")
    if t.accessory_wall == "z":
        _left_worm_side(t, v)
    else:
        # 右端壁内表面上的放油孔（正对观察者，螺纹孔画法：小径粗实线圆，大径细实线 3/4 圆）
        yd = t.drain[1] * MM
        v.circle((W / 2, yd), MINOR[16] / 2)
        a_lo = math.degrees(math.asin(max((y_floor - yd) / 8.0, -1.0)))  # 大径圆在箱底剖面以下的部分被挡住
        v.arc((W / 2, yd), 8.0, 0, 180 - a_lo, "细实线")
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


def _left_worm_side(t: HousingDetail, v: View):
    """蜗杆减速器箱座 A-A 剖视中剖切面后方的部分：+x 端内凸台端面（蜗杆座孔）、前侧壁上的油标座和放油孔。"""
    h = t.h
    W = h.inner_width * MM
    delta = h.delta * MM
    y_floor = h.y_range[0] * MM
    wb = t.worm_bore
    cz, cy = wb.z * MM, wb.y * MM
    for r_ in (wb.boss_r * MM, wb.D * MM / 2):
        pts = [(cz + r_ * math.cos(2 * math.pi * k / 96), cy + r_ * math.sin(2 * math.pi * k / 96)) for k in range(97)]
        for p, q in zip(pts, pts[1:]):
            if 0 <= p[0] <= W and 0 <= q[0] <= W and p[1] >= y_floor and q[1] >= y_floor:
                v.line(p, q)
    v.centerline((cz - wb.D * MM / 2, cy), (cz + wb.D * MM / 2, cy), 3)
    # 油标座（在前侧壁外，45° 斜向上），螺纹孔不可见
    (_, oy_), ang = t.dipstick
    oy_ *= MM
    zw = W + delta
    c, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))

    def P(s_, n_):
        return (zw + c * s_ - sn * n_, oy_ + sn * s_ + c * n_)

    def s_at(z, n_):
        return (z - zw + sn * n_) / c

    r_b, r_h = 11.0, MINOR[12] / 2
    v.poly([P(s_at(zw, -r_b), -r_b), P(14, -r_b), P(14, r_b), P(s_at(zw, r_b), r_b)])
    for n_ in (-r_h, r_h):
        v.line(P(s_at(W, n_), n_), P(14, n_), "虚线")
    v.line(P(s_at(W, 0) - 3, 0), P(17, 0), "点画线")
    # 放油孔（在前侧壁内，不可见）
    yd = t.drain[1] * MM
    for yy in (yd - MINOR[16] / 2, yd + MINOR[16] / 2):
        v.line((W, yy), (zw, yy), "虚线")
    v.line((W - 3, yd), (zw + 3, yd), "点画线")
