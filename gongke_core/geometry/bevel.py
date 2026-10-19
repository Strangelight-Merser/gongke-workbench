"""圆锥-圆柱齿轮减速器的零件和装配体（单位 mm）。

坐标与 `layout.bevel_reducer` 一致：Ⅱ轴在 x = 0、Ⅲ轴在 x = a，z 沿Ⅱ、Ⅲ轴，Ⅰ轴沿 −x、轴线在 (y, z) = (0, z_apex)。
Ⅰ轴的零件先在局部坐标中建模（局部 z = u，自锥顶沿轴线向外），再绕 y 轴转 −90°（局部 +z → 总体 −x）
并平移到锥顶，局部 y 与总体 y 相同，因此键槽方向不变。
"""

from __future__ import annotations

import math

import build123d as bd

from gongke_core import standards
from gongke_core.geometry import parts
from gongke_core.layout import bevel_blank, bevel_reducer

MM = 1e-3


def _mm(v: float) -> float:
    return v / MM


def _revolve(profile: list[tuple[float, float]]) -> bd.Solid:
    """(z, r) 半剖面轮廓（m）绕 z 轴回转。"""
    pts = [bd.Vector(_mm(r), 0, _mm(z)) for z, r in profile]
    return bd.Solid.revolve(bd.Face(bd.Wire.make_polygon(pts, close=True)), 360, bd.Axis.Z)


def bevel_gear(g: bevel_blank.BevelBlank) -> bd.Solid:
    """直齿锥齿轮（`layout.bevel_blank.BevelBlank`）：齿部按齿顶圆锥简化，开键槽。轴线为 z，锥顶在原点，
    大端朝 +z（z = t）。"""
    body = _revolve(g.profile())
    if g.key_b:
        t0, t1 = g.hub_span
        kb, kt = _mm(g.key_b), _mm(g.key_t2)
        key = bd.Solid.make_box(kb, _mm(g.bore) / 2 + kt, _mm(t1 - t0) + 2).moved(bd.Location((-kb / 2, 0, _mm(t0) - 1)))
        body = body.cut(key)
    return body.clean()


def tapered_bearing(brg: standards.TaperedBearing) -> bd.Solid:
    """圆锥滚子轴承简化模型：内圈、外圈、滚子（合成一个回转体环）。占 z ∈ [0, T]，外圈背面在 z = 0，
    内圈背面在 z = T；压力中心偏向内圈背面一侧。"""
    d, D, T, B, C = brg.d, brg.D, brg.T, brg.b_inner, brg.c_outer
    w = (D - d) / 2
    cone = [(T - B, d / 2), (T, d / 2), (T, d / 2 + 0.42 * w), (T - B, d / 2 + 0.28 * w)]
    cup = [(0, D / 2), (C, D / 2), (C, D / 2 - 0.22 * w), (0, D / 2 - 0.38 * w)]
    k0, k1 = 0.12 * T, 0.88 * T
    r_in = lambda z: d / 2 + 0.28 * w + 0.14 * w * (z - (T - B)) / B + 0.02 * w  # noqa: E731
    r_out = lambda z: D / 2 - 0.38 * w + 0.16 * w * z / C - 0.02 * w  # noqa: E731
    rollers = [(k0, r_in(k0)), (k1, r_in(k1)), (k1, r_out(k1)), (k0, r_out(k0))]
    return bd.Compound([_revolve(cone), _revolve(cup), _revolve(rollers)])


def place_tapered(brg: standards.TaperedBearing, z_load: float, back: int) -> bd.Shape:
    """把轴承放在压力中心 z_load 处（m），back = +1 表示内圈背面朝 +z。"""
    off = brg.a - brg.T / 2
    zc = z_load - back * off
    s = tapered_bearing(brg).moved(bd.Location((0, 0, -_mm(brg.T) / 2)))
    if back < 0:
        s = s.mirror(bd.Plane.XY)
    return s.moved(bd.Location((0, 0, _mm(zc))))


def cup(c: bevel_reducer.Cup) -> bd.Solid:
    """Ⅰ轴轴承套杯：内孔装两轴承外圈，中间挡肩，外端凸缘带螺钉孔。局部 z = u。"""
    r_o, r_i, r_rib, r_f = c.D_out / 2, c.D / 2, c.rib_d / 2, c.flange_D / 2
    uf = c.u_flange
    prof = [(c.u0, r_i), (c.u0, r_o), (uf, r_o), (uf, r_f), (uf + c.flange_t, r_f), (uf + c.flange_t, r_i),
            (c.rib[1], r_i), (c.rib[1], r_rib), (c.rib[0], r_rib), (c.rib[0], r_i)]
    body = _revolve(prof)
    pcd = (c.D_out + 2.5 * c.screw_d) / 2
    for k in range(c.screws):
        a = 2 * math.pi * (k + 0.5) / c.screws
        body = body.cut(bd.Solid.make_cylinder(_mm(c.screw_d) / 2 + 0.5, _mm(c.flange_t) + 2,
                                               bd.Plane((_mm(pcd) * math.cos(a), _mm(pcd) * math.sin(a), _mm(uf) - 1))))
    return body.clean()


def cup_cap(c: bevel_reducer.Cup, thickness: float, seal_d: float) -> bd.Solid:
    """套杯外端的轴承透盖（凸缘式，与套杯凸缘同径，通过同一组螺钉固定在轴承座上）。"""
    u0 = c.u_flange + c.flange_t
    cap = bd.Solid.make_cylinder(_mm(c.flange_D) / 2, _mm(thickness), bd.Plane((0, 0, _mm(u0))))
    cap = cap.cut(bd.Solid.make_cylinder(_mm(seal_d) / 2 + 1, _mm(thickness) + 2, bd.Plane((0, 0, _mm(u0) - 1))))
    return cap.clean()


