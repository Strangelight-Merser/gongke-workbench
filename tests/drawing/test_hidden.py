"""消隐：线段、圆弧被圆或矩形挡住部分的计算（解析几何）。"""

import pytest

from gongke_core.drawing import hidden


def test_segment_through_circle():
    segs = hidden.visible_segments((-2, 0), (2, 0), circles=[(0, 0, 1)])
    assert segs == [((-2, 0), pytest.approx((-1, 0))), (pytest.approx((1, 0)), (2, 0))]


def test_segment_inside_rect_removed():
    assert hidden.visible_segments((0.2, 0.5), (0.8, 0.5), rects=[(0, 0, 1, 1)]) == []
    # 与矩形边重合的线不算被挡住
    assert len(hidden.visible_segments((0, 0), (1, 0), rects=[(0, 0, 1, 1)])) == 1


def test_arc_behind_circle():
    # 单位圆被圆心 (1, 0)、半径 1 的圆挡住 −60°～60° 一段（两圆交点在 ±60°）
    arcs = hidden.visible_arcs(0, 0, 1, 0, 360, circles=[(1, 0, 1)])
    total = sum(b - a for a, b in arcs)
    assert total == pytest.approx(240)
    assert hidden.visible_arcs(0, 0, 1, 0, 360, circles=[(0, 0, 2)]) == []


def test_hidden_arc_behind_rect():
    # 单位圆被矩形 [−2, 2] × [−0.5, 0.5] 挡住 |y| < 0.5 的部分：剩下 30°～150° 和 210°～330°
    arcs = hidden.visible_arcs(0, 0, 1, 0, 360, rects=[(-2, -0.5, 2, 0.5)])
    assert arcs == [pytest.approx((30, 150)), pytest.approx((210, 330))]
