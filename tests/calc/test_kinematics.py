"""运动和动力参数计算。出处：濮良贵《机械设计》第八版 式(15-2) T = 9550 P/n；
《机械设计课程设计》指导书 卷筒转速 n = 60×1000v/(πD)、展开式二级减速器 i1 = √((1.3~1.5)i)。"""

import math

import pytest

from gongke_core.calc import kinematics as k


def test_torque_matches_9550_formula():
    # T(N·m) = 9550 P(kW) / n(r/min)
    assert k.torque_from_power(10e3, 960) == pytest.approx(9550 * 10 / 960, rel=1e-3)


def test_drum_speed():
    assert k.drum_speed(1.4, 0.4) == pytest.approx(60 * 1000 * 1.4 / (math.pi * 400))


def test_split_ratio():
    i1, i2 = k.split_ratio(20, 1.3)
    assert i1 == pytest.approx(math.sqrt(26))
    assert i1 * i2 == pytest.approx(20)


def test_efficiency_chain():
    e = k.Efficiencies()
    assert e.total() == pytest.approx(0.99**2 * 0.99**3 * 0.97**2 * 0.96)


def test_solve_conveyor():
    r = k.solve(k.ConveyorTask(belt_pull=2500, belt_speed=1.4, drum_diameter=0.4))
    assert r.work_power == pytest.approx(3500)
    assert r.required_power == pytest.approx(3500 / r.eta_total)
    assert r.motor.power >= r.required_power  # 额定功率不小于所需功率
    assert r.motor.model == "Y132S-4"
    assert r.i_high * r.i_low == pytest.approx(r.total_ratio)
    # 输出轴转速等于卷筒转速
    assert r.shafts[3].speed_rpm == pytest.approx(r.drum_speed_rpm)
    # 功率逐级降低
    powers = [s.power for s in r.shafts]
    assert powers == sorted(powers, reverse=True)


def test_single_stage_scheme():
    # V 带 + 一级圆柱齿轮：效率链 η = η带 η联 η轴承² η齿轮 η卷筒（《机械设计课程设计》传动装置总效率计算）；
    # V 带传动比推荐 2～4、一级圆柱齿轮 3～5（指导书常用传动比推荐值），程序取 i带 = i/4 并限制在 2～4
    e = k.Efficiencies()
    assert e.total("single") == pytest.approx(0.96 * 0.99 * 0.99**2 * 0.97 * 0.96)
    assert k.belt_ratio_single(13.4) == pytest.approx(3.35)
    assert k.belt_ratio_single(6) == 2.0 and k.belt_ratio_single(30) == 4.0
    r = k.solve(k.ConveyorTask(belt_pull=2300, belt_speed=1.5, drum_diameter=0.4, sync_speed_rpm=1000, scheme="single"))
    assert len(r.shafts) == 4 and r.i_low == 1.0
    assert r.i_belt * r.i_high == pytest.approx(r.total_ratio)
    assert r.shafts[2].speed_rpm == pytest.approx(r.drum_speed_rpm)
