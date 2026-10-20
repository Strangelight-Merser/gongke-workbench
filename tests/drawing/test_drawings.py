"""二维工程图：公法线长度公式、比例选择、整套图纸生成。"""

import math
from pathlib import Path

import ezdxf
import pytest

from gongke_core import design, drawing
from gongke_core.drawing import gear, lint, sheet

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
    # 整套 PDF：每张图一页，页面等于图幅（A1 841×594 mm）
    data = (files[0].dxf.parent / "drawings.pdf").read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"/Type /Page ") == len(files)
    assert b"/MediaBox [0 0 2383.94 1683.78]" in data


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


def _dim_texts(path):
    """尺寸块中的文字（含极限偏差）。"""
    doc = ezdxf.readfile(str(path))
    out = []
    for blk in doc.blocks:
        if blk.name.startswith("*D"):
            out += [e.text for e in blk.query("MTEXT")]
    return " ".join(out)


def test_shaft_drawing_has_limit_deviations_and_geometric_tolerances(drawings):
    # 课程设计轴零件图的通行要求：配合段注极限偏差，键槽注宽度偏差和槽底尺寸偏差及对称度，
    # 轴颈注圆柱度（GB/T 275），轴承定位轴肩注端面圆跳动
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "shaft3")
    dims = _dim_texts(f.dxf)
    lay = d.shafts[2].layout
    from gongke_core.calc import tolerance as tol
    up, lo = tol.deviations("k6", lay.diameters["轴承"])
    assert tol.fmt_dev(up) in dims and tol.fmt_dev(lo) in dims
    assert "-0.200" in dims  # 槽底尺寸 d − t1 的下偏差
    _, texts = _texts(f.dxf)
    assert texts.count("A-B") >= 4
    assert tol.fmt_mm(tol.journal_cylindricity(lay.diameters["轴承"])) in texts
    assert tol.fmt_mm(tol.shoulder_runout(lay.diameters["轴承"])) in texts


def test_gear_drawing_lists_accuracy_items(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "gear_high2")
    _, texts = _texts(f.dxf)
    for sym in ("±fpt", "Fp", "Fα", "Fβ", "Fr", "公法线长度偏差", "xn"):
        assert sym in texts, sym
    from gongke_core.calc import tolerance as tol
    fp = tol.cumulative_pitch_Fp(d.high.inp.grade, d.high.d2, d.high.mn)
    assert f"{round(fp * 1e6) / 1000:.3f}" in texts


def test_assembly_has_installation_dimensions_and_trial_run(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "assembly")
    doc, texts = _texts(f.dxf)
    joined = " ".join(texts)
    assert "空载试运转" in joined and "负载试运转" in joined
    assert "4×Ø" in joined  # 地脚螺栓孔
    assert "H7/d11" in joined  # 轴承盖与座孔
    # 深沟球轴承规定画法：每个轴承一个滚动体圆
    from gongke_core.layout.housing_detail import detail
    t = detail(d)
    n_brg = 2 * len(d.shafts)
    msp = doc.modelspace()
    small = [c for c in msp.query('CIRCLE[layer=="粗实线"]')
             if any(abs(c.dxf.radius * 2 - (sr.layout.bearing.D - sr.layout.bearing.d) / 4 * 1e3 * 0.5) < 0.05
                    for sr in d.shafts)]
    assert len(small) >= n_brg
    assert len(msp.query('CIRCLE[layer=="虚线"]')) >= len(t.foot_bolts)


def test_assembly_front_view_local_sections(drawings):
    """主视图对放油螺塞和油标、视孔、连接螺栓作局部剖：有波浪线（细实线多段线）和多组剖面线；
    放油孔小径下缘与油池底面平齐（课程设计指导书：放油孔设在油池最低处），吊钩不碰油标。"""
    from gongke_core.drawing.assembly import MINOR
    from gongke_core.layout.housing_detail import _hook_hits_dipstick, detail

    d, files = drawings
    t = detail(d)
    assert abs(t.drain[1] - MINOR[16] / 2 * 1e-3 - d.housing.y_range[0]) < 0.1e-3
    yt = t.hook_top or -d.housing.flange_base - 1.6 * d.housing.bolt_bearing
    assert not _hook_hits_dipstick(t.dipstick, t.flange_w, yt, t.hook_drop, gap=2e-3)
    f = next(f for f in files if f.dxf.stem == "assembly")
    msp = ezdxf.readfile(f.dxf).modelspace()
    wavy = [p for p in msp.query('LWPOLYLINE[layer=="细实线"]') if len(p) > 8]
    assert len(wavy) >= 5  # 放油处 2 条、视孔 2 条、螺栓 1～2 条
    assert len(msp.query("HATCH")) >= 8


def _assert_no_overlaps(files):
    """GB/T 4458.4：尺寸数字、文字不被图线通过，文字之间不重叠（lint 按预览字体估外框）。"""
    bad = [(f.dxf.name, i.as_dict()) for f in files for i in lint.check(f.dxf).issues]
    assert not bad, bad


def test_coupling_scheme_drawings_have_no_overlaps(drawings):
    _assert_no_overlaps(drawings[1])


def test_vbelt_scheme_adds_pulley_drawing(tmp_path):
    vb = EXAMPLE.parent / "conveyor_vbelt.yaml"
    d = design.run(design.ReducerTask.from_yaml(vb))
    files = drawing.build_all(d, tmp_path, svg=False, pdf=False)
    pul = next(f for f in files if f.number == "GK-03-01")
    texts = " ".join(e.dxf.text for e in ezdxf.readfile(pul.dxf).modelspace().query("TEXT"))
    assert "大带轮" in texts and "HT200" in texts and "槽角" in texts
    _assert_no_overlaps(files)


