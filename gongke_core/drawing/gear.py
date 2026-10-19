"""圆柱齿轮零件图。

按 GB/T 4459.2 齿轮规定画法：主视图通过轴线全剖，轮齿按不剖处理（齿顶线、齿根线用粗实线，不画剖面线），
分度线用点画线；左视图画齿顶圆、分度圆、轮毂、减重孔和带键槽的轴孔。右上角为齿轮参数表。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.calc.gear import GearPair, transverse_pressure_angle
from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale
from gongke_core.layout.gear_blank import GearBlank, blank


def _inv(a: float) -> float:
    return math.tan(a) - a


def base_tangent_length(z: int, mn: float, alpha_n: float, beta: float) -> tuple[float, int]:
    """公法线长度 Wk 与跨测齿数 k（斜齿轮按假想齿数 z' = z·inv αt / inv αn 计算）。

    Wk = mn cos αn [π(k − 0.5) + z' inv αn]，k = round(αn z'/180° + 0.5)。
    """
    at = transverse_pressure_angle(alpha_n, beta)
    zp = z * _inv(at) / _inv(alpha_n)
    k = max(2, round(math.degrees(alpha_n) / 180 * zp + 0.5))
    w = mn * math.cos(alpha_n) * (math.pi * (k - 0.5) + zp * _inv(alpha_n))
    return w, k


def dms(rad: float) -> str:
    deg = math.degrees(rad)
    d = int(deg)
    m = int((deg - d) * 60)
    s = round(((deg - d) * 60 - m) * 60)
    if s == 60:
        m, s = m + 1, 0
    return f"{d}°{m:02d}′{s:02d}″"


def param_rows(pair: GearPair, member: int) -> list[list[str]]:
    z = pair.z1 if member == 1 else pair.z2
    mate = pair.z2 if member == 1 else pair.z1
    w, k = base_tangent_length(z, pair.mn, pair.alpha_n, pair.beta)
    f = lambda v: f"{v * 1e3:g}"
    return [
        ["法向模数", "mn", f(pair.mn)],
        ["齿数", "z", str(z)],
        ["法向压力角", "αn", f"{pair.inp.alpha_n_deg:g}°"],
        ["齿顶高系数", "ha*", "1"],
        ["螺旋角", "β", dms(pair.beta)],
        ["螺旋方向", "", "右旋" if member == 1 else "左旋"],
        ["精度等级", "", f"{pair.inp.grade} GB/T 10095.1"],
        ["公法线长度", "Wk", f"{w * 1e3:.3f}"],
        ["跨测齿数", "k", str(k)],
        ["配对齿轮齿数", "", str(mate)],
        ["中心距", "a", f(pair.a)],
    ]


def param_table(sh: Sheet, pair: GearPair, member: int):
    x1, y1 = sh.inner[2], sh.inner[3]
    widths = [32, 14, 34]
    sh.table(x1 - sum(widths), y1, param_rows(pair, member), widths, 7)


def _section_loops(g: GearBlank) -> list[list[tuple[float, float]]]:
    """主视图上半部分的剖面区域（mm），下半部分镜像。不含轮齿。"""
    b = g.b * 1e3 / 2
    rb = g.bore * 1e3 / 2
    rf = g.df * 1e3 / 2
    if not g.web:
        return [[(-b, rb), (b, rb), (b, rf), (-b, rf)]]
    rh = g.hub_d * 1e3 / 2
    r2 = g.rim_inner_d * 1e3 / 2
    c = g.web_thickness * 1e3 / 2
    h0, h1 = (g.hole_pcd - g.hole_d) * 1e3 / 2, (g.hole_pcd + g.hole_d) * 1e3 / 2
    # 剖切面通过减重孔：腹板在孔处断开
    return [
        [(-b, rb), (b, rb), (b, rh), (c, rh), (c, h0), (-c, h0), (-c, rh), (-b, rh)],
        [(-c, h1), (c, h1), (c, r2), (b, r2), (b, rf), (-b, rf), (-b, r2), (-c, r2)],
    ]


def draw(pair: GearPair, member: int, bore: float, path: str | Path, title: str, drawing_no: str = "",
         material: str = "45") -> Sheet:
    g = blank(pair, member, bore)
    da, d, df, b = g.da * 1e3, g.d * 1e3, g.df * 1e3, g.b * 1e3
    rb = g.bore * 1e3 / 2
    t2 = g.key_t2 * 1e3
    kb = g.key_b * 1e3

    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        avail_w = (x1 - x0 - 140) / (1 + 1.6)  # 主视图宽 b，左视图宽 da，按比例分配
        s = pick_scale(b + da + 60, da + 20, x1 - x0 - 150, y1 - y0 - 56 - 50)
        if s >= 0.5 or size == "A1":
            break
    main_cx = x0 + 30 + b * s / 2 + 20
    cy = y0 + 56 + 25 + da * s / 2 + 10
    left_cx = main_cx + b * s / 2 + 50 + da * s / 2
    mv = View(sh, (main_cx, cy), s)
    lv = View(sh, (left_cx, cy), s)

    # ------------------------------------------------ 主视图（全剖）
    for sgn in (1, -1):
        loops = _section_loops(g)
        if sgn < 0:
            loops = [[(x, -y) for x, y in loop] for loop in loops]
        else:
            # 上半部分剖切面通过键槽：轴孔线抬高到键槽底
            loops = [[(x, rb + t2 if abs(y - rb) < 1e-6 else y) for x, y in loop] for loop in loops]
        for loop in loops:
            mv.poly(loop, close=True)
        mv.hatch(loops)
        ra, rf, rp = da / 2 * sgn, df / 2 * sgn, d / 2 * sgn
        mv.line((-b / 2, rf), (-b / 2, ra))
        mv.line((b / 2, rf), (b / 2, ra))
        mv.line((-b / 2, ra), (b / 2, ra))
        mv.line((-b / 2 - 3 / s, rp), (b / 2 + 3 / s, rp), "点画线")
    mv.centerline((-b / 2, 0), (b / 2, 0), 5)
    if g.web:
        # 剖切面后方可见的减重孔孔壁（腹板两侧面在孔处的轮廓线）
        c = g.web_thickness * 1e3 / 2
        h0, h1 = (g.hole_pcd - g.hole_d) * 1e3 / 2, (g.hole_pcd + g.hole_d) * 1e3 / 2
        for sgn in (1, -1):
            for x in (-c, c):
                mv.line((x, sgn * h0), (x, sgn * h1))
        mv.centerline((-g.web_thickness * 1e3 / 2 - 2, g.hole_pcd * 1e3 / 2), (g.web_thickness * 1e3 / 2 + 2, g.hole_pcd * 1e3 / 2), 2)
        mv.centerline((-g.web_thickness * 1e3 / 2 - 2, -g.hole_pcd * 1e3 / 2), (g.web_thickness * 1e3 / 2 + 2, -g.hole_pcd * 1e3 / 2), 2)

    # 主视图尺寸
    mv.dim((-b / 2, da / 2), (b / 2, da / 2), (-b / 2, da / 2 + 10 / s), 0, "<>", 0)
    xd = b / 2 + 14 / s
    mv.dim((b / 2, -da / 2), (b / 2, da / 2), (xd, 0), 90, "%%c<>h11", 2)
    mv.dim((b / 2, -d / 2), (b / 2, d / 2), (xd + 12 / s, 0), 90, "%%c<>", 2)
    mv.dim((-b / 2, -rb), (-b / 2, rb), (-b / 2 - 8 / s, 0), 90, "%%c<>H7", 0)
    if g.web:
        mv.dim((-b / 2, -g.hub_d * 1e3 / 2), (-b / 2, g.hub_d * 1e3 / 2), (-b / 2 - 20 / s, 0), 90, "%%c<>", 0)
        mv.dim((-b / 2, -g.rim_inner_d * 1e3 / 2), (-b / 2, g.rim_inner_d * 1e3 / 2), (-b / 2 - 32 / s, 0), 90, "%%c<>", 0)
        c = g.web_thickness * 1e3 / 2
        mv.dim((-c, -g.rim_inner_d * 1e3 / 2), (c, -g.rim_inner_d * 1e3 / 2), (-c, -da / 2 - 10 / s), 0, "<>", 0)
    # 表面结构
    sh.roughness(*mv.P(-b * 0.3, -rb), "Ra 1.6", 0, 3.0)  # 轴孔（符号在孔内，尖端朝下指向孔壁）
    sh.roughness(*mv.P(-b / 2, da / 2 * 0.75), "Ra 3.2", 90, 3.0)
    tx, ty = mv.P(b / 2, -(df / 2 + g.rim_inner_d * 1e3 / 2) / 2 if g.web else -df / 4)
    sh.roughness_leader((tx, ty), (tx + 12, ty - 10), "Ra 3.2")
    sh.roughness(*mv.P(-b * 0.25, d / 2), "Ra 1.6", 0, 3.0)  # 齿面（标在分度线上）
    # 基准与跳动
    sh.datum(*mv.P(b * 0.25, -rb), "A", "up")
    px, py = mv.P(b * 0.2, da / 2)
    sh.arrow((px - 8, py + 22), (px, py), 2.5, "细实线")
    sh.gtol(px - 30, py + 22, "runout", "0.040", "A")
    px, py = mv.P(b / 2, -da / 2 * 0.45)
    sh.arrow((px + 10, py - 12), (px, py), 2.5, "细实线")
    sh.gtol(px + 10, py - 19, "runout", "0.020", "A")

    # ------------------------------------------------ 左视图
    lv.circle((0, 0), da / 2)
    lv.circle((0, 0), d / 2, "点画线")
    if g.web:
        lv.circle((0, 0), g.hub_d * 1e3 / 2)
        lv.circle((0, 0), g.rim_inner_d * 1e3 / 2)
        lv.circle((0, 0), g.hole_pcd * 1e3 / 2, "点画线")
        for k in range(g.holes):
            a = 2 * math.pi * k / g.holes
            c = (g.hole_pcd * 1e3 / 2 * math.cos(a), g.hole_pcd * 1e3 / 2 * math.sin(a))
            lv.circle(c, g.hole_d * 1e3 / 2)
            sh.cross(lv.P(*c), g.hole_d * 1e3 / 2 * s, 1.5)
        lv.dim((-g.hole_d * 1e3 / 2, -g.hole_pcd * 1e3 / 2), (g.hole_d * 1e3 / 2, -g.hole_pcd * 1e3 / 2),
               (0, -g.hole_pcd * 1e3 / 2 - g.hole_d * 1e3 / 2 - 6 / s), 0, f"{g.holes}×%%c<>", 0)
    # 轴孔和键槽
    hb = kb / 2
    ang = math.degrees(math.asin(hb / rb))
    sh.arc(lv.P(0, 0), rb * s, 90 + ang, 90 - ang + 360)
    yb = math.sqrt(rb**2 - hb**2)
    lv.line((-hb, yb), (-hb, rb + t2))
    lv.line((hb, yb), (hb, rb + t2))
    lv.line((-hb, rb + t2), (hb, rb + t2))
    sh.cross(lv.P(0, 0), da / 2 * s, 4)
    lv.dim((-hb, rb + t2), (hb, rb + t2), (-hb, rb + t2 + 8 / s), 0, "<>JS9", 0)
    lv.dim((hb, -rb), (hb, rb + t2), (rb + 10 / s, 0), 90, "<>", 1)
    sh.roughness(*lv.P(hb, rb + t2), "Ra 3.2", 0, 2.5)

    # ------------------------------------------------ 参数表、图框
    param_table(sh, pair, member)
    reqs = ["调质处理 217～255HBW。" if not material.startswith("40Cr") else "调质处理 241～286HBW。",
            "未注倒角 C2，未注圆角 R3。",
            "未注尺寸公差按 GB/T 1804-m。"]
    sh.frame(TitleInfo(title, material, s, "1", drawing_no), reqs, "Ra 6.3")
    sh.save(path)
    return sh
