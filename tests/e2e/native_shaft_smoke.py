"""在真实 FreeCAD 内验证原生轴的手改、Undo 和保存重开。

由 FreeCAD 宏或自带 Python 调用 run(output_dir)，不关闭用户已有文档。
本测试验证原生编辑机制，不代表台阶轴局部应力或疲劳验收。
"""

import json
import math
import uuid
from pathlib import Path


def run(output_dir):
    import FreeCAD as App
    from freecad.gongke import native_shaft

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    entity = str(uuid.uuid4())
    snapshot = {
        "schema_version": 1, "entity_id": entity, "scope": "simplified_shaft",
        "segments": [
            {"segment_id": "left", "length_m": 0.05, "diameter_m": 0.03,
             "editable": False, "min_diameter_m": 0.03, "max_diameter_m": 0.03},
            {"segment_id": "middle", "length_m": 0.1, "diameter_m": 0.04,
             "editable": True, "min_diameter_m": 0.032, "max_diameter_m": 0.05},
            {"segment_id": "right", "length_m": 0.05, "diameter_m": 0.03,
             "editable": False, "min_diameter_m": 0.03, "max_diameter_m": 0.03},
        ],
        "material": {"name": "教学弹性材料", "young_modulus_pa": 2e11,
                     "allowable_stress_pa": 6e7, "source": "解析基准假定值"},
        "supports_m": [0.025, 0.175],
        "loads": [{"z_m": 0.1, "fx_n": 0, "fy_n": -1000}],
        "torque_points": [],
        "constraints": {"alpha": 0.6, "max_deflection_m": 0.0001},
    }
    doc = App.newDocument("NativeShaftSmoke" + uuid.uuid4().hex[:8])
    try:
        doc.UndoMode = 1
        doc.openTransaction("建立测试轴")
        body = native_shaft.create_shaft(doc, snapshot)
        doc.commitTransaction()
        assert native_shaft.read_snapshot(body) == snapshot
        old_volume = body.Shape.Volume
        expected_volume = sum(math.pi * (s["diameter_m"] * 500.0) ** 2 * s["length_m"] * 1000.0
                              for s in snapshot["segments"])
        assert math.isclose(old_volume, expected_volume, rel_tol=1e-8)
        doc.openTransaction("修改中段直径")
        native_shaft.set_diameter(body, "middle", 0.036)
        doc.commitTransaction()
        assert body.Shape.Volume < old_volume
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.036)
        doc.undo()
        doc.recompute()
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.04)

        # 直接修改原生草图，模拟学生通过 Sketcher 改尺寸，绕过 set_diameter。
        meta = json.loads(body.GkMetadata)
        name = meta["dimensions"][1]["radius"]
        constraint = next(i for i, value in enumerate(body.GkSketch.Constraints) if value.Name == name)
        doc.openTransaction("学生手动修改")
        body.GkSketch.setDatum(constraint, App.Units.Quantity("19 mm"))
        doc.recompute()
        doc.commitTransaction()
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.038)
        filename = str(out / "native_shaft.FCStd")
        doc.saveAs(filename)
        App.closeDocument(doc.Name)
        doc = App.openDocument(filename)
        body = next(obj for obj in doc.Objects if "GkEntityId" in obj.PropertiesList and obj.GkEntityId == entity)
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.038)
        doc.openTransaction("重开后修改")
        native_shaft.set_diameter(body, "middle", 0.037)
        doc.commitTransaction()
        assert math.isclose(native_shaft.read_snapshot(body)["segments"][1]["diameter_m"], 0.037)
        doc.save()

        # 用户增加未知后续特征时，原有特征保留，自动分析范围明确降级。
        extra = body.newObject("PartDesign::Feature", "StudentFeature")
        extra.Shape = body.GkRevolution.Shape.copy()
        body.Tip = extra
        doc.recompute()
        assert not native_shaft.supported(body)
        assert doc.getObject(extra.Name) is not None
        result = {"ok": True, "freecad_version": App.Version(), "entity_id": entity,
                  "saved_project": filename, "checks": ["native_geometry", "read_current_constraints",
                  "transaction_undo", "manual_edit", "save_reopen", "edit_after_reopen", "preserve_unknown_feature"]}
        (out / "native_shaft_smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
