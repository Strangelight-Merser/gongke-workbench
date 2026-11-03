"""在 FreeCAD 自带 Python 中运行；创建临时测试文档，不接触用户文档。

macOS（沙箱外）：
/Applications/FreeCAD.app/Contents/Resources/bin/python tests/e2e/model_inspection_freecad.py
结果：out/model-inspection/freecad.json。任何断言失败均返回非零。
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if sys.platform == "darwin":
    sys.path.append("/Applications/FreeCAD.app/Contents/Resources/lib")
import FreeCAD as App
import Part
import Sketcher
import freecad

# FreeCAD 初始化会加入已安装工作台路径；本独立验收进程必须检查当前 checkout。
sys.path.insert(0, str(ROOT))
freecad.__path__ = [str(ROOT / "freecad"), *freecad.__path__]
for name in list(sys.modules):
    if name == "freecad.gongke" or name.startswith("freecad.gongke."):
        del sys.modules[name]
if hasattr(freecad, "gongke"):
    del freecad.gongke
from freecad.gongke import bridge, native_inspection, native_shaft
from gongke_app import inspection

MODULE_SOURCES = {}
for module, relative in (
    (bridge, "freecad/gongke/bridge.py"),
    (native_inspection, "freecad/gongke/native_inspection.py"),
    (native_shaft, "freecad/gongke/native_shaft.py"),
    (inspection, "gongke_app/inspection.py"),
):
    source = Path(module.__file__).resolve()
    if source != ROOT / relative:
        raise RuntimeError(f"验收加载了其他工作台源码：{module.__name__}: {source}")
    MODULE_SOURCES[module.__name__] = str(source)
print(json.dumps({"module_sources": MODULE_SOURCES}, ensure_ascii=False), flush=True)

DocumentState = bridge.DocumentState
check = inspection.check

FIXTURES = ROOT / "tests/fixtures/model_inspection"
OUT = ROOT / "out/model-inspection"
OUT.mkdir(parents=True, exist_ok=True)
state = DocumentState(OUT)


def call(command, **params):
    return state.inspect_host(command, params)


CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
P7, P8, EXPECTED = CASES["p7"], CASES["p8"], CASES["expected"]


def baseline(doc):
    return [(o.Name, list(o.State), o.Shape.exportBrepToString() if hasattr(o, "Shape") else None) for o in doc.Objects]


def run():
    result = {"freecad_version": App.Version(), "module_sources": MODULE_SOURCES, "samples": {}}
    for name, expected in EXPECTED.items():
        path = FIXTURES / (name + ".step")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        doc = App.newDocument("InspectionFixture")
        try:
            obj = doc.addObject("PartDesign::Feature", "Imported")
            obj.Shape = Part.read(str(path))
            doc.recompute()  # 仅测试准备；采集期间禁止调用。
            context = call("model.context")
            document = next(d["document"] for d in context["documents"] if d["name"] == doc.Name)
            args = {"document": document, "object_ref": obj.Name}
            before = baseline(doc)
            snapshot = call("model.inspect", **args)
            report = check(snapshot, P7 if name.startswith("p7") else P8,
                           lambda plane: call("model.section", **args, plane=plane))
            assert baseline(doc) == before, "只读检查修改了文档"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            if expected == "pass":
                assert report["status"] == "pass", (name, report)
            else:
                row = next(r for r in report["checks"] if r["id"] == expected)
                assert row["status"] == "fail", (name, report)
            result["samples"][name] = {"sha256": digest, "snapshot": snapshot, "report": report, "unchanged": True}
        finally:
            App.closeDocument(doc.Name)
    # 原生草图、Body 放置及修订拒绝：STEP 无法验证这些内容。
    doc = App.newDocument("InspectionNative")
    try:
        body = doc.addObject("PartDesign::Body", "Body")
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5), False)
        sketch.addConstraint(Sketcher.Constraint("Diameter", 0, 10.0))
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 8
        body.Placement = App.Placement(App.Vector(100, 20, 30), App.Rotation(App.Vector(0, 1, 0), 90))
        doc.recompute()
        reference = next(d["document"] for d in call("model.context")["documents"] if d["name"] == doc.Name)
        args = {"document": reference, "object_ref": body.Name}
        before = baseline(doc)
        snapshot = call("model.inspect", **args)
        assert baseline(doc) == before
        native_sketch = next(f["sketch"] for f in snapshot["features"] if f["native_ref"] == "Sketch")
        assert native_sketch["degrees_of_freedom"] == 2
        assert native_sketch["fully_constrained"] is False
        face = next(f for f in snapshot["faces"] if f["kind"] == "cylinder")
        assert abs(abs(face["direction"][0])-1) < 1e-10
        assert max(abs(a-b) for a, b in zip(face["point"], [0, .02, .03])) < 1e-10
        pad.Length = 9
        try:
            call("model.inspect", **args)
        except ValueError:
            pass
        else:
            raise AssertionError("旧修订未被拒绝")
        result["native_sketch_and_placement"] = snapshot
    finally:
        App.closeDocument(doc.Name)
    result["status"] = "passed"
    return result


if __name__ == "__main__":
    try:
        result = run()
        (OUT / "freecad.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS: 8 STEP 样本、原生草图、全局放置、只读与过期修订")
    finally:
        App.removeDocumentObserver(state)
