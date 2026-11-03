"""无需 FreeCAD 的回归；仅验证属性契约和探查记录，不声称原生几何通过。"""
import importlib.util
import json
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("driving", [True, False])
def test_constraint_summary_reads_constraint_properties(monkeypatch, driving):
    monkeypatch.setitem(sys.modules, "FreeCAD", ModuleType("FreeCAD"))
    monkeypatch.setitem(sys.modules, "Part", ModuleType("Part"))
    spec = importlib.util.spec_from_file_location("inspection_constraint_test", ROOT / "freecad/gongke/native_inspection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 不提供 getConstraintName/isDriving；名字与状态只存在于 Constraint。
    dimensional = SimpleNamespace(Type="Diameter", Name="Bore", Value=42.0,
                                  First=0, Second=-2000, Driving=driving)
    geometric = SimpleNamespace(Type="Horizontal", Name="", First=1, Second=-2000)
    sketch = SimpleNamespace(
        Document=object(), Name="Sketch", Label="草图", TypeId="Sketcher::SketchObject",
        State=[], PropertiesList=[], OutList=[], Constraints=[dimensional, geometric],
        isDerivedFrom=lambda typ: typ == "Sketcher::SketchObject",
        FullyConstrained=False, DoF=2, isValid=lambda: True, GeometryCount=2,
        ConflictingConstraints=[], RedundantConstraints=[],
    )
    summary = module.feature_tree(sketch)[0]["sketch"]
    assert summary["constraints"][0] == {
        "index": 0, "name": "Bore", "type": "Diameter", "value": .042, "unit": "m",
        "first": 0, "second": -2000, "driving": driving,
    }
    assert summary["constraints"][1]["value"] is None
    assert summary["constraints"][1]["driving"] is None
    assert summary["status"] == "under_constrained"


def test_probe_records_missing_members_and_continues(tmp_path):
    ns = runpy.run_path(str(ROOT / "tests/e2e/freecad_api_probe.py"), run_name="probe_helpers_test")
    probe = ns["Probe"]()

    class Example:
        Name = "example"
        PropertiesList = ["Name", "Broken"]

        def getTypeIdOfProperty(self, name):
            return "App::PropertyString"

        @property
        def Broken(self):
            raise RuntimeError("property unavailable")

    row = probe.capture("example", Example(), ("missing", "Name"), {
        "bad_call": lambda: 1/0, "good_call": lambda: [1, 2, 3],
    })
    assert "Name" in row["dir"]
    assert row["attributes"]["example.missing"]["type"] == "AttributeError"
    assert row["attributes"]["example.Name"]["value"] == "example"
    assert row["calls"]["example.good_call"]["value"] == [1, 2, 3]
    assert row["properties"]["example.property.Broken"]["type"] == "RuntimeError"
    assert len(probe.data["errors"]) == 3
    # 与实际入口同一写入函数，验证异常对象没有泄漏到 JSON。
    probe.write.__func__.__globals__["OUTPUT"] = tmp_path / "api-probe.json"
    probe.write()
    saved = json.loads((tmp_path / "api-probe.json").read_text())
    assert saved["objects"]["example"] == row
