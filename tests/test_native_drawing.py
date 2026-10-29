"""只读宿主替身回归；不充当真实 FreeCAD 或 TechDraw 运行证据。"""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from freecad.gongke import native_drawing
from gongke_core.drawing_review import review
from gongke_core.revision_mapping import map_capture


ROOT = Path(__file__).resolve().parents[1]


def forbidden(*args, **kwargs):
    raise AssertionError("只读采集触发了修改或额外宿主操作")


class ReadOnlyObject:
    """属性赋值和文档修改方法均立即失败；输入只由测试构建。"""

    def __init__(self, **values):
        self.__dict__.update(values)

    def __setattr__(self, name, value):
        raise AssertionError(f"只读对象不允许改写 {name}")

    def __getattr__(self, name):
        if name in {"recompute", "touch", "purgeTouched", "save", "saveAs", "saveCopy", "addObject", "removeObject",
                    "openTransaction", "commitTransaction", "abortTransaction", "undo", "redo", "addProperty",
                    "setDatum", "setExpression", "setEditorMode", "setEdit", "resetEdit"}:
            return forbidden
        raise AttributeError(name)


def replace(obj, **values):
    """仅用于设定测试输入；被测代码无法通过普通属性写入修改替身。"""
    obj.__dict__.update(values)


@pytest.fixture
def host(monkeypatch, tmp_path):
    def get_edge(index):
        if index != 1:
            raise RuntimeError("missing edge")
        return object()

    doc = ReadOnlyObject(Name="ExistingShaft", FileName=str(tmp_path / "shaft.FCStd"),
                         HasPendingTransaction=False, UndoMode=1)
    body = ReadOnlyObject(Name="Rotor", Label="已有轴", TypeId="PartDesign::Body", Document=doc,
                          GkEntityId="existing-entity", State=[])
    sketch = ReadOnlyObject(Name="Outline", Label="原剖面", TypeId="Sketcher::SketchObject", Document=doc, State=[])
    view = ReadOnlyObject(Name="Front", Label="前视图", TypeId="TechDraw::DrawViewPart", Document=doc,
                          State=[], Source=[body], isDerivedFrom=lambda kind: kind == "TechDraw::DrawViewPart",
                          getVisibleEdges=lambda: [object()],
                          getEdgeByIndex=get_edge)
    dim = ReadOnlyObject(Name="DiameterFront", Label="前视图直径", TypeId="TechDraw::DrawViewDimension", Document=doc,
                         Type="Diameter", State=[], References2D=[(view, ["Edge1"])], References3D=[],
                         getRawValue=lambda: 38.0, getText=lambda: "⌀38.00 mm", FormatSpec="⌀%.2w",
                         Arbitrary=False, ArbitraryTolerances=False, MeasureType="Projected", isValid=lambda: True,
                         OverTolerance=ReadOnlyObject(Value=0.0), UnderTolerance=ReadOnlyObject(Value=0.0))
    page = ReadOnlyObject(Name="Sheet", Label="原图纸", TypeId="TechDraw::DrawPage", Document=doc,
                          State=[], Views=[view, dim], KeepUpdated=True)
    objects = [body, sketch, page, view, dim]
    replace(doc, Objects=objects, getObject=lambda name: next((obj for obj in objects if obj.Name == name), None))
    gui_doc = ReadOnlyObject(Modified=True, getInEdit=lambda: None)
    opened = {doc.Name: doc}
    app = ReadOnlyObject(Version=lambda: ["1", "1", "4"], ActiveDocument=doc,
                         listDocuments=lambda: opened, addDocumentObserver=lambda observer: None,
                         newDocument=forbidden, openDocument=forbidden, closeDocument=forbidden, setActiveDocument=forbidden)
    selection = ReadOnlyObject(getSelection=lambda: [dim], clearSelection=forbidden,
                               addSelection=forbidden, removeSelection=forbidden)
    gui = ReadOnlyObject(getDocument=lambda name: gui_doc, Selection=selection,
                         activateWorkbench=forbidden, activeDocument=forbidden)
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    monkeypatch.setitem(sys.modules, "PySide", SimpleNamespace(QtCore=SimpleNamespace()))
    signature = [{"name": "middle_radius", "type": "DistanceY", "driving": True}]
    description = {"body_name": "Rotor", "label": "已有轴", "sketch": "Outline", "revolution": "Turned",
                   "segments": [{"length_m": .05, "diameter_m": .03, "radius_constraint": "left_radius"},
                                {"length_m": .1, "diameter_m": .038, "radius_constraint": "middle_radius"},
                                {"length_m": .05, "diameter_m": .03, "radius_constraint": "right_radius"}]}
    monkeypatch.setattr(native_drawing.native_shaft, "_describe_simple_parts", lambda obj: deepcopy(description))
    monkeypatch.setattr(native_drawing.native_shaft, "_constraint_signature", lambda obj: deepcopy(signature))
    case = {"schema_version": 1, "case_id": "readonly-host-test",
            "document": {"path": doc.FileName, "body": "Rotor", "sketch": "Outline", "revolution": "Turned",
                         "entity_id": "existing-entity", "structure_signature": signature},
            "target": {"radius_constraint": "middle_radius", "segment_index": 1}, "pages": ["Sheet"],
            "annotations": [{"page": "Sheet", "view": "Front", "dimension": "DiameterFront", "target": "diameter"}]}
    return SimpleNamespace(doc=doc, body=body, sketch=sketch, page=page, view=view, dim=dim,
                           gui_doc=gui_doc, app=app, gui=gui, opened=opened, case=case)


