"""建模协议、工程保护与写入恢复；不冒充 CAD 内核验收。"""
from copy import deepcopy
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mcp import Client, StdioServerParameters
from gongke_app import modeling as m
from gongke_app.commands import Commands
from gongke_app.hosts import Hosts, _fingerprint
from gongke_app.project import Project
from gongke_app.tools import definitions, validate
from tests.mcp_helpers import ServiceProcess
from tests.e2e.native_modeling_recipes import build

DOC = {"host_instance": "instance", "document_id": "doc", "revision": 3, "configuration": ""}
ROOT = Path(__file__).resolve().parents[1]


def test_all_modeling_writes_use_single_execution_gate(tmp_path):
    project = Project.create(tmp_path / "project")
    commands = Commands(Hosts(tmp_path))
    # 使用各工具有效参数，证明不是被 schema 提前挡住。
    samples = {
        "host.model_new": {"host_id": "freecad", "host_instance": "instance", "path": "part.FCStd", "name": "Body", "operation_id": str(uuid4())},
        "host.model_copy": {"path": "copy.FCStd"}, "host.body": {"name": "Body"},
        "host.sketch": {"body_ref": "Body", "name": "Sketch", "support": {"plane": "XY"}, "geometry": [], "constraints": []},
        "host.feature": {"body_ref": "Body", "name": "Pad", "feature": {"kind": "pad", "sketch_ref": "Sketch", "length": .008}},
        "host.feature_edit": {"feature_ref": "Pad", "parameter": "Length", "value": .01},
        "host.feature_delete": {"feature_ref": "Pad"}, "host.rebuild": {}, "host.model_save": {},
    }
    for name, extra in samples.items():
        args = extra if name == "host.model_new" else {"host_id": "freecad", "document": DOC, "operation_id": str(uuid4()), **extra}
        validate(args, definitions()[name][1])
        with pytest.raises(ValueError, match="未授权"):
            commands.call(name, args, project, allow_writes=False)
    with pytest.raises(ValueError, match="未授权"):
        commands.call("host.write", {"host_id": "freecad", "method": "model.rebuild", "params": {"document": DOC, "operation_id": str(uuid4())}}, project, allow_writes=False)
    with pytest.raises(ValueError):
        commands.call("host.read", {"host_id": "freecad", "method": "model.feature", "params": {}}, project, allow_writes=False)


@pytest.mark.parametrize("change", [
    {"script": "print(1)"}, {"geometry": [{"kind": "python", "code": "print(1)"}]},
    {"support": {"plane": "XY", "face_ref": "Face1"}}, {"sketch_ref": "Sketch"},
    {"support": {"plane": "XY", "offset": float("nan")}},
])
def test_sketch_schema_rejects_ambiguous_or_executable_inputs(change):
    args = {"host_id": "freecad", "document": DOC, "operation_id": str(uuid4()), "name": "Sketch", "body_ref": "Body", "support": {"plane": "XY"}, "geometry": [], "constraints": [], **change}
    with pytest.raises(ValueError):
        validate(args, definitions()["host.sketch"][1])


@pytest.fixture
def host(tmp_path, monkeypatch):
    project = Project.create(tmp_path / "project")
    hosts = Hosts(tmp_path)
    calls, replies = [], {}
    context = {"host_instance": "instance", "capabilities": sorted(m.WRITE_METHODS), "documents": [{"document": deepcopy(DOC), "path": str(project.path / "part.FCStd")}]}
    def native(method, **args):
        assert method == "inspect_host"
        calls.append((args["command"], deepcopy(args["params"])))
        if args["command"] == "model.context":
            return deepcopy(context)
        reply = replies[args["command"]]
        if isinstance(reply, Exception):
            raise reply
        return deepcopy(reply)
    monkeypatch.setattr("gongke_app.hosts.native_client.call", native)
    return project, hosts, context, calls, replies


