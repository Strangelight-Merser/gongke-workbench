"""直齿锥齿轮传动与圆锥滚子轴承。出处：濮良贵《机械设计》第八版 §10-8 式(10-23)～(10-26)（锥齿轮几何、
受力与强度计算），§13-5 表 13-7 与式(13-11)（圆锥滚子轴承派生轴向力与轴向载荷）；均做公式代入检查。"""

import math

import pytest

from gongke_core import design, standards
from gongke_core.calc import bearing as bc
from gongke_core.calc import bevel as bv
from gongke_core.calc import gear as g
from gongke_core.calc import kinematics

MM = 1e-3


@pytest.fixture(scope="module")
def pair():
    t = kinematics.torque_from_power(10e3, 960)
    return bv.design(bv.BevelPairInput("高速级", t, 960, 3.2, 15 * 300 * 16))


def test_geometry(pair):
    p = pair
    assert p.delta1 == pytest.approx(math.atan(p.z1 / p.z2))
    assert p.delta1 + p.delta2 == pytest.approx(math.pi / 2)
    assert p.cone_distance == pytest.approx(p.m / 2 * math.hypot(p.z1, p.z2))
    assert p.dm1 == pytest.approx(p.d1 * (1 - 0.5 * p.inp.phi_r))
    assert p.da1 == pytest.approx(p.d1 + 2 * p.m * math.cos(p.delta1))
    assert p.b == pytest.approx(p.inp.phi_r * p.cone_distance, abs=1 * MM)
    assert p.m in standards.bevel_modules() and p.m >= p.m_design - 1e-12


def test_forces(pair):
    p = pair
    assert p.tangential_force * p.dm1 / 2 == pytest.approx(p.inp.torque1)
    a = math.radians(20)
    assert p.radial_force1 == pytest.approx(p.tangential_force * math.tan(a) * math.cos(p.delta1))
    assert p.axial_force1 == pytest.approx(p.tangential_force * math.tan(a) * math.sin(p.delta1))
    # 小锥齿轮的径向力与轴向力合成为 Ft tan α
    assert math.hypot(p.radial_force1, p.axial_force1) == pytest.approx(p.tangential_force * math.tan(a))


def test_strength_formulas(pair):
    p, c = pair, pair.check
    assert c.ok
    phi = p.b / p.cone_distance
    k = c.k_h
    sh = 2.5 * g.Z_E_STEEL * math.sqrt(4 * k * p.inp.torque1 / (phi * (1 - 0.5 * phi) ** 2 * p.d1**3 * p.u))
    assert c.sigma_h == pytest.approx(sh)
    ft = 2 * p.inp.torque1 / (p.d1 * (1 - 0.5 * phi))
    assert c.sigma_f[0] == pytest.approx(k * ft * c.y_fa[0] * c.y_sa[0] / (p.b * p.m * (1 - 0.5 * phi)))
    assert c.zv[0] == pytest.approx(p.z1 / math.cos(p.delta1))
    assert c.k_hbeta == pytest.approx(1.5 * 1.1)


def test_tapered_bearing_axial_loads():
    b = standards.tapered_with_bore(40 * MM)[0]
    fr_a, fr_b = 4000.0, 2000.0
    fd_a, fd_b = fr_a / (2 * b.Y), fr_b / (2 * b.Y)
    # 正装，外力沿 +z（指向 B）：B 端被压紧，Fa_B = Fae + Fd_A，Fa_A = Fd_A
    r = bc.check_tapered_pair(b, fr_a, fr_b, 800.0, 960, 1e4)
    assert r.fa == pytest.approx((fd_a, 800.0 + fd_a))
    # 外力很小、反向：A 端被压紧，Fa_A = Fd_B − Fae
    r = bc.check_tapered_pair(b, fr_a, fr_b, -900.0, 960, 1e4)
    assert r.fa[0] == pytest.approx(max(fd_a, fd_b + 900.0))
    # 反装时承受 +z 推力的是 A 端
    r = bc.check_tapered_pair(b, fr_a, fr_b, 3000.0, 960, 1e4, arrangement="反装")
    assert r.fa == pytest.approx((3000.0 + fd_b, fd_b))
    # 寿命指数 10/3
    assert r.life[0] == pytest.approx(1e6 / (60 * 960) * (b.Cr / r.p[0]) ** (10 / 3))


def test_bevel_ratio_split():
    assert kinematics.split_ratio_bevel(10) == pytest.approx((2.5, 4.0))
    assert kinematics.split_ratio_bevel(20)[0] == 3.0


@pytest.fixture(scope="module")
def reducer():
    from pathlib import Path
    ex = Path(__file__).resolve().parents[2] / "examples" / "conveyor_bevel.yaml"
    return design.run(design.ReducerTask.from_yaml(ex))


def test_bevel_reducer_checks(reducer):
    d = reducer
    assert d.ok, [c for c in d.checks if not c[1]]
    assert d.actual_ratio == pytest.approx(d.bevel.u * d.low.u)
    assert d.pinion.span >= 2 * d.pinion.overhang - 1e-9


def test_bevel_reducer_equilibrium(reducer):
    for s in reducer.shafts:
        c = s.load_case
        r = s.strength.reactions
        assert sum(p.fx for p in c.loads) + r.ax + r.bx == pytest.approx(0, abs=1e-6)
        assert sum(p.fy for p in c.loads) + r.ay + r.by == pytest.approx(0, abs=1e-6)
        assert sum(t for _, t in c.torque_points) == pytest.approx(0, abs=1e-9)


def test_intermediate_axial_forces_partly_cancel(reducer):
    loads = reducer.shafts[1].load_case.loads
    fz = [p.fz for p in loads]
    assert fz[0] * fz[1] < 0
    assert abs(sum(fz)) < max(abs(v) for v in fz)
