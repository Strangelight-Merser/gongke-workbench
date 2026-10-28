"""真实 FreeCAD 外来三段轴绑定：保留用户原生对象，事务由调用者管理。"""

from copy import deepcopy
import json
import math
from pathlib import Path
import uuid


def create_student_shaft(doc):
    """独立学生模型：个人命名、打乱线编号、Body 放置及原生手改中径 38 mm。"""
    import FreeCAD as App
    import Part
    import Sketcher

    body = doc.addObject("PartDesign::Body", "MyRotor")
    body.Label = "我的课程轴"
    body.Placement = App.Placement(App.Vector(12, -25, 40), App.Rotation(App.Vector(0, 0, 1), 37))
    sketch = body.newObject("Sketcher::SketchObject", "MyOutline")
    sketch.Label = "学生原有尺寸草图"
    points = [(0, 0), (0, 15), (50, 15), (50, 20), (150, 20), (150, 15), (200, 15), (200, 0)]
    order = [5, 0, 7, 3, 2, 6, 1, 4]  # 故意打乱几何编号，识别不得依赖工作台生成顺序。
    indices = {original: added for added, original in enumerate(order)}
    sketch.addGeometry([Part.LineSegment(App.Vector(*points[i], 0), App.Vector(*points[(i + 1) % 8], 0))
                        for i in order], False)
    for i in range(8):
        sketch.addConstraint(Sketcher.Constraint("Coincident", indices[i], 2, indices[(i + 1) % 8], 1))
        sketch.addConstraint(Sketcher.Constraint("Vertical" if i % 2 == 0 else "Horizontal", indices[i]))
    sketch.addConstraint(Sketcher.Constraint("Coincident", indices[0], 1, -1, 1))
    for number, original, length, radius in zip(range(1, 4), (1, 3, 5), (50, 100, 50), (15, 20, 15)):
        index = sketch.addConstraint(Sketcher.Constraint("Distance", indices[original], length))
        sketch.renameConstraint(index, f"my_length_{number}")
        index = sketch.addConstraint(Sketcher.Constraint("DistanceY", indices[original], 2, radius))
        sketch.renameConstraint(index, f"my_radius_{number}")
    doc.recompute()
    revolution = body.newObject("PartDesign::Revolution", "MyTurnedShaft")
    revolution.Label = "学生原有回转"
    revolution.Profile = sketch
    revolution.ReferenceAxis = (sketch, ["H_Axis"])
    revolution.Angle = 360
    body.Tip = revolution
    doc.recompute()
    middle = next(i for i, constraint in enumerate(sketch.Constraints) if constraint.Name == "my_radius_2")
    sketch.setDatum(middle, App.Units.Quantity("19 mm"))
    doc.recompute()
    return body


