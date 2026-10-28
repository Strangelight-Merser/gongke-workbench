"""批处理回调不得写入后来切换的文档；真实几何导入另用 FreeCAD 验证。"""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def panel(monkeypatch):
    class Document:
        HasPendingTransaction = False

        def __init__(self, name):
            self.Name = name
            self.objects = ["student_work"]
            self.commits = 0

        def openTransaction(self, name):
            self.before = list(self.objects)

        def commitTransaction(self):
            self.commits += 1

        def abortTransaction(self):
            self.objects[:] = self.before

        def recompute(self):
            pass

    original, other = Document("Original"), Document("Other")
    docs = {d.Name: d for d in (original, other)}
    views = []
    state = SimpleNamespace(editing=False, fail=False, imports=[])

    def new_document(name):
        doc = Document(name)
        docs[name] = doc
        return doc

    def insert(path, name):
        state.imports.append((path, name))
        docs[name].objects.append("imported_step")
        if state.fail:
            raise RuntimeError("partial import failed")

    app = SimpleNamespace(ActiveDocument=other, listDocuments=lambda: docs,
                          newDocument=new_document, closeDocument=lambda name: docs.pop(name))
    gui = SimpleNamespace(getDocument=lambda name: SimpleNamespace(
        getInEdit=lambda: state.editing,
        activeView=lambda: SimpleNamespace(viewIsometric=lambda: views.append(name), fitAll=lambda: None)))
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    monkeypatch.setitem(sys.modules, "Import", SimpleNamespace(insert=insert))
    monkeypatch.setitem(sys.modules, "PySide", SimpleNamespace(QtCore=SimpleNamespace(), QtGui=SimpleNamespace()))
    monkeypatch.setitem(sys.modules, "freecad.gongke.commands", SimpleNamespace(params=lambda: None))
    path = Path(__file__).resolve().parents[1] / "freecad/gongke/panels.py"
    spec = importlib.util.spec_from_file_location("panel_binding_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instance = module.ReducerTaskPanel.__new__(module.ReducerTaskPanel)
    instance.target_document = original
    instance.target_document_name = original.Name
    return instance, original, other, docs, state, views, module


def test_finish_imports_into_original_document_after_user_switches(panel):
    instance, original, other, _, state, views, _ = panel
    instance._import_model("result.step")
    assert state.imports == [("result.step", "Original")]
    assert other.objects == ["student_work"]
    assert original.objects == ["student_work", "imported_step"] and original.commits == 1
    assert views == ["Original"]


@pytest.mark.parametrize("recreated", [False, True])
def test_closed_target_never_redirects_to_active_or_same_name_document(panel, recreated):
    instance, original, other, docs, state, _, _ = panel
    del docs[original.Name]
    if recreated:
        docs[original.Name] = type(original)(original.Name)
    with pytest.raises(ValueError, match="已关闭"):
        instance._import_model("result.step")
    assert not state.imports and other.objects == ["student_work"]


@pytest.mark.parametrize("editing", ["sketch", "transaction"])
def test_import_does_not_enter_student_edit(panel, editing):
    instance, original, _, _, state, _, _ = panel
    state.editing = editing == "sketch"
    original.HasPendingTransaction = editing == "transaction"
    with pytest.raises(ValueError, match="正在编辑"):
        instance._import_model("result.step")
    assert not state.imports


def test_failed_import_rolls_back_partial_objects(panel):
    instance, original, _, _, state, _, _ = panel
    state.fail = True
    with pytest.raises(RuntimeError, match="partial import failed"):
        instance._import_model("result.step")
    assert original.objects == ["student_work"] and original.commits == 0


def test_run_started_without_document_creates_separate_result_document(panel):
    instance, _, other, docs, state, _, _ = panel
    instance.target_document = None
    instance.target_document_name = None
    instance._import_model("result.step")
    assert state.imports == [("result.step", "减速器")]
    assert docs["减速器"].commits == 1 and other.objects == ["student_work"]


def test_failed_process_never_consumes_previous_outputs(panel, monkeypatch):
    instance, _, _, _, state, _, module = panel
    messages = []
    instance.run_btn = SimpleNamespace(setEnabled=lambda value: None)
    instance.install_btn = SimpleNamespace(setVisible=lambda value: None)
    instance.result = SimpleNamespace(setPlainText=messages.append)
    instance.proc = SimpleNamespace(readAllStandardOutput=lambda: b"", readAllStandardError=lambda: b"solver failed")
    monkeypatch.setattr(module.runner, "read_outputs", lambda _: pytest.fail("不能读取旧产物"))
    instance.done(3)
    assert not state.imports and "solver failed" in messages[0]