def test_original_and_stale_revision_never_reach_native_mutation(host):
    project, hosts, context, calls, replies = host
    path = project.path / "part.FCStd"; path.write_text("original")
    args = {"document": DOC, "operation_id": str(uuid4())}
    with pytest.raises(ValueError, match="工作副本"):
        hosts.command("freecad", "model.rebuild", args, project)
    project.register_copy(path, "freecad", {"path": str(path)})
    context["documents"][0]["document"]["revision"] += 1
    with pytest.raises(ValueError, match="修订"):
        hosts.command("freecad", "model.rebuild", args, project)
    assert all(name == "model.context" for name, _ in calls)
    assert path.read_text() == "original"


def test_unknown_new_is_recovered_by_exact_receipt_without_resubmission(host):
    project, hosts, _, calls, replies = host
    operation = str(uuid4())
    args = {"host_instance": "instance", "operation_id": operation, "path": "new.FCStd", "name": "Body"}
    replies["model.new"] = TimeoutError("result unknown")
    with pytest.raises(TimeoutError):
        hosts.command("freecad", "model.new", args, project)
    original = project.copy_operation(operation)
    path = project.path / "new.FCStd"; path.write_bytes(b"host-created")
    receipt = {"operation_id": operation, "outcome": "committed", "document": DOC, "path": str(path), "file_exists": True}
    replies["model.operation"] = {"state": "finished", "host_instance": "instance", "fingerprint": original["fingerprint"], "result": receipt}
    hosts.command("freecad", "model.operation", {"operation_id": operation}, project)
    assert project.is_working_copy(path, "freecad")
    assert sum(name == "model.new" for name, _ in calls) == 1
    assert original["fingerprint"] == _fingerprint("model.new", original["params"])


@pytest.mark.parametrize("changed", [{"host_instance": "new-instance"}, {"fingerprint": "forged"}])
def test_unrelated_recovery_cannot_grant_write_access(host, changed):
    project, hosts, _, _, replies = host
    operation = str(uuid4())
    replies["model.new"] = {"error": {"outcome": "unknown"}}
    hosts.command("freecad", "model.new", {"host_instance": "instance", "operation_id": operation, "path": "new.FCStd", "name": "Body"}, project)
    original = project.copy_operation(operation)
    path = project.path / "new.FCStd"; path.write_bytes(b"other")
    replies["model.operation"] = {"state": "finished", "host_instance": "instance", "fingerprint": original["fingerprint"], "result": {"outcome": "committed", "path": str(path), "file_exists": True, "document": DOC, "operation_id": operation}, **changed}
    hosts.command("freecad", "model.operation", {"operation_id": operation}, project)
    assert not project.is_working_copy(path, "freecad")


def test_output_paths_are_project_scoped_and_do_not_overwrite(host):
    project, hosts, _, calls, _ = host
    (project.path / "original.FCStd").write_bytes(b"original")
    for path in ["../escape.FCStd", "original.FCStd", "model.step"]:
        with pytest.raises(ValueError):
            hosts.command("freecad", "model.new", {"host_instance": "instance", "operation_id": str(uuid4()), "path": path, "name": "Body"}, project)
    assert all(name == "model.context" for name, _ in calls)


def test_mcp_modeling_guidance_and_readonly_binding(tmp_path):
    service = ServiceProcess(tmp_path)
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(service.state), "--project", str(service.project)], cwd=str(ROOT))
        async with Client(params) as client:
            resources = await client.list_resources()
            assert any(str(r.uri) == "gongke://modeling" for r in resources.resources)
            guidance = await client.read_resource("gongke://modeling")
            assert guidance.contents[0].text == m.GUIDE
            prompts = await client.list_prompts()
            assert any(p.name == "native-modeling" for p in prompts.prompts)
            prompt = await client.get_prompt("native-modeling")
            assert prompt.messages[0].content.text == m.GUIDE
            tools = {t.name for t in (await client.list_tools()).tools}
            assert "host.model_operation" in tools and not set(m.TO_NATIVE).difference({"host.model_operation"}) & tools
            result = await client.call_tool("host.rebuild", {"host_id": "freecad", "document": DOC, "operation_id": str(uuid4())})
            assert result.is_error
    try:
        asyncio.run(run())
    finally:
        service.close()


