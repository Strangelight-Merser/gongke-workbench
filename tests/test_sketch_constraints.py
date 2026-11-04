"""原生参数重载边界；真实求解/桥接恢复另由 sketch_constraint_acceptance 验证。"""
import json
from types import SimpleNamespace

import pytest
from tests.test_native_modeling import native, ROOT


def sketch(types, point=(0, 0)):
    return SimpleNamespace(GeometryCount=len(types), Geometry=[SimpleNamespace(TypeId="Part::Geom"+t, Circle=SimpleNamespace(Axis=SimpleNamespace(z=1))) for t in types],
                           Constraints=[], getPoint=lambda *_: SimpleNamespace(x=point[0], y=point[1]))


def test_recorded_fixed_center_preserves_radius_freedom(native):
    module, _, _ = native
    data = json.loads((ROOT / "tests/fixtures/native_modeling/fixed-center.json").read_text())["sketch"]
    obj = sketch(["ArcOfCircle", "LineSegment", "ArcOfCircle", "LineSegment"])
    specs = [s for c in data["constraints"] for s in module._constraint_specs(obj, c)]
    assert specs[0][0] == ("Coincident", 0, 3, -1, 1)
    assert not any(args[0] == "Block" for args, _ in specs)
    assert specs[-2] == (("Radius", 0, 10.0), "BaseEndRadius")
    assert specs[-1] == (("Distance", 0, 3, 2, 3, 32.0), "BaseCenterDistance")


@pytest.mark.parametrize("point, expected", [
    ((20, 30), [("DistanceX", 0, 3, 20.0), ("DistanceY", 0, 3, 30.0)]),
    ((0, 30), [("PointOnObject", 0, 3, -2), ("DistanceY", 0, 3, 30.0)]),
    ((20, 0), [("DistanceX", 0, 3, 20.0), ("PointOnObject", 0, 3, -1)]),
])
def test_fixed_point_uses_coordinates_and_native_axes(native, point, expected):
    module, _, _ = native
    specs = module._constraint_specs(sketch(["Circle"], point), {"kind": "fixed", "entities": [{"geometry": 0, "point": "center"}], "name": "Anchor"})
    assert [args for args, _ in specs] == expected
    assert [name for _, name in specs] == ["Anchor_X", "Anchor_Y"]


def test_whole_block_and_dimension_numeric_overloads(native):
    module, _, _ = native
    obj = sketch(["Circle"])
    assert module._constraint_specs(obj, {"kind": "fixed", "entities": [{"geometry": 0}]}) == [(("Block", 0), None)]
    args, _ = module._constraint_specs(obj, {"kind": "radius", "entities": [{"geometry": 0}], "value": 1})[0]
    assert args == ("Radius", 0, 1000.0) and type(args[-1]) is float


@pytest.mark.parametrize("constraint", [
    {"kind": "fixed", "entities": [{"geometry": 0}, {"geometry": 1}]},
    {"kind": "fixed", "entities": [{"geometry": 0, "point": "start"}]},
    {"kind": "radius", "entities": [{"geometry": 0, "point": "center"}], "value": .01},
    {"kind": "horizontal", "entities": [{"geometry": 0}]},
    {"kind": "coincident", "entities": [{"geometry": 0}, {"geometry": 1}]},
    {"kind": "fixed", "entities": [{"geometry": 4}]},
])
def test_invalid_combination_never_calls_native_constructor(native, constraint):
    module, _, _ = native
    # fixture 的 Sketcher 没有 Constraint；若错误进入构造器会抛 AttributeError。
    with pytest.raises(ValueError):
        module._constraints(sketch(["Circle", "Circle"]), [constraint])


def test_clockwise_arc_constraints_keep_input_endpoint_meaning(native):
    module, _, _ = native
    obj = sketch(["ArcOfCircle", "LineSegment"])
    obj.Geometry[0].Circle.Axis.z = -1
    args, _ = module._constraint_specs(obj, {"kind": "coincident", "entities": [
        {"geometry": 0, "point": "start"}, {"geometry": 1, "point": "end"}]})[0]
    assert args == ("Coincident", 0, 2, 1, 2)


def test_solved_geometry_reports_post_solver_local_coordinates(native):
    module, _, _ = native
    vector = lambda x,y: SimpleNamespace(x=x,y=y)
    obj = SimpleNamespace(Name="Profile", Geometry=[
        SimpleNamespace(TypeId="Part::GeomLineSegment", StartPoint=vector(2,3), EndPoint=vector(8,3)),
        SimpleNamespace(TypeId="Part::GeomCircle", Center=vector(5,6), Radius=2),
        SimpleNamespace(TypeId="Part::GeomArcOfCircle", StartPoint=vector(0,5), EndPoint=vector(0,-5),
                        Circle=SimpleNamespace(Center=vector(0,0), Radius=5))])
    rows = module._solved_geometry(obj)
    assert rows[0]["start"] == [.002,.003] and rows[0]["end"] == [.008,.003]
    assert rows[1]["center"] == [.005,.006] and rows[1]["radius"] == .002
    assert rows[2]["start"] == [0,.005] and rows[2]["end"] == [0,-.005]


def test_solver_indices_match_zero_based_inspection_indices(native):
    module, _, _ = native
    obj = SimpleNamespace(Name="Sketch", FullyConstrained=False, DoF=2, ConflictingConstraints=[1,3],
                          RedundantConstraints=[4], isValid=lambda:True)
    result = module._sketch_status(obj)
    assert result["conflicting_constraints"] == [0,2]
    assert result["redundant_constraints"] == [3]
