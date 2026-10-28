"""真实 FreeCAD 验证批处理结果的文档绑定和原生导入事务。"""

import json
import math
import os
from pathlib import Path
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore

OUT = Path(os.environ["GONGKE_NATIVE_OUT"])
OUT.mkdir(parents=True, exist_ok=True)
Gui.activateWorkbench("GongKeWorkbench")
from freecad.gongke.panels import ReducerTaskPanel
documents = []


def make_document(name):
    doc = App.newDocument(name)
    doc.UndoMode = 1
    documents.append(doc.Name)
    return doc


try:
    source = make_document("BindingStepSource")
    cylinder = source.addObject("Part::Feature", "Cylinder")
    cylinder.Shape = Part.makeCylinder(5, 30)
    source.recompute()
    step = OUT / "import_sample.step"
    Part.export([cylinder], str(step))

    target = make_document("BindingOriginal")
    student = target.addObject("Part::Feature", "StudentBox")
    student.Shape = Part.makeBox(10, 12, 14)
    target.recompute()
    panel = ReducerTaskPanel.__new__(ReducerTaskPanel)
    panel.target_document = target
    panel.target_document_name = target.Name

    other = make_document("BindingOther")
    other_student = other.addObject("Part::Feature", "OtherStudentBox")
    other_student.Shape = Part.makeBox(2, 3, 4)
    other.recompute()
    App.setActiveDocument(other.Name)
    panel._import_model(step)
    assert App.ActiveDocument == other
    assert len(other.Objects) == 1 and math.isclose(other_student.Shape.Volume, 24), (
        [obj.Name for obj in other.Objects], other_student.Shape.Volume)
    imported = [obj for obj in target.Objects if obj != student and hasattr(obj, "Shape")]
    assert imported and all(obj.Shape.isValid() for obj in imported)
    assert target.UndoNames[0] == "导入减速器批处理模型"
    target.undo()
    target.recompute()
    assert len(target.Objects) == 1 and target.Objects[0] == student
    checks = ["real_step_import_stays_in_started_document_after_switch",
              "native_undo_removes_import_and_preserves_student_geometry"]

    old_name = target.Name
    App.closeDocument(old_name)
    recreated = make_document(old_name)
    try:
        panel._import_model(step)
    except ValueError as exc:
        assert "已关闭" in str(exc)
    else:
        raise AssertionError("同名新文档不应接收旧任务结果")
    assert not recreated.Objects and len(other.Objects) == 1
    checks.append("closed_target_cannot_bind_to_recreated_same_name_document")

    panel.target_document = other
    panel.target_document_name = other.Name
    other.openTransaction("学生尚未完成的编辑")
    other_student.Label = "学生正在修改的零件"
    assert other.HasPendingTransaction
    try:
        panel._import_model(step)
    except ValueError as exc:
        assert "正在编辑" in str(exc) and other.HasPendingTransaction
    else:
        raise AssertionError("导入不应进入学生事务")
    other.abortTransaction()
    checks.append("pending_student_transaction_remains_untouched")
    (OUT / "panel_document_binding.json").write_text(json.dumps({
        "ok": True, "checks": checks, "freecad_version": App.Version(),
        "scope": "真实 FreeCAD STEP 导入回调与文档切换；未使用可访问性点击。"
    }, ensure_ascii=False, indent=2))
except Exception:
    (OUT / "panel_document_binding_error.txt").write_text(traceback.format_exc())
finally:
    for name in set(documents):
        if name in App.listDocuments():
            App.closeDocument(name)
    QtCore.QTimer.singleShot(0, Gui.getMainWindow().close)
