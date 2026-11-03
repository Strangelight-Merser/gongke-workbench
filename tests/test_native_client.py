"""本机命令桥的协议测试；真实 FreeCAD 编辑旅程由原生集成验收覆盖。"""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from gongke_core import native_client
from gongke_app.commands import Commands
from gongke_app.native import create_shaft_project
from gongke_app.project import Project
from gongke_app.tools import NATIVE


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    requests = []
    state = {"response": {"ok": True, "result": {"session_id": "current-session"}}, "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                             "payload": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            self.send_response(state["status"])
            if state["status"] == 307:
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirected")
            self.end_headers()
            self.wfile.write(json.dumps(state["response"]).encode("utf-8"))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}",
                                        "token": "local-session-secret", "pid": 123}), encoding="utf-8")
    monkeypatch.setenv("GONGKE_FREECAD_SESSION", str(session_file))
    try:
        yield requests, state, session_file
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_authenticated_loopback_command_ignores_proxy(bridge, monkeypatch):
    requests, _, _ = bridge
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    assert native_client.call("read_engineering_object", session_id="s", entity_id="e") == {"session_id": "current-session"}
    assert requests == [{"path": "/command", "authorization": "Bearer local-session-secret",
                         "payload": {"method": "read_engineering_object", "params": {"session_id": "s", "entity_id": "e"}}}]


def test_bridge_error_reaches_application(bridge):
    _, state, _ = bridge
    state["response"] = {"ok": False, "error": "候选已过期，请重新读取当前轴"}
    with pytest.raises(native_client.NativeBridgeError, match="候选已过期"):
        Commands().call("freecad.context", {}, None)


@pytest.mark.parametrize("url", ["http://example.com:80", "http://192.168.1.1:8080", "https://127.0.0.1:8080",
                                  "http://secret@127.0.0.1:8080", "http://127.0.0.1", "http://127.0.0.1:8080/elsewhere"])
def test_only_explicit_local_bridge_is_allowed(tmp_path, monkeypatch, url):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"url": url, "token": "secret"}))
    monkeypatch.setenv("GONGKE_FREECAD_SESSION", str(path))
    with pytest.raises(native_client.NativeBridgeError, match="本机回环"):
        native_client.call("get_project_context")


def test_missing_session_has_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GONGKE_FREECAD_SESSION", str(tmp_path / "absent.json"))
    with pytest.raises(native_client.NativeBridgeError, match="启用工科工作台"):
        native_client.call("get_project_context")


def test_redirect_does_not_forward_token(bridge):
    requests, state, _ = bridge
    state["status"] = 307
    with pytest.raises(native_client.NativeBridgeError, match="HTTP 307"):
        native_client.call("apply_change", operation_id="op")
    assert len(requests) == 1


def test_invalid_reply_and_nonfinite_arguments_are_errors(bridge):
    requests, state, _ = bridge
    with pytest.raises(native_client.NativeBridgeError, match="数值必须有限"):
        native_client.call("preview_shaft_change", diameter_m=float("nan"))
    assert not requests
    state["response"] = {"ok": True}
    with pytest.raises(native_client.NativeBridgeError, match="缺少操作结果"):
        native_client.call("get_project_context")


def test_native_tools_distinguish_read_and_write():
    tools = Commands().definitions
    for short in ("context", "read", "preview", "preview_fillet", "review", "get_job"):
        assert tools["freecad." + short][2] is False
    for short in ("create", "bind", "apply", "undo", "save", "run_analysis", "cancel_job"):
        assert tools["freecad." + short][2] is True
    assert tools["freecad.preview"][1]["properties"]["diameter_m"]["exclusiveMinimum"] == 0
    assert tools["freecad.preview_fillet"][1]["properties"]["radius_m"]["exclusiveMinimum"] == 0


@pytest.mark.parametrize(("name", "arguments"), [
    ("run_analysis", {"session_id": "s", "entity_id": "e"}),
    ("get_job", {"job_id": "job-1"}),
    ("cancel_job", {"job_id": "job-1"}),
    ("review_current_object", {"session_id": "s", "entity_id": "e"}),
    ("preview_fillet_change", {"session_id": "s", "entity_id": "e", "left_segment_id": "left",
                              "right_segment_id": "right", "radius_m": 0.0012}),
])
def test_analysis_tools_forward_only_identifiers(bridge, name, arguments, tmp_path):
    requests, state, _ = bridge
    state["response"] = {"ok": True, "result": {"job_id": "job-1", "status": "queued"}}
    short = next(key for key, method in NATIVE.items() if method == name)
    project = Project.create(str(tmp_path / "project"))
    result = Commands().call("freecad." + short, arguments, project)
    assert result["job_id"] == "job-1"
    assert requests[0]["payload"] == {"method": name, "params": arguments}


def test_analysis_rejects_injected_snapshot_before_bridge(bridge):
    requests, _, _ = bridge
    commands = Commands()
    assert set(commands.definitions["freecad.run_analysis"][1]["properties"]) == {"session_id", "entity_id"}
    with pytest.raises(ValueError, match="未知参数"):
        commands.call("freecad.run_analysis", {"session_id": "s", "entity_id": "e", "snapshot": {}}, None)
    assert not requests


def test_course_project_creation_preserves_full_forces(bridge):
    requests, _, _ = bridge
    create_shaft_project(case="course_output")
    request = requests[0]["payload"]
    assert request["method"] == "create_project"
    snapshot = request["params"]["snapshot"]
    assert snapshot["scope"] == "course_shaft_review"
    assert len(snapshot["segments"]) == 7
    assert snapshot["loads"][0]["fz_n"] != 0
    assert snapshot["loads"][0]["couple_xz_nm"] != 0
    assert snapshot["read_only"] is False
    assert snapshot["editable_parameters"] == ["right_bearing_shoulder_radius_m"]


@pytest.mark.parametrize("case,task", [("unknown", None), ("teaching", {}), ("course_output", {"scheme": "worm"})])
def test_invalid_project_creation_does_not_touch_freecad(bridge, case, task):
    requests, _, _ = bridge
    with pytest.raises(ValueError):
        create_shaft_project(case=case, task=task)
    assert not requests