def build(design, with_housing: bool = True, teeth: bool = False) -> dict[str, bd.Shape]:
    """圆锥-圆柱齿轮减速器装配体（y 向上，未转成 Z 向上），{零件名: 已定位实体}。

    锥齿轮的齿部按齿顶圆锥简化（teeth 只影响圆柱齿轮）。"""
    from gongke_core.geometry.assembly import _phase_for_mesh

    out: dict[str, bd.Shape] = {}
    bevel, low, pos, ps = design.bevel, design.low, design.positions, design.pinion
    s1, s2, s3 = (s.layout for s in design.shafts)
    za = _mm(pos.z_apex)
    to_global = bd.Location((0, 0, za)) * bd.Location((0, 0, 0), (0, 1, 0), -90)

    # Ⅰ轴：小锥齿轮（或齿轮轴）、两轴承反装、套杯、透盖、联轴器
    g1 = bevel_blank.blank(bevel, 1, ps.seat_d or ps.diameters["齿轮"], ps.pinion_length)
    pin = bevel_gear(g1) if not ps.integral else _revolve(g1.profile())
    shaft = parts.stepped_shaft([s for s in ps.segments if s.role != "齿轮轴"], (), teeth)
    if ps.integral:
        t0, t1 = g1.hub_span
        core = bd.Solid.make_cylinder(_mm(g1.bore) / 2 + 0.1, _mm(t1 - t0), bd.Plane((0, 0, _mm(t0))))
        shaft = shaft.fuse(pin).fuse(core).clean()
        out[f"{s1.name}（齿轮轴）"] = to_global * shaft
    else:
        out[s1.name] = to_global * shaft
        out["小锥齿轮"] = to_global * pin
    brg = ps.bearing
    for i, (u, back) in enumerate(zip(ps.bearing_u, (-1, +1))):
        out[f"{s1.name}轴承{brg.designation}-{'AB'[i]}"] = to_global * place_tapered(brg, u, back)
    c = bevel_reducer.cup(ps)
    out["套杯"] = to_global * cup(c)
    h = design.housing
    out["轴承透盖-1"] = to_global * cup_cap(c, h.cap_thickness, ps.diameters["密封"])
    end = next(s for s in ps.segments if s.role == "端部")
    out[f"{s1.name}联轴器半体"] = to_global * parts.coupling_half(end.d, ps.hub).moved(bd.Location((0, 0, _mm(end.z0))))

    # Ⅱ轴：大锥齿轮（大端朝 −z）、圆柱小齿轮、两轴承正装
    integral = [(low, g.z, 0.0) for g in s2.gears if g.pair == "low" and g.integral]
    out[s2.name] = parts.stepped_shaft(s2.segments, integral, teeth)
    g2 = bevel_blank.blank(bevel, 2, s2.diameters["齿轮"], pos.hub)
    out["大锥齿轮"] = bevel_gear(g2).mirror(bd.Plane.XY).moved(bd.Location((0, 0, za)))
    for g in s2.gears:
        if g.pair == "low" and not g.integral:
            seat = next(s for s in s2.segments if s.role == "齿轮" and s.z0 <= g.z <= s.z1)
            out[f"{low.inp.name}小齿轮"] = parts.gear_blank(low, 1, g.seat_d, seat.keyway, 0.0, teeth).moved(
                bd.Location((0, 0, _mm(g.z))))
    b2 = s2.bearing
    for i, (zc, back) in enumerate(zip(s2.bearing_z, (+1, -1))):
        out[f"{s2.name}轴承{b2.designation}-{'AB'[i]}"] = place_tapered(b2, zc, back)

    # Ⅲ轴：与展开式的低速轴相同
    x3 = _mm(s3.x)
    out[s3.name] = parts.stepped_shaft(s3.segments, [], teeth).moved(bd.Location((x3, 0, 0)))
    for g in s3.gears:
        seat = next(s for s in s3.segments if s.role == "齿轮" and s.z0 <= g.z <= s.z1)
        blank = parts.gear_blank(low, 2, g.seat_d, seat.keyway, _phase_for_mesh(low.z2), teeth)
        out[f"{low.inp.name}大齿轮"] = blank.moved(bd.Location((x3, 0, _mm(g.z))))
    b3 = s3.bearing
    for i, zc in enumerate(s3.bearing_z):
        out[f"{s3.name}轴承{b3.designation}-{'AB'[i]}"] = parts.ball_bearing(b3.d, b3.D, b3.B).moved(
            bd.Location((x3, 0, _mm(zc))))
    end = next(s for s in s3.segments if s.role == "端部")
    out[f"{s3.name}联轴器半体"] = parts.coupling_half(end.d, s3.coupling_hub).moved(bd.Location((x3, 0, _mm(end.z0))))

    if with_housing:
        from gongke_core.geometry import housing as hg
        from gongke_core.layout.housing_detail import detail

        t = detail(design)
        out["箱座"] = parts.housing_base(h, t.shaft_x, [s2.bearing.D, s3.bearing.D], t.side_bore, t)
        out["箱盖"] = hg.cover(t)
        out.update(hg.accessories(t))
        caps = hg.bearing_caps(t, [None, s3.extension], [None, s3.diameters.get("密封")])
        out.update({k.replace("-1", "-2", 1) if "-1" in k else k.replace("-2", "-3", 1): v for k, v in caps.items()})
    return out
