"""公差计算。数值对照 GB/T 1800.1-2020 表 1、GB/T 10095.1-2008 附录 B 的 Fβ 表、GB/T 275-2015 表 6。"""

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