def capture(host):
    return native_drawing.capture(host.doc, "Rotor", ["Sheet"], "session-test")


def test_capture_keeps_existing_unsaved_document_and_native_properties(host):
    before = [(obj, dict(obj.__dict__)) for obj in host.doc.Objects]
    native_lists = (tuple(host.page.Views), tuple(host.view.Source), tuple(host.dim.State),
                    tuple((obj, tuple(subs)) for obj, subs in host.dim.References2D))
    result = capture(host)
    assert result["document"]["modified"] is True
    assert result["document"]["pending_transaction"] is False
    assert result["document"]["needs_rebuild"] is False
    dimension = result["drawing"]["pages"][0]["views"][0]["dimensions"][0]
    assert dimension["measurement_m"] == .038 and dimension["raw_value"] == 38.0
    assert dimension["reference_status"] == "valid"
    assert all(obj.__dict__ == values for obj, values in before)
    assert native_lists == (tuple(host.page.Views), tuple(host.view.Source), tuple(host.dim.State),
                            tuple((obj, tuple(subs)) for obj, subs in host.dim.References2D))
    assert host.gui.Selection.getSelection() == [host.dim]
    assert review(result, map_capture(host.case, result))["status"] == "pass"


def test_unloaded_projection_never_reads_zero_cached_measurement(host):
    replace(host.view, getVisibleEdges=lambda: [])
    replace(host.dim, getRawValue=forbidden, getText=forbidden)
    result = native_drawing._dimension(host.dim)
    assert result["reference_status"] == "unknown"
    assert result["raw_value"] is None and result["measurement_m"] is None and result["display_text"] is None
    assert result["issues"]


@pytest.mark.parametrize("unknown", ["unsupported", "unloaded", "non_edge"])
@pytest.mark.parametrize("dangling_first", [True, False])
def test_dangling_cannot_be_overwritten_by_unknown_reference(host, unknown, dangling_first):
    other = ReadOnlyObject(Name="OtherView", Document=host.doc,
                           isDerivedFrom=lambda kind: unknown != "unsupported",
                           getVisibleEdges=lambda: [] if unknown == "unloaded" else [object()],
                           getEdgeByIndex=lambda index: object())
    refs = [(host.view, ["Edge999"]), (other, ["Vertex1" if unknown == "non_edge" else "Edge1"])]
    if not dangling_first:
        refs.reverse()
    replace(host.dim, References2D=refs, getRawValue=forbidden, getText=forbidden)
    result = native_drawing._dimension(host.dim)
    assert result["reference_status"] == "dangling"
    assert result["measurement_m"] is None


