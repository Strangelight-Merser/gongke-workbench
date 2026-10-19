"""箱盖和减速器附件的简化模型（尺寸来自 `layout.housing_detail`），单位 mm。

坐标系与布置计算一致：y 向上、剖分面 y = 0、z 沿轴线。
"""

from __future__ import annotations

import math

import build123d as bd

from gongke_core.layout.housing_detail import HousingDetail, envelope_height, envelope_points

MM = 1e-3


def _mm(v: float) -> float:
    return v / MM


def _profile(points_m: list[tuple[float, float]]) -> bd.Face:
    pts = [bd.Vector(_mm(x), _mm(y), 0) for x, y in points_m]
    return bd.Face(bd.Wire.make_polygon(pts, close=True))


def _box(x0, y0, z0, x1, y1, z1) -> bd.Solid:
    return bd.Solid.make_box(x1 - x0, y1 - y0, z1 - z0).moved(bd.Location((x0, y0, z0)))


def cover(t: HousingDetail) -> bd.Solid:
    """箱盖：上凸包外形的薄壁壳体、下凸缘、轴承座上半部分和轴承孔，顶部开视孔。"""
    h = t.h
    d1 = _mm(h.delta1)
    W = _mm(h.inner_width)
    fw = _mm(t.flange_w)
    b1 = _mm(h.flange_cover)
    L1 = _mm(h.bearing_seat_length)
    za, zb = -_mm(h.delta), W + _mm(h.delta)
    outer = bd.Solid.extrude(_profile(envelope_points(t.cover_outer)), (0, 0, zb - za)).moved(bd.Location((0, 0, za)))
    inner_pts = envelope_points(t.cover_inner)
    inner = bd.Solid.extrude(_profile(inner_pts), (0, 0, W)).moved(bd.Location((0, -0.01, 0)))
    body = outer.cut(inner)
    # 凸缘：外轮廓与箱座凸缘一致，内侧让开箱座内腔和箱盖内腔
    xo0, xo1 = (_mm(v) for v in t.x_outer)
    fl = _box(xo0 - fw, 0, za - fw, xo1 + fw, b1, zb + fw)
    x_in0, x_in1 = (_mm(v) for v in h.x_range)
    fl = fl.cut(_box(x_in0, -1, 0, x_in1, b1 + 1, W)).cut(inner)
    body = body.fuse(fl)
    # 轴承座上半部分
    for x, rb in zip(t.shaft_x, t.boss_r):
        for z0 in (-L1, W):
            body = body.fuse(bd.Solid.make_cylinder(_mm(rb), L1, bd.Plane((_mm(x), 0, z0))))
    if t.side_bore is not None:
        from gongke_core.geometry.parts import side_boss

        side_solids = side_boss(t.side_bore, h.x_range[0])
        body = body.fuse(side_solids[0])
    big = 1e4
    body = body.cut(_box(-big, -big, -big, big, 0, big))
    for x, cap in zip(t.shaft_x, t.caps):
        body = body.cut(bd.Solid.make_cylinder(_mm(cap.D) / 2, W + 2 * L1 + 2, bd.Plane((_mm(x), 0, -L1 - 1))))
    if t.side_bore is not None:
        body = body.cut(side_solids[1])
    # 视孔
    ins = t.inspection
    pl = _inspection_plane(t)
    hole = bd.Solid.make_box(_mm(ins.hole_length), 60, _mm(ins.hole_width)).moved(
        pl * bd.Location((-_mm(ins.hole_length) / 2, -40, -_mm(ins.hole_width) / 2)))
    body = body.cut(hole)
    # 安装螺栓的通孔
    for x in t.bearing_bolts:
        for zc in (za - fw / 2, zb + fw / 2):
            body = body.cut(bd.Solid.make_cylinder(_mm(h.bolt_bearing) / 2 + 1, b1 + 2, bd.Plane((_mm(x), -1, zc), z_dir=(0, 1, 0))))
    return body.clean()


def _inspection_plane(t: HousingDetail) -> bd.Location:
    """视孔盖局部坐标：原点在盖板底面中点，x 沿公切线，y 为外法线，z 沿轴线（箱宽中点）。"""
    ins = t.inspection
    cx, cy = (_mm(v) for v in ins.center)
    return bd.Location((cx, cy, _mm(t.h.inner_width) / 2), (0, 0, 1), ins.angle)


