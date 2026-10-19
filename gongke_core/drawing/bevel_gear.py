"""直齿锥齿轮零件图。

按 GB/T 4459.2 锥齿轮规定画法：主视图通过轴线全剖，轮齿按不剖处理（齿顶线、齿根线用粗实线，分度线用点画线，
分度线延长到锥顶），轮体画剖面线；右侧用局部视图表示带键槽的轴孔。
尺寸按指导书的锥齿轮图例：大端齿顶圆直径、齿宽、轮冠距、安装距（锥顶到基准端面）、顶锥角、背锥角、
轮毂和轴孔。右上角为参数表。结构尺寸来自 `layout.bevel_blank`。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.calc.bevel import BevelPair
from gongke_core.drawing.gear import dms
from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale
from gongke_core.layout.bevel_blank import BevelBlank, blank

MM = 1e3


def param_rows(pair: BevelPair, member: int) -> list[list[str]]:
    z = pair.z1 if member == 1 else pair.z2
    mate = pair.z2 if member == 1 else pair.z1
    delta = pair.delta1 if member == 1 else pair.delta2
    theta_f = math.atan(1.2 * pair.m / pair.cone_distance)
    f = lambda v: f"{v * MM:g}"  # noqa: E731
    return [
        ["大端模数", "m", f(pair.m)],
        ["齿数", "z", str(z)],
        ["压力角", "α", f"{pair.inp.alpha_deg:g}°"],
        ["齿顶高系数", "ha*", "1"],
        ["顶隙系数", "c*", "0.2"],
        ["分度圆直径", "d", f"{(pair.d1 if member == 1 else pair.d2) * MM:.2f}".rstrip("0").rstrip(".")],
        ["分度圆锥角", "δ", dms(delta)],
        ["根锥角", "δf", dms(delta - theta_f)],
        ["锥距", "R", f"{pair.cone_distance * MM:.2f}"],
        ["轴交角", "Σ", "90°"],
        ["精度等级", "", f"{pair.inp.grade} GB/T 11365"],
        ["配对齿轮齿数", "", str(mate)],
    ]


def param_table(sh: Sheet, pair: BevelPair, member: int):
    x1, y1 = sh.inner[2], sh.inner[3]
    widths = [32, 14, 34]
    sh.table(x1 - sum(widths), y1, param_rows(pair, member), widths, 7)


def reference_face(g: BevelBlank) -> float:
    """基准端面（安装时靠轴肩或轴环定位的背面）沿 t 的位置。"""
    return g.hub_span[1] if g.member == 1 else g.t_back


def draw(pair: BevelPair, member: int, bore: float, path: str | Path, title: str, drawing_no: str = "",
         material: str = "45", hub_length: float | None = None) -> Sheet:
    g = blank(pair, member, bore, hub_length)
    prof = [(t * MM, r * MM) for t, r in g.profile()]
    tipS, tipL, rootL, K = prof[0], prof[1], prof[2], prof[3]
    rootS = (g.root_small[0] * MM, g.root_small[1] * MM)
    rb = g.bore * MM / 2
    t2, kb = g.key_t2 * MM, g.key_b * MM
    t_ref = reference_face(g) * MM
    t_max = max(p[0] for p in prof)
    da = g.da * MM
    rK = K[1]

    r_local = rb + t2 + 6  # 轴孔局部视图的范围
    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        # 主视图从锥顶画到最外端，右侧另有尺寸和局部视图；上方留给参数表左侧的跳动框格
        s = pick_scale(t_max + 2 * r_local, da, x1 - x0 - 90 - 110, y1 - y0 - 56 - 70)
        if s >= 0.5 or size == "A1":
            break
    apex_x = x0 + 40
    cy = y0 + 56 + 45 + da * s / 2
    mv = View(sh, (apex_x, cy), s)
    side_cx = apex_x + t_max * s + 45 + r_local * s
    lv = View(sh, (side_cx, cy), s)

    # ------------------------------------------------ 主视图（全剖，轮齿不剖）
    body = prof[2:]  # 去掉两个齿顶点后的轮体（含齿根线）
    for sgn in (1, -1):
        loop = [(t, sgn * r) for t, r in body]
        if sgn > 0:  # 上半部分剖切面通过键槽：轴孔线抬高到键槽底
            loop = [(t, rb + t2 if abs(r - rb) < 1e-6 else r) for t, r in loop]
        mv.poly(loop, close=True)
        mv.hatch([loop])
        mv.poly([(rootS[0], sgn * rootS[1]), (tipS[0], sgn * tipS[1]), (tipL[0], sgn * tipL[1]),
                 (rootL[0], sgn * rootL[1])])
        # 分度圆锥母线延长到锥顶
        c, sn = math.cos(g.delta), math.sin(g.delta)
        R = g.R * MM
        mv.line((0, 0), ((R + 3 / s) * c, sgn * (R + 3 / s) * sn), "点画线")
    mv.centerline((0, 0), (t_max, 0), 5)

    # ------------------------------------------------ 主视图尺寸
    top = da / 2
    # 大端齿顶圆直径（竖直，标在右侧）
    xd = t_max + 12 / s
    mv.dim((tipL[0], -tipL[1]), (tipL[0], tipL[1]), (xd, 0), 90, "%%c<>h11", 2)
    # 轴孔（右视图注键槽）
    t0, t1 = g.hub_span[0] * MM, g.hub_span[1] * MM
    mv.dim((t0, -rb), (t0, rb), (t0 - 8 / s, 0), 90, "%%c<>H7", 0)
    rh = g.hub_r * MM
    # 安装距（锥顶到基准端面）、轮冠距（大端齿顶到基准端面）、轮毂长度：标在下方
    yb = -top - 10 / s
    mv.dim((0, 0), (t_ref, -rK if member == 2 else -rh), (0, yb - 12 / s), 0, "<>", 2)
    mv.dim((tipL[0], -tipL[1]), (t_ref, -rK if member == 2 else -rh), (tipL[0], yb), 0, "<>", 2)
    mv.dim((t0, -rh), (t1, -rh), (t0, yb - 24 / s), 0, "<>", 0)
    # 齿宽（沿母线方向，注在齿顶线外侧）
    nrm = (-math.sin(g.delta), math.cos(g.delta))
    off = 8 / s
    a = (tipS[0] + nrm[0] * off, tipS[1] + nrm[1] * off)
    b = (tipL[0] + nrm[0] * off, tipL[1] + nrm[1] * off)
    sh.line(mv.P(*tipS), mv.P(*a), "细实线")
    sh.line(mv.P(*tipL), mv.P(*b), "细实线")
    sh.arrow(mv.P(*b), mv.P(*a), 2.5)
    sh.arrow(mv.P(*a), mv.P(*b), 2.5)
    mid = mv.P((a[0] + b[0]) / 2 + nrm[0] * 2 / s, (a[1] + b[1]) / 2 + nrm[1] * 2 / s)
    sh.text(mid[0], mid[1], f"{g.b * MM:g}", 3.5, "CENTER", rotation=math.degrees(g.delta))
    # 顶锥角 δa = δ + θa 注在齿顶线旁
    theta_a = math.atan(pair.m / pair.cone_distance)
    px, py = mv.P(tipL[0] * 0.55, tipL[1] * 0.55)
    sh.text(px - 6, py + 4, f"δa = {dms(g.delta + theta_a)}", 3.0, "RIGHT")
    # 表面结构
    sh.roughness(*mv.P(t0 + (t1 - t0) * 0.12, -rb), "Ra 1.6", 0, 3.0)
    fx, fy = mv.P(t_ref, -(rb + rK) / 2 if member == 2 else -(rb + rh) / 2)
    sh.roughness_leader((fx, fy), (fx + 12, fy - 8), "Ra 1.6")
    mx, my = (tipS[0] + tipL[0]) / 2, (tipS[1] + tipL[1]) / 2
    fx, fy = mv.P(mx, -my)
    steep = g.delta > math.radians(45)  # 齿面接近竖直时引线向左引出，避免压住下方尺寸
    sh.roughness_leader((fx, fy), (fx - 22, fy + 2) if steep else (fx - 10, fy - 14), "Ra 1.6")
    # 基准与跳动：齿顶圆锥对轴孔的圆跳动、基准端面对轴孔的端面圆跳动
    sh.datum(*mv.P(t0 + (t1 - t0) * 0.75, -rb), "A", "up")
    px, py = mv.P(tipL[0] - 0.3 * (tipL[0] - tipS[0]), tipL[1] - 0.3 * (tipL[1] - tipS[1]))
    sh.arrow((px + 6, py + 22), (px, py), 2.5, "细实线")
    sh.gtol(px + 6, py + 22, "runout", "0.040", "A")
    px, py = mv.P(t_ref, (rK if member == 2 else rh) * 0.8)
    sh.arrow((px + 12, py + 8), (px, py), 2.5, "细实线")
    sh.gtol(px + 12, py + 8, "runout", "0.025", "A")

    # ------------------------------------------------ 轴孔局部视图
    hb = kb / 2
    ang = math.degrees(math.asin(hb / rb))
    sh.arc(lv.P(0, 0), rb * s, 90 + ang, 90 - ang + 360)
    yk = math.sqrt(rb**2 - hb**2)
    lv.line((-hb, yk), (-hb, rb + t2))
    lv.line((hb, yk), (hb, rb + t2))
    lv.line((-hb, rb + t2), (hb, rb + t2))
    sh.cross(lv.P(0, 0), rb * s, 4)
    lv.dim((-hb, rb + t2), (hb, rb + t2), (-hb, rb + t2 + 8 / s), 0, "<>JS9", 0)
    lv.dim((hb, -rb), (hb, rb + t2), (rb + 10 / s, 0), 90, "<>", 1)
    sh.roughness(*lv.P(hb, rb + t2), "Ra 3.2", 0, 2.5)

    # ------------------------------------------------ 参数表、图框
    param_table(sh, pair, member)
    reqs = ["调质处理 217～255HBW。" if not material.startswith("40Cr") else "调质处理 241～286HBW。",
            "未注倒角 C2，未注圆角 R3。",
            "未注尺寸公差按 GB/T 1804-m。",
            "齿侧间隙按 GB/T 11365 选用。"]
    sh.frame(TitleInfo(title, material, s, "1", drawing_no), reqs, "Ra 6.3")
    sh.save(path)
    return sh
