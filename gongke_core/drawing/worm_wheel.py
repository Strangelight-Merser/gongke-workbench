"""蜗轮零件图（齿圈压配式）和蜗杆、蜗轮的参数表。

按 GB/T 4459.2 蜗轮规定画法：主视图通过轴线全剖，轮齿按不剖处理——齿顶（喉圆弧和外圆）、齿根圆弧用粗实线，
分度圆弧用点画线，圆弧都以蜗杆轴线为圆心；齿圈和轮芯是两个零件，剖面线方向相反。左视图画外圆 de2（粗实线）
和分度圆 d2（点画线），不画喉圆和齿根圆；同时表示轮芯挡肩、腹板减重孔和带键槽的轴孔。
结构尺寸来自 `layout.worm_blank`。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.calc.worm import WormPair
from gongke_core.drawing.gear import dms
from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale
from gongke_core.layout.worm_blank import WheelBlank, blank

MM = 1e3


def _f(v: float, nd: int = 3) -> str:
    t = f"{v * MM:.{nd}f}"
    return t.rstrip("0").rstrip(".") if "." in t else t


def param_rows(w: WormPair, member: int) -> list[list[str]]:
    """member = 1 为蜗杆，2 为蜗轮。"""
    common = [["模数", "m", _f(w.m)], ["齿形角", "α", "20°"]]
    grade = f"{w.inp.grade} GB/T 10089"
    if member == 1:
        return [
            ["蜗杆类型", "", "ZA（阿基米德）"],
            *common,
            ["头数", "z1", str(w.z1)],
            ["直径系数", "q", f"{w.q:g}"],
            ["分度圆直径", "d1", _f(w.d1)],
            ["导程角", "γ", dms(w.gamma)],
            ["螺旋方向", "", "右旋"],
            ["轴向齿距", "px", _f(math.pi * w.m)],
            ["导程", "pz", _f(math.pi * w.m * w.z1)],
            ["精度等级", "", grade],
            ["配对蜗轮齿数", "z2", str(w.z2)],
            ["中心距", "a", _f(w.a)],
        ]
    return [
        *common,
        ["齿数", "z2", str(w.z2)],
        ["变位系数", "x2", f"{w.x2:+.3f}".replace("+0.000", "0")],
        ["分度圆直径", "d2", _f(w.d2)],
        ["导程角", "γ", dms(w.gamma)],
        ["螺旋方向", "", "右旋"],
        ["精度等级", "", grade],
        ["配对蜗杆头数", "z1", str(w.z1)],
        ["中心距", "a", _f(w.a)],
    ]


def param_table(sh: Sheet, w: WormPair, member: int):
    x1, y1 = sh.inner[2], sh.inner[3]
    widths = [32, 14, 34]
    sh.table(x1 - sum(widths), y1, param_rows(w, member), widths, 7)


def _arc_pts(g: WheelBlank, R: float, z_max: float, n: int = 24) -> list[tuple[float, float]]:
    """以蜗杆轴线 (0, a) 为圆心、半径 R 的圆弧在 |z| ≤ z_max 内的点（mm，上半部分，r 从小到大的下侧弧）。"""
    a = g.a * MM
    zm = min(z_max, R)
    return [(-zm + 2 * zm * k / n, a - math.sqrt(max(R**2 - (-zm + 2 * zm * k / n) ** 2, 0.0))) for k in range(n + 1)]


def draw(w: WormPair, bore: float, hub_length: float, path: str | Path, title: str = "蜗轮", drawing_no: str = "",
         material: str = "ZCuSn10P1 / HT200") -> Sheet:
    g = blank(w, bore, hub_length)
    a = g.a * MM
    h = g.b2 * MM / 2
    de, da, d, df = g.de2 * MM, g.da2 * MM, g.d2 * MM, g.df2 * MM
    rb, rh = g.bore * MM / 2, g.hub_d * MM / 2
    ro, rc, rsd = g.ring_inner_d * MM / 2, g.core_inner_d * MM / 2, g.shoulder_d * MM / 2
    L = g.hub_length * MM / 2
    c = g.web_thickness * MM / 2
    z0 = -h - g.shoulder * MM
    kb, t2 = g.key_b * MM, g.key_t2 * MM
    zw = max(L, h + g.shoulder * MM)

    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        s = pick_scale(2 * zw + de + 70, de + 30, x1 - x0 - 150, y1 - y0 - 56 - 50)
        if s >= 0.5 or size == "A1":
            break
    main_cx = x0 + 45 + zw * s
    cy = y0 + 56 + 28 + de * s / 2 + 8
    left_cx = main_cx + zw * s + 55 + de * s / 2
    mv = View(sh, (main_cx, cy), s)
    lv = View(sh, (left_cx, cy), s)

    # ------------------------------------------------ 主视图（全剖）
    R_root = a - df / 2
    R_pitch = a - d / 2
    for sgn in (1, -1):
        F = lambda pts: [(x, sgn * y) for x, y in pts]  # noqa: E731
        rb_s = rb + t2 if sgn > 0 else rb  # 上半部分剖切面通过键槽：孔线抬高到键槽底
        if g.holes:
            h0, h1 = (g.hole_pcd - g.hole_d) * MM / 2, (g.hole_pcd + g.hole_d) * MM / 2
            core = [
                [(-L, rb_s), (L, rb_s), (L, rh), (c, rh), (c, h0), (-c, h0), (-c, rh), (-L, rh)],
                [(-c, h1), (c, h1), (c, rc), (h, rc), (h, ro), (-h, ro), (-h, rsd), (z0, rsd), (z0, rc), (-c, rc)],
            ]
        else:
            core = [[(-L, rb_s), (L, rb_s), (L, rh), (c, rh), (c, rc), (h, rc), (h, ro), (-h, ro), (-h, rsd),
                     (z0, rsd), (z0, rc), (-c, rc), (-c, rh), (-L, rh)]]
        if rc <= rh + 1e-6:  # 实心轮芯
            core = [[(-L, rb_s), (L, rb_s), (L, rh), (h, rh), (h, ro), (-h, ro), (-h, rsd), (z0, rsd), (z0, rh),
                     (-L, rh)]]
        core = [F(lp) for lp in core]
        for lp in core:
            mv.poly(lp, close=True)
        mv.hatch(core, 45)
        root = _arc_pts(g, R_root, h)
        ring = F([(-h, ro), (h, ro)] + list(reversed(root)))
        mv.poly(ring, close=True)
        mv.hatch([ring], 135)
        # 轮齿（不剖）：外圆、喉圆弧、两侧端面
        tip = [(z, g.tip_r(z / MM) * MM) for z in [(-h + 2 * h * k / 40) for k in range(41)]]
        mv.poly(F(tip))
        mv.line((-h, sgn * root[0][1]), (-h, sgn * tip[0][1]))
        mv.line((h, sgn * root[-1][1]), (h, sgn * tip[-1][1]))
        pitch = _arc_pts(g, R_pitch, h + 3 / s)
        mv.poly(F(pitch), "点画线")
        if g.holes:
            for x in (-c, c):
                mv.line((x, sgn * h0), (x, sgn * h1))
            mv.centerline((-c - 2, sgn * g.hole_pcd * MM / 2), (c + 2, sgn * g.hole_pcd * MM / 2), 2)
        # 紧定螺钉孔（螺纹孔，粗实线为小径、细实线为大径，在 +z 端面）
        rs, ds, ls = g.screw_r * MM, g.screw_d * MM, g.screw_depth * MM
        for k, lay in ((0.85, "粗实线"), (1.0, "细实线")):
            mv.line((h - ls, sgn * (rs - ds / 2 * k)), (h, sgn * (rs - ds / 2 * k)), lay)
            mv.line((h - ls, sgn * (rs + ds / 2 * k)), (h, sgn * (rs + ds / 2 * k)), lay)
        mv.line((h - ls, sgn * (rs - ds / 2 * 0.85)), (h - ls, sgn * (rs + ds / 2 * 0.85)))
        mv.centerline((h - ls - 1, sgn * rs), (h + 1, sgn * rs), 2)
    mv.centerline((-zw, 0), (zw, 0), 5)
    # 蜗杆轴线（喉圆圆心）
    mv.centerline((-6 / s, a), (6 / s, a), 2)

    # 主视图尺寸
    mv.dim((-h, de / 2), (h, de / 2), (-h, de / 2 + 10 / s), 0, "<>", 0)
    xd = zw + 12 / s
    mv.dim((h, -de / 2), (h, de / 2), (xd, 0), 90, "%%c<>", 0)
    mv.dim((0, -da / 2), (0, da / 2), (xd + 13 / s, 0), 90, "%%c<>h11", 2)
    mv.dim((-L, -rb), (-L, rb), (-zw - 8 / s, 0), 90, "%%c<>H7", 0)
    mv.dim((-L, -rh), (-L, rh), (-zw - 20 / s, 0), 90, "%%c<>", 0)
    mv.dim((-h, -ro), (-h, ro), (-zw - 32 / s, 0), 90, "%%c<>H7/r6", 0)
    mv.dim((-L, -rh), (L, -rh), (-L, -de / 2 - 10 / s), 0, "<>", 0)
    if rc > rh:
        mv.dim((-c, -rc), (c, -rc), (-c, -de / 2 - 20 / s), 0, "<>", 0)
    # 喉圆半径 rg2：引出标注，箭头指向喉部
    tx, ty = mv.P(0, da / 2)
    sh.leader_text((tx, ty), (tx + 10, ty + 18), f"R{_f(g.rg2, 1)}")
    sh.leader_text(mv.P(0, a), (tx + 10, ty + 30), f"蜗杆轴线 a={_f(g.a, 0)}", 3.0)
    # 表面结构
    sh.roughness(*mv.P(-L * 0.4, -rb), "Ra 1.6", 0, 3.0)
    sh.roughness(*mv.P(-h * 0.55, g.tip_r(h * 0.55) * MM), "Ra 1.6", 0, 3.0)
    sh.roughness(*mv.P(-h, (ro + rsd) / 2 + 2), "Ra 3.2", 90, 3.0)
    # 基准与跳动
    sh.datum(*mv.P(L * 0.5, -rb), "A", "up")
    px, py = mv.P(h * 0.6, de / 2)
    sh.arrow((px + 8, py + 22), (px, py), 2.5, "细实线")
    sh.gtol(px + 8, py + 22, "runout", "0.050", "A")
    px, py = mv.P(h, -(ro + rsd) / 2)
    sh.arrow((px + 12, py - 12), (px, py), 2.5, "细实线")
    sh.gtol(px + 12, py - 19, "runout", "0.025", "A")

    # ------------------------------------------------ 左视图（从 −z 一侧看）
    lv.circle((0, 0), de / 2)
    lv.circle((0, 0), d / 2, "点画线")
    lv.circle((0, 0), rsd)
    if rc > rh:
        lv.circle((0, 0), rc)
    lv.circle((0, 0), rh)
    if g.holes:
        lv.circle((0, 0), g.hole_pcd * MM / 2, "点画线")
        for k in range(g.holes):
            ang = 2 * math.pi * k / g.holes
            cc = (g.hole_pcd * MM / 2 * math.cos(ang), g.hole_pcd * MM / 2 * math.sin(ang))
            lv.circle(cc, g.hole_d * MM / 2)
            sh.cross(lv.P(*cc), g.hole_d * MM / 2 * s, 1.5)
        lv.dim((-g.hole_d * MM / 2, -g.hole_pcd * MM / 2), (g.hole_d * MM / 2, -g.hole_pcd * MM / 2),
               (0, -g.hole_pcd * MM / 2 - g.hole_d * MM / 2 - 6 / s), 0, f"{g.holes}×%%c<>", 0)
        lv.dim((-g.hole_pcd * MM / 2, 0), (g.hole_pcd * MM / 2, 0), (0, rsd + 4 / s), 0, "%%c<>", 0)
    hb = kb / 2
    ang = math.degrees(math.asin(hb / rb))
    sh.arc(lv.P(0, 0), rb * s, 90 + ang, 90 - ang + 360)
    yb = math.sqrt(rb**2 - hb**2)
    lv.line((-hb, yb), (-hb, rb + t2))
    lv.line((hb, yb), (hb, rb + t2))
    lv.line((-hb, rb + t2), (hb, rb + t2))
    sh.cross(lv.P(0, 0), de / 2 * s, 4)
    lv.dim((-hb, rb + t2), (hb, rb + t2), (-hb, rb + t2 + 8 / s), 0, "<>JS9", 0)
    lv.dim((hb, -rb), (hb, rb + t2), (rh + 8 / s, 0), 90, "<>", 1)
    sh.roughness(*lv.P(hb, rb + t2), "Ra 3.2", 0, 2.5)

    # ------------------------------------------------ 参数表、图框
    param_table(sh, w, 2)
    screw_len = math.floor(g.screw_depth * MM / 2) * 2
    reqs = [f"齿圈 {w.material.name.split()[0]}（{w.material.casting}），轮芯 HT200。",
            "齿圈与轮芯按 H7/r6 压配后，精车齿顶和端面，再切制轮齿。",
            f"接缝处钻孔攻螺纹，装 {g.screws} 个紧定螺钉 M{g.screw_d * MM:g}×{screw_len:g}（GB/T 71），"
            "螺钉头部低于端面。",
            "未注倒角 C2，未注铸造圆角 R3～5。",
            "未注尺寸公差按 GB/T 1804-m。"]
    sh.frame(TitleInfo(title, material, s, "1", drawing_no), reqs, "Ra 6.3")
    sh.save(path)
    return sh
