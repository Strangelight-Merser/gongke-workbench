"""AutoCAD 回执恢复使用真实 Project 登记，管道边界由协议测试覆盖。"""
import copy

import pytest

from gongke_app.hosts import Hosts, _fingerprint
from gongke_app.project import Project


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    project = Project.create(str(tmp_path / "project"))
    source = project.path / "source.dxf"
    source.write_text("synthetic source")
    hosts = Hosts(tmp_path / "hosts")
    old = {"host_id": "autocad-old", "host": "autocad", "instance_id": "old-session"}
    monkeypatch.setattr(hosts, "discover", lambda: [old])
    _, params, operation = hosts._prepare_command(old["host_id"], "drawing.import_dxf", {
        "operation_id": "copy-operation", "source_path": "source.dxf", "target_path": "copy.dwg",
    }, project)
    (project.path / "copy.dwg").write_bytes(b"synthetic receipt fixture, not native CAD validation")
    result = {"operation_id": "copy-operation", "session_id": "old-session", "method": "drawing.import_dxf",
              "fingerprint": operation["fingerprint"], "status": "completed", "outcome": "committed",
              "response": {"id": operation["request_id"], "result": {
                  "operation_id": "copy-operation", "source_path": params["source_path"], "path": params["target_path"],
                  "outcome": "committed", "original_preserved": True, "disk_reopen_verified": True,
              }}}
    new = {"host_id": "autocad-new", "host": "autocad", "instance_id": "new-session"}
    return hosts, Project.open(str(project.path)), new, result


def test_recover_copy_across_plugin_and_application_restart(recovery):
    hosts, project, config, result = recovery
    hosts._recover_copy(config, {"operation_id": "copy-operation"}, result, project)
    assert project.is_working_copy(project.path / "copy.dwg", "autocad")


@pytest.mark.parametrize("field,value", [
    ("session_id", "unrelated-session"), ("fingerprint", "different-params"),
    ("method", "document.save_copy"), ("operation_id", "different-operation"),
])
def test_recovery_checks_original_identity(recovery, field, value):
    hosts, project, config, result = recovery
    result[field] = value
    with pytest.raises(ValueError, match="不匹配"):
        hosts._recover_copy(config, {"operation_id": "copy-operation"}, result, project)
    assert not project.is_working_copy(project.path / "copy.dwg", "autocad")


def test_recovery_rejects_unrelated_response_and_target(recovery):
    hosts, project, config, result = recovery
    wrong = copy.deepcopy(result)
    wrong["response"]["id"] = "another-request"
    with pytest.raises(ValueError, match="ID 不匹配"):
        hosts._recover_copy(config, {"operation_id": "copy-operation"}, wrong, project)
    wrong = copy.deepcopy(result)
    wrong["response"]["result"]["path"] = str(project.path / "original.dwg")
    with pytest.raises(ValueError):
        hosts._recover_copy(config, {"operation_id": "copy-operation"}, wrong, project)
    assert not project.is_working_copy(project.path / "copy.dwg", "autocad")


@pytest.mark.parametrize("status,outcome", [("unknown", "unknown"), ("interrupted", "unknown"),
                                          ("interrupted_before_start", "unchanged"), ("running", "unknown")])
def test_unfinished_or_unknown_never_grants_copy_permission(recovery, status, outcome):
    hosts, project, config, result = recovery
    result.update(status=status, outcome=outcome)
    hosts._recover_copy(config, {"operation_id": "copy-operation"}, result, project)
    assert not project.is_working_copy(project.path / "copy.dwg", "autocad")


def test_fingerprint_matches_native_unicode_vector():
    assert _fingerprint("drawing.import_dxf", {
        "operation_id": "指纹-1", "source_path": "C:\\课程\\😀\u0085\u2028\u2029\x1f.dxf", "target_path": "C:\\副本.dwg",
    }) == "1759d0c6d11dbb879b8e78cd9509c73cecec422ac1979876257a5f9314e7d726"
