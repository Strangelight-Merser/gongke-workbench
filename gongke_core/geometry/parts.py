"""零件建模：渐开线斜齿轮、阶梯轴、深沟球轴承、联轴器半体、箱座。

内部计算用 SI（m），build123d 建模统一换算为 mm（STEP 文件的常用单位）。
"""

from __future__ import annotations

import math

import build123d as bd

from gongke_core.calc.gear import GearPair, transverse_pressure_angle
from gongke_core.calc.shaft import Segment
from gongke_core.layout.reducer import Housing

MM = 1e-3


def _mm(v: float) -> float:
    return v / MM


def _inv(a: float) -> float:
    return math.tan(a) - a


def gear_outline(z: int, mn: float, beta: float, alpha_n: float = math.radians(20),
                 ha: float = 1.0, c: float = 0.25, flank_points: int = 7) -> list[list[tuple[float, float]]]:
    """标准渐开线齿轮的端面齿廓，返回每个齿的一组 (x, y) 点（mm），齿 0 对称于 +x 轴。

    齿廓按端面参数计算：mt = mn/cos β，αt = arctan(tan αn / cos β)。
    齿根圆低于基圆时，齿根处用径向直线连接到齿根圆。
    """
    mt = mn / math.cos(beta)
    at = transverse_pressure_angle(alpha_n, beta)
    r = _mm(z * mt / 2)
    rb = r * math.cos(at)
    ra = r + _mm(ha * mn)
    rf = r - _mm((ha + c) * mn)
    psi = math.pi / (2 * z)  # 分度圆上半齿厚对应的圆心角
    r_start = max(rf, rb)
    flank = []
    for i in range(flank_points):
        rho = r_start + (ra - r_start) * i / (flank_points - 1)
        a_rho = math.acos(min(rb / rho, 1.0))
        flank.append((rho, psi + _inv(at) - _inv(a_rho)))
    teeth = []
    for k in range(z):
        c0 = 2 * math.pi * k / z
        pts = []
        if rf < rb:
            pts.append((rf, c0 - flank[0][1]))
        pts += [(rho, c0 - th) for rho, th in flank]
        pts += [(rho, c0 + th) for rho, th in reversed(flank)]
        if rf < rb:
            pts.append((rf, c0 + flank[0][1]))
        teeth.append([(rho * math.cos(t), rho * math.sin(t)) for rho, t in pts])
    return teeth


def gear_face(z: int, mn: float, beta: float, rotation: float = 0.0, hole_r: float | None = None) -> bd.Face:
    """端面齿廓面（可带中心圆孔，半径 mm）。齿廓用折线逼近（每侧 7 点），满足装配与出图示意。"""
    pts = []
    for tooth in gear_outline(z, mn, beta):
        pts += tooth
    c, s = math.cos(rotation), math.sin(rotation)
    pts = [(x * c - y * s, x * s + y * c) for x, y in pts]
    wire = bd.Wire.make_polygon([bd.Vector(x, y, 0) for x, y in pts], close=True)
    if hole_r:
        return bd.Face(wire, [bd.Wire.make_circle(hole_r)])
    return bd.Face(wire)


def helical_gear(z: int, mn: float, beta: float, width: float, hand: int = 1, rotation: float = 0.0,
                 hole_r: float | None = None, teeth: bool = True) -> bd.Solid:
    """斜齿轮齿圈实体，轴线为 z，齿宽中面在 z=0。hand=+1 右旋、−1 左旋。hole_r 为内孔半径（mm）。"""
    if not teeth:
        # 简化表示：齿顶圆柱体（文件小、打开快，适合装配和出图）
        ra = _mm(z * mn / math.cos(beta) / 2 + mn)
        b = _mm(width)
        solid = bd.Solid.make_cylinder(ra, b, bd.Plane((0, 0, -b / 2)))
        if hole_r:
            solid = solid.cut(bd.Solid.make_cylinder(hole_r, b, bd.Plane((0, 0, -b / 2))))
        return solid
    r = _mm(z * mn / math.cos(beta) / 2)
    b = _mm(width)
    twist = math.degrees(b * math.tan(beta) / r) * hand
    face = gear_face(z, mn, beta, rotation - math.radians(twist) / 2, hole_r)
    solid = bd.Solid.extrude_linear_with_rotation(face, (0, 0, 0), (0, 0, b), twist)
    return solid.moved(bd.Location((0, 0, -b / 2)))


def _keyway_cutter(width: float, depth_from_axis: float, length: float, radius: float) -> bd.Solid:
    """沿 z 方向的圆头键槽切削体，位于 +y 一侧，槽底到轴线距离 depth_from_axis（mm）。"""
    h = radius - depth_from_axis + 2
    box = bd.Solid.make_box(width, h, max(length - width, 0.01)).moved(
        bd.Location((-width / 2, depth_from_axis, -(length - width) / 2)))
    cut = box
    for zc in (-(length - width) / 2, (length - width) / 2):
        cyl = bd.Solid.make_cylinder(width / 2, h, bd.Plane((0, depth_from_axis, zc), z_dir=(0, 1, 0)))
        cut = cut.fuse(cyl)
    return cut


