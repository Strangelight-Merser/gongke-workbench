"""人工构造的原生修订基准；不是学生样本，也不修改原有测试材料。"""

import importlib.util
import json
import math
from pathlib import Path
import time


def settle(doc, views):
    """仅基准构造阶段等待 TechDraw 异步投影，读取器不调用此函数。"""
    import FreeCADGui as Gui
    doc.recompute()
    for _ in range(100):
        Gui.updateGui()
        if all(v.getVisibleEdges() for v in views):
            # 投影就绪后，让依赖标注完成本轮事件处理。
            Gui.updateGui()
            return
        time.sleep(0.05)
    raise AssertionError("TechDraw 投影未生成，不能把零值作为基准")


def build(output_dir):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.gongke import native_drawing, native_shaft

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("existing_fixture", root / "tests/e2e/existing_shaft_smoke.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    Gui.activateWorkbench("TechDrawWorkbench")
    doc = App.newDocument("RevisionTeachingFixture")
    doc.UndoMode = 1
    body = helper.create_student_shaft(doc)
    body.Label = "人工构造的三段轴基准"
    page = doc.addObject("TechDraw::DrawPage", "ShaftDrawing")
    template = doc.addObject("TechDraw::DrawSVGTemplate", "DrawingTemplate")
    template.Template = App.getResourceDir() + "Mod/TechDraw/Templates/Default_Template_A4_Landscape.svg"
    page.Template = template
    views = []
    for name, x in (("EndView", 75), ("SecondEndView", 210)):
        view = doc.addObject("TechDraw::DrawViewPart", name)
        view.Source = [body]
        view.Direction = body.Placement.Rotation.multVec(App.Vector(1, 0, 0))
        view.X, view.Y = x, 105
        page.addView(view)
        views.append(view)
    Gui.activeDocument().getObject(page.Name).show()
    settle(doc, views)
    # 首次显示会由 TechDraw 自动置中；投影就绪后再确定两个视图的位置。
    for view, x in zip(views, (75, 210)):
        view.X, view.Y = x, 105
        view.LockPosition = True
    doc.recompute()
    Gui.updateGui()
    dimensions = []
    for i, view in enumerate(views):
        # 从真实投影边找 19 mm 圆，不能假设模型 Edge 编号等于图纸 Edge 编号。
        edge = next(j for j in range(1, len(view.getVisibleEdges()) + 1)
                    if math.isclose(getattr(view.getEdgeByIndex(j).Curve, "Radius", -1), 19.0))
        dim = doc.addObject("TechDraw::DrawViewDimension", "MiddleDiameter" + str(i + 1))
        dim.Type = "Diameter"
        dim.References2D = [(view, (f"Edge{edge}",))]
        page.addView(dim)
        dim.X, dim.Y = 26, 22
        dimensions.append(dim)
    settle(doc, views)
    assert all(math.isclose(d.getRawValue(), 38.0) for d in dimensions)
    conditions = json.loads((root / "examples/revision_conditions.json").read_text())
    description = native_shaft._describe_simple_parts(body)
    signature = native_shaft._constraint_signature(doc.getObject(description["sketch"]))
    records = []

    def save(name, expected, source_conditions=conditions):
        project = out / (name + ".FCStd")
        doc.saveAs(str(project))
        case = {
            "schema_version": 1, "case_id": "teaching-" + name,
            "provenance": "人工构造基准，载荷与材料为教学假定，不代表实际设计依据",
            "document": {"path": str(project), "body": body.Name, "sketch": description["sketch"],
                         "revolution": description["revolution"], "structure_signature": signature},
            "target": {"radius_constraint": "my_radius_2", "segment_index": 1},
            "pages": [page.Name],
            "annotations": [{"page": page.Name, "view": v.Name, "dimension": d.Name, "target": "diameter"}
                            for v, d in zip(views, dimensions)],
            "conditions": source_conditions,
        }
        (out / (name + ".case.json")).write_text(json.dumps(case, ensure_ascii=False, indent=2))
        capture = native_drawing.capture(doc, body.Name, [page.Name], "fixture-build")
        (out / (name + ".capture.json")).write_text(json.dumps(capture, ensure_ascii=False, indent=2))
        records.append({"name": name, "expected": expected, "project": str(project)})

    save("normal", "pass")
    doc.openTransaction("构造显示覆盖负例")
    dimensions[0].Arbitrary = True
    dimensions[0].FormatSpec = "⌀99.00 mm"
    settle(doc, views)
    doc.commitTransaction()
    save("override", "dimension_override")
    doc.undo()
    settle(doc, views)
    doc.openTransaction("构造错误模型引用负例")
    other = doc.addObject("PartDesign::Feature", "OtherShaft")
    other.Shape = body.Shape.copy()
    views[0].Source = [other]
    settle(doc, views)
    doc.commitTransaction()
    save("wrong_reference", "wrong_model_reference")
    doc.undo()
    settle(doc, views)
    doc.openTransaction("构造失联标注负例")
    dimensions[0].References2D = [(views[0], ("Edge999",))]
    settle(doc, views)
    doc.commitTransaction()
    save("dangling", "dangling_reference")
    doc.undo()
    settle(doc, views)
    incomplete = json.loads(json.dumps(conditions))
    incomplete["fields"].pop("young_modulus")
    save("missing_condition", "deflection_unavailable_stress_retained", incomplete)
    # 单独保留可继续手改的正常工程用于真实界面验收。
    save("interactive", "pass")
    (out / "manifest.json").write_text(json.dumps({"artificial_fixture": True, "cases": records},
                                                ensure_ascii=False, indent=2))
    return doc, records
