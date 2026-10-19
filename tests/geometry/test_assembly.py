"""示例任务书的完整装配体：能导出 STEP，再读回来零件数一致，零件间无明显干涉。"""

from pathlib import Path

import pytest

bd = pytest.importorskip("build123d")

from gongke_core import design  # noqa: E402
from gongke_core.geometry import assembly  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"


@pytest.fixture(scope="module")
def result():
    return design.run(design.ReducerTask.from_yaml(EXAMPLE))


def test_export_and_reimport(result, tmp_path):
    path = tmp_path / "asm.step"
    shapes = assembly.export(result, path, with_housing=True)
    assert all(s.is_valid for s in shapes.values())
    back = bd.import_step(str(path))
    assert len(back.solids()) >= len(shapes)


def test_gears_do_not_hit_other_shafts(result):
    shapes = assembly.build(result, with_housing=False)
    high_gear = shapes["高速级大齿轮"]
    low_shaft = shapes["Ⅲ轴（低速轴）"]
    assert high_gear.intersect(low_shaft) is None or high_gear.intersect(low_shaft).volume < 1e-6


def test_bevel_scheme_assembly():
    # 圆锥-圆柱方案：小锥齿轮在左端壁内侧，Ⅰ轴从左端伸出；各实体有效
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_bevel.yaml"))
    shapes = assembly.build(d, with_housing=True, z_up=False)
    assert all(s.is_valid for s in shapes.values())
    pin = shapes["小锥齿轮"].bounding_box()
    za = d.positions.z_apex * 1e3
    assert pin.max.X < 0 and pin.min.X > d.housing.x_range[0] * 1e3
    assert (pin.min.Z + pin.max.Z) / 2 == pytest.approx(za, abs=0.5)
    shaft1 = shapes["Ⅰ轴（高速轴）"].bounding_box()
    assert shaft1.min.X < (d.housing.x_range[0] - d.housing.delta) * 1e3
    gear = shapes["大锥齿轮"].bounding_box()
    assert gear.min.Z == pytest.approx(d.positions.z_back * 1e3, abs=0.5)


def test_worm_scheme_assembly():
    # 蜗杆方案：蜗杆在蜗轮正下方，螺纹中点在蜗轮中间平面；蜗轮在箱体内；蜗杆轴从 −x 端伸出
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_worm.yaml"))
    shapes = assembly.build(d, with_housing=True, z_up=False)
    assert all(s.is_valid for s in shapes.values())
    W = d.housing.inner_width * 1e3
    ring = shapes["蜗轮齿圈"].bounding_box()
    assert (ring.min.Z + ring.max.Z) / 2 == pytest.approx(W / 2, abs=0.5)
    assert ring.min.Z > 0 and ring.max.Z < W
    worm = shapes["Ⅰ轴（蜗杆轴）（蜗杆）"].bounding_box()
    assert (worm.min.Y + worm.max.Y) / 2 == pytest.approx(-d.worm.a * 1e3, abs=0.5)
    assert worm.min.X < (d.housing.x_range[0] - d.housing.delta) * 1e3
    # 蜗杆轴承座内凸台不碰蜗轮
    base, wheel = shapes["箱座"], shapes["蜗轮齿圈"]
    inter = base.intersect(wheel)
    assert inter is None or inter.volume < 1e-3
    # 轴承装在座孔内：轴承外圈与箱座不重叠
    for k, v in shapes.items():
        if "轴承3" in k:
            i = base.intersect(v)
            assert i is None or i.volume < 1.0, k
