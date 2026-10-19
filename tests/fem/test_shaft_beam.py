"""CalculiX 梁单元模型：与解析解对照。没有 ccx（或版本低于 2.21）时跳过求解部分。

悬臂梁自由端集中力 F 的挠度计入剪切变形：w = FL³/(3EI) + FL/(κGA)
（S. P. Timoshenko, J. M. Gere. Mechanics of Materials，剪切变形引起的挠度一节；
实心圆截面剪切系数 κ = 6(1+ν)/(7+6ν) 取自 G. R. Cowper, J. Appl. Mech. 33(2), 1966）。
简支梁跨内集中力的弯曲挠度见《材料力学 Ⅰ》（刘鸿文主编，第 6 版）附录 Ⅳ。
"""

import math
from pathlib import Path

import pytest

from gongke_core.calc import shaft_stiffness as st
from gongke_core.calc.shaft import PointLoad, Segment, ShaftLoadCase
from gongke_core.fem import ccx, shaft_beam

E, NU = 2.06e11, 0.3


def _have_ccx() -> bool:
    try:
        ccx.check_version()
        return True
    except ccx.CcxNotFound:
        return False


needs_ccx = pytest.mark.skipif(not _have_ccx(), reason="没有 CalculiX ccx ≥ 2.21")


def test_inp_has_supports_loads_and_sections(tmp_path: Path):
    segs = [Segment(0.0, 0.05, 0.03, "轴承"), Segment(0.05, 0.1, 0.04, "齿轮"), Segment(0.15, 0.05, 0.03, "轴承")]
    case = ShaftLoadCase((0.01, 0.19), [PointLoad(0.1, fx=1000.0, fz=200.0, y0=0.05)], [])
    nodes = shaft_beam.write_inp(tmp_path / "s.inp", segs, case)
    text = (tmp_path / "s.inp").read_text()
    assert nodes == sorted(nodes) and max(b - a for a, b in zip(nodes, nodes[1:])) <= 2e-3 + 1e-12
    assert text.count("SECTION=GENERAL") == 2  # 两种直径
    assert f"{math.pi * 40**4 / 64:.6e}" in text
    # 轴向力 200 N、偏距 50 mm：绕 x 轴的力偶 10000 N·mm
    assert "1.000000e+04" in text
    assert "*USER ELEMENT, TYPE=U1" in text


@needs_ccx
def test_overhang_tip_load_with_shear(tmp_path: Path):
    l, c, d, F = 0.2, 0.08, 0.03, 2000.0
    segs = [Segment(0.0, l + c, d, "轴")]
    case = ShaftLoadCase((0.0, l), [PointLoad(l + c, fy=F)], [])
    res = shaft_beam.solve(segs, case, tmp_path, "o")
    I, A = math.pi * d**4 / 64, math.pi * d**2 / 4
    G, kappa = E / (2 * (1 + NU)), 6 * (1 + NU) / (7 + 6 * NU)
    # 弯曲：Fc²(l + c)/(3EI)；剪切：跨内剪力 Fc/l、外伸段剪力 F，各段 dy/dz = V/(κGA)，
    # 再加刚体转动使两支点挠度为零，得外伸端 Fc(l + c)/(lκGA)
    w = F * c**2 * (l + c) / (3 * E * I) + F * c * (l + c) / (l * kappa * G * A)
    assert res.deflection(l + c) == pytest.approx(w, rel=2e-3)
    assert st.solve(segs, case, E, shear=True).deflection(l + c) == pytest.approx(w, rel=2e-3)


@needs_ccx
def test_stepped_simply_supported_matches_timoshenko(tmp_path: Path):
    segs = [Segment(0.0, 0.05, 0.03, "轴承"), Segment(0.05, 0.1, 0.06, "齿轮"), Segment(0.15, 0.05, 0.03, "轴承")]
    case = ShaftLoadCase((0.0, 0.2), [PointLoad(0.1, fy=3000.0), PointLoad(0.07, fx=-1200.0, fz=500.0, x0=0.04)], [])
    res = shaft_beam.solve(segs, case, tmp_path, "s")
    curve = st.solve(segs, case, E, shear=True)
    for z in (0.0, 0.07, 0.1, 0.2):
        assert res.slope(z) == pytest.approx(curve.slope(z), rel=5e-3)
    for z in (0.07, 0.1):
        assert res.deflection(z) == pytest.approx(curve.deflection(z), rel=5e-3)


@needs_ccx
def test_slender_beam_matches_textbook(tmp_path: Path):
    l, a, d, F = 0.8, 0.3, 0.02, 500.0
    b = l - a
    case = ShaftLoadCase((0.0, l), [PointLoad(a, fy=F)], [])
    res = shaft_beam.solve([Segment(0.0, l, d, "轴")], case, tmp_path, "t")
    I = math.pi * d**4 / 64
    assert res.deflection(a) == pytest.approx(F * a**2 * b**2 / (3 * E * I * l), rel=2e-3)
    assert res.slope(0.0) == pytest.approx(F * a * b * (l + b) / (6 * E * I * l), rel=2e-3)


@needs_ccx
def test_design_fem_check(tmp_path: Path):
    from gongke_core import design
    from gongke_core.fem import shaft_check

    root = Path(__file__).resolve().parents[2]
    res = design.run(design.ReducerTask.from_yaml(root / "examples" / "conveyor_bevel.yaml"))
    rep = shaft_check.run(res, tmp_path, gears=False)
    assert len(rep.shafts) == 3 and rep.ok
    assert rep.max_diff < 0.01
    assert "有限元" in shaft_check.to_markdown(rep)
