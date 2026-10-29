"""已提交的操作只读查询，不重放修改。CAD 原生几何另由 GUI 验收覆盖。"""
from tests.test_native_bridge_transactions import session
from gongke_core.shaft_review import preview


def test_query_committed_operation_does_not_apply_again(session):
    state, doc, snapshot = session
    source = state.read_engineering_object("unit-session", snapshot["entity_id"])
    candidate = state.remember_preview(source, preview(snapshot, "middle", .035))
    applied = state.apply_change("unit-session", candidate["change_id"], "once")
    commits = doc.commits
    receipt = state.get_operation_status("unit-session", "once")
    assert receipt["state"] == "committed"
    assert receipt["result"] == applied
    assert doc.commits == commits
    assert state.get_operation_status("unit-session", "missing")["state"] == "not_found"
