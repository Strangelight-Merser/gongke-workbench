"""解析几何、命令入口和拒绝语义；这些测试不冒充 CAD 真机运行。"""
from copy import deepcopy
import pytest

from gongke_app import inspection as i
from gongke_app.commands import Commands
from gongke_app.hosts import Hosts
from gongke_app.tools import definitions, validate

DOC = {"host_instance": "instance", "document_id": "doc", "revision": 3, "configuration": ""}


@pytest.fixture
def snapshot():
    # 两条平行圆柱轴相距 116 mm，半径 21 mm；两平面相距 8 mm，解析定义。
    return {"document": DOC, "object_ref": "Body", "state": "ready", "features": [], "edges": [], "faces": [
        {"native_ref": "Face1", "kind": "cylinder", "point": [0, 0, 0], "direction": [0, 0, 1], "radius": .021, "inward": True},
        {"native_ref": "Face2", "kind": "cylinder", "point": [.116, 0, 0], "direction": [0, 0, -1], "radius": .021, "inward": True},
        {"native_ref": "Face3", "kind": "plane", "point": [0, 0, 0], "direction": [0, 0, 1]},
        {"native_ref": "Face4", "kind": "plane", "point": [.01, .02, .008], "direction": [0, 0, -1]}]}


def condition(kind, refs, expected, tolerance=0, unit="mm"):
    return {"id": kind, "source": "解析测试定义", "measurement": {"kind": kind, "selectors": [{"native_ref": r} for r in refs]},
            "expected": expected, "tolerance": tolerance, "unit": unit}


def test_dimensions_and_tolerance(snapshot):
    conditions = [condition("diameter", ["Face1"], 42), condition("axis_distance", ["Face1", "Face2"], 116),
                  condition("plane_distance", ["Face3", "Face4"], 8, .1)]
    result = i.check(snapshot, conditions)
    assert result["status"] == "pass"
    assert result["checks"][1]["actual"]["value"] == pytest.approx(.116)
    snapshot["faces"][3]["point"][2] = .0081
    assert i.check(snapshot, conditions)["status"] == "pass"
    snapshot["faces"][3]["point"][2] = .00811
    result = i.check(snapshot, conditions)
    assert result["status"] == "fail"
    assert result["checks"][2]["actual"]["locations"][1]["native_ref"] == "Face4"


def test_missing_ambiguous_rebuild_and_unit_are_unknown(snapshot):
    request = {"kind": "diameter", "selectors": [{"kind": "cylinder"}]}
    assert i.measure(snapshot, request)["reason"] == "ambiguous_entity"
    request["selectors"] = [{"native_ref": "missing"}]
    assert i.measure(snapshot, request)["reason"] == "missing_entity"
    snapshot["state"] = "needs_rebuild"
    assert i.measure(snapshot, request)["reason"] == "model_not_ready"
    snapshot["state"] = "ready"
    c = condition("diameter", ["Face1"], 42, unit="rad")
    assert i.check(snapshot, [c])["checks"][0]["actual"]["reason"] == "unit_mismatch"


def test_axis_origin_is_not_bore_position_and_shift_is_detected(snapshot):
    assert i.line_point([0, 0, 200], [0, 0, -1]) == [0, 0, 0]
    assert i.matches(snapshot["faces"][0], {"point": [0, 0, 300]})
    c = condition("coordinate", ["Face2"], 116, .1)
    c["measurement"]["axis"] = 0
    snapshot["faces"][1]["point"][0] += .001
    assert i.check(snapshot, [c])["status"] == "fail"


def test_skew_axes_are_not_center_distance(snapshot):
    snapshot["faces"][1]["direction"] = [1, 0, 0]
    c = condition("axis_distance", ["Face1", "Face2"], 116)
    assert i.check(snapshot, [c])["status"] == "unknown"


def test_section_and_stale_result(snapshot):
    request = {"kind": "section_area", "plane": {"origin": [0, 0, .01], "normal": [0, 0, 1]}}
    def cut(plane):
        return {"document": DOC, "plane": plane, "status": "ok", "area": .000416}
    assert i.measure(snapshot, request, cut)["value"] == .000416
    def stale(plane):
        return {**cut(plane), "document": {**DOC, "revision": 4}}
    with pytest.raises(ValueError, match="修订"):
        i.measure(snapshot, request, stale)


