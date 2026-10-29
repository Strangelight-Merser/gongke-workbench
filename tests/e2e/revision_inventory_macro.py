"""在隔离 FreeCAD GUI 中重开原生基准并验证只读；只操作指定测试目录。"""

import hashlib
import json
from pathlib import Path
import time


def state(doc):
    import FreeCAD as App
    import FreeCADGui as Gui
    gui = Gui.getDocument(doc.Name)
    return {
        "file_hash": hashlib.sha256(Path(doc.FileName).read_bytes()).hexdigest(),
        "modified": bool(gui.Modified), "pending_transaction": bool(doc.HasPendingTransaction),
        "undo_count": doc.UndoCount, "redo_count": doc.RedoCount,
        "active_document": App.ActiveDocument.Name, "editing": repr(gui.getInEdit()),
        "selection": [(s.DocumentName, s.ObjectName, list(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()],
        "objects": [{"name": o.Name, "type": o.TypeId, "label": o.Label,
                     "properties": list(o.PropertiesList), "state": list(o.State),
                     "placement": str(o.Placement) if hasattr(o, "Placement") else None,
                     "constraints": [(c.Type, c.Value) for c in o.Constraints] if hasattr(o, "Constraints") else None,
                     "format": o.FormatSpec if hasattr(o, "FormatSpec") else None,
                     "override": o.Arbitrary if hasattr(o, "Arbitrary") else None,
                     "refs": [(v.Name, list(e)) for v, e in o.References2D] if hasattr(o, "References2D") else None}
                    for o in doc.Objects],
    }


def run(fixture_dir, output_dir):
    import FreeCAD as App
    import FreeCADGui as Gui
    from freecad.gongke import bridge, native_drawing
    from gongke_core.revision_case import inspect_revision

    fixtures, out = Path(fixture_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    Gui.activateWorkbench("TechDrawWorkbench")
    records = []
    documents = []
    for name in ("normal", "override", "wrong_reference", "dangling", "missing_condition", "interactive"):
        case = json.loads((fixtures / (name + ".case.json")).read_text())
        doc = App.openDocument(case["document"]["path"])
        documents.append(doc)
        page = doc.getObject(case["pages"][0])
        Gui.getDocument(doc.Name).getObject(page.Name).show()
        # 这是明确的宿主更新步骤；capture 本身不得做这些动作。
        doc.recompute()
        for _ in range(50):
            Gui.updateGui()
            time.sleep(0.03)
        # 投影异步返回后会再触碰依赖标注；显式完成这轮宿主更新再取基线。
        doc.recompute()
        Gui.updateGui()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.getObject(case["annotations"][0]["dimension"]))
        # 宿主选中标注时可能回写其 X/Y 显示位置。先完成本测试的选择动作，
        # 明确更新后再记录只读前基线；捕获阶段不处理事件、不重算。
        Gui.updateGui()
        doc.recompute()
        before = state(doc)
        first = native_drawing.capture(doc, case["document"]["body"], case["pages"], "inventory-" + name)
        second = native_drawing.capture(doc, case["document"]["body"], case["pages"], "inventory-" + name)
        after = state(doc)
        assert before == after, f"只读检查改变了 {name} 的状态"
        assert first == second, f"重复读取不一致：{name}"
        result = inspect_revision(case, first)
        (out / (name + ".revision.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        expected = "fail" if name in ("override", "wrong_reference", "dangling") else "pass"
        assert result["drawing_review"]["status"] == expected, (name, result["drawing_review"])
        if name == "missing_condition":
            assert result["calculation"]["checks"][0]["value"] is not None
            assert result["calculation"]["checks"][1]["status"] == "unavailable"
        records.append({"case": name, "drawing": expected, "read_only_unchanged": True,
                        "before": before, "after": after})

    doc = documents[-1]
    doc.openTransaction("验收：保留正在进行的人工编辑")
    dimension = doc.getObject(case["annotations"][0]["dimension"])
    dimension.Label = "manual label retained"
    before = state(doc)
    captured = native_drawing.capture(doc, case["document"]["body"], case["pages"], "pending-edit")
    after = state(doc)
    assert before == after and doc.HasPendingTransaction
    result = inspect_revision(case, captured)
    assert result["drawing_review"]["status"] == "unknown"
    assert all(c["status"] == "unavailable" for c in result["calculation"]["checks"])
    (out / "pending.revision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    doc.abortTransaction()  # 撤回本测试自身的编辑，不由读取器完成。
    Gui.activateWorkbench("GongKeWorkbench")
    bridge.start()
    (out / "inventory.json").write_text(json.dumps({
        "host_version": App.Version(), "installed_module": native_drawing.__file__,
        "reopened": records, "pending_edit_unchanged": before == after,
        "pending_before": before, "pending_after": after,
        "interactive_document": doc.Name, "interactive_path": doc.FileName,
    }, ensure_ascii=False, indent=2))
    return doc
