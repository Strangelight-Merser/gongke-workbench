"""Protocol fixtures for late native copy receipts, never native CAD validation."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from gongke_app.hosts import Hosts, _fingerprint
from gongke_app.project import MANIFEST, Project


class LostCopy:
    def __init__(self, tmp_path, monkeypatch, kind="solidworks", pair=False, importing=False):
        self.project = Project.create(str(tmp_path / "project"), teaching=False)
        self.hosts = Hosts(tmp_path / "hosts")
        self.kind, self.pair = kind, pair
        self.config = {"host_id": kind + "-1", "host": kind,
                       "session_id" if kind == "solidworks" else "instance_id": "native-session"}
        monkeypatch.setattr(self.hosts, "discover", lambda: [self.config])
        monkeypatch.setattr(self.hosts, "_request", self.transport)
        self.operation_id = str(uuid4())
        self.method = "drawing.import_dxf" if importing else "document.save_copy"
        self.params = {"operation_id": self.operation_id, "expected_revision": 7}
        if kind == "solidworks":
            self.params.update(session_id="native-session", document_path="C:\\original.slddrw" if pair else "C:\\original.sldprt",
                               configuration="Default", output_path="revision/drawing.slddrw" if pair else "revision/shaft.sldprt")
            if pair:
                self.params.update(output_part_path="revision/shaft.sldprt", expected_part_revision=3)
        else:
            self.params.update(document_id="original", target_path="revision/drawing.dwg")
            if importing:
                self.params["source_path"] = "drawing.dxf"
                (self.project.path / "drawing.dxf").write_bytes(b"original DXF protocol fixture")
        self.requests, self.reply, self.outputs = [], None, []

    def transport(self, config, method, params, **kwargs):
        self.requests.append((method, deepcopy(params), kwargs.get("request_id")))
        if method == self.method:
            record = self.project.copy_operation(self.operation_id)
            assert record["params"] == params and record["request_id"] == kwargs["request_id"]
            persisted = json.loads((self.project.path / MANIFEST).read_text())
            assert persisted["copy_operations"][self.operation_id] == record
            self.outputs = [Path(params[key]) for key in ("output_path", "output_part_path", "target_path") if key in params]
            for path in self.outputs:
                path.write_bytes(b"native file protocol fixture")
            if self.kind == "solidworks":
                result = {"status": "saved", "path": params["output_path"], "file_exists": True, "errors": 0}
                if self.pair:
                    result.update(references_verified=True, parameter_values_verified=True,
                                  source_state_preserved=True, reopen_verified=True,
                                  working_copies=[{"path": str(path), "verified": True} for path in self.outputs])
                self.reply = {"state": "finished", "operation_id": self.operation_id,
                              "session_id": "native-session", "fingerprint": _fingerprint(method, params)}
            else:
                result = {"outcome": "committed", "operation_id": self.operation_id, "path": params["target_path"],
                          "original_preserved": True, "disk_reopen_verified": True}
                if method == "drawing.import_dxf":
                    result["source_path"] = params["source_path"]
                self.reply = {"status": "completed", "outcome": "committed", "operation_id": self.operation_id}
            self.reply["response"] = {"id": kwargs["request_id"], "result": result}
            raise TimeoutError("native operation completed but its response was lost")
        if method in {"operation.get", "operation.status"}:
            return deepcopy(self.reply)
        if method == "documents.list":
            return {"documents": [{"document_id": "copy", "path": str(self.outputs[0])}]}
        return {"applied": True}

    def lose(self):
        with pytest.raises(TimeoutError, match="response was lost"):
            self.hosts.command(self.config["host_id"], self.method, self.params, self.project)
        assert self.project.manifest["working_copies"] == []

    def query(self):
        return self.hosts.command(self.config["host_id"], "operation.get" if self.kind == "solidworks" else "operation.status",
                                  {"operation_id": self.operation_id}, self.project)

    def edit(self):
        method = "parameter.change" if self.kind == "solidworks" else "drawing.edit_text"
        params = {"operation_id": str(uuid4()), "document_path": str(self.outputs[-1]), "document_id": "copy"}
        return self.hosts.command(self.config["host_id"], method, params, self.project)


@pytest.mark.parametrize("kind,pair,importing", [("solidworks", False, False), ("solidworks", True, False),
                                               ("autocad", False, False), ("autocad", False, True)])
def test_lost_response_recovers_after_application_reopen_without_replaying_write(tmp_path, monkeypatch, kind, pair, importing):
    flow = LostCopy(tmp_path, monkeypatch, kind, pair, importing)
    flow.lose()
    refused = flow.edit()
    assert refused["error"]["outcome"] == "not_applied" and "工作副本" in refused["error"]["message"]
    flow.project = Project.open(str(flow.project.path))
    expected_reply = deepcopy(flow.reply)
    assert flow.query() == expected_reply
    assert flow.edit()["applied"] is True
    copies = flow.project.view()["working_copies"]
    assert len(copies) == (2 if pair else 1)
    assert all(copy["operation_id"] == flow.operation_id and copy["host"] == kind for copy in copies)
    assert flow.project.copy_operation(flow.operation_id)["state"] == "registered"
    assert flow.query() == expected_reply
    assert len(flow.project.view()["working_copies"]) == len(copies)
    assert sum(method == flow.method for method, _, _ in flow.requests) == 1


@pytest.mark.parametrize("kind", ["solidworks", "autocad"])
@pytest.mark.parametrize("mismatch", ["operation_id", "request_id", "host_session", "original_params", "original_method", "target", "missing_file", "nested_error"])
def test_mismatched_receipt_never_registers_copy(tmp_path, monkeypatch, kind, mismatch):
    flow = LostCopy(tmp_path, monkeypatch, kind)
    flow.lose()
    if mismatch == "operation_id":
        flow.reply["operation_id"] = str(uuid4())
    elif mismatch == "request_id":
        flow.reply["response"]["id"] = "unrelated-native-request"
    elif mismatch == "host_session":
        flow.config["session_id" if kind == "solidworks" else "instance_id"] = "different-instance"
    elif mismatch == "original_params":
        flow.project.manifest["copy_operations"][flow.operation_id]["params"]["expected_revision"] = 999
    elif mismatch == "original_method":
        flow.project.manifest["copy_operations"][flow.operation_id]["method"] = "parameter.change"
    elif mismatch == "target":
        unrelated = flow.project.path / "original.dwg"
        unrelated.write_bytes(b"original")
        flow.reply["response"]["result"]["path"] = str(unrelated)
    elif mismatch == "missing_file":
        flow.outputs[0].unlink()
    else:
        flow.reply["response"] = {"id": flow.reply["response"]["id"], "error": {"outcome": "unknown"}}
    if mismatch == "nested_error":
        flow.query()
    else:
        with pytest.raises(ValueError):
            flow.query()
    assert flow.project.view()["working_copies"] == []
    assert flow.project.copy_operation(flow.operation_id)["state"] == "unregistered"


@pytest.mark.parametrize("field", ["references_verified", "parameter_values_verified", "source_state_preserved", "reopen_verified", "child_verified", "missing_part"])
def test_recovered_solidworks_pair_is_registered_atomically(tmp_path, monkeypatch, field):
    flow = LostCopy(tmp_path, monkeypatch, pair=True)
    flow.lose()
    result = flow.reply["response"]["result"]
    if field == "missing_part":
        flow.outputs[-1].unlink()
    elif field == "child_verified":
        result["working_copies"][-1]["verified"] = False
    else:
        result[field] = False
    with pytest.raises(ValueError):
        flow.query()
    assert flow.project.view()["working_copies"] == []
    assert Project.open(str(flow.project.path)).view()["working_copies"] == []


@pytest.mark.parametrize("kind", ["solidworks", "autocad"])
def test_unknown_or_non_successful_receipt_does_not_grant_write_permission(tmp_path, monkeypatch, kind):
    flow = LostCopy(tmp_path, monkeypatch, kind)
    flow.lose()
    finished = deepcopy(flow.reply)
    if kind == "solidworks":
        flow.reply["state"] = "started"
    else:
        flow.reply.update(status="unknown", outcome="unknown")
    flow.query()
    assert not flow.project.view()["working_copies"]
    flow.reply = finished
    flow.reply["response"]["result"].update(status="needs_review", outcome="unknown")
    flow.query()
    assert not flow.project.view()["working_copies"]


def test_native_fingerprint_mismatch_or_unrequested_success_cannot_register(tmp_path, monkeypatch):
    flow = LostCopy(tmp_path, monkeypatch)
    flow.lose()
    flow.reply["fingerprint"] = "another-command-and-parameter-fingerprint"
    with pytest.raises(ValueError, match="指纹"):
        flow.query()
    del flow.project.manifest["copy_operations"][flow.operation_id]
    flow.query()  # Read unrelated receipts, without interpreting them as permission.
    assert not flow.project.view()["working_copies"]


@pytest.mark.parametrize("kind", ["solidworks", "autocad"])
def test_original_edit_refusal_is_known_not_applied_and_does_not_block_copy(tmp_path, monkeypatch, kind):
    flow = LostCopy(tmp_path, monkeypatch, kind)
    original = flow.project.path / ("original.sldprt" if kind == "solidworks" else "original.dwg")
    original.write_bytes(b"original file")
    flow.outputs = [original]
    refusal = flow.edit()
    assert refusal["error"]["code"] == "command_not_submitted"
    assert refusal["error"]["outcome"] == "not_applied"
    assert not flow.project.manifest.get("copy_operations")
    assert all(method == "documents.list" for method, _, _ in flow.requests)
    flow.lose()
    flow.query()
    assert flow.edit()["applied"] is True
    assert original.read_bytes() == b"original file"


def test_solidworks_fingerprint_matches_real_newtonsoft_protocol_golden():
    # Obtained from Protocol.cs compiled against Newtonsoft.Json 13.0.3.
    params = {"operation_id": "11111111-1111-4111-8111-111111111111", "session_id": "s",
              "document_path": "C:\\工程\\源轴.sldprt", "configuration": "Default", "expected_revision": 7,
              "output_path": "C:\\工程\\副本.sldprt"}
    assert _fingerprint("document.save_copy", params) == "06ad485ffbe23e476a4a3e43e1af5890064e73a4fa81c29a9cecf5e6ee5127af"
