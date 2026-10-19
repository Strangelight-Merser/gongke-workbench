"""单级蜗杆减速器（蜗杆下置）的零件和装配体（单位 mm）。

坐标与 `layout.worm_reducer` 一致：Ⅱ轴（蜗轮轴）沿 z、在 x = 0、y = 0；Ⅰ轴（蜗杆轴）沿 x、在 y = −a、z = W/2。
蜗杆轴的零件先在局部坐标中建模（局部 z = 总体 x），再绕 y 轴转 +90°（局部 +z → 总体 +x，局部 x → 总体 −z），
局部 y 与总体 y 相同，因此键槽方向不变。
"""

from __future__ import annotations

import math

import build123d as bd

from gongke_core.geometry import parts
from gongke_core.geometry.bevel import _revolve, place_tapered
from gongke_core.layout import worm_blank

MM = 1e-3


def _mm(v: float) -> float:
    return v / MM


def wheel(g: worm_blank.WheelBlank) -> tuple[bd.Solid, bd.Solid]:
    """蜗轮的 (齿圈, 轮芯)。轴线为 z、中间平面 z = 0。齿部按齿顶喉圆回转体简化。"""
    ring = _revolve(g.ring_profile())
    core = _revolve(g.core_profile())
    L = _mm(g.hub_length)
    if g.holes:
        for k in range(g.holes):
            a = 2 * math.pi * k / g.holes
            r = _mm(g.hole_pcd) / 2
            core = core.cut(bd.Solid.make_cylinder(_mm(g.hole_d) / 2, L + 2,
                                                   bd.Plane((r * math.cos(a), r * math.sin(a), -L / 2 - 1))))
    kb, kt = _mm(g.key_b), _mm(g.key_t2)
    core = core.cut(bd.Solid.make_box(kb, _mm(g.bore) / 2 + kt, L + 2).moved(bd.Location((-kb / 2, 0, -L / 2 - 1))))
    # 齿圈与轮芯接缝处的紧定螺钉孔（从 +z 端面钻入）
    h = _mm(g.b2) / 2
    for k in range(g.screws):
        a = 2 * math.pi * (k + 0.5) / g.screws
        r = _mm(g.screw_r)
        hole = bd.Solid.make_cylinder(_mm(g.screw_d) / 2, _mm(g.screw_depth) + 1,
                                      bd.Plane((r * math.cos(a), r * math.sin(a), h - _mm(g.screw_depth))))
        ring, core = ring.cut(hole), core.cut(hole)
    return ring.clean(), core.clean()


def worm_shaft(ws, w, teeth: bool = False) -> bd.Solid:
    """蜗杆轴（局部 z = 总体 x）：阶梯轴 + 螺纹部分。teeth=False 时螺纹按齿顶圆柱简化；
    True 时建出阿基米德蜗杆的螺纹（轴向齿形为直线，齿形角 20°，右旋）。"""
    shaft = parts.stepped_shaft([s for s in ws.segments if s.role != "齿轮轴"], (), False)
    thread = next(s for s in ws.segments if s.role == "齿轮轴")
    z0, L = _mm(thread.z0), _mm(thread.length)
    ra, rf = _mm(w.da1) / 2, _mm(w.df1) / 2
    if teeth:
        lead = math.pi * _mm(w.m) * w.z1
        face = bd.Face(bd.Wire.make_polygon([bd.Vector(x, y, 0) for x, y in worm_section(w)], close=True))
        body = bd.Solid.extrude_linear_with_rotation(face, (0, 0, 0), (0, 0, L), 360 * L / lead)
        body = body.moved(bd.Location((0, 0, z0)))
    else:
        body = bd.Solid.make_cylinder(ra, L, bd.Plane((0, 0, z0)))
    # 螺纹两端倒角到齿根圆
    for zc, dz in ((z0, 1), (z0 + L, -1)):
        c = ra - rf
        cone = bd.Solid.make_cone(rf, ra + 1, c + 1, bd.Plane((0, 0, zc), z_dir=(0, 0, dz)))
        cut = bd.Solid.make_cylinder(ra + 2, c + 1, bd.Plane((0, 0, zc), z_dir=(0, 0, dz))).cut(cone)
        body = body.cut(cut)
    return shaft.fuse(body).clean()


