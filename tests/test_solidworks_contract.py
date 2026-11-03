"""SolidWorks 副本回执与应用授权契约；不调用 COM。"""
from copy import deepcopy
from uuid import uuid4

import pytest

from gongke_app.hosts import Hosts, _fingerprint


class Project:
    def __init__(self):
        self.registered = []
        self.operation = None

    def register_copy(self, path, host, result, **kwargs):
        self.registered.append(path)

    def copy_operation(self, operation_id):
        return self.operation


@pytest.fixture
def copy_receipt(tmp_path):
    target = str(tmp_path / "part.sldprt")
    operation_id = str(uuid4())
    params = {"output_path": target, "operation_id": operation_id, "session_id": "session"}
    operation = dict(operation_id=operation_id, host="solidworks", host_id="sw-1", host_session="session",
                     method="document.save_copy", params=params, request_id="request-1",
                     fingerprint=_fingerprint("document.save_copy", params))
    receipt = dict(status="saved", outcome="applied", path=target, file_exists=True, errors=0,
                   reopen_verified=True, parameter_values_verified=True, source_state_preserved=True)
    return operation, receipt


def test_verified_single_part_registers(copy_receipt):
    operation, receipt = copy_receipt
    project = Project()
    Hosts._register_copy_result(operation, receipt, project)
    assert project.registered == [operation["params"]["output_path"]]


@pytest.mark.parametrize("flag", ["reopen_verified", "parameter_values_verified", "source_state_preserved", "file_exists"])
@pytest.mark.parametrize("value", [False, None, "true"])
def test_incomplete_single_part_never_registers(copy_receipt, flag, value):
    operation, receipt = copy_receipt
    receipt[flag] = value
    project = Project()
    with pytest.raises(ValueError):
        Hosts._register_copy_result(operation, receipt, project)
    assert not project.registered


def test_different_output_never_registers(copy_receipt):
    operation, receipt = copy_receipt
    receipt["path"] += ".other.sldprt"
    with pytest.raises(ValueError):
        Hosts._register_copy_result(operation, receipt, Project())


@pytest.mark.parametrize("status", ["needs_review", "unknown", "not_applied"])
def test_non_success_never_registers(copy_receipt, status):
    operation, receipt = copy_receipt
    receipt["status"] = status
    project = Project()
    Hosts._register_copy_result(operation, receipt, project)
    assert not project.registered


def test_query_original_receipt_registers_without_replay(copy_receipt):
    operation, receipt = copy_receipt
    project = Project()
    project.operation = operation
    result = dict(state="finished", operation_id=operation["operation_id"], session_id="session",
                  fingerprint=operation["fingerprint"], response=dict(id="request-1", result=receipt))
    Hosts()._recover_copy(dict(host="solidworks", host_id="sw-1", session_id="session"),
                         {"operation_id": operation["operation_id"]}, result, project)
    assert project.registered == [receipt["path"]]
    altered = deepcopy(result)
    altered["response"]["result"]["reopen_verified"] = False
    project = Project()
    project.operation = operation
    with pytest.raises(ValueError):
        Hosts()._recover_copy(dict(host="solidworks", host_id="sw-1", session_id="session"),
                             {"operation_id": operation["operation_id"]}, altered, project)
    assert not project.registered


def test_session_is_supplied_for_ui_writes_without_hiding_stale_session(monkeypatch):
    hosts = Hosts()
    monkeypatch.setattr(hosts, "discover", lambda: [dict(host="solidworks", host_id="sw-1", session_id="live")])
    args = dict(operation_id=str(uuid4()), expected_revision=1, persistent_reference="reference")
    _, prepared, _ = hosts._prepare_command("sw-1", "selection.set", args, Project())
    assert prepared["session_id"] == "live"
    args["session_id"] = "stale"
    _, prepared, _ = hosts._prepare_command("sw-1", "selection.set", args, Project())
    assert prepared["session_id"] == "stale"