@pytest.mark.parametrize("missing", ["view", "subelement"])
def test_missing_reference_does_not_read_a_cached_value(host, missing):
    refs = [(None, ["Edge1"])] if missing == "view" else [(host.view, [])]
    replace(host.dim, References2D=refs, getRawValue=forbidden, getText=forbidden)
    result = native_drawing._dimension(host.dim)
    assert result["reference_status"] == "dangling"
    assert result["raw_value"] is None and result["display_text"] is None


@pytest.mark.parametrize("where", ["page", "view", "dim", "body"])
def test_touched_state_is_reported_and_stale_measurement_never_passes(host, where):
    replace(getattr(host, where), State=["Touched"])
    replace(host.dim, getRawValue=lambda: 40.0)
    result = capture(host)
    assert result["document"]["needs_rebuild"] is True
    checked = review(result, map_capture(host.case, result))
    assert checked["status"] == "unknown"
    assert "measurement_mismatch" not in {issue["code"] for issue in checked["issues"]}


def test_pending_transaction_is_observed_without_commit_or_stale_comparison(host):
    replace(host.doc, HasPendingTransaction=True)
    replace(host.dim, getRawValue=lambda: 40.0)
    result = capture(host)
    assert result["document"]["pending_transaction"] is True
    assert host.doc.HasPendingTransaction is True
    checked = review(result, map_capture(host.case, result))
    assert checked["status"] == "unknown"
    assert "measurement_mismatch" not in {issue["code"] for issue in checked["issues"]}


def test_unknown_page_objects_remain_explicit(host):
    note = ReadOnlyObject(Name="ManualNote", TypeId="TechDraw::DrawViewAnnotation", Document=host.doc, State=[])
    replace(host.page, Views=[host.view, host.dim, note])
    result = capture(host)
    assert result["drawing"]["coverage"]["status"] == "partial"
    assert result["drawing"]["pages"][0]["unknown_objects"] == [{"name": "ManualNote", "type": "TechDraw::DrawViewAnnotation"}]
    assert review(result, map_capture(host.case, result))["status"] == "unknown"


@pytest.mark.parametrize("pages", [[], ["Sheet", "Sheet"], ["Missing"], "Sheet", [None]])
def test_page_scope_must_be_explicit_existing_and_unique(host, pages):
    with pytest.raises(ValueError):
        native_drawing.capture(host.doc, "Rotor", pages, "session-test")


def bridge_state(host, tmp_path):
    spec = importlib.util.spec_from_file_location("bridge_drawing_readonly_unit", ROOT / "freecad/gongke/bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    return bridge.DocumentState(tmp_path / "results")


@pytest.mark.parametrize("pending", [False, True])
def test_bridge_reads_explicit_document_and_reuses_session_without_writable_context(host, tmp_path, monkeypatch, pending):
    replace(host.doc, HasPendingTransaction=pending)
    state = bridge_state(host, tmp_path)
    other = ReadOnlyObject(Name="OtherActiveDocument", FileName=str(tmp_path / "other.FCStd"), getObject=forbidden)
    host.opened[other.Name] = other
    replace(host.app, ActiveDocument=other)
    monkeypatch.setattr(native_drawing.native_shaft, "inspect", forbidden)
    monkeypatch.setattr(native_drawing.native_shaft, "describe_unbound", forbidden)
    result = state.read_revision_context(host.doc.FileName, "Rotor", ["Sheet"])
    again = state.read_revision_context(host.doc.FileName, "Rotor", ["Sheet"])
    assert result["session_id"] == again["session_id"]
    assert result["document"]["path"] == host.doc.FileName
    assert result["document"]["pending_transaction"] is pending
    assert host.app.ActiveDocument is other
    assert len(state.sessions) == 1
    assert host.gui.Selection.getSelection() == [host.dim]


@pytest.mark.parametrize("kind", ["relative", "not_open", "ambiguous"])
def test_bridge_never_opens_or_guesses_requested_document(host, tmp_path, kind):
    state = bridge_state(host, tmp_path)
    path = host.doc.FileName
    if kind == "relative":
        path = "shaft.FCStd"
    elif kind == "not_open":
        path = str(tmp_path / "other" / "shaft.FCStd")
    else:
        host.opened["SecondDocument"] = ReadOnlyObject(Name="SecondDocument", FileName=path)
    with pytest.raises(ValueError):
        state.read_revision_context(path, "Rotor", ["Sheet"])
