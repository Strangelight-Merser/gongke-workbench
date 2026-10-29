import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gongke_app.commands import Commands
from gongke_app.project import Project
from gongke_app.service import Application
from gongke_app.tasks import Tasks


def finished(app, task_id):
    for _ in range(200):
        record = app.tasks.get(task_id)
        if record["status"] not in {"queued", "running"}:
            return record
        time.sleep(0.02)
    raise AssertionError("task did not finish")


@pytest.fixture
def app(tmp_path):
    service = Application(tmp_path / "state")
    service.dispatch("project.create", {"path": str(tmp_path / "project"), "teaching": True})
    yield service
    service.close()


def test_project_real_calculation_export_reopen(app):
    summary = app.dispatch("design.calculate", {})
    assert summary["teaching"] is True
    assert summary["motor"]["power_kw"] > 0
    assert "failed" in summary and "checks" in summary
    job = app.dispatch("design.generate", {"name": "first", "drawings": False, "report_docx": False})
    result = finished(app, job["task_id"])
    assert result["status"] == "complete"
    assert result["result"]["artifacts"]["markdown"]["status"] == "complete"
    path = app.project.path
    assert (path / "revisions/first/report.md").is_file()
    reopened = app.dispatch("project.open", {"path": str(path)})
    assert reopened["results"][0]["path"] == "revisions/first"
    assert any(item["path"] == "revisions/first/summary.json" for item in reopened["files"])
    assert "content" in app.dispatch("project.read_file", {"path": "revisions/first/report.md"})


def test_project_paths_and_originals_preserved(app, tmp_path):
    original = app.project.path / "original.FCStd"
    original.write_bytes(b"original native model")
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    (app.project.path / "escape.txt").symlink_to(outside)
    for path in ("../outside.txt", str(outside), "escape.txt"):
        with pytest.raises(ValueError):
            app.dispatch("project.read_file", {"path": path})
    with pytest.raises(ValueError, match="目标已存在"):
        app.dispatch("freecad.save", {"session_id": "test", "path": "original.FCStd"})
    assert original.read_bytes() == b"original native model"
    with pytest.raises(ValueError):
        app.project.output("../../oops")
    with pytest.raises(FileExistsError):
        app.dispatch("project.create", {"path": str(app.project.path)})


def test_missing_model_and_non_teaching_conditions_are_explicit(app, tmp_path):
    with pytest.raises(ValueError, match="未连接模型"):
        app.dispatch("agent.run", {"message": "计算轴"})
    app.dispatch("project.create", {"path": str(tmp_path / "empty"), "teaching": False})
    with pytest.raises(ValueError, match="尚无计算条件"):
        app.dispatch("design.calculate", {})
    with pytest.raises(ValueError, match="未知参数"):
        app.dispatch("design.calculate", {"shell": "anything"})


def test_cancel_does_not_claim_running_operation_was_interrupted(tmp_path):
    tasks = Tasks(tmp_path, lambda event: None)
    started, release = threading.Event(), threading.Event()
    def operation(ctx):
        started.set()
        release.wait(3)
        ctx.receipt("write", {}, {"saved": True})
        return {"saved": True, "exports_complete": True}
    job = tasks.start("generation", "/project", operation)
    assert started.wait(1)
    assert tasks.cancel(job["task_id"])["cancel_requested"] is True
    release.set()
    tasks.close()
    recovered = Tasks(tmp_path, lambda event: None)
    record = recovered.get(job["task_id"])
    assert record["status"] == "complete" and record["result"]["saved"] is True
    assert record["receipts"][0]["result"]["saved"] is True
    assert record["cancel_requested"] is True
    recovered.close()


def test_restart_marks_unfinished_tasks_interrupted(tmp_path):
    tasks = Tasks(tmp_path, lambda event: None)
    record = {"task_id": "unfinished", "status": "running", "project": "/a"}
    tasks.db.execute("INSERT INTO tasks VALUES (?,?)", ("unfinished", json.dumps(record)))
    tasks.db.commit()
    tasks.close()
    reopened = Tasks(tmp_path, lambda event: None)
    assert reopened.get("unfinished")["status"] == "interrupted"
    reopened.close()


