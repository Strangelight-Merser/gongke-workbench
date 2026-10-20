"""图纸重叠检查与自动避让（gongke_core.drawing.lint）。"""

import ezdxf

from gongke_core.drawing import lint
from gongke_core.drawing.sheet import Sheet


def _sheet_with_text():
    sh = Sheet("A4")
    sh.text(50, 100, "Ø40k6", 3.5)
    return sh


def test_line_through_text_is_reported(tmp_path):
    sh = _sheet_with_text()
    sh.line((52, 90), (52, 110), "粗实线")  # 竖直粗实线穿过“Ø40k6”
    sh.line((40, 98), (70, 98), "粗实线")  # 文字下方 2 mm，不算压字
    f = tmp_path / "a.dxf"
    sh.save(f)
    r = lint.check(f)
    assert r.count("line-text") == 1 and r.count("text-text") == 0


def test_text_text_overlap_is_reported(tmp_path):
    sh = _sheet_with_text()
    sh.text(53, 101, "M12", 3.5)
    f = tmp_path / "b.dxf"
    sh.save(f)
    assert lint.check(f).count("text-text") == 1


def test_centerline_and_thin_lines_are_broken_at_text(tmp_path):
    """GB/T 4458.4：尺寸数字不能被任何图线通过，否则须将图线断开。出图时点画线、细实线自动断开。"""
    sh = _sheet_with_text()
    sh.line((30, 101.7), (90, 101.7), "点画线")
    sh.line((53, 80), (53, 120), "细实线")
    f = tmp_path / "c.dxf"
    sh.save(f)
    msp = ezdxf.readfile(f).modelspace()
    assert len(msp.query('LINE[layer=="点画线"]')) == 2
    assert len(msp.query('LINE[layer=="细实线"]')) == 2
    assert lint.check(f).issues == []


def test_leader_text_moves_off_lines(tmp_path):
    """引出标注原定位置压在一排粗实线上时，出图时在附近另找空位；原位置空着时不动。"""
    sh = Sheet("A4")
    for k in range(6):  # 原定文字位置处的一排竖线
        sh.line((60 + 2 * k, 120), (60 + 2 * k, 140), "粗实线")
    sh.leader_text((50, 120), (58, 128), "Ø30H7/r6", 3.0)
    sh.leader_text((150, 120), (158, 128), "Ø30k6", 3.0)  # 周围是空的
    f = tmp_path / "d.dxf"
    sh.save(f)
    assert lint.check(f).issues == []
    texts = {e.dxf.text: e for e in ezdxf.readfile(f).modelspace().query("TEXT")}
    assert abs(texts["Ø30k6"].dxf.insert.x - 159) < 1e-6


def test_text_inside_hatch_gets_an_island(tmp_path):
    """剖面线遇文字断开：文字整个落在剖面区域内时，文字外框作为孤岛加进剖面线边界。"""
    sh = Sheet("A4")
    sh.hatch([[(30, 80), (100, 80), (100, 130), (30, 130)]])
    sh.text(50, 100, "Ø58H7/r6", 3.0)
    f = tmp_path / "e.dxf"
    sh.save(f)
    h = ezdxf.readfile(f).modelspace().query("HATCH")[0]
    assert len(h.paths) == 2
