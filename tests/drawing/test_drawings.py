"""二维工程图：公法线长度公式、比例选择、整套图纸生成。"""

import math
from pathlib import Path

import ezdxf
import pytest

from gongke_core import design, drawing
from gongke_core.drawing import gear, sheet

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"


def test_base_tangent_length_spur():
    # 标准直齿轮 m=1、α=20°、z=30：k=4，W* = cos20°[π(4−0.5) + 30 inv20°] = 10.7526
    # （GB/T 10095 附录及各版《机械设计手册》公法线长度表，m=1 时 z=30 一栏）
    w, k = gear.base_tangent_length(30, 1.0, math.radians(20), 0.0)
    assert k == 4
    assert w == pytest.approx(10.7526, abs=1e-3)


def test_base_tangent_length_helical_uses_virtual_teeth():
    # 斜齿轮按假想齿数 z' = z·inv αt / inv αn 计算，z' > z，Wk 大于同齿数直齿轮
    w_spur, _ = gear.base_tangent_length(28, 1.5e-3, math.radians(20), 0.0)
    w_hel, _ = gear.base_tangent_length(28, 1.5e-3, math.radians(20), math.radians(18))
    assert w_hel > w_spur


def test_pick_scale_prefers_largest_fitting():
    assert sheet.pick_scale(300, 50, 350, 100) == 1
    assert sheet.pick_scale(500, 50, 350, 100) == pytest.approx(1 / 1.5)
    assert sheet.pick_scale(100, 20, 350, 100) == 2.5
    assert sheet.scale_label(1 / 1.5) == "1:1.5"


def test_material_name():
    assert drawing.material_name("40Cr_QT") == "40Cr"
    assert drawing.material_name("45") == "45"


@pytest.fixture(scope="module")
def drawings(tmp_path_factory):
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE))
    out = tmp_path_factory.mktemp("dw")
    return d, drawing.build_all(d, out)


def test_build_all_files(drawings):
    d, files = drawings
    stems = {f.dxf.stem for f in files}
    assert {"assembly", "shaft1", "shaft2", "shaft3"} <= stems
    n_gears = sum(1 for sr in d.shafts for g in sr.layout.gears if not g.integral)
    assert sum(1 for s in stems if s.startswith("gear_")) == n_gears
    for f in files:
        assert f.dxf.exists() and f.svg.exists()
        assert f.dxf.name.isascii()


def _texts(path):
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    return doc, [e.dxf.text if e.dxftype() == "TEXT" else e.text for e in msp.query("TEXT MTEXT")]


def test_assembly_parts_list(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "assembly")
    doc, texts = _texts(f.dxf)
    joined = " ".join(texts)
    for sr in d.shafts:
        assert f"深沟球轴承 {sr.layout.bearing.designation}" in joined
    assert "轴承透盖" in joined and "轴承闷盖" in joined
    for name in ("箱盖", "视孔盖", "通气器", "杆式油标", "放油螺塞", "吊环螺钉", "圆锥销", "起盖螺钉"):
        assert name in joined, name
    assert "技术要求" in joined
    # 粗实线、剖面线图层都有内容
    msp = doc.modelspace()
    assert len(msp.query('*[layer=="粗实线"]')) > 50
    assert len(msp.query("HATCH")) > 10


def test_gear_drawing_has_param_table_and_material(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "gear_low1")
    _, texts = _texts(f.dxf)
    assert "公法线长度" in texts
    assert drawing.material_name(d.low.inp.material1) in texts
    w, k = gear.base_tangent_length(d.low.z1, d.low.mn, d.low.alpha_n, d.low.beta)
    assert f"{w * 1e3:.3f}" in texts


def test_gear_shaft_drawing_has_param_table(drawings):
    d, files = drawings
    i = next(i for i, sr in enumerate(d.shafts, 1) if any(g.integral for g in sr.layout.gears))
    f = next(f for f in files if f.dxf.stem == f"shaft{i}")
    _, texts = _texts(f.dxf)
    assert "公法线长度" in texts
    assert "A-A" in texts or any("A" == t for t in texts)
