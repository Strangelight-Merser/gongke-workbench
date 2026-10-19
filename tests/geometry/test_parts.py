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
