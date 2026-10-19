"""锥齿轮结构尺寸（layout.bevel_blank）与圆锥-圆柱减速器的轴向布置。

几何关系按正常收缩齿：齿顶、齿根圆锥的锥顶与分度圆锥锥顶重合，背锥垂直于分度圆锥母线
（濮良贵《机械设计》第八版 §10-8 表 10-7 的几何尺寸）；均为解析式代入检查。"""

import math
from pathlib import Path

import pytest

from gongke_core import design
from gongke_core.calc import bevel as bv
from gongke_core.calc import kinematics
from gongke_core.layout import bevel_blank as bb
from gongke_core.layout import bevel_reducer as br

MM = 1e-3
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_bevel.yaml"


@pytest.fixture(scope="module")
def pair():
    t = kinematics.torque_from_power(4e3, 1440)
    return bv.design(bv.BevelPairInput("高速级", t, 1440, 3.0, 15 * 300 * 16))


@pytest.mark.parametrize("member", [1, 2])
def test_tip_and_root_points(pair, member):
    g = bb.blank(pair, member, 30 * MM)
    delta = pair.delta1 if member == 1 else pair.delta2
    da = pair.da1 if member == 1 else pair.da2
    # 大端齿顶点的半径就是 da/2，齿顶、齿根点都在过锥顶的直线上（收缩齿）
    assert g.tip_large[1] == pytest.approx(da / 2)
    assert math.atan2(g.tip_large[1], g.tip_large[0]) == pytest.approx(delta + math.atan(pair.m / pair.cone_distance))
    assert math.atan2(g.root_small[1], g.root_small[0]) == pytest.approx(
        math.atan2(g.root_large[1], g.root_large[0]))
    # 背锥垂直于分度圆锥母线
    tx, tr = g.tip_large
    kx, kr = g.back_point
    assert (tx - kx) * math.cos(delta) + (tr - kr) * math.sin(delta) == pytest.approx(0, abs=1e-12)
    # 齿宽沿母线方向等于 b
    assert math.dist(g.tip_small, g.tip_large) == pytest.approx(
        pair.b / math.cos(math.atan(pair.m / pair.cone_distance)), rel=1e-9)


def test_profile_is_simple_polygon(pair):
    for member in (1, 2):
        pts = bb.blank(pair, member, 30 * MM).profile()
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2
        assert abs(area) > 0
        assert all(r >= 15 * MM - 1e-12 for _, r in pts)  # 不进入轴孔


def test_hub_covers_bore_and_teeth(pair):
    g = bb.blank(pair, 2, 35 * MM)
    t0, t1 = g.hub_span
    assert t1 == pytest.approx(g.t_back)
    assert t1 - t0 >= max(1.2 * 35 * MM, g.t_back - g.t_front) - 1e-12


def test_bevel_layout_apex_and_cup():
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE))
    p, bevel = d.positions, d.bevel
    g2 = bb.blank(bevel, 2, d.shafts[1].layout.diameters["齿轮"], p.hub)
    # 大锥齿轮背面贴在 z_back，锥顶到背面的距离 = t_back
    assert p.z_apex - p.z_back == pytest.approx(g2.t_back)
    assert p.z_apex - p.z_large == pytest.approx(bevel.d1 / 2)
    # 小锥齿轮轮毂套在Ⅰ轴的齿轮段上，轴端缩进 2 mm
    seat = next(s for s in d.pinion.segments if s.role in ("齿轮", "齿轮轴"))
    g1 = bb.blank(bevel, 1, d.pinion.diameters["齿轮"], d.pinion.pinion_length)
    assert seat.z1 == pytest.approx(g1.hub_span[1])
    # 套杯：内端与箱体内壁齐平，凸缘贴在外侧轴承端面处，挡肩在两轴承之间
    c = br.cup(d.pinion)
    brg = [s for s in d.pinion.segments if s.role == "轴承"]
    assert c.u0 == pytest.approx(-d.housing.x_range[0])
    assert c.u_flange == pytest.approx(brg[1].z1)
    assert c.rib == (pytest.approx(brg[0].z1), pytest.approx(brg[1].z0))
    assert d.pinion.bearing.d < c.rib_d < c.D < c.D_out
