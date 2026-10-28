"""命令桥事务顺序的单元测试；文档替身不代表真实 FreeCAD 几何或 Undo 验收。"""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from threading import Lock
from uuid import uuid4

import pytest

from gongke_core.shaft_review import preview, review
from gongke_core import shaft_jobs


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("method", ["get_job", "cancel_job"])
@pytest.mark.parametrize("stored_version", [None, "shaft-beam-obsolete", shaft_jobs.METHOD_VERSION])
def test_beam_result_requires_current_method_even_when_geometry_matches(session, tmp_path, method, stored_version):
    """读取真实持久化任务；CAD 替身只提供当前几何，不代表求解或界面验收。"""
    state, _, snapshot = session
    current = state.read_engineering_object("unit-session", snapshot["entity_id"])
    job_id = str(uuid4())
    directory = tmp_path / "runs" / job_id
    directory.mkdir(parents=True)
    record = {"job_id": job_id, "status": "succeeded", "result": {"conclusion": "pass"},
              "source_context": {"entity_id": snapshot["entity_id"], "session_id": "closed-session",
                                 "revision": 99, "content_hash": current["content_hash"]}}
    if stored_version is not None:
        record["method_version"] = stored_version
    status = directory / "status.json"
    status.write_text(json.dumps(record), encoding="utf-8")
    original = status.read_bytes()

    bridge_type = state.apply_change.__globals__["Bridge"]
    bridge = bridge_type.__new__(bridge_type)
    bridge.jobs = shaft_jobs.JobManager(directory.parent)
    bridge.jobs_lock = Lock()

    def find_current(name, **params):
        assert name == "find_engineering_object"
        assert params == {"entity_id": snapshot["entity_id"]}
        return current

    bridge.main_call = find_current
    result = bridge.dispatch(method, {"job_id": job_id})
    expected = "current" if stored_version == shaft_jobs.METHOD_VERSION else "stale"
    assert result["applicability"] == expected
    assert result["status"] == "succeeded" and result["result"] == record["result"]
    assert status.read_bytes() == original  # 派生适用性不能改写历史求解结果。


