"""箱体细部：箱盖外形包络、螺栓布置、附件位置。"""

import math
from pathlib import Path

import pytest

from gongke_core import design
from gongke_core.layout import housing_detail as hd

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"


def test_envelope_two_equal_circles_is_flat_top():
    # 两个等半径圆的上公切线是水平线 y = R（解析解）
    env = hd.upper_envelope([(0.0, 1.0), (3.0, 1.0)])
    seg = next(e for e in env if isinstance(e, hd.Seg))
    assert seg.p == pytest.approx((0.0, 1.0)) and seg.q == pytest.approx((3.0, 1.0))
    assert hd.envelope_height(env, 1.5) == pytest.approx(1.0)


def test_envelope_tangent_is_perpendicular_to_radii():
    circles = [(0.0, 0.6), (1.4, 1.37), (3.25, 1.68)]
    env = hd.upper_envelope(circles)
    for e in env:
        if isinstance(e, hd.Seg):
            dx, dy = e.q[0] - e.p[0], e.q[1] - e.p[1]
            for (cx, r) in circles:
                for pt in (e.p, e.q):
                    if abs(math.hypot(pt[0] - cx, pt[1]) - r) < 1e-9:
                        assert (pt[0] - cx) * dx + pt[1] * dy == pytest.approx(0.0, abs=1e-9)
    # 包络从左端 (x−R, 0) 到右端 (x+R, 0)，且不低于每个圆
    pts = hd.envelope_points(env)
    assert pts[0] == pytest.approx((-0.6, 0.0)) and pts[-1] == pytest.approx((4.93, 0.0))
    for cx, r in circles:
        for k in range(1, 20):
            x = cx - r + 2 * r * k / 20
            assert hd.envelope_height(env, x) >= math.sqrt(r * r - (x - cx) ** 2) - 1e-9


def test_envelope_small_circle_inside_is_skipped():
    env = hd.upper_envelope([(0.0, 2.0), (0.5, 0.5)])
    assert len(env) == 1 and isinstance(env[0], hd.Arc)


@pytest.fixture(scope="module")
def det():
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE))
    return d, hd.detail(d)


def test_cover_clears_gears(det):
    d, t = det
    h = d.housing
    # 箱盖内壁到大齿轮齿顶的距离不小于 Δ1
    for x, r, tip in zip(t.shaft_x, t.cover_r, [d.high.da1, max(d.high.da2, d.low.da1), d.low.da2]):
        assert r - h.delta1 - tip / 2 >= h.gap_radial - 1e-9


def test_bolts_inside_flange_and_clear_of_bearing_bores(det):
    d, t = det
    h = d.housing
    lo, hi = t.x_outer[0] - t.flange_w, t.x_outer[1] + t.flange_w
    for x in t.bearing_bolts + t.flange_bolts:
        assert lo + h.bolt_bearing / 2 < x < hi - h.bolt_bearing / 2
    for x in t.bearing_bolts:
        for xc, cap in zip(t.shaft_x, t.caps):
            assert abs(x - xc) - h.bolt_bearing / 2 > cap.D / 2  # 不打穿轴承孔
    xs = sorted(t.bearing_bolts + t.flange_bolts)
    assert max(b - a for a, b in zip(xs, xs[1:])) <= 0.15 + 1e-9  # 螺栓间距不大于 150 mm


def test_oil_level_and_accessories(det):
    d, t = det
    # 大齿轮浸油深度 ≥ 10 mm，油面在箱座内
    assert -d.low.da2 / 2 + 0.01 <= t.oil_level + 1e-12
    assert d.housing.y_range[0] < t.oil_level < 0
    # 视孔盖贴在箱盖外表面上
    c = t.inspection.center
    assert c[1] == pytest.approx(hd.envelope_height(t.cover_outer, c[0]), abs=1e-6)
    assert t.bolt_length_d1 >= d.housing.flange_base + d.housing.flange_cover + 1.35 * d.housing.bolt_bearing


def test_envelope_left_wall_tangent():
    # 端壁顶点 (−1, 1) 到单位圆 (0, 0) 的切线：切点 (0, 1)（解析解），端壁竖直
    env = hd.upper_envelope([(0.0, 1.0)], left_wall=(-1.0, 1.0))
    assert isinstance(env[0], hd.Seg) and env[0].p == pytest.approx((-1.0, 0.0)) and env[0].q == pytest.approx((-1.0, 1.0))
    assert env[1].q == pytest.approx((0.0, 1.0), abs=1e-12)
    assert hd.envelope_height(env, -0.5) == pytest.approx(1.0)
    assert hd.envelope_points(env)[-1] == pytest.approx((1.0, 0.0))
    # 端壁顶点在圆内：端壁只升到圆上
    env = hd.upper_envelope([(0.0, 1.0)], left_wall=(-0.6, 0.5))
    assert env[0].q == pytest.approx((-0.6, 0.8))
    # 顶点直接与后面更大的圆相切
    env = hd.upper_envelope([(0.0, 0.5), (2.0, 2.0)], left_wall=(-0.5, 2.0))
    assert env[1].q == pytest.approx((2.0, 2.0)) and len([e for e in env if isinstance(e, hd.Arc)]) == 1


def test_bearing_side_boss_clears_bearing_seat(det):
    _, t = det
    h = t.h
    # 螺母支承面（半径 1.05d1）落在凸台下表面 y = −h 上时，不与轴承座圆柱 (x − xc)² + y² ≤ rb² 相交
    r_seat = 1.05 * h.bolt_bearing
    for xb in t.bearing_bolts:
        for xc, rb in zip(t.shaft_x, t.boss_r):
            u = max(abs(xb - xc) - r_seat, 0.0)
            assert u >= rb or math.hypot(u, t.boss_h) >= rb
        # 每个轴承旁螺栓都在凸台范围内，且支承面不超出凸台
        assert any(a <= xb - r_seat and xb + r_seat <= b for a, b in t.side_bosses)
    # 连接螺栓 d2 不布置在凸台上；轴承旁螺栓长度按两凸台高度计
    assert not any(a <= x <= b for x in t.flange_bolts for a, b in t.side_bosses)
    assert t.bolt_length_d1 >= 2 * t.boss_h + 1.35 * h.bolt_bearing - 1e-9