class ProviderFixture:
    """Local HTTP protocol fixture; never presented as a live model account."""
    def __init__(self, replies):
        self.requests = []
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                assert self.path == "/v1/chat/completions"
                assert self.headers["Authorization"] == "Bearer fixture-secret"
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append(payload)
                chunks = replies[len(fixture.requests) - 1]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for delta, finish in chunks:
                    value = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    self.wfile.write(("data: " + json.dumps(value) + "\n\n").encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def configure(self, app):
        return app.dispatch("agent.configure", {"base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
                                                "model": "protocol-fixture", "api_key": "fixture-secret"})

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def tool_reply(name, arguments, call_id="call_1"):
    # Fragmented arguments exercise actual SSE reconstruction.
    text = json.dumps(arguments)
    return [({"tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": text[:1]}}]}, None),
            ({"tool_calls": [{"index": 0, "function": {"arguments": text[1:]}}]}, "tool_calls")]


def test_agent_consumes_real_calculation_then_generates_files(app):
    fixture = ProviderFixture([
        tool_reply("design_calculate", {}),
        tool_reply("design_generate", {"name": "agent-run", "drawings": False, "report_docx": False}, "call_2"),
        [({"content": "已完成教学计算和文件生成。"}, "stop")],
    ])
    try:
        configured = fixture.configure(app)
        assert "api_key" not in configured
        job = app.dispatch("agent.run", {"message": "计算当前教学示例并生成文件", "allow_writes": True})
        record = finished(app, job["task_id"])
        assert record["status"] == "complete", record
        assert record["result"]["tool_calls"] == 2
        assert (app.project.path / "revisions/agent-run/report.md").is_file()
        calculation = json.loads(fixture.requests[1]["messages"][-1]["content"])
        assert calculation["motor"]["power_kw"] > 0
        assert calculation["teaching"] is True
        generation = json.loads(fixture.requests[2]["messages"][-1]["content"])
        assert generation["exports_complete"] is True
        assert "fixture-secret" not in json.dumps(record)
        assert "fixture-secret" not in (app.tasks.db.execute("SELECT record FROM tasks").fetchone()[0])
    finally:
        fixture.close()


def test_agent_unauthorized_native_write_returns_error_without_execution(app, monkeypatch):
    called = []
    monkeypatch.setattr(app.commands, "call", lambda *args: called.append(args))
    fixture = ProviderFixture([tool_reply("freecad_apply", {"session_id": "s", "change_id": "c", "operation_id": "o"}),
                               [({"content": "缺少本次修改授权。"}, "stop")]])
    try:
        fixture.configure(app)
        job = app.dispatch("agent.run", {"message": "查看工程"})
        record = finished(app, job["task_id"])
        assert record["status"] == "complete"
        assert not called
        assert "未授权" in record["receipts"][0]["result"]["error"]
        names = {tool["function"]["name"] for tool in fixture.requests[0]["tools"]}
        assert "freecad_apply" not in names
    finally:
        fixture.close()


