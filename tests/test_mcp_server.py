"""官方 SDK 客户端 -> stdio 代理 -> 运行中服务 -> 同一工程、任务与收据。"""
import asyncio
import json
from pathlib import Path
import sys

import pytest
from mcp import Client, StdioServerParameters

from gongke_app.connection import Connection, ConnectionServer
from gongke_app.service import Application
from tests.mcp_helpers import ROOT, ServiceProcess


@pytest.fixture
def service(tmp_path):
    service = ServiceProcess(tmp_path)
    try:
        yield service
    finally:
        service.close()


def client_params(service, *, write=True, command=None):
    return StdioServerParameters(command=(command or [sys.executable])[0],
        args=[*(command[1:] if command else ["-m", "gongke_app"]), "mcp", "--state-dir", str(service.state),
              "--project", str(service.project), *(["--allow-writes"] if write else [])], cwd=str(ROOT))


def test_official_sdk_reads_calculates_generates_same_desktop_task(service):
    async def journey():
        async with Client(client_params(service)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            definitions = service.request("tools.list")
            assert tools.keys() == {t["name"] for t in definitions}
            assert all(tools[t["name"]].input_schema == t["inputSchema"] for t in definitions)
            assert "generate_files" not in tools and "host.command" not in tools
            current = await client.call_tool("project.current", {})
            assert current.structured_content["result"]["path"] == str(service.project)
            calculated = await client.call_tool("design.calculate", {})
            assert not calculated.is_error
            assert calculated.structured_content["result"]["motor"]["power_kw"] > 0
            assert "checks" in calculated.structured_content["result"]
            generated = await client.call_tool("design.generate", {"name": "sdk", "drawings": False, "report_docx": False})
            assert not generated.is_error
            value = generated.structured_content
            assert value["status"] == "complete"
            task = service.request("task.get", {"task_id": value["task_id"]})
            assert task["project"] == str(service.project)
            assert task["result"] == value["result"]
            assert task["receipts"][0]["command"] == "design.generate"
            assert task["receipts"][0]["phase"] == "finished"
            assert (service.project / "revisions/sdk/report.md").stat().st_size > 0
            events = [e for e in service.events if e.get("task", {}).get("task_id") == task["task_id"]]
            assert {e["task"]["status"] for e in events} >= {"queued", "running", "complete"}
            receipts = [e["receipt"] for e in service.events if e.get("event") == "task.receipt" and e.get("task_id") == task["task_id"]]
            assert [r["phase"] for r in receipts] == ["prepared", "finished"]
            assert receipts[0]["result"] is None
            refused = await client.call_tool("design.generate", {"name": "sdk", "drawings": False, "report_docx": False})
            assert refused.is_error and "已存在" in refused.content[0].text
    asyncio.run(journey())


def test_read_only_binding_enforces_execution_not_only_listing(service):
    async def journey():
        async with Client(client_params(service, write=False)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "design.calculate" in names and "design.generate" not in names
            refused = await client.call_tool("design.generate", {"name": "forbidden"})
            assert refused.is_error and "未授权" in refused.content[0].text
            assert not (service.project / "revisions/forbidden").exists()
            invalid = await client.call_tool("design.calculate", {"shell": "anything"})
            assert invalid.is_error and "未知参数" in invalid.content[0].text
            escaped = await client.call_tool("host.read", {"host_id": "x", "method": "document.save_copy", "params": {}})
            assert escaped.is_error
    asyncio.run(journey())


def test_project_switch_invalidates_existing_connection_even_when_switched_back(service, tmp_path):
    async def journey():
        async with Client(client_params(service)) as client:
            await client.list_tools()
            other = tmp_path / "second"
            service.request("project.create", {"path": str(other)})
            for _ in range(2):
                response = await client.call_tool("design.generate", {"name": "wrong"})
                assert response.is_error and "绑定已失效" in response.content[0].text
                service.request("project.open", {"path": str(service.project)})
            assert not (other / "revisions/wrong").exists()
            assert not (service.project / "revisions/wrong").exists()
    asyncio.run(journey())


def test_wrong_project_cannot_bind(service, tmp_path):
    with pytest.raises(ValueError, match="不是桌面当前工程"):
        Connection(service.state).request("bind", project=str(tmp_path), allow_writes=True)


def test_original_outside_and_stale_writes_same_rules_on_all_entries(tmp_path, monkeypatch):
    from gongke_core import native_client
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    connection = ConnectionServer(app, tmp_path / "state")
    original = app.project.path / "original.FCStd"
    original.write_bytes(b"original")
    context = {"session_id": "s", "path": str(original), "revision": 2}
    writes = []
    def native(method, **params):
        if method == "get_project_context":
            return dict(context)
        writes.append((method, params))
        return {"applied": True}
    monkeypatch.setattr(native_client, "call", native)
    stub = type("Service", (), {"state": tmp_path / "state", "project": app.project.path})()
    async def journey():
        async with Client(client_params(stub)) as client:
            cases = [("freecad.apply", {"session_id": "s", "change_id": "c", "operation_id": "o"}),
                     ("freecad.save", {"session_id": "s", "path": "original.FCStd"}),
                     ("freecad.save", {"session_id": "s", "path": "../outside.FCStd"})]
            for name, args in cases:
                with pytest.raises(ValueError) as desktop_error:
                    app.dispatch(name, args)
                result = await client.call_tool(name, args)
                assert result.is_error and str(desktop_error.value) in result.content[0].text
            app.project.register_copy(original, "freecad", {"path": str(original)})
            args = {"session_id": "s", "page_name": "Sheet", "expected_revision": 1}
            with pytest.raises(ValueError, match="过期"):
                app.dispatch("freecad.update_drawing", args)
            result = await client.call_tool("freecad.update_drawing", args)
            assert result.is_error and "过期" in result.content[0].text
            assert not writes and original.read_bytes() == b"original"
            assert (await client.call_tool("freecad.context", {})).structured_content["result"] == context
    try:
        asyncio.run(journey())
    finally:
        connection.close()
        app.close()


def test_workbuddy_config_preserves_other_servers_and_uses_packaged_command(service, tmp_path):
    executable = tmp_path / "gongke-service"
    executable.write_text("packaged executable fixture")
    config = Path.home() / ".workbuddy/mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {"other": {"command": "existing"}}}))
    result = Connection(service.state).request("configure", project=str(service.project), executable=str(executable), allow_writes=True, confirm_user_config=True)
    value = json.loads(config.read_text())
    assert value["mcpServers"]["other"] == {"command": "existing"}
    assert result["server"] == value["mcpServers"][result["service_name"]]
    assert result["server"]["command"] == str(executable)
    assert result["server"]["args"][-1] == "--allow-writes"
    assert "python" not in result["server"]["command"]


def test_write_intent_is_durable_before_host_and_lost_reply_queries_original_id(tmp_path, monkeypatch):
    from gongke_core import native_client
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    target = app.project.path / "copy.FCStd"
    target.write_bytes(b"working copy")
    app.project.register_copy(target, "freecad", {"path": str(target)})
    calls = []
    def native(method, **params):
        calls.append((method, params))
        if method == "get_project_context":
            return {"session_id": "s", "path": str(target), "revision": 3}
        if method == "apply_change":
            task = app.tasks.list()[0]
            receipt = app.tasks.get(task["task_id"])["receipts"][0]
            assert receipt["phase"] == "prepared" and receipt["result"] is None
            assert receipt["params"]["operation_id"] == "original-operation"
            raise native_client.NativeBridgeError("桥接未响应")
        assert method == "get_operation_status" and params["operation_id"] == "original-operation"
        return {"state": "committed", "undone": False, "result": {"applied": True, "revision": 4}}
    monkeypatch.setattr(native_client, "call", native)
    try:
        result = app.dispatch("freecad.apply", {"session_id": "s", "change_id": "candidate", "operation_id": "original-operation"})
        assert "未响应" in result["error"]
        assert result["readback"]["result"] == {"applied": True, "revision": 4}
        assert [m for m, _ in calls] == ["get_project_context", "apply_change", "get_operation_status"]
        task = app.tasks.get(app.tasks.list()[0]["task_id"])
        assert task["status"] == "failed"
        assert task["receipts"][0]["result"] == result
        assert task["receipts"][0]["phase"] == "finished"
    finally:
        app.close()


def test_registered_current_copy_can_save_without_duplicate_registration(tmp_path, monkeypatch):
    from gongke_core import native_client
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    target = app.project.path / "copy.FCStd"
    target.write_bytes(b"old")
    app.project.register_copy(target, "freecad", {"path": str(target)})
    def native(method, **params):
        if method == "get_project_context":
            return {"session_id": "s", "path": str(target), "revision": 2}
        assert method == "save_project" and params["path"] == str(target)
        target.write_bytes(b"new")
        return {"saved": True, "path": str(target), "revision": 2}
    monkeypatch.setattr(native_client, "call", native)
    try:
        assert app.dispatch("freecad.save", {"session_id": "s", "path": "copy.FCStd"})["saved"]
        assert target.read_bytes() == b"new"
        assert len(app.project.manifest["working_copies"]) == 1
    finally:
        app.close()


def test_active_bound_task_blocks_switch_and_cancel_preserves_committed_result(tmp_path, monkeypatch):
    import threading
    from gongke_app.mcp_server import call_bound
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    server = ConnectionServer(app, tmp_path / "state")
    connection = Connection(tmp_path / "state")
    binding = connection.request("bind", project=str(app.project.path), allow_writes=True)
    entered, release = threading.Event(), threading.Event()
    def execute(method, params, project, ctx, **kwargs):
        entered.set()
        assert release.wait(10)
        return {"saved": True}
    monkeypatch.setattr(app.commands, "_execute", execute)
    async def journey():
        task = asyncio.create_task(call_bound(connection, binding, "project.set_task", {"task": app.project.task()}))
        assert await asyncio.to_thread(entered.wait, 5)
        with pytest.raises(ValueError, match="仍有任务执行中"):
            app.dispatch("project.create", {"path": str(tmp_path / "other")})
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        task_id = app.tasks.list()[0]["task_id"]
        assert app.tasks.get(task_id)["cancel_requested"]
        release.set()
        from tests.test_app_service import finished
        record = await asyncio.to_thread(finished, app, task_id)
        assert record["status"] == "complete" and record["result"]["saved"]
        assert record["receipts"][0]["result"]["saved"]
    try:
        asyncio.run(journey())
    finally:
        release.set()
        server.close()
        app.close()


def test_connection_auth_and_config_preview(service, tmp_path):
    from urllib.error import HTTPError
    conn = Connection(service.state)
    conn.token = "incorrect"
    with pytest.raises(HTTPError) as error:
        conn.request("bind", project=str(service.project))
    assert error.value.code == 403
    result = Connection(service.state).request("configure", project=str(service.project), executable=sys.executable, allow_writes=False)
    assert result["status"] == "confirmation_required"
    assert not Path(result["path"]).exists()


def test_native_rejection_cannot_be_replaced_with_old_success_receipt(tmp_path, monkeypatch):
    from gongke_core import native_client
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    target = app.project.path / "copy.FCStd"
    target.write_bytes(b"working copy")
    app.project.register_copy(target, "freecad", {"path": str(target)})
    def native(method, **params):
        if method == "get_project_context":
            return {"session_id": "s", "path": str(target), "revision": 4}
        if method == "apply_change":
            raise native_client.NativeBridgeError("operation_id 已用于另一候选")
        assert method == "get_operation_status"
        return {"state": "committed", "result": {"applied": True, "revision": 3}}
    monkeypatch.setattr(native_client, "call", native)
    try:
        result = app.dispatch("freecad.apply", {"session_id": "s", "change_id": "different-candidate", "operation_id": "old-id"})
        assert "另一候选" in result["error"]
        assert "applied" not in result
        assert app.tasks.list()[0]["status"] == "failed"
    finally:
        app.close()


# 配置测试使用独立用户目录，不读取开发者真实 WorkBuddy 配置。
import pytest

@pytest.fixture(autouse=True)
def workbuddy_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
