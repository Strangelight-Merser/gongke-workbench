"""真实 FreeCAD 课程轴受控圆角修改；由主线程调用，不启动或退出 GUI。"""

import json
import math
from pathlib import Path
import uuid


def run(output_dir, snapshot_path):
    import FreeCAD as App
    from freecad.gongke import native_shaft

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    project = out / "course_fillet_edit.FCStd"
    if project.exists():
        raise FileExistsError("验收输出已存在，请使用新目录以保留原工程")
    source = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    previous = App.ActiveDocument
    doc = App.newDocument("CourseFilletEdit" + uuid.uuid4().hex[:8])
    checks = []
    try:
        doc.UndoMode = 1
        doc.openTransaction("创建课程圆角验收轴")
        body = native_shaft.create_shaft(doc, source)
        doc.commitTransaction()
        baseline = native_shaft.read_snapshot(body)
        assert baseline["read_only"] is False
        assert baseline["editable_parameters"] == ["right_bearing_shoulder_radius_m"]
        meta = json.loads(body.GkMetadata)
        target = next(item for item in baseline["fillet_assumptions"]
                      if math.isclose(item["z_m"], 0.164, abs_tol=1e-10))
        left, right = target["left_segment_id"], target["right_segment_id"]
        feature_index = next(i for i, item in enumerate(meta["fillets"])
                             if item["left_segment_id"] == left and item["right_segment_id"] == right)
        original_volume = body.Shape.Volume
        original_names = [obj.Name for obj in body.Group]
        original_radii = [obj.Radius.Value for obj in body.GkFillets]

        def verify_radius(snapshot, radius_m):
            value = next(item["cad_radius_m"] for item in snapshot["fillet_assumptions"]
                         if item["left_segment_id"] == left and item["right_segment_id"] == right)
            assert math.isclose(value, radius_m, abs_tol=1e-12)
            assert snapshot["segments"] == baseline["segments"]
            assert snapshot["loads"] == baseline["loads"] and snapshot["supports_m"] == baseline["supports_m"]
            assert snapshot["cad_geometry_state"]["fillets_current"]
            assert snapshot["cad_geometry_state"]["keyways_current"]
            assert [obj.Name for obj in body.Group] == original_names
            assert body.GkMetadata == json.dumps(meta, ensure_ascii=False)
            for i, obj in enumerate(body.GkFillets):
                if i != feature_index:
                    assert math.isclose(obj.Radius.Value, original_radii[i], abs_tol=1e-10)

        for radius in (0.0012, 0.0015):
            doc.openTransaction("应用受控圆角")
            current = native_shaft.set_fillet_radius(body, left, right, radius)
            doc.commitTransaction()
            verify_radius(current, radius)
            assert not math.isclose(body.Shape.Volume, original_volume, abs_tol=1e-8)
            doc.undo()
            doc.recompute()
            verify_radius(native_shaft.read_snapshot(body), 0.001)
            assert math.isclose(body.Shape.Volume, original_volume, rel_tol=1e-10)
        checks.append("only_target_radius_changes_and_native_undo_restores_1_2_and_1_5_mm")

        # 调用者可在提交前取消一次已经完成的原生写入；不依赖再次改回参数。
        doc.openTransaction("取消圆角修改")
        native_shaft.set_fillet_radius(body, left, right, 0.0012)
        doc.abortTransaction()
        doc.recompute()
        verify_radius(native_shaft.read_snapshot(body), 0.001)
        assert math.isclose(body.Shape.Volume, original_volume, rel_tol=1e-10)
        checks.append("abort_transaction_restores_completed_native_write")

        wrong = meta["fillets"][0]
        rejected = [(left, right, 0.002), (left, right, 0.0008),
                    (wrong["left_segment_id"], wrong["right_segment_id"], 0.0012),
                    (right, left, 0.0012), (left, right, float("nan")), (left, right, True)]
        for a, b, value in rejected:
            doc.openTransaction("验证不允许的圆角修改")
            try:
                native_shaft.set_fillet_radius(body, a, b, value)
            except ValueError:
                doc.abortTransaction()
                doc.recompute()
            else:
                doc.abortTransaction()
                raise AssertionError("越界值或错误轴肩未被拒绝")
            verify_radius(native_shaft.read_snapshot(body), 0.001)
            assert math.isclose(body.Shape.Volume, original_volume, rel_tol=1e-10)
        checks.append("oversized_decreasing_nonfinite_and_wrong_target_changes_rejected")

        # 复现真实上游圆角失败；新 API 必须保留学生的无效当前模型，不能暗中修复。
        names = next(item for item in meta["dimensions"] if item["segment_id"] == left)
        index = next(i for i, c in enumerate(body.GkSketch.Constraints) if c.Name == names["radius"])
        doc.openTransaction("学生手改到不可行直径")
        body.GkSketch.setDatum(index, App.Units.Quantity("32.5 mm"))
        doc.recompute()
        doc.commitTransaction()
        assert "Invalid" in body.GkFillets[2].State and body.Shape.isValid()
        doc.openTransaction("拒绝在失效模型上改圆角")
        try:
            native_shaft.set_fillet_radius(body, left, right, 0.0012)
        except native_shaft.UnsupportedShaft:
            doc.abortTransaction()
        else:
            doc.abortTransaction()
            raise AssertionError("失效祖先被末端缓存实体掩盖")
        assert math.isclose(body.GkSketch.getDatum(index).Value, 32.5, abs_tol=1e-10)
        assert math.isclose(body.GkFillets[feature_index].Radius.Value, 1.0, abs_tol=1e-10)
        doc.undo()
        doc.recompute()
        verify_radius(native_shaft.read_snapshot(body), 0.001)
        checks.append("invalid_ancestor_rejected_without_overwriting_student_edit")

        doc.openTransaction("验证课程改径仍禁用")
        try:
            native_shaft.set_diameter(body, left, 0.0645)
        except ValueError as error:
            assert "agent 改径已禁用" in str(error)
            doc.abortTransaction()
        else:
            doc.abortTransaction()
            raise AssertionError("圆角开放不应开放课程轴径")
        checks.append("course_diameter_remains_locked")

        doc.saveAs(str(project))
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(project))
        doc.UndoMode = 1
        body = next(obj for obj in doc.Objects if getattr(obj, "GkEntityId", None) == baseline["entity_id"])
        doc.openTransaction("重开后继续改圆角")
        current = native_shaft.set_fillet_radius(body, left, right, 0.0015)
        doc.commitTransaction()
        verify_radius(current, 0.0015)
        assert not doc.UseHasher
        doc.save()
        checks.append("same_native_fillet_remains_editable_after_save_reopen")
        result = {"ok": True, "freecad_version": App.Version(), "checks": checks,
                  "saved_project": str(project), "snapshot": current,
                  "scope": "右轴承邻接轴肩的受控原生圆角修改与事务验收，未宣告整轴机械合格。"}
        (out / "course_fillet_edit_smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
        if previous is not None and previous.Name in App.listDocuments():
            App.setActiveDocument(previous.Name)