def test_stdio_process_contains_only_json_and_runs_actual_core(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requests = [
        {"id": 1, "method": "system.status"},
        {"id": 2, "method": "project.create", "params": {"path": str(tmp_path / "project")}},
        {"id": 3, "method": "design.calculate"},
    ]
    process = subprocess.run([sys.executable, "-m", "gongke_app.service", "--state-dir", str(tmp_path / "state")],
                             cwd=root, input="".join(json.dumps(row) + "\n" for row in requests),
                             capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert [row["id"] for row in responses] == [1, 2, 3]
    assert responses[-1]["result"]["motor"]["power_kw"] > 0


def test_stdio_utf8_is_independent_of_host_codepage(tmp_path):
    root = Path(__file__).resolve().parents[1]
    request = {"id": 1, "method": "project.create", "params": {"path": str(tmp_path / "中文工程"), "name": "机械课程"}}
    process = subprocess.run([sys.executable, "-m", "gongke_app.service", "--state-dir", str(tmp_path / "state")],
                             cwd=root, env={**os.environ, "PYTHONIOENCODING": "ascii"},
                             input=(json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"),
                             capture_output=True, timeout=15)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.decode("utf-8"))["result"]["name"] == "机械课程"


def test_native_commands_use_existing_bridge_and_copy_path(app, monkeypatch):
    from gongke_core import native_client
    calls = []
    def native(method, **params):
        calls.append((method, params))
        if method == "save_project":
            Path(params["path"]).write_bytes(b"native file")
            return {"saved": True, "path": params["path"]}
        return {"session_id": "s"}
    monkeypatch.setattr(native_client, "call", native)
    app.dispatch("freecad.context", {})
    app.dispatch("freecad.save", {"session_id": "s", "path": "work/shaft.FCStd"})
    assert calls[0] == ("get_project_context", {})
    assert calls[1][0] == "save_project"
    assert calls[1][1]["path"] == str(app.project.path / "work/shaft.FCStd")
    assert app.project.is_working_copy(calls[1][1]["path"], "freecad")


def test_native_write_requires_actual_working_copy_context(app, monkeypatch):
    from gongke_core import native_client
    calls = []
    context = {"session_id": "s", "path": "/external/original.FCStd"}
    def native(method, **params):
        calls.append(method)
        return context if method == "get_project_context" else {"applied": True}
    monkeypatch.setattr(native_client, "call", native)
    with pytest.raises(ValueError, match="新工作副本"):
        app.dispatch("freecad.apply", {"session_id": "s", "change_id": "c", "operation_id": "o"})
    assert calls == ["get_project_context"]
    target = app.project.path / "revision.FCStd"
    target.write_bytes(b"native working file")
    context["path"] = str(target)
    with pytest.raises(ValueError, match="新工作副本"):
        app.dispatch("freecad.apply", {"session_id": "s", "change_id": "c", "operation_id": "o"})
    app.project.register_copy(str(target), "freecad", {"saved": True, "path": str(target)})
    assert app.dispatch("freecad.apply", {"session_id": "s", "change_id": "c", "operation_id": "o"})["applied"]


def test_no_project_required_for_freecad_read_and_teaching_label(app, monkeypatch):
    from gongke_core import native_client
    project_path = app.project.path
    monkeypatch.setattr(native_client, "call", lambda *args, **kwargs: {"session_id": "s"})
    app.project = None
    assert app.dispatch("freecad.context", {}) == {"session_id": "s"}
    assert app.dispatch("freecad.scene", {}) == {"session_id": "s"}
    assert app.dispatch("freecad.select", {"session_id": "s", "object_name": "Body", "expected_revision": 1}) == {"session_id": "s"}
    assert app.dispatch("freecad.operation", {"session_id": "s", "operation_id": "o"}) == {"session_id": "s"}
    app.dispatch("project.open", {"path": str(project_path)})
    updated = app.dispatch("project.set_task", {"task": app.project.manifest["task"], "teaching": False})
    assert updated["teaching"] is False
    updated = app.dispatch("project.set_task", {"task": app.project.manifest["task"], "teaching": True})
    assert updated["teaching"] is True


def test_host_import_separates_source_and_target_and_does_not_overwrite(app, monkeypatch):
    discovery = {"host_id": "autocad-1", "host": "autocad", "capabilities": []}
    monkeypatch.setattr(app.hosts, "discover", lambda: [discovery])
    calls = []
    def request(config, method, params):
        calls.append(params)
        Path(params["target_path"]).write_text("native DWG fixture")
        return {"outcome": "committed", "path": params["target_path"]}
    monkeypatch.setattr(app.hosts, "_request", request)
    source = app.project.path / "source.dxf"
    source.write_text("source")
    params = {"host_id": "autocad-1", "method": "drawing.import_dxf", "params": {
        "source_path": "source.dxf", "target_path": "revisions/copy.dwg", "operation_id": "o"}}
    app.dispatch("host.command", params)
    assert calls[0]["source_path"] == str(source)
    assert calls[0]["target_path"] == str(app.project.path / "revisions/copy.dwg")
    assert app.project.is_working_copy(calls[0]["target_path"], "autocad")
    (app.project.path / "revisions/copy.dwg").write_text("existing")
    with pytest.raises(ValueError, match="已存在"):
        app.dispatch("host.command", params)
    with pytest.raises(ValueError, match="未获应用层支持"):
        app.dispatch("host.command", {**params, "method": "document.save"})


def test_host_probe_error_does_not_claim_connection(app, monkeypatch):
    from gongke_core import native_client
    monkeypatch.setattr(native_client, "call", lambda *args, **kwargs: {"session_id": None})
    monkeypatch.setattr(app.hosts, "discover", lambda: [{"host_id": "solidworks-1", "host": "solidworks", "token": "secret"}])
    monkeypatch.setattr(app.hosts, "_request", lambda *args, **kwargs: {"error": {"code": "auth_failed"}})
    result = app.dispatch("hosts.list", {})
    assert result["hosts"][0]["host"] == "freecad" and result["hosts"][0]["connected"] is True
    assert result["hosts"][1]["connected"] is False
    assert "secret" not in json.dumps(result)


def test_copy_registration_requires_matching_receipt_and_real_file(app):
    target = app.project.path / "copy.FCStd"
    with pytest.raises(ValueError, match="实际文件"):
        app.project.register_copy(target, "freecad", {"path": str(target)})
    target.write_bytes(b"actual copy")
    with pytest.raises(ValueError, match="不一致"):
        app.project.register_copy(target, "freecad", {"path": str(app.project.path / "other.FCStd")})
    assert not app.project.is_working_copy(target, "freecad")
    app.project.register_copy(target, "freecad", {"path": str(target), "saved": True})
    reopened = Project.open(str(app.project.path))
    assert reopened.is_working_copy(target, "freecad")
    assert not reopened.is_working_copy(target, "solidworks")


def test_solidworks_pair_registers_only_complete_verified_receipt(app, monkeypatch):
    monkeypatch.setattr(app.hosts, "discover", lambda: [{"host_id": "sw-1", "host": "solidworks", "capabilities": []}])
    verified = False
    def save(config, method, params):
        for key in ("output_path", "output_part_path"):
            Path(params[key]).write_bytes(b"protocol file fixture")
        return {"status": "saved", "path": params["output_path"], "references_verified": verified,
                "working_copies": [{"path": params[key], "verified": True} for key in ("output_path", "output_part_path")]}
    monkeypatch.setattr(app.hosts, "_request", save)
    def params(folder):
        return {"host_id": "sw-1", "method": "document.save_copy", "params": {"operation_id": folder,
                "output_path": folder + "/drawing.slddrw", "output_part_path": folder + "/shaft.sldprt"}}
    with pytest.raises(ValueError, match="未完整验证"):
        app.dispatch("host.command", params("unverified"))
    assert app.project.manifest["working_copies"] == []
    verified = True
    app.dispatch("host.command", params("verified"))
    assert app.project.is_working_copy(app.project.path / "verified/drawing.slddrw", "solidworks")
    assert app.project.is_working_copy(app.project.path / "verified/shaft.sldprt", "solidworks")


def two_calls():
    return [({"tool_calls": [
        {"index": 0, "id": "one", "type": "function", "function": {"name": "freecad_apply", "arguments": "{}"}},
        {"index": 1, "id": "two", "type": "function", "function": {"name": "freecad_apply", "arguments": "{}"}},
    ]}, "tool_calls")]


def test_unknown_native_outcome_stops_further_agent_actions(app, monkeypatch):
    calls = []
    def execute(*args):
        calls.append(args)
        return {"error": {"outcome": "unknown", "message": "timeout"}}
    monkeypatch.setattr(app.commands, "agent_call", execute)
    fixture = ProviderFixture([two_calls()])
    try:
        fixture.configure(app)
        record = finished(app, app.dispatch("agent.run", {"message": "修改工作副本", "allow_writes": True})["task_id"])
        assert len(calls) == 1 and len(record["receipts"]) == 1
        assert record["status"] == "failed" and "结果待确认" in record["error"]
        assert len(fixture.requests) == 1
    finally:
        fixture.close()


def test_agent_cancel_preserves_completed_receipt_and_skips_next_action(app, monkeypatch):
    calls = []
    def execute(name, params, project, allow_writes, ctx):
        calls.append(name)
        app.tasks.cancel(ctx.task_id)
        return {"applied": True}
    monkeypatch.setattr(app.commands, "agent_call", execute)
    fixture = ProviderFixture([two_calls()])
    try:
        fixture.configure(app)
        record = finished(app, app.dispatch("agent.run", {"message": "修改工作副本", "allow_writes": True})["task_id"])
        assert len(calls) == 1 and record["status"] == "canceled"
        assert record["receipts"][0]["result"]["applied"] is True
    finally:
        fixture.close()


def test_truncated_provider_tool_stream_is_never_executed(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.commands, "agent_call", lambda *args: calls.append(args))
    fixture = ProviderFixture([[({"tool_calls": [{"index": 0, "id": "cut", "function": {"name": "freecad_apply", "arguments": "{}"}}]}, None)]])
    try:
        fixture.configure(app)
        record = finished(app, app.dispatch("agent.run", {"message": "修改工作副本", "allow_writes": True})["task_id"])
        assert record["status"] == "failed" and "未完整结束" in record["error"]
        assert not calls and not record["receipts"]
    finally:
        fixture.close()