def gear_blank(pair: GearPair, member: int, bore: float | None, key: tuple[float, float, float] | None,
               rotation: float = 0.0, teeth: bool = True) -> bd.Solid:
    """完整齿轮：齿圈 + 轮毂孔 + 键槽，腹板式齿轮开减重孔（结构尺寸见 layout.gear_blank）。

    为加快布尔运算，齿圈（带螺旋扭转）与轮体（普通回转体）分别建模后合并。
    """
    from gongke_core.layout.gear_blank import blank

    g = blank(pair, member, bore)
    hand = 1 if member == 1 else -1
    if bore is None:
        return helical_gear(g.z, pair.mn, pair.beta, g.b, hand, rotation, teeth=teeth)
    b = _mm(g.b)
    db = _mm(g.bore)
    r_in = _mm(g.rim_inner_d) / 2 if g.web else _mm(g.df) / 2 - max(3 * _mm(pair.mn), 10)
    # 先做实心斜齿轮再挖去内部，比直接拉伸带孔截面快得多
    ring = helical_gear(g.z, pair.mn, pair.beta, g.b, hand, rotation, teeth=teeth)
    ring = ring.cut(bd.Solid.make_cylinder(r_in, b + 2, bd.Plane((0, 0, -b / 2 - 1))))
    body = bd.Solid.make_cylinder(r_in, b, bd.Plane((0, 0, -b / 2)))
    if g.web:
        recess = (b - _mm(g.web_thickness)) / 2
        for z0 in (-b / 2 - 1, b / 2 - recess):
            ring_cut = bd.Solid.make_cylinder(r_in, recess + 1, bd.Plane((0, 0, z0)))
            ring_cut = ring_cut.cut(bd.Solid.make_cylinder(_mm(g.hub_d) / 2, recess + 1, bd.Plane((0, 0, z0))))
            body = body.cut(ring_cut)
        for k in range(g.holes):
            a = 2 * math.pi * k / g.holes
            c = _mm(g.hole_pcd) / 2
            hole = bd.Solid.make_cylinder(_mm(g.hole_d) / 2, b + 2, bd.Plane((c * math.cos(a), c * math.sin(a), -b / 2 - 1)))
            body = body.cut(hole)
    body = body.cut(bd.Solid.make_cylinder(db / 2, b + 2, bd.Plane((0, 0, -b / 2 - 1))))
    if key:
        kb, t2 = _mm(g.key_b), _mm(g.key_t2)
        body = body.cut(bd.Solid.make_box(kb, db / 2 + t2, b + 4).moved(bd.Location((-kb / 2, 0, -b / 2 - 2))))
    return ring.fuse(body).clean()


def stepped_shaft(segments: list[Segment], integral: list[tuple[GearPair, float, float]] = (), teeth: bool = True) -> bd.Solid:
    """阶梯轴：各段圆柱合并，切出键槽；integral 为齿轮轴的 (齿轮副, 齿宽中点 z, 转角)。"""
    solid = None
    for s in segments:
        if s.role == "齿轮轴":
            continue
        cyl = bd.Solid.make_cylinder(_mm(s.d) / 2, _mm(s.length), bd.Plane((0, 0, _mm(s.z0))))
        solid = cyl if solid is None else solid.fuse(cyl)
    for pair, zc, rot in integral:
        gear = helical_gear(pair.z1, pair.mn, pair.beta, pair.b1, 1, rot, teeth=teeth).moved(bd.Location((0, 0, _mm(zc))))
        solid = solid.fuse(gear)
    for s in segments:
        if s.keyway:
            kb, t1, kl = s.keyway
            r = _mm(s.d) / 2
            cutter = _keyway_cutter(_mm(kb), r - _mm(t1), _mm(kl), r)
            solid = solid.cut(cutter.moved(bd.Location((0, 0, _mm(s.z0 + s.length / 2)))))
    return solid.clean()


def ball_bearing(d: float, D: float, B: float) -> bd.Solid:
    """深沟球轴承简化模型：内圈、外圈和钢球。中面在 z=0。"""
    d, D, B = _mm(d), _mm(D), _mm(B)
    wall = 0.3 * (D - d) / 2
    dw = 0.3 * (D - d)  # 钢球直径
    dm = (D + d) / 2
    pl = bd.Plane((0, 0, -B / 2))

    def ring(r_out, r_in):
        return bd.Solid.make_cylinder(r_out, B, pl).cut(bd.Solid.make_cylinder(r_in, B, pl))

    inner = ring(d / 2 + wall, d / 2)
    outer = ring(D / 2, D / 2 - wall)
    n = max(int(math.pi * dm / (dw * 1.5)), 6)
    parts = [inner, outer]
    for k in range(n):
        a = 2 * math.pi * k / n
        parts.append(bd.Solid.make_sphere(dw / 2).moved(bd.Location((dm / 2 * math.cos(a), dm / 2 * math.sin(a), 0))))
    return bd.Compound(parts)