def run(output_dir):
    import FreeCAD as App
    from freecad.gongke import native_shaft
    from gongke_core.shaft_binding import prepare_snapshot

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    project = out / "existing_shaft.FCStd"
    if project.exists():
        raise FileExistsError("请使用新验收目录，不能覆盖已有工程")
    previous = App.ActiveDocument
    doc = App.newDocument("StudentShaft" + uuid.uuid4().hex[:8])
    checks = []
    try:
        doc.UndoMode = 1
        body = create_student_shaft(doc)
        sketch = next(obj for obj in body.Group if obj.TypeId == "Sketcher::SketchObject")
        revolution = body.Tip

        def original_state():
            return {"names": [obj.Name for obj in body.Group],
                    "labels": [obj.Label for obj in (body, sketch, revolution)],
                    "placement": [list(obj.Placement.toMatrix().A) for obj in (body, sketch, revolution)],
                    "geometry": [[list(g.StartPoint), list(g.EndPoint)] for g in sketch.Geometry],
                    "constraints": native_shaft._constraint_signature(sketch),
                    "dimensions": [sketch.getDatum(i).Value for i, c in enumerate(sketch.Constraints) if c.Name],
                    "volume": body.Shape.Volume}

        description = native_shaft.describe_unbound(body)
        assert description["can_bind"], description
        assert [s["radius_constraint"] for s in description["segments"]] == [f"my_radius_{i}" for i in range(1, 4)]
        assert description["sketch"] == sketch.Name and description["revolution"] == revolution.Name
        assert all(not name.startswith("Gk") for name in body.PropertiesList)
        baseline = original_state()
        assert native_shaft.describe_unbound(body) == description and original_state() == baseline
        checks.append("personal_names_permuted_geometry_and_body_placement_described_without_mutation")

        doc.openTransaction("拒绝未完全约束的学生草图")
        index = next(i for i, c in enumerate(sketch.Constraints) if c.Name == "my_radius_2")
        sketch.delConstraint(index)
        doc.recompute()
        assert not native_shaft.describe_unbound(body)["can_bind"]
        doc.abortTransaction()
        doc.recompute()
        doc.openTransaction("拒绝表达式驱动的尺寸")
        sketch.setExpression("Constraints.my_radius_2", "19 mm")
        doc.recompute()
        assert not native_shaft.describe_unbound(body)["can_bind"]
        doc.abortTransaction()
        doc.recompute()
        assert original_state() == baseline
        checks.append("underconstrained_and_expression_driven_sketches_rejected")

        conditions = {
            "coordinate_system": "body_local_x", "source": "独立原生绑定验收：显式给定的简支梁解析工况",
            "material": {"name": "解析测试材料", "young_modulus_pa": 2e11,
                         "allowable_stress_pa": 6e7, "source": "解析测试输入，非工程材料牌号"},
            "supports_m": [0.025, 0.175], "loads": [{"z_m": 0.1, "fx_n": 0.0, "fy_n": -1000.0}],
            "torque_points": [], "constraints": {"alpha": 0.6, "max_deflection_m": 0.0001},
            "middle_diameter_bounds_m": [0.032, 0.05],
        }
        snapshot = prepare_snapshot(description, conditions)
        invalid = deepcopy(snapshot)
        invalid["segments"][1]["length_m"] += 0.001
        doc.openTransaction("拒绝不一致尺寸")
        try:
            native_shaft.bind_existing(body, invalid)
        except ValueError:
            doc.abortTransaction()
        else:
            doc.abortTransaction()
            raise AssertionError("不一致输入被绑定")
        assert original_state() == baseline and "GkEntityId" not in body.PropertiesList
        missing = deepcopy(snapshot)
        missing.pop("loads")
        doc.openTransaction("拒绝缺失工况")
        try:
            native_shaft.bind_existing(body, missing)
        except ValueError:
            doc.abortTransaction()
        else:
            doc.abortTransaction()
            raise AssertionError("缺失载荷列表不能套用默认工况")
        assert original_state() == baseline and "GkEntityId" not in body.PropertiesList
        checks.append("dimension_mismatch_and_missing_conditions_rejected_without_metadata")

        doc.openTransaction("绑定已有学生轴")
        actual = native_shaft.bind_existing(body, snapshot)
        doc.commitTransaction()
        assert actual == snapshot and original_state() == baseline
        assert not native_shaft.describe_unbound(body)["can_bind"]
        assert json.loads(body.GkMetadata)["binding_origin"] == "existing_native_shaft"
        doc.undo()
        doc.recompute()
        assert "GkEntityId" not in body.PropertiesList
        assert native_shaft.describe_unbound(body)["can_bind"] and original_state() == baseline
        checks.append("binding_only_adds_metadata_and_native_undo_removes_binding")

        doc.openTransaction("重新绑定学生轴")
        native_shaft.bind_existing(body, snapshot)
        doc.commitTransaction()
        middle = snapshot["segments"][1]["segment_id"]
        doc.openTransaction("通过现有尺寸修改中段")
        current = native_shaft.set_diameter(body, middle, 0.036)
        doc.commitTransaction()
        assert math.isclose(current["segments"][1]["diameter_m"], 0.036)
        doc.undo()
        doc.recompute()
        assert original_state() == baseline
        radius_index = next(i for i, c in enumerate(sketch.Constraints) if c.Name == "my_radius_2")
        doc.openTransaction("学生在自己的草图手改")
        sketch.setDatum(radius_index, App.Units.Quantity("18.5 mm"))
        doc.recompute()
        doc.commitTransaction()
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.037)
        checks.append("agent_and_manual_edit_share_original_named_dimension")

        doc.openTransaction("错误的尺寸语义映射")
        bad_meta = json.loads(body.GkMetadata)
        bad_meta["dimensions"][1]["radius"] = bad_meta["dimensions"][0]["radius"]
        body.GkMetadata = json.dumps(bad_meta, ensure_ascii=False)
        doc.recompute()
        doc.commitTransaction()
        assert not native_shaft.supported(body)
        doc.undo()
        doc.recompute()
        assert native_shaft.supported(body)
        checks.append("wrong_constraint_semantics_rejected_after_binding")

        doc.openTransaction("学生添加隐藏的未知特征")
        extra = body.newObject("PartDesign::Feature", "MyHiddenFeature")
        extra.Shape = revolution.Shape.copy()
        body.Tip = revolution
        doc.recompute()
        doc.commitTransaction()
        assert not native_shaft.supported(body) and doc.getObject(extra.Name) is not None
        doc.undo()
        doc.recompute()
        assert native_shaft.supported(body)
        checks.append("hidden_unknown_feature_preserved_and_rejected")

        doc.saveAs(str(project))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(project))
        doc.UndoMode = 1
        body = next(obj for obj in doc.Objects if getattr(obj, "GkEntityId", None) == snapshot["entity_id"])
        sketch, revolution = body.GkSketch, body.GkRevolution
        assert [obj.Label for obj in (body, sketch, revolution)] == baseline["labels"]
        assert all(math.isclose(a, b, abs_tol=1e-10) for a, b in
                   zip(body.Placement.toMatrix().A, baseline["placement"][0]))
        doc.openTransaction("重开后编辑原有轴")
        current = native_shaft.set_diameter(body, middle, 0.036)
        doc.commitTransaction()
        assert current["coordinate_system"] == "body_local_x"
        assert current["conditions_source"] == snapshot["conditions_source"]
        assert current["entity_id"] == snapshot["entity_id"]
        doc.save()
        checks.append("same_identity_local_frame_and_original_objects_survive_save_reopen")
        result = {"ok": True, "checks": checks, "freecad_version": App.Version(),
                  "saved_project": str(project), "snapshot": current}
        (out / "existing_shaft_smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
        if previous is not None and previous.Name in App.listDocuments():
            App.setActiveDocument(previous.Name)
