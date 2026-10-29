"""面板默认工况的标注回归；核对实际 DXF，不替代专业审图。"""

import ezdxf
import pytest

from freecad.gongke.runner import FormValues, task_dict
from gongke_core import design, drawing
from gongke_core.drawing import lint, shaft
from gongke_core.layout.housing_detail import detail


@pytest.mark.parametrize("scheme", ["coupling", "vbelt", "bevel", "single", "worm"])
def test_panel_drawings_remain_readable(tmp_path, scheme):
    # 与面板及 GUI E2E 相同的默认输入；single 的传动比由面板自动分配。
    values = FormValues(scheme=scheme, belt_ratio=None if scheme == "single" else 2.5)
    result = design.run(design.ReducerTask.from_dict(task_dict(values)))
    sheets = drawing.build_all(result, tmp_path, svg=False, pdf=False)
    issues = [(sheet.dxf.name, issue.as_dict()) for sheet in sheets for issue in lint.check(sheet.dxf).issues]
    assert not issues, issues
    if scheme == "vbelt":
        # 曾被吊钩轮廓穿过的 60 mm 凸台高度仍有实际标注，不能靠删除尺寸通过。
        expected = f"{detail(result).boss_h * 1000:g}"
        doc = ezdxf.readfile(tmp_path / "housing_base.dxf")
        texts = [entity.plain_text() if entity.dxftype() == "MTEXT" else entity.dxf.text
                 for dimension in doc.modelspace().query("DIMENSION")
                 for entity in dimension.get_geometry_block()
                 if entity.dxftype() in ("TEXT", "MTEXT")]
        assert expected in texts


def test_panel_bevel_shaft_fitted_diameter_stays_clear_of_cone(tmp_path):
    result = design.run(design.ReducerTask.from_dict(task_dict(FormValues(scheme="bevel"))))
    path = tmp_path / "shaft1.dxf"
    shaft.draw(result, result.shafts[0], path)
    issues = lint.check(path).issues
    assert not issues, [issue.as_dict() for issue in issues]
    doc = ezdxf.readfile(path)
    texts = [entity.plain_text() if entity.dxftype() == "MTEXT" else entity.dxf.text
             for dimension in doc.modelspace().query("DIMENSION")
             for entity in dimension.get_geometry_block()
             if entity.dxftype() in ("TEXT", "MTEXT")]
    # 40 mm 配合直径及上下偏差必须保留，不能删除标注或公差来消除压线。
    assert any("40+0.018^+0.002" in text for text in texts)