def coupling_half(bore: float, hub_length: float) -> bd.Solid:
    """弹性柱销联轴器半体示意：轮毂 + 法兰。轴孔一侧端面在 z=0，沿 +z 延伸。"""
    db, L = _mm(bore), _mm(hub_length)
    hub = bd.Solid.make_cylinder(db, L, bd.Plane((0, 0, 0)))
    flange = bd.Solid.make_cylinder(1.6 * db, 0.25 * L, bd.Plane((0, 0, L - 0.25 * L)))
    return hub.fuse(flange).cut(bd.Solid.make_cylinder(db / 2, L + 2, bd.Plane((0, 0, -1))))


def v_pulley(p) -> bd.Solid:
    """V 带轮（`layout.pulley.PulleyBlank`）：半剖面回转成实体，再开减重孔和键槽。轮毂左端面在 z=0。"""
    pts = [bd.Vector(_mm(r), 0, _mm(z)) for r, z in p.profile()]
    body = bd.Solid.revolve(bd.Face(bd.Wire.make_polygon(pts, close=True)), 360, bd.Axis.Z)
    L = _mm(p.hub_length)
    for k in range(p.holes):
        a = 2 * math.pi * k / p.holes + math.pi / p.holes
        r = _mm(p.hole_pcd) / 2
        body = body.cut(bd.Solid.make_cylinder(_mm(p.hole_d) / 2, L + 2, bd.Plane((r * math.cos(a), r * math.sin(a), -1))))
    kb, kt = _mm(p.key_b), _mm(p.key_t2)
    rd = _mm(p.bore) / 2
    key = bd.Solid.make_box(kb, rd + kt, L + 2).moved(bd.Location((-kb / 2, 0, -1)))
    return body.cut(key).clean()


def side_boss(side, x_inner: float) -> tuple[bd.Solid, bd.Solid]:
    """−x 端壁上Ⅰ轴的轴承座（`housing_detail.SideBore`）：返回 (凸台, 座孔)，从内壁 x_inner 到外端面，单位 mm。"""
    x0, x1 = _mm(side.x_face), _mm(x_inner)
    pl = bd.Plane((x0, 0, _mm(side.z)), z_dir=(1, 0, 0))
    boss = bd.Solid.make_cylinder(_mm(side.boss_r), x1 - x0, pl)
    bore = bd.Solid.make_cylinder(_mm(side.D) / 2, x1 - x0 + 2, bd.Plane((x0 - 1, 0, _mm(side.z)), z_dir=(1, 0, 0)))
    return boss, bore


def housing_base(h: Housing, shaft_x: list[float], bearing_D: list[float], side=None) -> bd.Solid:
    """箱座（剖分面以下）简化模型：壁、上凸缘、底座、轴承座和轴承孔。剖分面为 y = 0。

    side 为圆锥-圆柱减速器 −x 端壁上的Ⅰ轴轴承座（`housing_detail.SideBore`）。"""
    d = _mm(h.delta)
    x0, x1 = (_mm(v) for v in h.x_range)
    y0 = _mm(h.y_range[0])
    w = _mm(h.inner_width)
    flange_w = _mm(h.c1 + h.c2)
    L1 = _mm(h.bearing_seat_length)
    outer = bd.Solid.make_box(x1 - x0 + 2 * d, -y0 + d, w + 2 * d).moved(bd.Location((x0 - d, y0 - d, -d)))
    inner = bd.Solid.make_box(x1 - x0, -y0 + 1, w).moved(bd.Location((x0, y0, 0)))
    body = outer.cut(inner)
    # 上凸缘
    fb = _mm(h.flange_base)
    fl = bd.Solid.make_box(x1 - x0 + 2 * d + 2 * flange_w, fb, w + 2 * d + 2 * flange_w).moved(
        bd.Location((x0 - d - flange_w, -fb, -d - flange_w)))
    body = body.fuse(fl.cut(inner))
    # 底座
    b2 = _mm(h.flange_foot)
    foot = bd.Solid.make_box(x1 - x0 + 2 * d + 2 * flange_w, b2, w + 2 * d + 2 * flange_w).moved(
        bd.Location((x0 - d - flange_w, y0 - d, -d - flange_w)))
    body = body.fuse(foot)
    # 轴承座：两侧壁上的凸台，长度 L1 从内壁算起
    for x, D in zip(shaft_x, bearing_D):
        Dm = _mm(D)
        boss_d = Dm + 2 * max(0.25 * Dm, 12)
        for z0 in (-L1, w):
            boss = bd.Solid.make_cylinder(boss_d / 2, L1, bd.Plane((_mm(x), 0, z0)))
            body = body.fuse(boss)
    if side is not None:
        side_solids = side_boss(side, h.x_range[0])
        body = body.fuse(side_solids[0])
    # 剖分面以上的部分去掉
    big = 1e4
    body = body.cut(bd.Solid.make_box(2 * big, big, 2 * big).moved(bd.Location((-big, 0, -big))))
    # 轴承孔
    for x, D in zip(shaft_x, bearing_D):
        bore = bd.Solid.make_cylinder(_mm(D) / 2, w + 2 * L1 + 2, bd.Plane((_mm(x), 0, -L1 - 1)))
        body = body.cut(bore)
    if side is not None:
        body = body.cut(side_solids[1])
    return body.clean()
