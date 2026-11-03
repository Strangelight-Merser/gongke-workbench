"""用 FreeCAD 自带 Python 探查本机 API，结果写入 out/model-inspection/api-probe.json。

不导入待修复的采集器；只在本进程新建临时文档，读取 STEP，不保存或修改样本。
每个属性/调用独立记错，API 缺失不阻断其他记录。特征未配置时明确标注。
"""
from pathlib import Path
import ast
import hashlib
import json
import math
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "out/model-inspection/api-probe.json"
SOURCES = ("freecad/gongke/native_inspection.py", "tests/e2e/model_inspection_freecad.py")


def encode(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    return {"python_type": f"{type(value).__module__}.{type(value).__name__}", "repr": repr(value)}


class Probe:
    def __init__(self):
        self.data = {"status": "running", "objects": {}, "operations": {}, "errors": [],
                     "units": "FreeCAD 原生长度 mm、面积 mm²、体积 mm³；约束 Angle.Value 为 rad"}

    def attempt(self, label, operation, records=None):
        """仅探查器隔离异常；生产采集器仍直接报告失败。"""
        records = self.data["operations"] if records is None else records
        try:
            value = operation()
            records[label] = {"status": "ok", "value": encode(value)}
            return value
        except Exception as error:
            records[label] = {"status": "error", "type": type(error).__name__,
                              "message": str(error), "traceback": traceback.format_exc()}
            self.data["errors"].append(label)
            return None

    def capture(self, label, obj, attributes=(), calls=None):
        row = {"python_type": f"{type(obj).__module__}.{type(obj).__name__}",
               "repr": repr(obj), "dir": sorted(dir(obj)), "attributes": {}, "calls": {}}
        self.data["objects"][label] = row
        for name in attributes:
            self.attempt(label + "." + name, lambda name=name: getattr(obj, name), row["attributes"])
        for name, operation in (calls or {}).items():
            self.attempt(label + "." + name, operation, row["calls"])
        # 动态工程属性带实际类型和值，不猜测不同 PartDesign 特征的属性名称。
        if "PropertiesList" in row["dir"]:
            row["properties"] = {}
            for name in obj.PropertiesList:
                self.attempt(label + ".property." + name,
                             lambda name=name: {"type": obj.getTypeIdOfProperty(name), "value": getattr(obj, name)},
                             row["properties"])
        return row

    def write(self):
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


OBJECT_ATTRS = ("Name", "Label", "TypeId", "State", "Document", "OutList", "ExpressionEngine",
                "PropertiesList", "Placement", "Shape")
SKETCH_ATTRS = ("Constraints", "Geometry", "GeometryCount", "DoF", "FullyConstrained",
                "ConflictingConstraints", "RedundantConstraints")
CONSTRAINT_ATTRS = ("Name", "Type", "Value", "Driving", "IsActive", "First", "FirstPos",
                    "Second", "SecondPos", "Third", "ThirdPos")


def document_object(probe, label, obj, extra=()):
    probe.capture(label, obj, OBJECT_ATTRS + extra, {
        "getGlobalPlacement()": lambda: obj.getGlobalPlacement(),
        "getParentGeoFeatureGroup()": lambda: obj.getParentGeoFeatureGroup(),
        "isDerivedFrom(Sketcher::SketchObject)": lambda: obj.isDerivedFrom("Sketcher::SketchObject"),
        "isValid()": lambda: obj.isValid(),
    })


def shape_probe(probe, label, shape, App, Part):
    probe.capture(label, shape, ("ShapeType", "Placement", "Volume", "Area", "Solids", "Faces", "Edges", "Wires", "BoundBox"), {
        "isNull()": shape.isNull, "isValid()": shape.isValid,
        "copy()": shape.copy,
        "exportBrepToString()": lambda: {"length": len(shape.exportBrepToString()),
            "sha256": hashlib.sha256(shape.exportBrepToString().encode()).hexdigest()},
    })
    probe.capture(label + ".BoundBox", shape.BoundBox, ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"))
    # 每个样本的每种曲面/曲线各取一例，避免遗漏非圆柱和非直线类型。
    seen = set()
    for i, face in enumerate(shape.Faces, 1):
        surface = face.Surface
        key = type(surface).__name__
        if key in seen:
            continue
        seen.add(key)
        base = f"{label}.Face{i}"
        probe.capture(base, face, ("Area", "Surface", "ParameterRange", "CenterOfMass", "Orientation"), {
            "valueAt(midpoint)": lambda: face.valueAt((face.ParameterRange[0]+face.ParameterRange[1])/2,
                                                     (face.ParameterRange[2]+face.ParameterRange[3])/2),
            "normalAt(midpoint)": lambda: face.normalAt((face.ParameterRange[0]+face.ParameterRange[1])/2,
                                                       (face.ParameterRange[2]+face.ParameterRange[3])/2),
        })
        attrs = ("Axis", "Center", "Radius") if isinstance(surface, Part.Cylinder) else ("Axis",) if isinstance(surface, Part.Plane) else ()
        probe.capture(base + ".Surface", surface, attrs)
    seen = set()
    for i, edge in enumerate(shape.Edges, 1):
        curve = edge.Curve
        key = type(curve).__name__
        if key in seen:
            continue
        seen.add(key)
        base = f"{label}.Edge{i}"
        probe.capture(base, edge, ("Curve", "Length", "FirstParameter", "LastParameter"), {
            "valueAt(first)": lambda: edge.valueAt(edge.FirstParameter),
            "valueAt(last)": lambda: edge.valueAt(edge.LastParameter),
            "valueAt(midpoint)": lambda: edge.valueAt((edge.FirstParameter+edge.LastParameter)/2),
        })
        attrs = ("Radius", "Center", "Axis") if isinstance(curve, Part.Circle) else ("Direction",) if isinstance(curve, Part.Line) else ()
        probe.capture(base + ".Curve", curve, attrs)
    if shape.Solids:
        probe.capture(label + ".Solid1", shape.Solids[0], ("ShapeType", "Volume", "Area"))
    # P8 漏筋验收使用 z=10 mm；同时探查 z=4 mm 穿过底板的截面。
    for height in (4.0, 10.0):
        base = f"{label}.slice_z{height:g}"
        wires = probe.attempt(base, lambda: shape.slice(App.Vector(0, 0, 1), height))
        if wires is None:
            continue
        for i, wire in enumerate(wires):
            probe.capture(f"{base}.Wire{i}", wire, ("Edges", "Length"), {"isClosed()": wire.isClosed})
        if wires:
            face = probe.attempt(base + ".makeFace", lambda: Part.makeFace(wires, "Part::FaceMakerBullseye"))
            if face is not None:
                probe.capture(base + ".section_face", face, ("Area", "ShapeType", "Faces"))


def native_probe(probe, doc, App, Part, Sketcher):
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5)
    probe.capture("Part.Circle", circle, ("Radius", "Center", "Axis"))
    sketch.addGeometry(circle, False)
    sketch.addConstraint(Sketcher.Constraint("Diameter", 0, 10.0))
    probe.attempt("native.Sketch.renameConstraint(0)", lambda: sketch.renameConstraint(0, "DiameterProbe"))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sketch
    pad.Length = 8
    body.Placement = App.Placement(App.Vector(100, 20, 30), App.Rotation(App.Vector(0, 1, 0), 90))
    doc.recompute()  # 只用于本探查进程创建的临时模型。
    document_object(probe, "native.Body", body, ("Group", "Tip"))
    document_object(probe, "native.Sketch", sketch, SKETCH_ATTRS)
    document_object(probe, "native.Pad", pad, ("Profile", "Length"))
    probe.capture("native.Pad.Length", pad.Length, ("Value", "Unit", "UserString"))
    for i, constraint in enumerate(sketch.Constraints):
        probe.capture(f"native.Constraint{i}", constraint, CONSTRAINT_ATTRS)
    # 检验历史报错的两个方法是否存在，仅读取；失败预期会进入 errors。
    probe.attempt("native.Sketch.getConstraintName(0)", lambda: sketch.getConstraintName(0))
    probe.attempt("native.Sketch.isDriving(0)", lambda: sketch.isDriving(0))
    probe.attempt("native.Sketch.getDatum(0)", lambda: sketch.getDatum(0))
    probe.attempt("native.shape_probe", lambda: shape_probe(probe, "native.Body.Shape", body.Shape, App, Part))
    def world_shape_probe():
        global_shape = body.Shape.copy()
        global_shape.Placement = body.getGlobalPlacement().multiply(body.Placement.inverse()).multiply(global_shape.Placement)
        shape_probe(probe, "native.Body.world_shape", global_shape, App, Part)
    probe.attempt("native.world_shape_probe", world_shape_probe)
    vector = App.Vector(1, 2, 3)
    probe.capture("App.Vector", vector, ("x", "y", "z", "Length"), {
        "dot()": lambda: vector.dot(App.Vector(0, 0, 1)),
        "arithmetic": lambda: vector - App.Vector(0, 0, 1)*vector.dot(App.Vector(0, 0, 1)),
        "normalize()": lambda: App.Vector(1, 2, 3).normalize(),
    })
    probe.capture("App.Placement", body.Placement, ("Base", "Rotation", "Matrix"), {
        "inverse()": body.Placement.inverse,
        "multiply(inverse())": lambda: body.Placement.multiply(body.Placement.inverse()),
    })
    probe.capture("App.Rotation", body.Placement.Rotation, ("Axis", "Angle", "Q"))
    # 独立的引用尺寸与几何约束，避免改变上面的验收草图。
    other = doc.addObject("Sketcher::SketchObject", "ReferenceSketch")
    other.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)), False)
    other.addConstraint(Sketcher.Constraint("Horizontal", 0))
    other.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
    probe.attempt("native.ReferenceSketch.setDriving(1, False)", lambda: other.setDriving(1, False))
    doc.recompute()
    document_object(probe, "native.ReferenceSketch", other, SKETCH_ATTRS)
    for i, constraint in enumerate(other.Constraints):
        probe.capture(f"native.ReferenceConstraint{i}", constraint, CONSTRAINT_ATTRS)


