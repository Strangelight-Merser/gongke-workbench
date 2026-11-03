import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

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


def test_non_teaching_conditions_are_explicit(app, tmp_path):
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


def test_stdio_generates_drawings_and_step_while_input_pipe_stays_open(tmp_path):
    """The desktop keeps stdin open while its worker first imports native libraries."""
    from importlib.util import find_spec
    import queue

    if find_spec("build123d") is None:
        pytest.skip("STEP generation requires the geometry or desktop extra")
    root = Path(__file__).resolve().parents[1]
    requests = [
        {"id": 1, "method": "project.create", "params": {"path": str(tmp_path / "project"), "teaching": True}},
        {"id": 2, "method": "design.generate", "params": {"name": "drawing", "drawings": True, "report_docx": False, "step": True}},
    ]
    process = subprocess.Popen(
        [sys.executable, "-m", "gongke_app.service", "--state-dir", str(tmp_path / "state")],
        cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env={**os.environ, "GONGKE_TEST_DIAGNOSTICS_DIR": str(tmp_path / "diagnostics")},
    )
    output, stderr = queue.Queue(), []

    def read_output():
        for line in process.stdout:
            try:
                output.put(json.loads(line))
            except json.JSONDecodeError:
                output.put({"protocol_error": line})

    reader = threading.Thread(target=read_output, daemon=True)
    errors = threading.Thread(target=lambda: stderr.append(process.stderr.read()), daemon=True)
    reader.start()
    errors.start()
    try:
        process.stdin.write("".join(json.dumps(row) + "\n" for row in requests))
        process.stdin.flush()
        # No polling requests: waking stdin would mask the Windows import deadlock.
        deadline, terminal = time.monotonic() + 90, None
        while time.monotonic() < deadline:
            try:
                reply = output.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            assert "protocol_error" not in reply and "error" not in reply, reply
            record = reply.get("task", {})
            if record.get("status") in {"complete", "partial", "failed", "canceled"}:
                terminal = record
                break
        if terminal is None:
            dump = tmp_path / "diagnostics/python-threads.log"
            stacks = dump.read_text(encoding="utf-8", errors="replace")[-8000:] if dump.exists() else "(no thread dump)"
            raise AssertionError("drawing/STEP worker stalled while stdin remained open\n" + stacks)
        assert terminal["status"] == "complete", terminal
        result = terminal["result"]
        assert result["exports_complete"] is True
        assert len(result["drawings"]) == 9
        output_dir = tmp_path / "project/revisions/drawing/drawings"
        for item in result["drawings"]:
            assert (output_dir / item["dxf"]).stat().st_size > 0
            assert (output_dir / item["svg"]).stat().st_size > 0
        assert (output_dir / "drawings.pdf").read_bytes().startswith(b"%PDF-")
        step = (output_dir.parent / "reducer_assembly.step").read_bytes()
        assert step.startswith(b"ISO-10303-21;")
        assert step.rstrip().endswith(b"END-ISO-10303-21;")
        assert result["artifacts"]["step"]["status"] == "complete"
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        reader.join(timeout=2)
        errors.join(timeout=2)
    assert process.returncode == 0, "".join(stderr)


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
    discovery = {"host_id": "autocad-1", "host": "autocad", "instance_id": "session", "capabilities": []}
    monkeypatch.setattr(app.hosts, "discover", lambda: [discovery])
    calls = []
    def request(config, method, params, **kwargs):
        calls.append(params)
        Path(params["target_path"]).write_text("native DWG fixture")
        return {"outcome": "committed", "path": params["target_path"], "source_path": params["source_path"],
                "operation_id": params["operation_id"], "original_preserved": True, "disk_reopen_verified": True}
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
    rejected = app.dispatch("host.command", params)
    assert rejected["error"]["outcome"] == "not_applied" and "已存在" in rejected["error"]["message"]
    rejected = app.dispatch("host.command", {**params, "method": "document.save"})
    assert rejected["error"]["outcome"] == "not_applied" and "未获应用层支持" in rejected["error"]["message"]


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
    monkeypatch.setattr(app.hosts, "discover", lambda: [{"host_id": "sw-1", "host": "solidworks", "session_id": "session", "capabilities": []}])
    verified = False
    def save(config, method, params, **kwargs):
        for key in ("output_path", "output_part_path"):
            Path(params[key]).write_bytes(b"protocol file fixture")
        return {"status": "saved", "path": params["output_path"], "references_verified": verified,
                "parameter_values_verified": True, "source_state_preserved": True, "reopen_verified": True,
                "working_copies": [{"path": params[key], "verified": True} for key in ("output_path", "output_part_path")]}
    monkeypatch.setattr(app.hosts, "_request", save)
    def params(folder):
        from uuid import uuid5, NAMESPACE_URL
        return {"host_id": "sw-1", "method": "document.save_copy", "params": {"operation_id": str(uuid5(NAMESPACE_URL, folder)),
                "output_path": folder + "/drawing.slddrw", "output_part_path": folder + "/shaft.sldprt"}}
    with pytest.raises(ValueError, match="未完整验证"):
        app.dispatch("host.command", params("unverified"))
    assert app.project.manifest["working_copies"] == []
    verified = True
    app.dispatch("host.command", params("verified"))
    assert app.project.is_working_copy(app.project.path / "verified/drawing.slddrw", "solidworks")
    assert app.project.is_working_copy(app.project.path / "verified/shaft.sldprt", "solidworks")