@pytest.mark.parametrize("host", ["freecad", "sw-test"])
def test_unified_command_execution(host, snapshot, monkeypatch, tmp_path):
    calls = []
    hosts = Hosts(tmp_path)
    def execute(method, params):
        calls.append((method, params))
        return deepcopy(snapshot)
    if host == "freecad":
        def native(method, **args):
            assert method == "inspect_host"
            return execute(args["command"], args["params"])
        monkeypatch.setattr("gongke_app.hosts.native_client.call", native)
    else:
        monkeypatch.setattr(hosts, "discover", lambda: [{"host_id": host, "host": "solidworks", "capabilities": list(i.NATIVE_METHODS)}])
        monkeypatch.setattr(hosts, "_request", lambda config, method, params: execute(method, params))
    command = Commands(hosts)
    result = command.call("host.check", {"host_id": host, "document": DOC, "object_ref": "Body",
        "conditions": [condition("diameter", ["Face1"], 42)]}, None, allow_writes=False)
    assert result["status"] == "pass"
    assert calls == [("model.inspect", {"document": DOC, "object_ref": "Body"})]
    assert all(not definitions()[name][2] for name in i.definitions())


def test_generic_host_read_also_validates_reference(tmp_path):
    with pytest.raises(ValueError, match="参数无效"):
        Hosts(tmp_path).command("freecad", "model.inspect", {"document": {"document_id": "doc"}, "object_ref": "Body"}, None)
    with pytest.raises(ValueError, match="未声明"):
        Hosts(tmp_path).command("freecad", "parameter.change", {}, None)


@pytest.mark.parametrize("patch", [{"unit": "inch"}, {"tolerance": -1}, {"expected": float("nan")}, {"source": ""}])
def test_condition_input_is_explicit_and_finite(patch):
    args = {"host_id": "freecad", "document": DOC, "object_ref": "Body",
            "conditions": [{**condition("diameter", ["Face1"], 42), **patch}]}
    with pytest.raises(ValueError):
        validate(args, definitions()["host.check"][1])


def test_mcp_and_desktop_share_check_execution(snapshot, tmp_path, monkeypatch):
    """真实 SDK/stdio/应用服务路径；宿主采集替身，非 FreeCAD 真机证据。"""
    import asyncio
    import sys
    from pathlib import Path
    from mcp import Client, StdioServerParameters
    from gongke_app.service import Application
    from gongke_app.connection import ConnectionServer
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    server = ConnectionServer(app, tmp_path / "state")
    calls = []
    def native(method, **params):
        assert method == "inspect_host" and params["command"] == "model.inspect"
        calls.append(params)
        return deepcopy(snapshot)
    monkeypatch.setattr("gongke_app.hosts.native_client.call", native)
    args = {"host_id": "freecad", "document": DOC, "object_ref": "Body",
            "conditions": [condition("diameter", ["Face1"], 42)]}
    async def journey():
        params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp",
            "--state-dir", str(tmp_path / "state"), "--project", str(tmp_path / "project")],
            cwd=str(Path(__file__).resolve().parents[1]))
        async with Client(params) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in i.definitions():
                assert tools[name].annotations.read_only_hint
                assert tools[name].input_schema == app.commands.definitions[name][1]
            response = await client.call_tool("host.check", args)
            assert not response.is_error
            result = response.structured_content
            assert result["result"]["status"] == "pass"
            record = app.tasks.get(result["task_id"])
            assert record["receipts"][0]["command"] == "host.check"
            return result["result"]
    try:
        direct = app.dispatch("host.check", args)
        assert asyncio.run(journey()) == direct
        assert len(calls) == 2
    finally:
        server.close()
        app.close()


def test_fixture_files_unchanged_from_study():
    from pathlib import Path
    import hashlib
    import json
    folder = Path(__file__).parent / "fixtures/model_inspection"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert len(manifest["sha256"]) == 9
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest


def test_native_inspection_is_installable_without_application_package(tmp_path):
    # 模拟缺宿主运行时，仅检验真实独立安装的导入依赖；不验证几何。
    import os
    import runpy
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).parents[1]
    target = runpy.run_path(str(root / "tools/install_freecad_workbench.py"))["install"](tmp_path / "Mod")
    code = "import sys,types; sys.modules['FreeCAD']=types.ModuleType('FreeCAD'); sys.modules['Part']=types.ModuleType('Part'); from freecad.gongke import native_inspection; print(native_inspection.__file__)"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(target)}, capture_output=True, text=True, check=True)
    assert Path(result.stdout.strip()).is_relative_to(target)