@pytest.fixture
def session(tmp_path, monkeypatch):
    snapshot = json.loads((ROOT / "gongke_core/resources/native_shaft.json").read_text(encoding="utf-8"))

    class Document:
        Name = "TransactionUnitTest"
        FileName = ""
        HasPendingTransaction = False
        UndoMode = 1

        def __init__(self):
            self.Objects = []
            self.UndoNames = []
            self.commits = 0
            self.history = []

        def recompute(self):
            pass

        def openTransaction(self, name):
            self.HasPendingTransaction = True
            self.pending = (name, deepcopy(snapshot))

        def commitTransaction(self):
            self.HasPendingTransaction = False
            self.commits += 1
            self.UndoNames.insert(0, self.pending[0])
            self.history.append(self.pending[1])

        def abortTransaction(self):
            self.HasPendingTransaction = False
            snapshot.clear()
            snapshot.update(self.pending[1])

        def undo(self):
            snapshot.clear()
            snapshot.update(self.history.pop())
            self.UndoNames.pop(0)
            state.slotUndoDocument(self)

    doc = Document()
    monkeypatch.setitem(sys.modules, "FreeCAD", SimpleNamespace(
        addDocumentObserver=lambda observer: None,
        listDocuments=lambda: {doc.Name: doc},
    ))
    monkeypatch.setitem(sys.modules, "FreeCADGui", SimpleNamespace(
        getDocument=lambda name: SimpleNamespace(getInEdit=lambda: False),
    ))
    monkeypatch.setitem(sys.modules, "PySide", SimpleNamespace(QtCore=SimpleNamespace()))
    spec = importlib.util.spec_from_file_location("bridge_transaction_unit", ROOT / "freecad/gongke/bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    body = SimpleNamespace(GkEntityId=snapshot["entity_id"], State=[], Document=doc)
    doc.Objects = [body]
    state = bridge.DocumentState(tmp_path / "results")
    state.sessions["unit-session"] = {"doc": doc, "revision": 0}
    monkeypatch.setattr(bridge.native_shaft, "inspect", lambda body: {"supported": True})
    monkeypatch.setattr(bridge.native_shaft, "read_snapshot", lambda body: deepcopy(snapshot))

    def set_diameter(body, segment_id, diameter_m):
        next(item for item in snapshot["segments"] if item["segment_id"] == segment_id)["diameter_m"] = diameter_m
        state.slotChangedObject(body, "Constraints")

    monkeypatch.setattr(bridge.native_shaft, "set_diameter", set_diameter)
    return state, doc, snapshot


@pytest.mark.parametrize("cache_available", [True, False])
def test_committed_change_keeps_receipt_and_undo_when_cache_fails(session, cache_available):
    state, doc, snapshot = session
    if not cache_available:
        # 用确定的真实文件系统错误复现缓存不可写，无需依赖进程权限。
        state.results_dir.write_text("results 路径已被文件占用", encoding="utf-8")
    sid, eid = "unit-session", snapshot["entity_id"]
    context = state.read_engineering_object(sid, eid)
    candidate = state.remember_preview(context, preview(snapshot, "middle", 0.036))

    applied = state.apply_change(sid, candidate["change_id"], "same-operation")
    assert applied["applied"] is True
    assert applied["analysis_persisted"] is cache_available
    assert ("persistence_error" in applied) is not cache_available
    assert doc.commits == 1
    assert snapshot["segments"][1]["diameter_m"] == 0.036
    assert (sid, "same-operation") in state.operations
    current = state.read_engineering_object(sid, eid)
    assert current["analysis"]["applicability"] == ("current" if cache_available else "missing")

    replay = state.apply_change(sid, candidate["change_id"], "same-operation")
    assert replay["receipt_only"] is True
    assert replay["analysis_persisted"] is cache_available
    assert doc.commits == 1
    assert state.undo_last_agent_change(sid, "same-operation")["undone"] is True
    assert snapshot["segments"][1]["diameter_m"] == 0.04
    # 历史收据也不能在 Undo 后重新执行原修改。
    assert state.apply_change(sid, candidate["change_id"], "same-operation")["receipt_only"] is True
    assert snapshot["segments"][1]["diameter_m"] == 0.04
    assert doc.commits == 1


def test_review_returns_calculation_even_when_cache_cannot_be_saved(session):
    state, doc, snapshot = session
    state.results_dir.write_text("results 路径已被文件占用", encoding="utf-8")
    context = state.read_engineering_object("unit-session", snapshot["entity_id"])
    result = review(snapshot)

    returned = state.remember_review(context, result)
    assert returned["applicability"] == "current"
    assert returned["result"] == result
    assert returned["analysis_persisted"] is False
    assert returned["persistence_error"]
    assert not state.operations
    assert doc.commits == 0
    assert snapshot["segments"][1]["diameter_m"] == 0.04


@pytest.mark.parametrize("stored_version", [None, -1])
def test_same_geometry_cannot_reuse_review_from_an_old_method(session, stored_version):
    state, _, snapshot = session
    context = state.read_engineering_object("unit-session", snapshot["entity_id"])
    state.remember_review(context, review(snapshot))
    target = state._result_path(snapshot["entity_id"])
    record = json.loads(target.read_text())
    if stored_version is None:
        del record["method_version"]
    else:
        record["method_version"] = stored_version
    target.write_text(json.dumps(record))
    read = state.read_engineering_object("unit-session", snapshot["entity_id"])
    assert read["content_hash"] == context["content_hash"]
    assert read["analysis"]["applicability"] == "stale"


def test_readback_mismatch_aborts_the_entire_edit(session, monkeypatch):
    state, doc, snapshot = session
    context = state.read_engineering_object("unit-session", snapshot["entity_id"])
    candidate = state.remember_preview(context, preview(snapshot, "middle", 0.036))
    native = state.apply_change.__globals__["native_shaft"]

    def wrong_dimension(body, segment_id, diameter_m):
        snapshot["segments"][1]["diameter_m"] = 0.035

    monkeypatch.setattr(native, "set_diameter", wrong_dimension)
    with pytest.raises(ValueError, match="实际修改与候选不一致"):
        state.apply_change("unit-session", candidate["change_id"], "mismatch")
    assert snapshot["segments"][1]["diameter_m"] == 0.04
    assert doc.commits == 0 and not state.operations


def test_cache_read_failure_after_commit_cannot_lose_receipt_or_undo(session, monkeypatch):
    state, doc, snapshot = session
    sid, eid = "unit-session", snapshot["entity_id"]
    context = state.read_engineering_object(sid, eid)
    state.remember_review(context, review(snapshot))
    candidate = state.remember_preview(context, preview(snapshot, "middle", .036))
    target = state._result_path(eid)
    original = Path.read_text

    def unreadable_after_commit(path, *args, **kwargs):
        if path == target and doc.commits:
            raise PermissionError("校核缓存无法读取")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable_after_commit)
    result = state.apply_change(sid, candidate["change_id"], "unreadable-cache")
    assert result["applied"] and (sid, "unreadable-cache") in state.operations
    assert doc.commits == 1 and snapshot["segments"][1]["diameter_m"] == .036
    assert state.apply_change(sid, candidate["change_id"], "unreadable-cache")["receipt_only"]
    current = state.read_engineering_object(sid, eid)
    assert current["supported"] and current["analysis"]["applicability"] == "missing"
    assert "无法读取" in current["analysis"]["read_error"]
    assert state.undo_last_agent_change(sid, "unreadable-cache")["undone"]
    assert snapshot["segments"][1]["diameter_m"] == .04


def test_disabled_undo_refuses_writes_but_allows_reading(session):
    state, doc, snapshot = session
    context = state.read_engineering_object("unit-session", snapshot["entity_id"])
    candidate = state.remember_preview(context, preview(snapshot, "middle", .036))
    doc.UndoMode = 0
    assert state.read_engineering_object("unit-session", snapshot["entity_id"])["supported"]
    with pytest.raises(ValueError, match="未启用撤销"):
        state.apply_change("unit-session", candidate["change_id"], "undo-disabled")
    assert not state.operations and doc.commits == 0
    assert snapshot["segments"][1]["diameter_m"] == .04
