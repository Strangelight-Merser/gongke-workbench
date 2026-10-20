"""公差计算。数值对照 GB/T 1800.1-2020 表 1、GB/T 10095.1-2008 附录 B 的 Fβ 表、GB/T 275-2015 表 6。"""

import math

import pytest

from gongke_core.calc import tolerance as tol


def test_it_table():
    # GB/T 1800.1-2020 表 1：>120～180 mm，IT7 = 40 μm，IT8 = 63 μm；>30～50 mm，IT6 = 16 μm
    assert tol.it(7, 0.150) == pytest.approx(40e-6)
    assert tol.it(8, 0.150) == pytest.approx(63e-6)
    assert tol.it(6, 0.050) == pytest.approx(16e-6)  # 分段含上限
    with pytest.raises(ValueError):
        tol.it(7, 0.6)


def test_center_distance_fa():
    # 8 级、a = 150 mm：fa = IT8/2 = 31.5 μm（课程设计手册表中值 ±31.5 μm）
    assert tol.center_distance_fa(8, 0.150) == pytest.approx(31.5e-6)
    assert tol.center_distance_fa(6, 0.100) == pytest.approx(17.5e-6)


def test_helix_Fbeta_matches_table():
    # GB/T 10095.1-2008 表 B：50 < d ≤ 125、20 < b ≤ 40 时 5 级 8.5 μm、7 级 17 μm、8 级 24 μm
    for q, v in ((5, 8.5), (7, 17), (8, 24)):
        assert tol.helix_total_Fbeta(q, 0.080, 0.030) == pytest.approx(v * 1e-6)


def test_axis_parallelism():
    fd, fb = tol.axis_parallelism(0.150, 0.050, 20e-6)
    assert fb == pytest.approx(30e-6) and fd == pytest.approx(60e-6)


def test_housing_bore_cylindricity():
    # GB/T 275-2015 表 6：外壳孔 > 80～120 mm，普通级 10 μm
    assert tol.housing_bore_cylindricity(0.100) == pytest.approx(10e-6)


def _um(pair):
    return tuple(round(v * 1e6) for v in pair)


def test_limit_deviations_match_gb_tables():
    # GB/T 1800.2-2020 极限偏差表（μm）
    assert _um(tol.deviations("k6", 0.035)) == (18, 2)
    assert _um(tol.deviations("r6", 0.038)) == (50, 34)
    assert _um(tol.deviations("r6", 0.058)) == (60, 41)
    assert _um(tol.deviations("H7", 0.038)) == (25, 0)
    assert _um(tol.deviations("h11", 0.0473)) == (0, -160)
    assert _um(tol.deviations("d11", 0.080)) == (-100, -290)
    assert _um(tol.deviations("D11", 0.040)) == (240, 80)
    # 平键键槽宽（GB/T 1095-2003 表 1 正常连接）：轴槽 N9、毂槽 JS9，b = 10 mm
    assert _um(tol.deviations("N9", 0.010)) == (0, -36)
    assert _um(tol.deviations("JS9", 0.010)) == (18, -18)
    with pytest.raises(ValueError):
        tol.deviations("p6", 0.030)
    assert tol.fmt_dev(18e-6) == "+0.018" and tol.fmt_dev(0.0) == "0" and tol.fmt_dev(-36e-6) == "-0.036"


def test_gear_accuracy_matches_gb10095_tables():
    # GB/T 10095.1-2008 附录表、GB/T 10095.2-2008 附录表，8 级：
    # 50 < d ≤ 125、2 < m ≤ 3.5：±fpt 17、Fp 53、Fα 22、Fr 43 μm
    d, m = 0.080, 0.0025
    assert tol.single_pitch_fpt(8, d, m) == pytest.approx(17e-6)
    assert tol.cumulative_pitch_Fp(8, d, m) == pytest.approx(53e-6)
    assert tol.profile_total_Falpha(8, d, m) == pytest.approx(22e-6)
    assert tol.radial_runout_Fr(8, d, m) == pytest.approx(43e-6)
    # 125 < d ≤ 280、0.5 < m ≤ 2：Fp 69、Fα 20、Fr 55 μm；7 级、2 < m ≤ 3.5：±fpt 13、Fp 50 μm
    assert tol.cumulative_pitch_Fp(8, 0.2357, 0.0015) == pytest.approx(69e-6)
    assert tol.profile_total_Falpha(8, 0.2357, 0.0015) == pytest.approx(20e-6)
    assert tol.radial_runout_Fr(8, 0.2357, 0.0015) == pytest.approx(55e-6)
    assert tol.single_pitch_fpt(7, 0.150, 0.003) == pytest.approx(13e-6)
    assert tol.cumulative_pitch_Fp(7, 0.150, 0.003) == pytest.approx(50e-6)


def test_thickness_deviation():
    # 最小侧隙 jbn,min = 2/3(0.06 + 0.0005a + 0.03mn)（GB/Z 18620.2-2008）：a = 140、mn = 1.5 时 0.1167 mm
    assert tol.min_backlash(0.140, 0.0015) == pytest.approx(0.11667e-3, rel=1e-3)
    an = math.radians(20)
    th = tol.thickness_deviation(8, 0.140, 0.0015, an, 0.0443, 0.2357, 0.2357, 0.045, 0.188)
    # 上偏差至少要保证最小侧隙的一半，下偏差更负；公法线长度偏差 = 齿厚偏差 × cos αn
    assert th.Esns < -th.jbn_min / (2 * math.cos(an))
    assert th.Esni < th.Esns
    assert th.Ebns == pytest.approx(th.Esns * math.cos(an))
    assert th.Ebni == pytest.approx(th.Esni * math.cos(an))
    # 课程设计常见范围：8 级、m 1.5～3 的公法线长度偏差约 −0.08～−0.30 mm
    assert -0.15e-3 < th.Ebns < -0.08e-3 and -0.30e-3 < th.Ebni < -0.15e-3


def test_bearing_seat_and_keyway_tolerances():
    # GB/T 275-2015 表 6：轴颈 > 30～50 mm，普通级圆柱度 4 μm、轴肩端面圆跳动 12 μm
    assert tol.journal_cylindricity(0.035) == pytest.approx(4e-6)
    assert tol.shoulder_runout(0.035) == pytest.approx(12e-6)
    assert tol.shoulder_runout(0.055) == pytest.approx(15e-6)
    # 键槽对称度按 GB/T 1184 8 级，主参数为槽宽
    assert tol.keyway_symmetry(0.010) == pytest.approx(20e-6)
    assert tol.keyway_symmetry(0.016) == pytest.approx(25e-6)
