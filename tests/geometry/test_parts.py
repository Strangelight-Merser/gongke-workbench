"""三维零件建模。渐开线齿廓检查用解析关系：分度圆齿厚 s = π mt / 2，基圆 rb = r cos αt。"""

import math

import pytest

bd = pytest.importorskip("build123d")

from gongke_core.calc.shaft import Segment  # noqa: E402
from gongke_core.geometry import parts  # noqa: E402

MN, BETA = 2e-3, math.radians(14)


def test_outline_tooth_count_and_tip_root():
    teeth = parts.gear_outline(24, MN, BETA)
    assert len(teeth) == 24
    r = 24 * MN / math.cos(BETA) / 2 * 1e3
    radii = [math.hypot(x, y) for t in teeth for x, y in t]
    assert max(radii) == pytest.approx(r + 2.0, abs=1e-6)  # ra = r + ha* mn
    assert min(radii) >= r - 2.5 - 1e-6  # 不低于齿根圆


def test_tooth_thickness_at_pitch_circle():
    # 齿廓上半径等于分度圆半径处，齿厚对应圆心角 2ψ = π/z
    z = 30
    mt = MN / math.cos(BETA)
    at = math.atan(math.tan(math.radians(20)) / math.cos(BETA))
    r = z * mt / 2
    rb = r * math.cos(at)
    a_r = math.acos(rb / r)
    psi = math.pi / (2 * z)
    theta = psi + (math.tan(at) - at) - (math.tan(a_r) - a_r)
    assert 2 * theta * r == pytest.approx(math.pi * mt / 2)


def test_helical_gear_volume_between_root_and_tip():
    z, b = 30, 20e-3
    g = parts.helical_gear(z, MN, BETA, b)
    r = z * MN / math.cos(BETA) / 2 * 1e3
    v_tip = math.pi * (r + 2) ** 2 * 20
    v_root = math.pi * (r - 2.5) ** 2 * 20
    assert g.is_valid
    assert v_root < g.volume < v_tip


def test_stepped_shaft_volume():
    segs = [Segment(0.0, 0.05, 0.03, "轴承"), Segment(0.05, 0.08, 0.035, "齿轮", keyway=(0.01, 0.005, 0.07))]
    s = parts.stepped_shaft(segs)
    full = math.pi * 15**2 * 50 + math.pi * 17.5**2 * 80
    key = (10 * 60 + math.pi * 5**2) * 5  # 圆头键槽的近似体积（槽深 5 mm）
    assert s.is_valid
    assert s.volume == pytest.approx(full - key, rel=0.01)


def test_bearing_fits_dimensions():
    b = parts.ball_bearing(0.04, 0.08, 0.018)
    bb = b.bounding_box()
    assert bb.size.X == pytest.approx(80, abs=0.01)
    assert bb.size.Z == pytest.approx(18, abs=0.01)


def test_v_pulley_volume_matches_pappus():
    # 无孔腹板式带轮：实体体积 = 截面积 × 2π × 形心半径 − 键槽体积
    import math

    from gongke_core.calc import vbelt
    from gongke_core.layout import pulley

    p = pulley.blank(vbelt.section("A"), 180e-3, 3, 30e-3, 50e-3)
    assert p.kind == "腹板式"
    pts = [(r * 1e3, z * 1e3) for r, z in p.profile()]
    a = cx = 0.0
    for (r0, z0), (r1, z1) in zip(pts, pts[1:] + pts[:1]):
        c = r0 * z1 - r1 * z0
        a += c
        cx += (r0 + r1) * c
    a /= 2
    vol = a * 2 * math.pi * cx / (6 * a)
    solid = parts.v_pulley(p)
    assert solid.is_valid
    assert solid.volume == pytest.approx(vol, rel=0.03)


def test_bevel_gear_volume_matches_pappus():
    # 锥齿轮按齿顶圆锥简化：体积 = 半剖面面积 × 2π × 形心半径 − 键槽体积（≤ 3%）
    import math

    from gongke_core.calc import bevel as bv
    from gongke_core.calc import kinematics
    from gongke_core.geometry import bevel as bg
    from gongke_core.layout import bevel_blank

    t = kinematics.torque_from_power(4e3, 1440)
    pair = bv.design(bv.BevelPairInput("高速级", t, 1440, 3.0, 15 * 300 * 16))
    g = bevel_blank.blank(pair, 2, 35e-3)
    pts = [(z * 1e3, r * 1e3) for z, r in g.profile()]
    a = cr = 0.0
    for (z0, r0), (z1, r1) in zip(pts, pts[1:] + pts[:1]):
        c = z0 * r1 - z1 * r0
        a += c
        cr += (r0 + r1) * c
    a /= 2
    vol = abs(a) * 2 * math.pi * cr / (6 * a)
    solid = bg.bevel_gear(g)
    assert solid.is_valid
    assert solid.volume == pytest.approx(vol, rel=0.03)