def run(probe):
    if sys.platform == "darwin":
        sys.path.append("/Applications/FreeCAD.app/Contents/Resources/lib")
    import FreeCAD as App
    import Part
    import Sketcher

    probe.data["freecad_version"] = App.Version()
    probe.data["python"] = {"executable": sys.executable, "version": sys.version}
    for label, module in (("FreeCAD", App), ("Part", Part), ("Sketcher", Sketcher)):
        probe.capture(label, module, ("__file__",))
    # 同时留下当前两份源码的成员调用清单、行号和哈希，便于核对覆盖范围。
    probe.data["source_api_usage"] = {}
    for relative in SOURCES:
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        probe.data["source_api_usage"][relative] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "attributes": sorted([{"expression": ast.unparse(n), "line": n.lineno}
                                  for n in ast.walk(tree) if isinstance(n, ast.Attribute)], key=lambda n: n["line"]),
        }
    probe.data["samples"] = {}
    for path in sorted((ROOT / "tests/fixtures/model_inspection").glob("*.step")):
        doc = App.newDocument("ApiProbeSample")
        try:
            def sample():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                obj = doc.addObject("PartDesign::Feature", "Imported")
                obj.Shape = Part.read(str(path))
                doc.recompute()
                document_object(probe, path.stem + ".Imported", obj)
                shape_probe(probe, path.stem + ".Shape", obj.Shape, App, Part)
                probe.data["samples"][path.name] = {"sha256": digest,
                    "unchanged": digest == hashlib.sha256(path.read_bytes()).hexdigest()}
            probe.attempt("sample." + path.name, sample)
        finally:
            App.closeDocument(doc.Name)
            probe.write()
    doc = App.newDocument("ApiProbeNative")
    try:
        probe.capture("App.Document", doc, ("Name", "FileName", "Objects"), {
            "getObject(missing)": lambda: doc.getObject("MissingObject"),
        })
        probe.attempt("native_setup_and_probe", lambda: native_probe(probe, doc, App, Part, Sketcher))
        probe.capture("App.Document.after_setup", doc, ("Name", "FileName", "Objects"))
        probe.attempt("FreeCAD.listDocuments()", App.listDocuments)
        probe.attempt("FreeCAD.ActiveDocument", lambda: App.ActiveDocument)
    finally:
        App.closeDocument(doc.Name)
        probe.write()
    # 常用 PartDesign 特征各自独立创建；无 Profile 的默认状态不是有效建模结果。
    for kind in ("Pocket", "Hole", "Fillet", "Chamfer", "Revolution", "Groove", "AdditiveBox"):
        doc = App.newDocument("ApiProbeFeature")
        try:
            def feature():
                body = doc.addObject("PartDesign::Body", "Body")
                obj = body.newObject("PartDesign::" + kind, kind)
                document_object(probe, "unconfigured." + kind, obj)
                probe.data["objects"]["unconfigured." + kind]["setup"] = "仅创建默认实例；未配置、未重算，不作为有效几何"
            probe.attempt("create.PartDesign::" + kind, feature)
        finally:
            App.closeDocument(doc.Name)
            probe.write()


if __name__ == "__main__":
    probe = Probe()
    try:
        run(probe)
        probe.data["status"] = "completed_with_errors" if probe.data["errors"] else "completed"
    except Exception as error:
        probe.data["status"] = "aborted"
        probe.data["fatal_error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    finally:
        probe.write()
        print(f"{probe.data['status']}: {OUTPUT} ({len(probe.data['errors'])} 项探查错误)")
    sys.exit(1 if probe.data["status"] == "aborted" else 0)
