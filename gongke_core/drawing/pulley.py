"""V 带轮零件图。

主视图通过轴线全剖（孔板式的剖切面通过减重孔），轮槽按实际形状画出；左视图画外形、减重孔和带键槽的轴孔。
轮槽尺寸（GB/T 10412）列在右上角的轮槽参数表中，代替局部放大图。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale
from gongke_core.layout.pulley import PulleyBlank

# 带轮外圆的径向圆跳动公差（GB/T 10412，按基准直径分段），mm
RUNOUT_MM = [(100, 0.2), (160, 0.3), (250, 0.4), (400, 0.5), (630, 0.6), (1e9, 0.8)]


def runout(dd: float) -> float:
    return next(t for lim, t in RUNOUT_MM if dd * 1e3 <= lim)


def param_rows(p: PulleyBlank) -> list[list[str]]:
    sec = p.sec
    f = lambda v: f"{v * 1e3:g}"
    return [
        ["带型", "", sec.name],
        ["槽数", "z", str(p.grooves)],
        ["基准直径", "dd", f(p.dd)],
        ["槽角", "φ", f"{p.angle:.0f}°±30′"],
        ["基准宽度", "bd", f(sec.bp)],
        ["基准线上槽深", "ha", f"{f(sec.ha)} min"],
        ["基准线下槽深", "hf", f"{f(sec.hf)} min"],
        ["槽间距", "e", f"{f(sec.e)}±0.3" if sec.name in ("Z", "A") else f"{f(sec.e)}±0.4"],
        ["槽边距", "f", f"{f(sec.f)} min"],
    ]


def _loops(p: PulleyBlank) -> list[list[tuple[float, float]]]:
    """主视图上半部分的剖面区域（mm，x 沿轴线、以轮缘对称面为原点）。"""
    zc = p.z_center
    prof = [((z - zc) * 1e3, r * 1e3) for r, z in p.profile()]
    if p.holes == 0:
        return [prof]
    rb_groove = (p.dd / 2 - p.sec.hf) * 1e3
    top = [pt for pt in prof if pt[1] >= rb_groove - 1e-6]  # 轮缘外侧（含轮槽），自左向右
    L, B = p.hub_length * 1e3 / 2, p.width * 1e3 / 2
    c = p.web_thickness * 1e3 / 2
    rd, rh, ri = p.bore * 1e3 / 2, p.hub_d * 1e3 / 2, p.rim_inner_d * 1e3 / 2
    h0, h1 = (p.hole_pcd - p.hole_d) * 1e3 / 2, (p.hole_pcd + p.hole_d) * 1e3 / 2
    inner = [(-L, rd), (L, rd), (L, rh), (c, rh), (c, h0), (-c, h0), (-c, rh), (-L, rh)]
    outer = [(-c, h1), (c, h1), (c, ri), (B, ri)] + list(reversed(top)) + [(-B, ri), (-c, ri)]
    return [inner, outer]


def draw(p: PulleyBlank, path: str | Path, title: str = "大带轮", drawing_no: str = "",
         material: str = "HT200") -> Sheet:
    da, dd = p.da * 1e3, p.dd * 1e3
    L, B = p.hub_length * 1e3, p.width * 1e3
    rd = p.bore * 1e3 / 2
    t2, kb = p.key_t2 * 1e3, p.key_b * 1e3
    ri, rh = p.rim_inner_d * 1e3 / 2, p.hub_d * 1e3 / 2

    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        s = pick_scale(L + da + 80, da + 20, x1 - x0 - 150, y1 - y0 - 56 - 50)
        if s >= 0.5 or size == "A1":
            break
    main_cx = x0 + 45 + L * s / 2 + 20
    cy = y0 + 56 + 25 + da * s / 2 + 10
    left_cx = main_cx + L * s / 2 + 55 + da * s / 2
    mv = View(sh, (main_cx, cy), s)
    lv = View(sh, (left_cx, cy), s)

    # ------------------------------------------------ 主视图（全剖）
    for sgn in (1, -1):
        loops = _loops(p)
        if sgn < 0:
            loops = [[(x, -y) for x, y in loop] for loop in loops]
        else:
            loops = [[(x, rd + t2 if abs(y - rd) < 1e-6 else y) for x, y in loop] for loop in loops]
        for loop in loops:
            mv.poly(loop, close=True)
        mv.hatch(loops)
        # 各轮槽的基准线（细实线，宽 bd）
        for zk in p.groove_centers():
            x = (zk - p.z_center) * 1e3
            mv.line((x - p.sec.bp * 1e3 / 2, sgn * dd / 2), (x + p.sec.bp * 1e3 / 2, sgn * dd / 2), "细实线")
    mv.centerline((-L / 2, 0), (L / 2, 0), 5)
    if p.holes:
        c = p.web_thickness * 1e3 / 2
        h0, h1 = (p.hole_pcd - p.hole_d) * 1e3 / 2, (p.hole_pcd + p.hole_d) * 1e3 / 2
        for sgn in (1, -1):
            for x in (-c, c):
                mv.line((x, sgn * h0), (x, sgn * h1))
            mv.centerline((-c - 2, sgn * p.hole_pcd * 1e3 / 2), (c + 2, sgn * p.hole_pcd * 1e3 / 2), 2)

    # 主视图尺寸
    xr = max(L, B) / 2
    mv.dim((-B / 2, da / 2), (B / 2, da / 2), (-B / 2, da / 2 + 10 / s), 0, "<>", 0)
    if L > B + 1e-6:
        mv.dim((-L / 2, -rh), (L / 2, -rh), (-L / 2, -da / 2 - 10 / s), 0, "<>", 0)
    mv.dim((xr, -da / 2), (xr, da / 2), (xr + 14 / s, 0), 90, "%%c<>", 1)
    xg = (p.groove_centers()[-1] - p.z_center) * 1e3
    mv.dim((xg, -dd / 2), (xg, dd / 2), (xr + 26 / s, 0), 90, "%%c<>", 0)
    mv.dim((-L / 2, -rd), (-L / 2, rd), (-L / 2 - 8 / s, 0), 90, "%%c<>H7", 0)
    if p.kind != "实心式":
        mv.dim((-L / 2, -rh), (-L / 2, rh), (-L / 2 - 20 / s, 0), 90, "%%c<>", 0)
        mv.dim((-B / 2, -ri), (-B / 2, ri), (-L / 2 - 32 / s, 0), 90, "%%c<>", 0)
        c = p.web_thickness * 1e3 / 2
        mv.dim((-c, -ri), (c, -ri), (-c, -da / 2 - (22 if L > B + 1e-6 else 10) / s), 0, "<>", 0)
    # 槽间距和槽边距
    gz = [(z - p.z_center) * 1e3 for z in p.groove_centers()]
    if len(gz) > 1:
        mv.dim((gz[0], da / 2), (gz[1], da / 2), (gz[0], da / 2 + 20 / s), 0, "<>", 0)
    mv.dim((-B / 2, da / 2), (gz[0], da / 2), (-B / 2, da / 2 + 20 / s), 0, "<>", 0)
    # 表面结构
    sh.roughness(*mv.P(-L * 0.3, -rd), "Ra 3.2", 0, 3.0)  # 轴孔
    sh.roughness_leader(mv.P(gz[0], (da / 2 + dd / 2) / 2), (mv.P(gz[0], 0)[0] - 18, mv.P(0, da / 2)[1] + 30), "Ra 3.2")
    # 基准与跳动
    sh.datum(*mv.P(-L / 2 - 8 / s, -rd), "A", "down")  # 基准符号接在轴孔尺寸线上
    px, py = mv.P(B / 2, -da / 2)  # 外圆径向圆跳动
    sh.arrow((px + 8, py - 14), (px, py), 2.5, "细实线")
    sh.gtol(px + 8, py - 21, "runout", f"{runout(p.dd):g}", "A")

    # ------------------------------------------------ 左视图
    lv.circle((0, 0), da / 2)
    if p.kind != "实心式":
        lv.circle((0, 0), ri)
        lv.circle((0, 0), rh)
    if p.holes:
        lv.circle((0, 0), p.hole_pcd * 1e3 / 2, "点画线")
        for k in range(p.holes):
            a = 2 * math.pi * k / p.holes + math.pi / p.holes
            c = (p.hole_pcd * 1e3 / 2 * math.cos(a), p.hole_pcd * 1e3 / 2 * math.sin(a))
            lv.circle(c, p.hole_d * 1e3 / 2)
            sh.cross(lv.P(*c), p.hole_d * 1e3 / 2 * s, 1.5)
        a = math.pi / p.holes
        cx, cy2 = p.hole_pcd * 1e3 / 2 * math.cos(a), -p.hole_pcd * 1e3 / 2 * math.sin(a)
        sh.leader_text(lv.P(cx, cy2), (lv.P(cx, cy2)[0] + 25, lv.P(cx, cy2)[1] - 25),
                       f"{p.holes}×%%c{p.hole_d * 1e3:g}", 3.5)
    hb = kb / 2
    ang = math.degrees(math.asin(hb / rd))
    sh.arc(lv.P(0, 0), rd * s, 90 + ang, 90 - ang + 360)
    yb = math.sqrt(rd**2 - hb**2)
    lv.line((-hb, yb), (-hb, rd + t2))
    lv.line((hb, yb), (hb, rd + t2))
    lv.line((-hb, rd + t2), (hb, rd + t2))
    sh.cross(lv.P(0, 0), da / 2 * s, 4)
    lv.dim((-hb, rd + t2), (hb, rd + t2), (-hb, rd + t2 + 8 / s), 0, "<>JS9", 0)
    lv.dim((hb, -rd), (hb, rd + t2), (rd + 10 / s, 0), 90, "<>", 1)

    # ------------------------------------------------ 参数表、图框
    widths = [32, 14, 30]
    sh.table(sh.inner[2] - sum(widths), sh.inner[3], param_rows(p), widths, 7)
    reqs = ["铸件不得有砂眼、气孔、裂纹，轮槽工作面不得有毛刺。",
            "带轮作静平衡试验。",
            "未注铸造圆角 R3～5，未注倒角 C1.5。",
            "未注尺寸公差按 GB/T 1804-m。"]
    if p.note:
        reqs.append(p.note + "。")
    sh.frame(TitleInfo(title, material, s, "1", drawing_no), reqs, "Ra 12.5")
    sh.save(path)
    return sh