def worm_section(w, n: int = 8) -> list[tuple[float, float]]:
    """阿基米德蜗杆垂直于轴线的截面（mm）。轴向齿厚 s(r) = p/2 − 2(r − r1) tan α，截面上该处的齿
    所占圆心角为 2π s(r)/pz（pz 为导程），各头齿相隔 2π/z1，齿根处用齿根圆弧连接。"""
    m = _mm(w.m)
    pitch = math.pi * m
    lead = pitch * w.z1
    ra, rf, r1 = _mm(w.da1) / 2, _mm(w.df1) / 2, _mm(w.d1) / 2
    tan_a = math.tan(math.radians(20))
    half = lambda r: math.pi * (pitch / 2 - 2 * (r - r1) * tan_a) / lead  # noqa: E731  半齿所占圆心角
    pts = []
    for k in range(w.z1):
        c = 2 * math.pi * k / w.z1
        rs = [rf + (ra - rf) * i / n for i in range(n + 1)]
        tip = [(ra, c - half(ra) + 2 * half(ra) * i / 6) for i in range(1, 6)]
        flank = [(r, c - half(r)) for r in rs] + tip + [(r, c + half(r)) for r in reversed(rs)]
        nxt = 2 * math.pi * (k + 1) / w.z1 - half(rf)
        a0 = c + half(rf)
        gap = [(rf, a0 + (nxt - a0) * i / 12) for i in range(1, 12)]
        pts += flank + gap
    return [(r * math.cos(t), r * math.sin(t)) for r, t in pts]


def build(design, with_housing: bool = True, teeth: bool = False) -> dict[str, bd.Shape]:
    """蜗杆减速器装配体（y 向上，未转成 Z 向上），{零件名: 已定位实体}。"""
    out: dict[str, bd.Shape] = {}
    w, ws, h = design.worm, design.worm_shaft, design.housing
    s1, s2 = (s.layout for s in design.shafts)
    W = _mm(h.inner_width)
    a = _mm(w.a)
    to_global = bd.Location((0, -a, W / 2)) * bd.Location((0, 0, 0), (0, 1, 0), 90)

    # Ⅰ轴：蜗杆轴、两端圆锥滚子轴承正装、联轴器
    out[f"{s1.name}（蜗杆）"] = to_global * worm_shaft(ws, w, teeth)
    brg = ws.bearing
    for i, (xc, back) in enumerate(zip(ws.bearing_x, (+1, -1))):
        out[f"{s1.name}轴承{brg.designation}-{'AB'[i]}"] = to_global * place_tapered(brg, xc, back)
    end = next(s for s in ws.segments if s.role == "端部")
    hub = parts.coupling_half(end.d, ws.hub).moved(bd.Location((0, 0, _mm(end.z0) - 2)))
    hub = hub.mirror(bd.Plane((0, 0, _mm(end.z0) + _mm(ws.hub) / 2 - 2), z_dir=(0, 0, 1)))
    out[f"{s1.name}联轴器半体"] = to_global * hub

    # Ⅱ轴：蜗轮、两端圆锥滚子轴承正装、联轴器
    out[s2.name] = parts.stepped_shaft(s2.segments, [], False)
    g = next(g for g in s2.gears if g.pair == "worm")
    gb = worm_blank.blank(w, g.seat_d, g.width)
    ring, core = wheel(gb)
    zc = _mm(g.z)
    out["蜗轮齿圈"] = ring.moved(bd.Location((0, 0, zc)))
    out["蜗轮轮芯"] = core.moved(bd.Location((0, 0, zc)))
    b2 = s2.bearing
    for i, (zb, back) in enumerate(zip(s2.bearing_z, (+1, -1))):
        out[f"{s2.name}轴承{b2.designation}-{'AB'[i]}"] = place_tapered(b2, zb, back)
    end = next(s for s in s2.segments if s.role == "端部")
    out[f"{s2.name}联轴器半体"] = parts.coupling_half(end.d, s2.coupling_hub).moved(bd.Location((0, 0, _mm(end.z0))))

    if with_housing:
        from gongke_core.geometry import housing as hg
        from gongke_core.layout.housing_detail import detail

        t = detail(design)
        out["箱座"] = base(design, t)
        out["箱盖"] = hg.cover(t)
        out.update(hg.accessories(t))
        caps = hg.bearing_caps(t, [s2.extension], [s2.diameters.get("密封")])
        out.update({k.replace("-1", "-2", 1): v for k, v in caps.items()})
        for k, v in worm_caps(t, ws).items():
            out[k] = to_global * v
    return out


