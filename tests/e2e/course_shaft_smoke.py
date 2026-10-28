"""真实 FreeCAD 七段课程输出轴、两个键槽和六处圆角的绑定验收。

snapshot_path 由外部纯 Python 计算生成；本宏不加载 build123d/OCP。
run(output_dir, snapshot_path) 由现有 FreeCAD 主线程调用，不另开 GUI。
"""

import json
import math
from pathlib import Path
import uuid


def run(output_dir, snapshot_path, capture=True):
    import FreeCAD as App
    if capture:
        import FreeCADGui as Gui
    from freecad.gongke import native_shaft

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    source = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    assert source["scope"] == "course_shaft_review" and len(source["segments"]) == 7
    previous = App.ActiveDocument
    doc = App.newDocument("CourseShaftSmoke" + uuid.uuid4().hex[:8])
    checks = []

    def datum(sketch, name, value_mm):
        index = next(i for i, value in enumerate(sketch.Constraints) if value.Name == name)
        sketch.setDatum(index, App.Units.Quantity(f"{value_mm:.15g} mm"))

    try:
        marker = doc.addObject("PartDesign::Body", "ExistingStudentBody")
        old_hasher = doc.UseHasher
        try:
            native_shaft.create_shaft(doc, source)
        except ValueError as error:
            assert "新空文档" in str(error)
        else:
            raise AssertionError("课程轴不得改变已有文档的全局配置")
        assert doc.UseHasher == old_hasher and doc.getObject(marker.Name) is not None
        for child in list(marker.Group):
            doc.removeObject(child.Name)
        origin = marker.Origin
        for feature in list(origin.OriginFeatures):
            doc.removeObject(feature.Name)
        doc.removeObject(origin.Name)
        doc.removeObject(marker.Name)
        checks.append("existing_document_and_topology_configuration_preserved")

        doc.UndoMode = 1
        doc.openTransaction("创建课程输出轴")
        body = native_shaft.create_shaft(doc, source)
        doc.commitTransaction()
        assert not doc.UseHasher
        actual = native_shaft.read_snapshot(body)
        assert len(body.GkKeyPockets) == 2 and len(body.GkKeySketches) == 2
        assert len(body.GkFillets) == 6
        assert body.GkSketch.GeometryCount == 16
        previous_volume = body.GkRevolution.Shape.Volume
        for pocket in body.GkKeyPockets:
            assert pocket.TypeId == "PartDesign::Pocket"
            assert pocket.Shape.Volume < previous_volume and pocket.Shape.Volume > 0
            previous_volume = pocket.Shape.Volume
        for expected, current in zip(source["segments"], actual["segments"]):
            for field in ("z0_m", "length_m", "diameter_m"):
                assert math.isclose(current[field], expected[field], abs_tol=1e-11)
            if expected["keyway"]:
                for field in ("width_m", "length_m", "depth_m", "center_z_m"):
                    assert math.isclose(current["keyway"][field], expected["keyway"][field], abs_tol=1e-11)
        assert actual["loads"] == source["loads"] and actual["supports_m"] == source["supports_m"]
        assert actual["z_origin_m"] == source["z_origin_m"]
        assert actual["cad_geometry_state"]["load_binding_current"]
        assert actual["cad_geometry_state"]["keyways_current"]
        assert actual["cad_geometry_state"]["fillets_current"]
        assert all(math.isclose(current["cad_radius_m"], declared["assumed_radius_m"], abs_tol=1e-12)
                   for current, declared in zip(actual["fillet_assumptions"], source["fillet_assumptions"]))
        cavity = body.GkRevolution.Shape.cut(body.GkKeyPockets[-1].Shape)
        assert body.Shape.common(cavity).Volume <= max(1e-5, cavity.Volume * 1e-9)
        checks.append("seven_segments_two_pockets_six_native_fillets_without_keyway_intrusion")

        metadata = json.loads(body.GkMetadata)
        for segment in metadata["engineering"]["segments"]:
            assert "diameter_m" not in segment and "length_m" not in segment and "z0_m" not in segment
            if segment["keyway"]:
                assert not {"width_m", "length_m", "depth_m", "center_z_m"} & segment["keyway"].keys()
        assert all("cad_radius_m" not in item for item in metadata["engineering"]["fillet_assumptions"])
        assert all(set(item) == {"left_segment_id", "right_segment_id"} for item in metadata["fillets"])
        checks.append("dimensions_have_single_native_source")

        shoulder = next(segment for segment in source["segments"] if segment["role"] == "轴肩")
        names = next(item for item in metadata["dimensions"] if item["segment_id"] == shoulder["segment_id"])
        doc.openTransaction("学生手改轴肩直径")
        datum(body.GkSketch, names["radius"], (shoulder["diameter_m"] + 0.0005) * 500)
        doc.recompute()
        doc.commitTransaction()
        current = native_shaft.read_snapshot(body)
        changed = next(segment for segment in current["segments"] if segment["segment_id"] == shoulder["segment_id"])
        assert math.isclose(changed["diameter_m"], shoulder["diameter_m"] + 0.0005, abs_tol=1e-11)
        assert current["cad_geometry_state"]["load_binding_current"]
        try:
            native_shaft.set_diameter(body, shoulder["segment_id"], shoulder["diameter_m"])
        except ValueError as error:
            assert "agent 改径已禁用" in str(error)
        else:
            raise AssertionError("课程轴不应允许 agent 写入尺寸")
        doc.undo()
        doc.recompute()
        checks.append("manual_diameter_read_back_but_agent_edit_locked")

        # 第三肩的 R2.5 在直径 65 mm 时达到径向台阶极限；末端缓存仍可能有效。
        doc.openTransaction("学生改到圆角不可行直径")
        datum(body.GkSketch, names["radius"], 65.0 / 2)
        doc.recompute()
        doc.commitTransaction()
        assert "Invalid" in body.GkFillets[2].State
        assert body.Shape.isValid(), "本回归应覆盖末端缓存实体仍有效的真实场景"
        assert not native_shaft.inspect(body)["supported"]
        try:
            native_shaft.read_snapshot(body)
        except native_shaft.UnsupportedShaft:
            pass
        else:
            raise AssertionError("中间圆角失败时不得读取为当前有效工程")
        doc.undo()
        doc.recompute()
        assert native_shaft.supported(body)
        checks.append("invalid_intermediate_fillet_blocks_cached_final_shape_and_undo_restores")

        doc.openTransaction("学生手改真实圆角半径")
        old_radius = body.GkFillets[3].Radius.Value
        body.GkFillets[3].Radius = 1.5
        doc.recompute()
        doc.commitTransaction()
        current = native_shaft.read_snapshot(body)
        assert math.isclose(current["fillet_assumptions"][3]["cad_radius_m"], 0.0015, abs_tol=1e-12)
        assert current["cad_geometry_state"]["fillets_current"]
        doc.undo()
        doc.recompute()
        assert math.isclose(body.GkFillets[3].Radius.Value, old_radius, abs_tol=1e-10)
        checks.append("actual_native_radius_read_back_and_undo")

        first = source["segments"][0]
        doc.openTransaction("学生手改轴段长度")
        datum(body.GkSketch, metadata["dimensions"][0]["length"], (first["length_m"] + 0.001) * 1000)
        doc.recompute()
        doc.commitTransaction()
        current = native_shaft.read_snapshot(body)
        assert not current["cad_geometry_state"]["load_binding_current"]
        assert native_shaft.inspect(body)["analysis_status"] == "blocked"
        assert math.isclose(current["segments"][1]["z0_m"], source["segments"][1]["z0_m"] + 0.001, abs_tol=1e-11)
        assert current["loads"] == source["loads"] and current["supports_m"] == source["supports_m"]
        doc.undo()
        doc.recompute()
        assert native_shaft.read_snapshot(body)["cad_geometry_state"]["load_binding_current"]
        checks.append("length_edit_blocks_old_fixed_loads_and_undo_restores_binding")

        slot_mapping = metadata["keyways"][0]
        old_slot = next(segment["keyway"] for segment in source["segments"]
                        if segment["segment_id"] == slot_mapping["segment_id"])
        doc.openTransaction("学生手改键槽")
        datum(body.GkKeySketches[0], slot_mapping["dimensions"]["radius"], old_slot["width_m"] * 500 + 0.5)
        body.GkKeyPockets[0].Length = (old_slot["depth_m"] + 0.0005) * 1000
        doc.recompute()
        doc.commitTransaction()
        current = native_shaft.read_snapshot(body)
        current_slot = next(segment["keyway"] for segment in current["segments"]
                            if segment["segment_id"] == slot_mapping["segment_id"])
        assert math.isclose(current_slot["width_m"], old_slot["width_m"] + 0.001, abs_tol=1e-11)
        assert math.isclose(current_slot["depth_m"], old_slot["depth_m"] + 0.0005, abs_tol=1e-11)
        assert math.isclose(current_slot["length_m"], old_slot["length_m"] + 0.001, abs_tol=1e-11)
        doc.undo()
        doc.recompute()
        checks.append("keyway_width_length_depth_read_from_current_native_features")

        project = out / "course_shaft.FCStd"
        doc.saveAs(str(project))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(project))
        doc.UndoMode = 1
        assert not doc.UseHasher
        body = next(obj for obj in doc.Objects if getattr(obj, "GkEntityId", None) == source["entity_id"])
        assert native_shaft.supported(body)
        assert native_shaft.read_snapshot(body)["cad_geometry_state"]["load_binding_current"]
        assert native_shaft.read_snapshot(body)["cad_geometry_state"]["fillets_current"]
        checks.append("native_pocket_and_fillet_mapping_survives_save_reopen")
        doc.openTransaction("学生追加未支持特征")
        extra = body.newObject("PartDesign::Feature", "StudentCourseFeature")
        extra.Shape = body.GkKeyPockets[-1].Shape.copy()
        body.Tip = extra
        doc.recompute()
        doc.commitTransaction()
        assert not native_shaft.supported(body) and doc.getObject(extra.Name) is not None
        doc.undo()
        doc.recompute()
        assert native_shaft.supported(body)
        checks.append("unknown_student_feature_preserved_and_undo_restores_support")
        doc.save()
        image = None
        if capture:
            Gui.Selection.clearSelection()
            view = Gui.activeDocument().activeView()
            view.viewAxonometric()
            view.fitAll()
            image = out / "course_shaft.png"
            view.saveImage(str(image), 1600, 1000, "White")
        result = {"ok": True, "freecad_version": App.Version(), "checks": checks,
                  "saved_project": str(project), "image": str(image) if image else None,
                  "snapshot": native_shaft.read_snapshot(body),
                  "scope": "原生七段轴、两个键槽、六处声明半径圆角及当前几何读回；不代表材料、疲劳方法或完整机械安全验收。"}
        (out / "course_shaft_smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
        if previous is not None and previous.Name in App.listDocuments():
            App.setActiveDocument(previous.Name)
