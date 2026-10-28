"""本机命令桥的协议测试；真实 FreeCAD 编辑旅程由原生集成验收覆盖。"""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from gongke_core import mcp_server, native_client


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


def test_bridge_error_is_mcp_tool_error(bridge):
    _, state, _ = bridge
    state["response"] = {"ok": False, "error": "候选已过期，请重新读取当前轴"}
    result = mcp_server.Server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "apply_change", "arguments": {"session_id": "s", "change_id": "c", "operation_id": "op"}}})
    assert result["result"]["isError"] is True
    assert "候选已过期" in result["result"]["content"][0]["text"]


def test_stdio_mcp_reaches_bridge(bridge):
    requests, _, _ = bridge
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_project_context", "arguments": {}}}
    proc = subprocess.run([sys.executable, "-m", "gongke_core", "mcp"], input=json.dumps(message) + "\n",
                          cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15, check=True)
    result = json.loads(proc.stdout)
    assert result["result"]["isError"] is False
    assert result["result"]["structuredContent"]["session_id"] == "current-session"
    assert requests[0]["payload"] == {"method": "get_project_context", "params": {}}


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
    tools = {tool["name"]: tool for tool in mcp_server.TOOLS}
    for name in ("get_project_context", "read_engineering_object", "preview_shaft_change", "preview_fillet_change", "review_current_object", "get_job"):
        assert tools[name]["annotations"]["readOnlyHint"] is True
    for name in ("create_shaft_project", "bind_existing_shaft", "apply_change", "undo_last_agent_change", "save_project", "run_analysis", "cancel_job"):
        assert tools[name]["annotations"]["readOnlyHint"] is False
    assert tools["preview_shaft_change"]["inputSchema"]["properties"]["diameter_m"]["exclusiveMinimum"] == 0
    assert tools["preview_fillet_change"]["inputSchema"]["properties"]["radius_m"]["exclusiveMinimum"] == 0


@pytest.mark.parametrize(("name", "arguments"), [
    ("run_analysis", {"session_id": "s", "entity_id": "e"}),
    ("get_job", {"job_id": "job-1"}),
    ("cancel_job", {"job_id": "job-1"}),
    ("review_current_object", {"session_id": "s", "entity_id": "e"}),
    ("preview_fillet_change", {"session_id": "s", "entity_id": "e", "left_segment_id": "left",
                              "right_segment_id": "right", "radius_m": 0.0012}),
])
def test_analysis_tools_forward_only_identifiers(bridge, name, arguments):
    requests, state, _ = bridge
    state["response"] = {"ok": True, "result": {"job_id": "job-1", "status": "queued"}}
    result = mcp_server.Server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": name, "arguments": arguments}})
    assert result["result"]["isError"] is False
    assert requests[0]["payload"] == {"method": name, "params": arguments}


def test_analysis_rejects_injected_snapshot_before_bridge(bridge):
    requests, _, _ = bridge
    tool = next(t for t in mcp_server.TOOLS if t["name"] == "run_analysis")
    assert set(tool["inputSchema"]["properties"]) == {"session_id", "entity_id"}
    result = mcp_server.Server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "run_analysis", "arguments": {"session_id": "s", "entity_id": "e", "snapshot": {"diameter_m": 1}}}})
    assert result["result"]["isError"] is True
    assert not requests


def test_course_project_creation_preserves_full_forces(bridge):
    requests, _, _ = bridge
    mcp_server._create_shaft_project(case="course_output")
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
        mcp_server._create_shaft_project(case=case, task=task)
    assert not requests