def base(design, t) -> bd.Solid:
    """箱座：在通用箱座上加两端的蜗杆轴承座（外凸台 + 伸入箱内的内凸台）和座孔。"""
    h = design.housing
    wb = t.worm_bore
    body = parts.housing_base(h, t.shaft_x, [design.shafts[1].layout.bearing.D])
    r = _mm(wb.boss_r)
    y, z = _mm(wb.y), _mm(wb.z)
    xi, xf = _mm(wb.x_inner), _mm(wb.x_face)
    for sgn in (-1, 1):
        boss = bd.Solid.make_cylinder(r, xf - xi, bd.Plane((sgn * xi, y, z), z_dir=(sgn, 0, 0)))
        body = body.fuse(boss)
    bore = bd.Solid.make_cylinder(_mm(wb.D) / 2, 2 * xf + 2, bd.Plane((-xf - 1, y, z), z_dir=(1, 0, 0)))
    body = body.cut(bore)
    # 轴承盖螺钉孔
    cap = wb.cap
    for sgn in (-1, 1):
        for k in range(cap.n):
            ang = 2 * math.pi * (k + 0.5) / cap.n
            pr = _mm(cap.D0) / 2
            hole = bd.Solid.make_cylinder(_mm(cap.d3) / 2, 2 * _mm(cap.d3) + 1,
                                          bd.Plane((sgn * (xf + 1), y + pr * math.sin(ang), z + pr * math.cos(ang)),
                                                   z_dir=(-sgn, 0, 0)))
            body = body.cut(hole)
    return body.clean()


def worm_caps(t, ws) -> dict[str, bd.Solid]:
    """蜗杆轴两端的轴承盖（局部 z = 总体 x）：凸缘贴在轴承座外端面，止口一直伸到轴承外圈背面，
    输入端（−x）为透盖。"""
    wb = t.worm_bore
    cap = wb.cap
    e = _mm(t.h.cap_thickness)
    xf = _mm(wb.x_face)
    D, D2 = _mm(cap.D), _mm(cap.D2)
    brg = ws.bearing
    out = {}
    for sgn, name, body_x in ((-1, "轴承透盖-1左", ws.bodies[0]), (1, "轴承闷盖-1右", ws.bodies[1])):
        x_brg = _mm(abs(body_x) + brg.T / 2)  # 轴承外端面 |x|
        spigot = xf - x_brg
        if sgn < 0:
            flange = bd.Solid.make_cylinder(D2 / 2, e, bd.Plane((0, 0, -xf - e)))
            sp = bd.Solid.make_cylinder(D / 2 - 0.2, spigot, bd.Plane((0, 0, -xf)))
            c = flange.fuse(sp)
            seal = _mm(ws.diameters["密封"])
            c = c.cut(bd.Solid.make_cylinder(seal / 2 + 1, e + spigot + 2, bd.Plane((0, 0, -xf - e - 1))))
            # 止口做成套筒，内孔让开轴承内圈和轴肩
            c = c.cut(bd.Solid.make_cylinder(D / 2 - 6, spigot - 0.01, bd.Plane((0, 0, -xf + 0.01))))
        else:
            flange = bd.Solid.make_cylinder(D2 / 2, e, bd.Plane((0, 0, xf)))
            sp = bd.Solid.make_cylinder(D / 2 - 0.2, spigot, bd.Plane((0, 0, x_brg)))
            c = flange.fuse(sp).cut(bd.Solid.make_cylinder(D / 2 - 6, spigot - 0.01, bd.Plane((0, 0, x_brg))))
        out[name] = c.clean()
    return out
