"""圆柱蜗杆传动与蜗杆减速器。出处：濮良贵《机械设计》第八版 第十一章：式(11-1)～(11-4)（几何尺寸、
导程角、滑动速度），式(11-7)～(11-8)（受力），式(11-12)（接触强度校核 σH = ZE Zρ √(K T2/a³)），
式(11-13)（弯曲强度 σF = 1.53 K T2 YFa2 Yβ / (d1 d2 m cos γ)），式(11-21)（效率），式(11-22)（热平衡）；
均做公式代入检查。蜗杆刚度按简支梁挠度解析解 y = F L³/(48EI)。"""

import math

import pytest

from gongke_core import design, standards
from gongke_core.calc import kinematics
from gongke_core.calc import worm as wc

MM = 1e-3


@pytest.fixture(scope="module")
def pair():
    t = kinematics.torque_from_power(5.5e3, 1440)
    return wc.design(wc.WormPairInput("蜗杆传动", t, 1440, 24, 10 * 300 * 16))


def test_standard_parameters(pair):
    p = pair
    assert (p.m, p.d1) in standards.worm_module_d1()
    assert p.a in standards.worm_center_distances(include_series_2=True)
    # 中心距 a = (d1 + d2 + 2 x2 m)/2，|x2| ≤ 0.5（GB/T 10085）
    assert p.a == pytest.approx((p.d1 + p.d2 + 2 * p.x2 * p.m) / 2)
    assert abs(p.x2) <= 0.5 + 1e-9
    assert p.z1 == wc.worm_starts(24) == 2
    assert abs(p.u - 24) / 24 <= 0.04


def test_geometry(pair):
    p = pair
    assert math.tan(p.gamma) == pytest.approx(p.z1 / p.q)
    assert p.da1 == pytest.approx(p.d1 + 2 * p.m)
    assert p.df1 == pytest.approx(p.d1 - 2.4 * p.m)
    assert p.da2 == pytest.approx(p.m * (p.z2 + 2 + 2 * p.x2))
    assert p.throat_radius == pytest.approx(p.a - p.da2 / 2)
    assert p.da2 < p.de2 <= p.da2 + 1.5 * p.m + 1e-9  # z1 = 2：de2 ≤ da2 + 1.5m
    assert p.b2 <= 0.75 * p.da1 + 1e-9


def test_kinematics_and_forces(pair):
    p = pair
    assert p.sliding_velocity == pytest.approx(math.hypot(p.worm_velocity, p.worm_velocity * math.tan(p.gamma)))
    assert p.tangential_force1 == pytest.approx(2 * p.inp.torque1 / p.d1)
    assert p.axial_force1 == pytest.approx(p.tangential_force2)
    assert p.radial_force == pytest.approx(p.tangential_force2 * math.tan(math.radians(20)))
    # 无摩擦时 Ft1 = Fa1 tan γ；有摩擦时 Ft1 = Ft2 tan(γ + φv)，与效率式一致
    phi = wc.friction_angle(p.sliding_velocity, p.material.tin)
    assert p.eta_mesh == pytest.approx(math.tan(p.gamma) / math.tan(p.gamma + phi))
    assert p.eta == pytest.approx(0.96 * p.eta_mesh)


def test_strength_formulas(pair):
    p, c = pair, pair.check
    assert c.sigma_h == pytest.approx(160e3 * c.z_rho * math.sqrt(c.k * p.torque2 / p.a**3))
    assert c.sigma_f == pytest.approx(1.53 * c.k * p.torque2 * c.y_fa2 * c.y_beta
                                      / (p.d1 * p.d2 * p.m * math.cos(p.gamma)))
    assert c.zv2 == pytest.approx(p.z2 / math.cos(p.gamma) ** 3)
    assert c.y_beta == pytest.approx(1 - math.degrees(p.gamma) / 140)
    assert c.ok


def test_life_factors():
    assert wc.life_factor_contact(1e7) == pytest.approx(1.0)
    assert wc.life_factor_contact(2.56e9) == pytest.approx((1e7 / 25e7) ** 0.125)  # N > 25×10⁷ 取 25×10⁷
    assert wc.life_factor_bending(1e6) == pytest.approx(1.0)
    assert wc.life_factor_bending(5.12e7) == pytest.approx((1 / 51.2) ** (1 / 9))


