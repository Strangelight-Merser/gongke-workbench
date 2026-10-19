"""普通 V 带传动。出处：濮良贵《机械设计》第八版 §8-4 式(8-20)～(8-27)；包角系数与表 8-5、
功率增量与表 8-5 中 n1 = 1450 r/min、i ≥ 2 一栏对照；其余为设计公式本身的代入检查。"""

import math

import pytest

from gongke_core.calc import kinematics
from gongke_core.calc import vbelt as v

MM = 1e-3


@pytest.mark.parametrize("alpha, table", [(180, 1.00), (160, 0.95), (150, 0.92), (140, 0.89), (120, 0.82)])
def test_wrap_factor_matches_table(alpha, table):
    assert v.wrap_factor(alpha) == pytest.approx(table, abs=0.011)


def test_power_increment_formula():
    # 表 8-5：B 型 n1 = 1450 r/min、i ≥ 2 时 ΔP0 = 0.46 kW；A 型 0.17 kW
    assert v.power_increment("B", 1450, 2.5) == pytest.approx(0.46, abs=0.01)
    assert v.power_increment("A", 1450, 2.5) == pytest.approx(0.17, abs=0.015)
    assert v.power_increment("A", 1450, 1.0) == 0.0


def test_rated_power_table_and_interpolation():
    assert v.rated_power("A", 100 * MM, 1450) == pytest.approx(1.32)
    mid = v.rated_power("A", 100 * MM, (1200 + 1450) / 2)
    assert mid == pytest.approx((1.14 + 1.32) / 2)


def test_length_factor_and_series():
    assert v.length_factor("B", 2240 * MM) == pytest.approx(1.00)
    assert v.length_factor("B", 630 * MM) is None
    assert all(a < b for a, b in zip(v.datum_lengths("A"), v.datum_lengths("A")[1:]))


@pytest.fixture(scope="module")
def drive():
    return v.design(v.BeltInput(4.6e3, 1440, 2.5, 1.2, 38 * MM))


def test_design_formulas(drive):
    b = drive
    d1, d2, a0 = b.dd1, b.dd2, b.a0
    assert b.p_ca == pytest.approx(1.2 * 4.6e3)
    assert b.v == pytest.approx(math.pi * d1 * 1440 / 60)
    assert 5 <= b.v <= 25
    assert 0.7 * (d1 + d2) <= a0 <= 2 * (d1 + d2)
    assert b.ld0 == pytest.approx(2 * a0 + math.pi / 2 * (d1 + d2) + (d2 - d1) ** 2 / (4 * a0))
    assert b.a == pytest.approx(a0 + (b.ld - b.ld0) / 2)
    assert b.alpha1 == pytest.approx(180 - (d2 - d1) * 57.3 / b.a)
    assert b.z == math.ceil(b.z_exact) and b.z <= 5
    assert b.f0 == pytest.approx(500 * (2.5 - b.k_alpha) * b.p_ca / 1e3 / (b.k_alpha * b.z * b.v) + b.sec.q * b.v**2)
    assert b.fp == pytest.approx(2 * b.z * b.f0 * math.sin(math.radians(b.alpha1) / 2))
    assert b.width == pytest.approx((b.z - 1) * b.sec.e + 2 * b.sec.f)
    # 小带轮轮缘内径能容下电动机轴上的轮毂
    assert d1 - 2 * (b.sec.hf + b.sec.delta) >= 1.8 * 38 * MM


def test_larger_power_moves_to_b_section():
    b = v.design(v.BeltInput(15e3, 1460, 2.5, 1.2, 42 * MM))
    assert b.sec.name == "B" and b.z <= 5


def test_impossible_power_raises():
    with pytest.raises(v.standards.SelectionError):
        v.design(v.BeltInput(80e3, 1460, 2.5, 1.3))


def test_kinematics_with_belt():
    t = kinematics.ConveyorTask(2500, 1.4, 0.4, scheme="vbelt", belt_ratio=2.5)
    k = kinematics.solve(t, 2.4)
    e = t.efficiencies
    assert k.eta_total == pytest.approx(e.belt * e.coupling * e.bearing_pair**3 * e.gear_pair**2 * e.drum)
    assert k.shafts[1].speed_rpm == pytest.approx(k.motor.speed_rpm / 2.4)
    assert k.shafts[1].power == pytest.approx(k.required_power * e.belt)
    assert k.i_high * k.i_low == pytest.approx(k.total_ratio / 2.4)