def accessories(t: HousingDetail) -> dict[str, bd.Solid]:
    h = t.h
    out: dict[str, bd.Solid] = {}
    W = _mm(h.inner_width)
    za, zb = -_mm(h.delta), W + _mm(h.delta)
    fw = _mm(t.flange_w)
    b, b1 = _mm(h.flange_base), _mm(h.flange_cover)
    ins = t.inspection
    pl = _inspection_plane(t)
    L, Bw, th = _mm(ins.length), _mm(ins.width), _mm(ins.thickness)
    out["视孔盖"] = bd.Solid.make_box(L, th, Bw).moved(pl * bd.Location((-L / 2, 0, -Bw / 2)))
    vd = _mm(ins.vent_d)
    vent = bd.Solid.make_cylinder(vd / 2, th + 12, bd.Plane((0, 0, 0), z_dir=(0, 1, 0)))
    vent = vent.fuse(bd.Solid.make_cylinder(vd * 0.9, 10, bd.Plane((0, th + 12, 0), z_dir=(0, 1, 0))))
    out["通气器"] = vent.moved(pl)
    # 吊环螺钉：螺杆 + 圆环
    ed = _mm(t.eyebolt_d)
    for k, x in enumerate(t.eyebolts):
        y = _mm(envelope_height(t.cover_outer, x))
        rod = bd.Solid.make_cylinder(ed / 2, 2.2 * ed, bd.Plane((_mm(x), y - 0.6 * ed, W / 2), z_dir=(0, 1, 0)))
        ring_r = 1.2 * ed
        ring = bd.Solid.make_torus(ring_r, 0.4 * ed, bd.Plane((_mm(x), y + 1.6 * ed + ring_r, W / 2), z_dir=(0, 0, 1)))
        out[f"吊环螺钉-{k + 1}"] = rod.fuse(ring)
    # 连接螺栓（螺杆 + 六角头 + 螺母，简化为圆柱）
    def bolt_solid(x, z, d, length):
        d = _mm(d)
        s = bd.Solid.make_cylinder(d / 2, _mm(length), bd.Plane((x, b1 + 0.0, z), z_dir=(0, -1, 0)))
        s = s.fuse(bd.Solid.make_cylinder(d, 0.7 * d, bd.Plane((x, b1, z), z_dir=(0, 1, 0))))
        s = s.fuse(bd.Solid.make_cylinder(d, 0.8 * d, bd.Plane((x, -b - 0.25 * d, z), z_dir=(0, -1, 0))))
        return s
    bolts = []
    for x in t.bearing_bolts:
        for zc in (za - fw / 2, zb + fw / 2):
            bolts.append(bolt_solid(_mm(x), zc, h.bolt_bearing, t.bolt_length_d1))
    for x in t.flange_bolts:
        for zc in (za - fw / 2, zb + fw / 2):
            bolts.append(bolt_solid(_mm(x), zc, h.bolt_flange, t.bolt_length_d2))
    comp = bolts[0]
    for s in bolts[1:]:
        comp = comp.fuse(s)
    out["连接螺栓"] = comp
    # 油标（杆式，45° 斜插在右端壁）与放油螺塞
    (ox, oy), ang = t.dipstick
    a = math.radians(ang)
    dirv = (math.cos(a), math.sin(a), 0)
    out["油标"] = bd.Solid.make_cylinder(8, 45, bd.Plane((_mm(ox) - 15 * math.cos(a), _mm(oy) - 15 * math.sin(a), W / 2), z_dir=dirv)).fuse(
        bd.Solid.make_cylinder(11, 8, bd.Plane((_mm(ox) + 30 * math.cos(a), _mm(oy) + 30 * math.sin(a), W / 2), z_dir=dirv)))
    dx, dy = (_mm(v) for v in t.drain)
    dd = _mm(t.drain_d)
    out["放油螺塞"] = bd.Solid.make_cylinder(dd * 0.8, 10, bd.Plane((dx, dy, W / 2), z_dir=(1, 0, 0))).fuse(
        bd.Solid.make_cylinder(dd / 2, 14, bd.Plane((dx, dy, W / 2), z_dir=(-1, 0, 0))))
    return out


def bearing_caps(t: HousingDetail, open_sides: list[str | None], seal_d: list[float | None]) -> dict[str, bd.Solid]:
    """凸缘式轴承盖（凸缘 + 伸入座孔的止口）。伸出端为透盖，留出轴孔。"""
    h = t.h
    W = _mm(h.inner_width)
    L1 = _mm(h.bearing_seat_length)
    e = _mm(h.cap_thickness)
    out: dict[str, bd.Solid] = {}
    for k, (x, cap) in enumerate(zip(t.shaft_x, t.caps)):
        D, D2 = _mm(cap.D), _mm(cap.D2)
        for side in ("left", "right"):
            z0 = -L1 - e if side == "left" else W + L1
            c = bd.Solid.make_cylinder(D2 / 2, e, bd.Plane((_mm(x), 0, z0)))
            sp = 8.0  # 止口长度
            zs = -L1 if side == "left" else W + L1 - sp
            c = c.fuse(bd.Solid.make_cylinder(D / 2 - 0.2, sp, bd.Plane((_mm(x), 0, zs))))
            if open_sides[k] == side:
                c = c.cut(bd.Solid.make_cylinder(_mm(seal_d[k]) / 2 + 1, e + sp + 2, bd.Plane((_mm(x), 0, min(z0, zs) - 1))))
            out[f"轴承{'透' if open_sides[k] == side else '闷'}盖-{k + 1}{'左' if side == 'left' else '右'}"] = c.clean()
    return out
