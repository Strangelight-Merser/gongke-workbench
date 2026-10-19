"""齿条刀具展成的齿廓。

渐开线极坐标方程 θ = inv αK = tan αK − αK，cos αK = rb / rK；分度圆齿厚 s = πm/2（标准齿轮）；
齿根圆半径 rf = r − (ha* + c*)m。见《机械原理》（孙桓主编，第 8 版，高等教育出版社）第 10 章渐开线齿廓与标准齿轮尺寸。
基本齿条参数 ha* = 1、c* = 0.25、ρf* = 0.38 按 GB/T 1356-2001。
"""

import math

import pytest

from gongke_core.calc import tooth_profile as tp

ALPHA = math.radians(20)


def inv(a):
    return math.tan(a) - a


@pytest.mark.parametrize("z", [17, 20, 35.3, 100])
def test_involute_and_pitch_thickness(z):
    p = tp.generate(z, m=2.0)
    r, rb = p.r, p.r * math.cos(ALPHA)
    for x, y in p.involute:
        R = math.hypot(x, y)
        if R < rb * 1.0001:
            continue
        half = math.pi / 2 - math.atan2(y, x)  # 到齿对称线的圆心角
        assert half == pytest.approx(math.pi / (2 * z) + inv(ALPHA) - inv(math.acos(rb / R)), abs=1e-9)
    assert math.hypot(*p.involute[-1]) == pytest.approx(p.ra, rel=1e-9)
    assert math.hypot(*p.root[0]) == pytest.approx(r - 2.5, rel=1e-12)


@pytest.mark.parametrize("z", [17, 25, 60])
def test_profile_is_continuous_and_tangent(z):
    p = tp.generate(z)
    half = p.half()
    gaps = [math.dist(a, b) for a, b in zip(half, half[1:])]
    assert max(gaps) < 0.2  # m = 1，没有断开
    # 过渡曲线与渐开线、齿根圆相切：连接点两侧的方向差很小
    def direction(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])
    f, i = p.fillet, p.involute
    assert abs(direction(f[-2], f[-1]) - direction(i[0], i[1])) < math.radians(6)
    rs = [math.hypot(*q) for q in f]
    assert all(b >= a - 1e-12 for a, b in zip(rs, rs[1:]))  # 过渡曲线半径单调增加
    assert rs[0] == pytest.approx(p.rf, rel=1e-12)


def test_fillet_radius_near_root_matches_cutter():
    """齿条（z → ∞）时过渡曲线就是刀尖圆角本身，曲率半径为 0.38m。"""
    p = tp.generate(2000)
    a, b, c = p.fillet[3], p.fillet[12], p.fillet[21]
    # 三点定圆
    ax, ay = a; bx, by = b; cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    assert math.dist((ux, uy), a) == pytest.approx(0.38, rel=0.01)
