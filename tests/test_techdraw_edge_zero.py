"""TechDraw 的投影 Edge0 是合法引用，不能套用 Part 的 Edge1 起点。"""
from tests.test_native_drawing import host, replace
from freecad.gongke import native_drawing


def test_zero_based_projection_reference_is_read_without_mutation(host):
    indices = []
    replace(host.view, getEdgeByIndex=lambda index: indices.append(index) or object())
    replace(host.dim, References2D=[(host.view, ["Edge0"])])
    result = native_drawing._dimension(host.dim)
    assert indices == [0]
    assert result["reference_status"] == "valid"
    assert result["measurement_m"] == .038
