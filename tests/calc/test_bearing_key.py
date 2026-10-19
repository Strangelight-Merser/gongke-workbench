"""轴承寿命与平键校核。出处：濮良贵《机械设计》第八版 式(13-5a) L10h = 10⁶/(60n)(C/P)^ε、
式(13-8a) P = fp(XFr + YFa)；式(6-1) 平键挤压强度 σp = 2T/(kld)。"""

import pytest

from gongke_core import standards
from gongke_core.calc import bearing, key


def test_life_formula():
    assert bearing.life_hours(1000, 1000, 1000) == pytest.approx(1e6 / 60000)
    # 载荷减半，球轴承寿命变为 8 倍
    assert bearing.life_hours(2000, 1000, 1000) == pytest.approx(8 * 1e6 / 60000)


def test_equivalent_load_small_axial():
    p, e, x, y = bearing.equivalent_load(1000, 50, 15e3, f_p=1.0)
    assert (x, y) == (1.0, 0.0) and p == pytest.approx(1000)


def test_equivalent_load_large_axial():
    p, e, x, y = bearing.equivalent_load(1000, 600, 15e3, f_p=1.0)
    assert x == 0.56 and y > 1
    assert p == pytest.approx(0.56 * 1000 + y * 600)


def test_axial_goes_to_correct_bearing():
    b = standards.bearings_with_bore(0.04)[0]
    c = bearing.check_pair(b, 1000, 1000, -300, 1000, 10000)
    assert c.fa == (300, 0.0)


def test_key_crush_stress():
    assert key.crush_stress(200, 0.04, 0.008, 0.04) == pytest.approx(2 * 200 / (0.004 * 0.04 * 0.04))


def test_key_select_uses_hub_length():
    k = key.select("测试", 300, 0.045, 0.06)
    assert k.size.b == pytest.approx(0.014)
    assert k.length <= 0.055 + 1e-9
    assert k.ok
