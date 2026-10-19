"""轴的疲劳强度安全系数法。出处：濮良贵《机械设计》第八版 式(15-6)～(15-8)（安全系数法）、
附表 3-1（综合影响系数 Kσ = kσ/εσ + 1/βσ − 1）；应力集中系数按 Pilkey《Peterson's Stress Concentration
Factors》第 3 版 图 3.10（阶梯轴弯曲）的数值核对；敏感系数、尺寸、表面系数按 Shigley《机械工程设计》
第 10 版 式(6-35)、(6-20)、(6-19)。"""

import math

import pytest

from gongke_core.calc import fatigue as f
from gongke_core.calc.shaft import PointLoad, Segment, ShaftLoadCase

MPA = 1e6


def test_kt_shoulder_bending_peterson_chart():
    # Peterson 图 3.10：D/d = 1.5，r/d = 0.05 时 Kt ≈ 2.2；r/d = 0.1 时 Kt ≈ 1.75
    d = 0.04
    assert f.kt_shoulder_bending(1.5 * d, d, 0.05 * d) == pytest.approx(2.17, abs=0.08)
    assert f.kt_shoulder_bending(1.5 * d, d, 0.1 * d) == pytest.approx(1.74, abs=0.06)


def test_kt_monotonic_and_bounds():
    d = 0.04
    # 圆角越大应力集中越小；台阶越高应力集中越大；无台阶时为 1
    assert f.kt_shoulder_bending(1.2 * d, d, 1e-3) > f.kt_shoulder_bending(1.2 * d, d, 2e-3)
    assert f.kt_shoulder_bending(1.5 * d, d, 1e-3) > f.kt_shoulder_bending(1.1 * d, d, 1e-3)
    assert f.kt_shoulder_bending(d, d, 1e-3) == 1.0
    # 扭转的应力集中小于弯曲
    assert 1 < f.kt_shoulder_torsion(1.5 * d, d, 2e-3) < f.kt_shoulder_bending(1.5 * d, d, 2e-3)


def test_notch_sensitivity():
    # Shigley 图 6-20：Sut ≈ 700 MPa、r = 1 mm 时 q ≈ 0.75～0.8；扭转更敏感
    q = f.notch_sensitivity(700 * MPA, 1e-3)
    assert 0.7 < q < 0.85
    assert f.notch_sensitivity(700 * MPA, 3e-3) > q
    assert f.notch_sensitivity(700 * MPA, 1e-3, torsion=True) > q


def test_size_and_surface_factor():
    # Shigley 式(6-20)：d = 51 mm 时 kb = 1.24·51^−0.107 ≈ 0.814
    assert f.size_factor(0.051) == pytest.approx(1.24 * 51**-0.107, rel=1e-9)
    assert f.size_factor(0.08) == pytest.approx(1.51 * 80**-0.157, rel=1e-9)
    assert f.size_factor(0.08) < f.size_factor(0.03) <= 1
    # 式(6-19)：车削 4.51·Sut^−0.265
    assert f.surface_factor(640 * MPA, ground=False) == pytest.approx(4.51 * 640**-0.265, rel=1e-9)
    assert f.surface_factor(640 * MPA, ground=True) > f.surface_factor(640 * MPA, ground=False)


def _plain_case(L=0.2, F=4000.0, T=0.0):
    case = ShaftLoadCase((0.0, L), [PointLoad(L / 2, fy=-F)], [(-0.01, T), (L + 0.01, -T)] if T else [])
    return case


def test_safety_factor_formula_bending_only():
    # 纯弯曲（对称循环）：Sca = Sσ = σ−1 / (Kσ σa)，σa = M/W
    mat = f.MATERIALS["45"]
    d, L, F = 0.04, 0.2, 4000.0
    m = F * L / 4
    s = f._section("x", L / 2, d, "轴肩圆角", m, 0.0, 2.0, 1.5, 1e-3, None, mat, False)
    W = math.pi * d**3 / 32
    assert s.sigma_a == pytest.approx(m / W)
    assert s.S_ca == pytest.approx(mat.sigma_m1 / (s.K_sigma * m / W))
    assert s.K_sigma == pytest.approx(s.k_sigma / s.eps + 1 / s.beta - 1)


def test_safety_factor_formula_combined():
    # 弯扭联合：Sca = SσSτ/√(Sσ² + Sτ²)，扭转按脉动循环 τa = τm = T/(2WT)
    mat = f.MATERIALS["40Cr"]
    d, m, t = 0.05, 300.0, 400.0
    s = f._section("x", 0, d, "轴肩圆角", m, t, 2.0, 1.5, 1.5e-3, None, mat, True)
    WT = math.pi * d**3 / 16
    assert s.tau_a == pytest.approx(t / (2 * WT))
    s_t = mat.tau_m1 / (s.K_tau * s.tau_a + mat.psi_tau * s.tau_a)
    assert s.S_tau == pytest.approx(s_t)
    assert s.S_ca == pytest.approx(s.S_sigma * s_t / math.hypot(s.S_sigma, s_t))


def test_check_finds_shoulders_and_keyway():
    # 中点受力的阶梯轴：两个轴肩 + 一段带键槽的齿轮段
    segs = [Segment(0.0, 0.03, 0.035, "轴承"), Segment(0.03, 0.06, 0.042, "齿轮", keyway=(0.012, 0.005, 0.05)),
            Segment(0.09, 0.08, 0.035, "轴承")]
    case = ShaftLoadCase((0.015, 0.155), [PointLoad(0.06, fy=-5000.0)], [(0.06, 300.0), (0.2, -300.0)])
    res = f.check(segs, case, f.MATERIALS["45"])
    feats = sorted(s.feature for s in res.sections)
    assert feats == ["轴肩圆角", "轴肩圆角", "键槽"]
    assert res.critical.S_ca == min(s.S_ca for s in res.sections)
    # 加大载荷后安全系数按反比下降，并判为不合格
    weak = f.check(segs, ShaftLoadCase(case.supports, [PointLoad(0.06, fy=-5e5)], case.torque_points),
                   f.MATERIALS["45"])
    assert not weak.ok


def test_fit_k_adds_hub_sections():
    segs = [Segment(0.0, 0.03, 0.035, "轴承"), Segment(0.03, 0.06, 0.042, "齿轮"), Segment(0.09, 0.08, 0.035, "轴承")]
    case = ShaftLoadCase((0.015, 0.155), [PointLoad(0.06, fy=-5000.0)], [])
    base = f.check(segs, case, f.MATERIALS["45"])
    with_fit = f.check(segs, case, f.MATERIALS["45"], fit_k=2.6)
    hubs = [s for s in with_fit.sections if s.feature == "过盈配合"]
    assert len(hubs) == 2 and len(with_fit.sections) == len(base.sections) + 2
    # 过盈配合处 kσ/εσ 就是给定值
    assert hubs[0].k_sigma / hubs[0].eps == pytest.approx(2.6)
