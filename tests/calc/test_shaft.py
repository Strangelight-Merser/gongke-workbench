"""轴的强度计算。出处：濮良贵《机械设计》第八版 式(15-2) d ≥ A0∛(P/n)、式(15-5) 弯扭合成、
表 15-4 抗弯截面系数；简支梁反力和弯矩用材料力学解析解。"""

import math

import pytest

from gongke_core.calc import shaft as s


def test_min_diameter():
    assert s.min_diameter(10e3, 960, a0=112) == pytest.approx(112 * (10 / 960) ** (1 / 3) * 1e-3)


def test_simply_supported_center_load():
    # 跨度 L、中点集中力 F：RA = RB = F/2，Mmax = FL/4
    L, F = 0.2, 1000.0
    case = s.ShaftLoadCase((0.0, L), [s.PointLoad(L / 2, fy=-F)], [])
    r = s.reactions(case)
    assert r.ay == pytest.approx(F / 2) and r.by == pytest.approx(F / 2)
    _, my = s.bending_moments(case, L / 2 + 1e-9)
    assert abs(my) == pytest.approx(F * L / 4, rel=1e-6)


def test_offset_load():
    # 力作用在距 A 为 a 处：RB = F a / L，M = F a b / L
    L, a, F = 0.3, 0.1, 600.0
    case = s.ShaftLoadCase((0.0, L), [s.PointLoad(a, fx=F)], [])
    r = s.reactions(case)
    assert r.bx == pytest.approx(-F * a / L)
    mx, _ = s.bending_moments(case, a + 1e-9)
    assert abs(mx) == pytest.approx(F * a * (L - a) / L, rel=1e-6)


def test_axial_force_couple():
    # 轴向力 Fa 作用在半径 r 处，等效于力偶 C = Fa·r：两支反力 ±C/L
    L, fa, r = 0.2, 500.0, 0.05
    case = s.ShaftLoadCase((0.0, L), [s.PointLoad(0.1, fz=fa, x0=r)], [])
    re = s.reactions(case)
    assert abs(re.ax) == pytest.approx(fa * r / L)
    assert re.ax == pytest.approx(-re.bx)
    assert re.axial == pytest.approx(fa)


def test_section_modulus_with_keyway():
    d, b, t = 0.05, 0.014, 0.0055
    assert s.section_modulus(d) == pytest.approx(math.pi * d**3 / 32)
    assert s.section_modulus(d, (b, t, 0.05)) == pytest.approx(math.pi * d**3 / 32 - b * t * (d - t) ** 2 / (2 * d))


def test_combined_stress_pure_torsion():
    # 只有转矩时 σca = αT / W
    d, T = 0.04, 200.0
    segs = [s.Segment(0.0, 0.2, d, "轴")]
    case = s.ShaftLoadCase((0.0, 0.2), [], [(0.0, T), (0.2, -T)])
    chk = s.check(segs, case, alpha=0.6)
    assert chk.critical.sigma_ca == pytest.approx(0.6 * T / (math.pi * d**3 / 32), rel=1e-6)