def test_single_stage_scheme_drawings(tmp_path):
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_single.yaml"))
    files = drawing.build_all(d, tmp_path, svg=False, pdf=False)
    assert [f.number for f in files] == ["GK-00", "GK-01-01", "GK-01-02", "GK-02-01", "GK-02-02", "GK-03-01",
                                         "GK-04-01", "GK-04-02"]
    msp = ezdxf.readfile(files[0].dxf).modelspace()
    texts = " ".join(e.dxf.text for e in msp.query("TEXT"))
    assert "一级圆柱齿轮减速器" in texts and "高速级" not in texts
    _assert_no_overlaps(files)


def test_bevel_scheme_drawings(tmp_path):
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_bevel.yaml"))
    files = drawing.build_all(d, tmp_path, svg=False, pdf=False)
    names = [f.name for f in files]
    assert names[0] == "减速器装配图" and "大锥齿轮零件图" in names
    texts = lambda f: " ".join(e.dxf.text for e in ezdxf.readfile(f.dxf).modelspace().query("TEXT"))  # noqa: E731
    asm = texts(files[0])
    assert "圆锥-圆柱齿轮减速器" in asm and "圆锥滚子轴承 " in asm and "套杯" in asm
    big = texts(next(f for f in files if f.name == "大锥齿轮零件图"))
    assert "分度圆锥角" in big and "GB/T 11365" in big
    # 箱座、箱盖零件图：左端壁上有小锥齿轮轴承座，技术要求说明座孔与Ⅱ轴座孔垂直相交
    for name in ("箱座零件图", "箱盖零件图"):
        assert "垂直相交" in texts(next(f for f in files if f.name == name))
    _assert_no_overlaps(files)


def test_worm_scheme_drawings(tmp_path):
    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_worm.yaml"))
    files = drawing.build_all(d, tmp_path, svg=False, pdf=False)
    names = [f.name for f in files]
    assert "蜗杆零件图" in names and "蜗轮零件图" in names
    texts = lambda f: " ".join(e.dxf.text for e in ezdxf.readfile(f.dxf).modelspace().query("TEXT"))  # noqa: E731
    worm = texts(next(f for f in files if f.name == "蜗杆零件图"))
    assert "导程角" in worm and "GB/T 10089" in worm and "高频淬火" in worm
    wheel = texts(next(f for f in files if f.name == "蜗轮零件图"))
    assert "变位系数" in wheel and "HT200" in wheel and f"R{d.worm.throat_radius * 1e3:g}" in wheel
    asm = next(f for f in files if f.name == "减速器装配图")
    t = texts(asm)
    assert "蜗杆减速器" in t and "蜗轮齿圈" in t and "圆锥滚子轴承" in t and "B-B" in t
    # 中心距标注带极限偏差
    dims = [e.dxf.text for e in ezdxf.readfile(asm.dxf).modelspace().query("DIMENSION")]
    assert any("±" in s for s in dims)
    _assert_no_overlaps(files)


def test_housing_base_drawing(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "housing_base")
    assert f.number == "GK-04-01"
    doc, texts = _texts(f.dxf)
    joined = " ".join(texts)
    assert "箱座" in joined and "HT200" in joined and "A-A" in joined and "时效处理" in joined
    # 中心距按齿轮精度等级标注极限偏差（7～8 级 fa = IT8/2，GB/T 10095-1988 的取法）
    from gongke_core.calc import tolerance as tol

    dims = [e.dxf.text for e in doc.modelspace().query("DIMENSION")]
    fa = tol.center_distance_fa(d.high.inp.grade, d.high.a) * 1e3
    assert any(t.startswith("<>±") and abs(float(t[3:]) - fa) < 6e-4 for t in dims)
    # 每个轴承孔都标出 H7
    for sr in d.shafts:
        assert f"Ø{sr.layout.bearing.D * 1e3:g}H7" in joined


def test_housing_cover_drawing(drawings):
    d, files = drawings
    f = next(f for f in files if f.dxf.stem == "housing_cover")
    assert f.number == "GK-04-02"
    _, texts = _texts(f.dxf)
    joined = " ".join(texts)
    assert "箱盖" in joined and "A-A" in joined and "起盖螺钉" in joined and "视孔" in joined
    from gongke_core.layout.housing_detail import detail

    t = detail(d)
    # 箱盖外形各段圆弧半径都有标注
    assert f"R{max(t.cover_r) * 1e3:.0f}" in joined


def test_worm_housing_drawings(tmp_path):
    from gongke_core.layout.housing_detail import detail

    d = design.run(design.ReducerTask.from_yaml(EXAMPLE.parent / "conveyor_worm.yaml"))
    files = drawing.build_all(d, tmp_path, svg=False, pdf=False)
    t = detail(d)
    texts = lambda f: " ".join(e.dxf.text for e in ezdxf.readfile(f.dxf).modelspace().query("TEXT"))  # noqa: E731
    base = next(f for f in files if f.name == "箱座零件图")
    tb = texts(base)
    # 两端蜗杆座孔一次镗出，主视图局部剖视中标出座孔直径
    assert "GB/T 10089" in tb and f"Ø{t.worm_bore.D * 1e3:g}H7" in tb
    from gongke_core.drawing.worm_assembly import _fa

    dims = [e.dxf.text for e in ezdxf.readfile(base.dxf).modelspace().query("DIMENSION")]
    assert f"<>±{_fa(d.worm):.3f}".rstrip("0").rstrip(".") in dims
    # 半圆拱箱盖顶上铸出视孔平台，A-A 剖到视孔
    assert t.inspection.pad > 0
    cover = next(f for f in files if f.name == "箱盖零件图")
    assert "视孔" in texts(cover)
