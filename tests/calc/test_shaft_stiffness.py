"""轴的刚度：与等截面简支梁、外伸梁的挠度公式对照。

公式见《材料力学 Ⅰ》（刘鸿文主编，第 6 版，高等教育出版社）附录 Ⅳ“简单载荷作用下梁的挠度和转角”：
简支梁跨内集中力 F（距左支点 a、右支点 b，跨度 l）：力作用点挠度 w = F a² b² / (3EIl)，
左端转角 θA = F a b (l + b) / (6EIl)；外伸梁外伸端 c 处集中力 F：端点挠度 w = F c² (l + c) / (3EI)。
"""

import math

import pytest

from gongke_core.calc import shaft_stiffness as st
from gongke_core.calc.shaft import PointLoad, Segment, ShaftLoadCase

E = 2.06e11
d = 0.04
I = math.pi * d**4 / 64


def test_simply_supported_point_load():
    l, a = 0.2, 0.07
    b, F = l - a, 3000.0
    segs = [Segment(0.0, l, d, "轴承")]
    case = ShaftLoadCase((0.0, l), [PointLoad(a, fy=F)], [])
    c = st.solve(segs, case, E)
    assert c.deflection(a) == pytest.approx(F * a**2 * b**2 / (3 * E * I * l), rel=1e-4)
    assert c.slope(0.0) == pytest.approx(F * a * b * (l + b) / (6 * E * I * l), rel=1e-3)
    # 两个平面的力合成：x、y 方向各一个力时挠度按矢量合成
    case2 = ShaftLoadCase((0.0, l), [PointLoad(a, fx=F, fy=F)], [])
    assert st.solve(segs, case2, E).deflection(a) == pytest.approx(math.sqrt(2) * F * a**2 * b**2 / (3 * E * I * l), rel=1e-4)


def test_overhang_tip_load():
    l, c_, F = 0.2, 0.06, 1500.0
    segs = [Segment(0.0, l + c_, d, "轴承")]
    case = ShaftLoadCase((0.0, l), [PointLoad(l + c_, fx=F)], [])
    curve = st.solve(segs, case, E)
    assert curve.deflection(l + c_) == pytest.approx(F * c_**2 * (l + c_) / (3 * E * I), rel=1e-3)
    assert curve.deflection(0.0) == pytest.approx(0.0, abs=1e-12)
    assert curve.deflection(l) == pytest.approx(0.0, abs=1e-12)


def test_stepped_shaft_is_stiffer_than_thin_and_softer_than_thick():
    l, a, F = 0.2, 0.1, 3000.0
    case = ShaftLoadCase((0.0, l), [PointLoad(a, fy=F)], [])
    thin = st.solve([Segment(0.0, l, d, "轴承")], case, E).deflection(a)
    thick = st.solve([Segment(0.0, l, 1.2 * d, "轴承")], case, E).deflection(a)
    stepped = st.solve([Segment(0.0, 0.05, d, "轴承"), Segment(0.05, 0.1, 1.2 * d, "齿轮"),
                        Segment(0.15, 0.05, d, "轴承")], case, E).deflection(a)
    assert thick < stepped < thin


def test_design_shafts_pass_stiffness():
    from pathlib import Path

    from gongke_core import design

    d_ = design.run(design.ReducerTask.from_yaml(Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"))
    for sr in d_.shafts:
        assert sr.stiffness.ok
        assert any(i.kind == "y" for i in sr.stiffness.items)