@pytest.fixture
def native(monkeypatch, tmp_path):
    # 仅模拟文档事务与异常，几何正确性由沙箱外真实 FreeCAD 脚本检查。
    for name in ("FreeCAD", "Part", "Sketcher"):
        monkeypatch.setitem(sys.modules, name, SimpleNamespace())
    import freecad.gongke
    read = SimpleNamespace(document_ref=lambda state, doc: {**DOC, "revision": doc.revision})
    monkeypatch.setattr(freecad.gongke, "native_inspection", read, raising=False)
    spec = importlib.util.spec_from_file_location("native_modeling_unit", ROOT / "freecad/gongke/native_modeling.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    class Doc:
        FileName = str(tmp_path / "copy.FCStd")
        revision = 3
        Objects = []
        value = 1
        commits = 0
        def openTransaction(self, name): self.before = self.value
        def abortTransaction(self): self.value = self.before; self.revision += 1
        def commitTransaction(self): self.commits += 1
        def recompute(self): pass
    doc = Doc()
    state = SimpleNamespace(host_instance="instance", results_dir=tmp_path, modeling_copies={"doc": doc.FileName},
                            _session=lambda sid: {"doc": doc, "revision": doc.revision}, _writable=lambda session: None,
                            _edited=lambda value: setattr(value, "revision", value.revision+1))
    return module, state, doc


def test_native_failure_rolls_back_and_replay_never_mutates(native, monkeypatch):
    module, state, doc = native
    def fail(doc, method, p):
        doc.value = 2
        raise RuntimeError("真实宿主错误文本")
    monkeypatch.setattr(module, "_mutate", fail)
    args = {"document": DOC, "operation_id": str(uuid4())}
    result = module.dispatch(state, "model.rebuild", args)
    assert result["error"]["message"] == "真实宿主错误文本"
    assert result["error"]["outcome"] == "rolled_back" and doc.value == 1 and doc.commits == 0
    revision = doc.revision
    assert module.dispatch(state, "model.rebuild", args) == result
    assert doc.revision == revision
    assert module.dispatch(state, "model.operation", {"operation_id": args["operation_id"]})["result"] == result
    with pytest.raises(ValueError, match="另一请求"):
        module.dispatch(state, "model.save", args)


def test_native_started_receipt_and_original_document_block_mutation(native, monkeypatch):
    module, state, doc = native
    operation = str(uuid4()); args = {"document": DOC, "operation_id": operation}
    path = module._journal_path(state, operation)
    module._put(path, {"state": "started", "fingerprint": module._fingerprint("model.rebuild", args)})
    assert module.dispatch(state, "model.rebuild", args)["error"]["outcome"] == "unknown"
    state.modeling_copies.clear()
    result = module.dispatch(state, "model.rebuild", {**args, "operation_id": str(uuid4())})
    assert result["error"]["outcome"] == "not_applied" and doc.commits == 0


def test_p7_p8_recipe_uses_public_contract_without_native_geometry_import():
    # 验证脚本尺寸分解和所有调用 schema；不称为 CAD 验收。
    data = {
        "p7": {"base_thickness": 8, "boss_total_height": 11, "tube_total_height": 20, "tube_outer_diameter": 20, "tube_inner_diameter": 14, "slot_center_distance": 14, "slot_to_tube_center": 18, "boss_radius": 5, "slot_radius": 3, "base_end_radius": 10},
        "p8": {"base_thickness": 8, "base_width": 40, "nose_radius": 9, "nose_to_base_holes": 17, "base_holes_to_back": 30, "base_holes_to_wall_front": 22, "base_hole_spacing": 26, "base_hole_diameter": 8, "wall_hole_spacing": 26, "wall_hole_height": 32, "wall_hole_diameter": 8, "ear_radius": 7, "notch_radius": 6.5, "rib_length": 14, "rib_height": 14, "rib_width": 8},
    }
    async def run():
        for case in data:
            rows = []
            async def step(name, plane, offset, geometry, constraints, kind, length=None, **feature_options):
                base = {"host_id": "freecad", "document": DOC, "operation_id": str(uuid4()), "body_ref": "Body", "name": name}
                validate({**base, "support": {"plane": plane, "offset": offset/1000}, "geometry": geometry, "constraints": constraints}, definitions()["host.sketch"][1])
                feature = {"kind": kind, "sketch_ref": name+"Sketch", **feature_options}
                if length is not None:
                    feature["length"] = length/1000
                validate({**base, "feature": feature}, definitions()["host.feature"][1])
                if case == "p7" and name == "Bore":
                    assert (plane, offset, length) == ("XY", 0, None)
                    assert feature_options == {"through_all": True, "reversed": True}
                rows.append((name, plane, offset, length))
                return {"feature_ref": name}
            await build(case, data[case], step)
            assert len(rows) == 5
            if case == "p7": assert ("Tube", "XY", 8, 12) in rows
            else: assert ("Rib", "XZ", -4, 8) in rows
    asyncio.run(run())


def test_solidworks_typed_route_preserves_session_and_request_identity(tmp_path, monkeypatch):
    project = Project.create(tmp_path / "project")
    hosts = Hosts(tmp_path)
    config = {"host_id": "sw", "host": "solidworks", "session_id": "instance"}
    monkeypatch.setattr(hosts, "discover", lambda: [config])
    calls = []
    def request(c, method, params):
        calls.append((method, deepcopy(params)))
        if method == "model.context":
            return {"host_instance": "instance", "documents": [], "capabilities": sorted(m.WRITE_METHODS)}
        assert params["session_id"] == "instance"
        path = Path(params["path"]); path.write_bytes(b"native-copy")
        return {"path": str(path), "document": DOC, "file_exists": True, "outcome": "committed", "operation_id": params["operation_id"]}
    monkeypatch.setattr(hosts, "_request", request)
    operation = str(uuid4())
    result = Commands(hosts).call("host.model_new", {"host_id": "sw", "host_instance": "instance", "operation_id": operation, "path": "part.sldprt", "name": "Body"}, project)
    assert result["document"] == DOC and project.is_working_copy(result["path"], "solidworks")
    saved = project.copy_operation(operation)
    assert saved["params"]["session_id"] == "instance"
    assert saved["fingerprint"] == _fingerprint("model.new", calls[-1][1])


def test_old_host_terminal_receipt_does_not_authorize_restarted_session(host):
    project, hosts, context, calls, replies = host
    operation = str(uuid4())
    replies["model.new"] = {"error": {"outcome": "unknown"}}
    hosts.command("freecad", "model.new", {"host_instance": "instance", "operation_id": operation, "path": "new.FCStd", "name": "Body"}, project)
    saved = project.copy_operation(operation)
    path = project.path / "new.FCStd"; path.write_bytes(b"previous-host")
    replies["model.operation"] = {"state": "finished", "host_instance": "instance", "fingerprint": saved["fingerprint"], "result": {"operation_id": operation, "outcome": "committed", "path": str(path), "document": DOC, "file_exists": True}}
    context["host_instance"] = "restarted"
    hosts.command("freecad", "model.operation", {"operation_id": operation}, project)
    assert not project.is_working_copy(path, "freecad")


def test_expression_driven_freecad_parameter_is_not_writable(native):
    module, _, _ = native
    pad = SimpleNamespace(TypeId="PartDesign::Pad", Length=SimpleNamespace(Value=8),
                          ExpressionEngine=[("Length", "Spreadsheet.Length")], isDerivedFrom=lambda typ: False)
    assert module._editable(pad) == []
    pad.ExpressionEngine = []
    assert module._editable(pad) == [{"name": "Length", "unit": "m", "value": .008}]


def test_sketch_parameters_use_probed_constraint_properties(native):
    # FreeCAD 1.1.4 api-probe.json：Constraint.Name/Driving；Sketch 无
    # getConstraintName/isDriving。替身不提供这两个不存在的方法。
    module, _, _ = native
    constraints = [SimpleNamespace(Name=name, Type=kind, Value=value, Driving=driving)
                   for name, kind, value, driving in [
                       ("Diameter", "Diameter", 8, True),
                       ("Angle", "Angle", 1.2, True),
                       ("Reference", "Distance", 9, False),
                       ("", "Radius", 3, True),
                       ("Horizontal", "Horizontal", 0, True)]]
    sketch = SimpleNamespace(Constraints=constraints, ExpressionEngine=[], isDerivedFrom=lambda typ: True)
    assert module._editable(sketch) == [{"name": "Diameter", "value": .008, "unit": "m"},
                                        {"name": "Angle", "value": 1.2, "unit": "rad"}]
    sketch.ExpressionEngine = [("Constraints.Diameter", "Sheet.Diameter"), ("Constraints[1]", "Sheet.Angle")]
    assert module._editable(sketch) == []


def test_named_constraint_creation_and_duplicate_rejection(native):
    module, _, _ = native
    class Sketch:
        GeometryCount = 1
        Geometry = [SimpleNamespace(TypeId="Part::GeomCircle")]
        def __init__(self): self.Constraints = []
        def addConstraint(self, constraints):
            indices = list(range(len(self.Constraints), len(self.Constraints)+len(constraints)))
            self.Constraints.extend(constraints)
            return indices
        def renameConstraint(self, index, name): self.Constraints[index].Name = name
    module.Sketcher.Constraint = lambda kind, *args: SimpleNamespace(Name="", Type=kind, Args=args)
    sketch = Sketch()
    constraint = {"kind": "diameter", "entities": [{"geometry": 0}], "value": .008, "name": "Diameter"}
    assert module._constraints(sketch, [constraint]) == ([0], [{"input_index": 0, "native_indices": [0]}])
    assert sketch.Constraints[0].Name == "Diameter" and sketch.Constraints[0].Args == (0, 8)
    with pytest.raises(ValueError, match="名称重复"):
        module._constraints(sketch, [constraint])


@pytest.mark.parametrize("kind,unit,value,native_value", [("Diameter", "Length", .012, 12), ("Angle", "Angle", 1.5707963267948966, 90)])
def test_named_sketch_dimension_edit_converts_units(native, kind, unit, value, native_value):
    module, _, doc = native
    quantities = []
    def quantity(value, unit):
        quantities.append((value, unit))
        return SimpleNamespace(Value=value, Unit=unit)
    module.App.Units = SimpleNamespace(Quantity=quantity, Length="length-unit", Angle="angle-unit")
    constraint = SimpleNamespace(Name="Dimension", Type=kind, Value=1, Driving=True)
    changed = []
    def set_datum(index, quantity):
        changed.append(index)
        constraint.Value = quantity.Value if unit == "Length" else quantity.Value*3.141592653589793/180
    sketch = SimpleNamespace(Name="Sketch", Constraints=[constraint], ExpressionEngine=[],
                             isDerivedFrom=lambda typ: typ == "Sketcher::SketchObject", setDatum=set_datum, solve=lambda: 0)
    doc.getObject = lambda name: sketch
    result = module._mutate(doc, "model.feature_edit", {"feature_ref": "Sketch", "parameter": "Dimension", "value": value})
    assert changed == [0] and quantities == [(native_value, getattr(module.App.Units, unit))]
    assert result["editable_parameters"][0]["value"] == pytest.approx(value)
    constraint.Driving = False
    with pytest.raises(ValueError, match="editable_parameters"):
        module._mutate(doc, "model.feature_edit", {"feature_ref": "Sketch", "parameter": "Dimension", "value": value})
    assert changed == [0]


def test_feature_acceptance_can_submit_named_sketch():
    from tests.e2e.native_modeling_features import exercise
    class Submitted(Exception): pass
    async def call(tool, fields):
        if tool == "host.model_new":
            return {"document": DOC, "body_ref": "Body"}
        assert tool == "host.sketch" and fields["name"] == "Profile"
        validate({"host_id": "freecad", **fields}, definitions()[tool][1])
        raise Submitted
    with pytest.raises(Submitted):
        asyncio.run(exercise(call, DOC["host_instance"]))


def test_merged_bridge_keeps_inspection_and_modeling_routes(native, monkeypatch):
    import freecad.gongke
    module, state, _ = native
    monkeypatch.setitem(sys.modules, "FreeCADGui", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "PySide", SimpleNamespace(QtCore=SimpleNamespace()))
    spec = importlib.util.spec_from_file_location("bridge_modeling_unit", ROOT / "freecad/gongke/bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    monkeypatch.setattr(freecad.gongke, "native_modeling", module, raising=False)
    calls = []
    def inspect(state, method, params):
        calls.append(("read", method, params))
        return {"capabilities": ["model.context", "model.inspect"]} if method == "model.context" else {"state": "ready"}
    def model(state, method, params):
        calls.append(("write", method, params))
        return {"outcome": "committed"}
    monkeypatch.setattr(module.read, "dispatch", inspect, raising=False)
    monkeypatch.setitem(sys.modules, "freecad.gongke.native_inspection", module.read)
    monkeypatch.setattr(module, "dispatch", model)
    context = bridge.DocumentState.inspect_host(state, "model.context", {})
    assert set(module.METHODS) <= set(context["capabilities"])
    assert bridge.DocumentState.inspect_host(state, "model.inspect", {"document": DOC}) == {"state": "ready"}
    assert bridge.DocumentState.inspect_host(state, "model.rebuild", {"document": DOC}) == {"outcome": "committed"}
    assert calls == [("read", "model.context", {}), ("read", "model.inspect", {"document": DOC}), ("write", "model.rebuild", {"document": DOC})]


@pytest.mark.parametrize("extent", [{"through_all": True, "length": .02}, {"through_all": False}, {}])
def test_pocket_requires_exactly_one_extent(extent):
    args = {"host_id": "freecad", "document": DOC, "operation_id": str(uuid4()), "body_ref": "Body", "name": "Bore",
            "feature": {"kind": "pocket", "sketch_ref": "BoreSketch", **extent}}
    with pytest.raises(ValueError):
        validate(args, definitions()["host.feature"][1])


def test_through_pocket_sets_native_end_condition_and_hides_inactive_length(native, monkeypatch):
    # API 契约回归；真实切穿与加高后的圆环体积由 FreeCAD 验收检查。
    module, _, doc = native
    doc.Name = "Part"
    sketch = SimpleNamespace(Name="BoreSketch", Visibility=True)
    pocket = SimpleNamespace(Name="Bore", TypeId="PartDesign::Pocket", Type="Length", Length=SimpleNamespace(Value=5),
                             PropertiesList=[], ExpressionEngine=[], isDerivedFrom=lambda typ: False,
                             Shape=SimpleNamespace(isNull=lambda: False, isValid=lambda: True, Solids=[object()]))
    body = SimpleNamespace(Name="Body", Tip=SimpleNamespace(Name="Tube", Visibility=True), newObject=lambda typ, name: pocket)
    monkeypatch.setattr(module, "_object", lambda doc, name, type_id=None: body if name == "Body" else pocket)
    monkeypatch.setattr(module, "_member", lambda *args: sketch)
    monkeypatch.setattr(module, "_name", lambda doc, name: name)
    monkeypatch.setattr(module, "_rebuild", lambda doc: [])
    monkeypatch.setitem(sys.modules, "FreeCADGui", SimpleNamespace(getDocument=lambda name: SimpleNamespace(activeView=lambda: SimpleNamespace(fitAll=lambda: None))))
    result = module._feature(doc, {"body_ref": "Body", "name": "Bore", "feature": {
        "kind": "pocket", "sketch_ref": "BoreSketch", "through_all": True, "reversed": True}})
    assert pocket.Profile is sketch and pocket.Type == "ThroughAll" and pocket.Reversed is True
    assert body.Tip is pocket and pocket.Length.Value == 5
    assert result["editable_parameters"] == []
    with pytest.raises(ValueError, match="editable_parameters"):
        module._mutate(doc, "model.feature_edit", {"feature_ref": "Bore", "parameter": "Length", "value": .03})