def test_tables_monotonic():
    # Zρ 随 d1/a 增大而减小；当量摩擦系数随滑动速度增大而减小（vs ≥ 1 m/s 段）
    zs = [wc.z_rho(x) for x in (0.25, 0.35, 0.45, 0.55)]
    assert zs == sorted(zs, reverse=True)
    fs = [math.tan(wc.friction_angle(v)) for v in (1, 2, 4, 8)]
    assert fs == sorted(fs, reverse=True)
    assert wc.friction_angle(3, tin_bronze=False) > wc.friction_angle(3, tin_bronze=True)


def test_thermal():
    th = wc.thermal(4e3, 0.8, 0.16, alpha_d=15)
    assert th.heat == pytest.approx(800)
    assert th.t_oil == pytest.approx(20 + 800 / (15 * 9e-5 * 160**1.88))


def test_stiffness(pair):
    s = wc.worm_stiffness(pair, 0.3)
    f = math.hypot(pair.tangential_force1, pair.radial_force)
    assert s.deflection == pytest.approx(f * 0.3**3 / (48 * 206e9 * math.pi * pair.df1**4 / 64))
    assert s.allowable == pytest.approx(pair.d1 / 1000)


def test_higher_torque_needs_larger_center_distance():
    a = [wc.design(wc.WormPairInput("蜗杆传动", t, 1440, 24, 30000)).a for t in (20, 40, 80)]
    assert a == sorted(a) and a[0] < a[-1]


@pytest.fixture(scope="module")
def reducer():
    return design.run(design.ReducerTask.from_yaml("examples/conveyor_worm.yaml"))


def test_worm_reducer_passes(reducer):
    assert reducer.ok, [c for c in reducer.checks if not c[1]]
    assert reducer.kin.motor.model == "Y100L2-4"
    # 电动机按实际蜗杆效率选择：总效率中代入的是设计结果的 η
    assert reducer.kin.eta_total == pytest.approx(
        reducer.task.conveyor.efficiencies.coupling**2 * reducer.task.conveyor.efficiencies.bearing_pair**2
        * reducer.worm.eta * reducer.task.conveyor.efficiencies.drum)


def test_worm_reducer_equilibrium(reducer):
    # 两轴各自静力平衡：支反力之和与啮合力相抵
    for s in reducer.shafts:
        r = s.strength.reactions
        fx = sum(p.fx for p in s.load_case.loads)
        fy = sum(p.fy for p in s.load_case.loads)
        assert r.ax + r.bx + fx == pytest.approx(0, abs=1e-6)
        assert r.ay + r.by + fy == pytest.approx(0, abs=1e-6)
    # 蜗杆轴向力 = 蜗轮切向力，蜗轮轴向力 = 蜗杆切向力
    w = reducer.worm
    assert abs(reducer.shafts[0].strength.reactions.axial) == pytest.approx(w.tangential_force2)
    assert abs(reducer.shafts[1].strength.reactions.axial) == pytest.approx(w.tangential_force1)


def test_worm_shaft_layout(reducer):
    ws, w, h = reducer.worm_shaft, reducer.worm, reducer.housing
    segs = ws.segments
    for a, b in zip(segs, segs[1:]):
        assert a.z0 + a.length == pytest.approx(b.z0)
    thread = next(s for s in segs if s.role == "齿轮轴")
    assert thread.z0 == pytest.approx(-w.b1 / 2) and thread.length == pytest.approx(w.b1)
    # 轴承座凸台不碰蜗轮外圆，也不碰螺纹
    from gongke_core.layout import worm_reducer as wl
    r = wl.boss_radius(ws.bearing.D)
    assert ws.seat_inner >= w.b1 / 2 + 10 * MM - 1e-9
    assert math.hypot(ws.seat_inner, w.a - r) >= w.de2 / 2 + h.gap_radial - 1e-6 or w.a - r >= w.de2 / 2 + h.gap_radial
    # 蜗轮在内壁之间，蜗杆齿顶不碰箱底
    assert h.inner_width >= w.b2
    assert h.y_range[0] < -w.a - w.da1 / 2


@pytest.mark.parametrize("pull,speed,drum", [(1800, 0.6, 300), (3500, 1.1, 400), (4500, 0.5, 450)])
def test_other_worm_tasks(pull, speed, drum):
    t = design.ReducerTask.from_yaml("examples/conveyor_worm.yaml")
    from dataclasses import replace
    t = replace(t, conveyor=replace(t.conveyor, belt_pull=pull, belt_speed=speed, drum_diameter=drum * MM))
    d = design.run(t)
    assert d.ok, [c for c in d.checks if not c[1]]
