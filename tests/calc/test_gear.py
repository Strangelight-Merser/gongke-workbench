"""斜齿圆柱齿轮设计。公式出处均为濮良贵《机械设计》第八版第 10 章，各测试注明对应公式。"""

import math

import pytest

from gongke_core import standards
from gongke_core.calc import gear as g

A20 = math.radians(20)


def test_zone_factor_spur_is_2_5():
    # 标准直齿轮 ZH = √(2/(sin α cos α)) ≈ 2.5（教材图 10-30 β=0 处）
    assert g.zone_factor(A20, 0.0) == pytest.approx(2.495, abs=1e-3)


def test_zone_factor_decreases_with_helix():
    assert g.zone_factor(A20, math.radians(15)) < g.zone_factor(A20, 0.0)


def test_contact_ratio_vs_approximate_formula():
    # 近似式 εα ≈ [1.88 − 3.2(1/z1 + 1/z2)] cos β（教材式 10-8 的工程近似）
    for z1, z2, beta in [(24, 72, 0.0), (20, 100, math.radians(14)), (30, 90, math.radians(10))]:
        approx = (1.88 - 3.2 * (1 / z1 + 1 / z2)) * math.cos(beta)
        assert g.transverse_contact_ratio(z1, z2, A20, beta) == pytest.approx(approx, rel=0.03)


def test_overlap_ratio():
    # εβ = φd z1 tan β / π（教材式 10-9 下方）
    assert g.overlap_ratio(1.0, 24, math.radians(14)) == pytest.approx(24 * math.tan(math.radians(14)) / math.pi)


def test_contact_ratio_factor_spur():
    # 直齿轮 εβ = 0：Zε = √((4 − εα)/3)
    assert g.contact_ratio_factor(1.7, 0.0) == pytest.approx(math.sqrt((4 - 1.7) / 3))
    assert g.contact_ratio_factor(1.6, 1.5) == pytest.approx(math.sqrt(1 / 1.6))


def test_helix_factor_bending():
    # Yβ = 1 − εβ β/120°，εβ > 1 取 1
    assert g.helix_factor_bending(0.5, math.radians(12)) == pytest.approx(1 - 0.5 * 12 / 120)
    assert g.helix_factor_bending(2.0, math.radians(12)) == pytest.approx(0.9)


def test_virtual_teeth():
    assert g.virtual_teeth(24, math.radians(14)) == pytest.approx(24 / math.cos(math.radians(14)) ** 3)


def test_form_factor_table_points_and_interpolation():
    # 表 10-5 的表列值，以及相邻两点之间的线性插值
    assert standards.form_factors(24) == pytest.approx((2.65, 1.58))
    assert standards.form_factors(32.5) == pytest.approx(((2.52 + 2.45) / 2, (1.625 + 1.65) / 2))
    yfa, ysa = standards.form_factors(1e9)
    assert yfa == pytest.approx(2.06, abs=1e-3) and ysa == pytest.approx(1.97, abs=1e-3)


def test_face_load_factor_formula():
    # 表 10-4 8 级精度经验式，φd = 1、b = 50 mm
    assert g.face_load_factor_contact(1.0, 0.05, 8) == pytest.approx(1.15 + 0.18 * 1.6 + 0.31e-3 * 50)


def test_life_factor_anchor_points():
    # ISO 6336-2/-3 寿命曲线的拐点
    assert g.life_factor_contact(5e7) == pytest.approx(1.0)
    assert g.life_factor_contact(1e10) == pytest.approx(0.85)
    assert g.life_factor_contact(1e5) == pytest.approx(1.6)
    assert g.life_factor_bending(3e6) == pytest.approx(1.0)
    assert g.life_factor_bending(1e10) == pytest.approx(0.85)


def test_contact_stress_formula_inverts_design_formula():
    # 校核式 σH = ZH ZE Zε Zβ √(2KT1/(b d1²)·(u+1)/u) 与设计式 d1 ≥ ∛(2KT1/φd·(u+1)/u·(Z/[σH])²) 互逆
    inp = g.GearPairInput("高速级", 100.0, 960, 4.0, 48000, overrides={"k_v": 1.0, "k_alpha": 1.0, "k_hbeta": 1.0})
    z1, z2, mn, beta, b = 24, 96, 2.5e-3, math.radians(14), 60e-3
    chk = g.check_strength(inp, z1, z2, mn, beta, b, 500e6, (300e6, 300e6))
    d1 = z1 * mn / math.cos(beta)
    z = chk.z_h * g.Z_E_STEEL * chk.z_eps * chk.z_beta
    expected = z * math.sqrt(2 * 1.0 * 100.0 / (b * d1**2) * (1 + 1 / 4))
    assert chk.sigma_h == pytest.approx(expected)


def test_design_satisfies_checks_and_geometry():
    p = g.design(g.GearPairInput("高速级", 26.75, 1440, 5.29, 48000))
    assert p.check.ok
    assert p.mn in standards.standard_modules(1)
    # 中心距圆整到 5 mm，反算的螺旋角在 8°–20°
    assert round(p.a * 1e3) % 5 == 0
    assert 8 <= math.degrees(p.beta) <= 20
    assert p.a == pytest.approx((p.d1 + p.d2) / 2)
    assert p.u == pytest.approx(5.29, rel=0.03)
    # 啮合力关系 Fr = Ft tan αn / cos β，Fa = Ft tan β
    assert p.radial_force == pytest.approx(p.tangential_force * math.tan(A20) / math.cos(p.beta))
    assert p.axial_force == pytest.approx(p.tangential_force * math.tan(p.beta))


def test_higher_torque_needs_bigger_gears():
    small = g.design(g.GearPairInput("低速级", 100, 300, 4, 48000))
    big = g.design(g.GearPairInput("低速级", 400, 300, 4, 48000))
    assert big.a > small.a
