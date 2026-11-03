"""主线程中的受限 PartDesign/Sketcher 写操作；不接收可执行代码。"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from uuid import UUID
import FreeCAD as App
import Part
import Sketcher

from freecad.gongke import native_inspection as read

WRITES = {"model.new", "model.copy", "model.body", "model.sketch", "model.feature",
          "model.feature_edit", "model.feature_delete", "model.rebuild", "model.save"}
METHODS = sorted(WRITES | {"model.operation"})
FEATURE_TYPES = {"pad": "PartDesign::Pad", "pocket": "PartDesign::Pocket", "revolve": "PartDesign::Revolution",
                 "hole": "PartDesign::Hole", "fillet": "PartDesign::Fillet", "chamfer": "PartDesign::Chamfer",
                 "mirror": "PartDesign::Mirrored", "linear_pattern": "PartDesign::LinearPattern", "polar_pattern": "PartDesign::PolarPattern"}
PARAMETERS = {"PartDesign::Pad": {"Length": "m"}, "PartDesign::Pocket": {"Length": "m"},
              "PartDesign::Revolution": {"Angle": "rad"}, "PartDesign::Hole": {"Diameter": "m", "Depth": "m"},
              "PartDesign::Fillet": {"Radius": "m"}, "PartDesign::Chamfer": {"Size": "m"},
              "PartDesign::LinearPattern": {"Length": "m", "Occurrences": "1"},
              "PartDesign::PolarPattern": {"Angle": "rad", "Occurrences": "1"}}


def _fingerprint(method, params):
    value = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for c in ("\u0085", "\u2028", "\u2029"):
        value = value.replace(c, "\\u" + format(ord(c), "04x"))
    return hashlib.sha256((method+"\n"+value).encode()).hexdigest()


def _journal_path(state, operation_id):
    return state.results_dir / "modeling" / (str(UUID(operation_id)) + ".json")


def _put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False)
        f.flush()
        import os
        os.fsync(f.fileno())
    temp.replace(path)


def _bound(state, ref, writable=True):
    if ref["host_instance"] != state.host_instance or ref["configuration"] != "":
        raise ValueError("宿主实例或配置已改变")
    session = state._session(ref["document_id"])
    if session["revision"] != ref["revision"]:
        raise ValueError("文档修订已改变，请重新读取")
    doc = session["doc"]
    state._writable(session)
    if writable and getattr(state, "modeling_copies", {}).get(ref["document_id"]) != doc.FileName:
        raise ValueError("只允许修改在本宿主会话中新建或复制的工作副本")
    return doc


def _object(doc, name, type_id=None):
    ob = doc.getObject(name)
    if ob is None or (type_id and not ob.isDerivedFrom(type_id)):
        raise ValueError("原生对象不存在或类型不符：" + name)
    return ob


def _member(body, name, type_id=None):
    ob = _object(body.Document, name, type_id)
    if ob not in body.Group:
        raise ValueError("对象不属于指定 Body："+name)
    return ob


def _name(doc, name):
    import re
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name) or doc.getObject(name):
        raise ValueError("对象名必须为尚未使用的 ASCII 标识符")
    return name


def _new_path(path):
    target = Path(path)
    if not target.is_absolute() or target.suffix.lower() != ".fcstd" or target.exists() or not target.parent.is_dir():
        raise ValueError("需要未使用的 .FCStd 绝对路径及已存在目录")
    return target


def _vector(point):
    return App.Vector(point[0]*1000, point[1]*1000, 0)


def _frame(sketch):
    p = sketch.getGlobalPlacement()
    return {"origin": read.vector(p.Base, .001), "u": read.vector(p.Rotation.multVec(App.Vector(1, 0, 0))),
            "v": read.vector(p.Rotation.multVec(App.Vector(0, 1, 0))), "normal": read.vector(p.Rotation.multVec(App.Vector(0, 0, 1)))}


def _sketch_status(sketch):
    return {"native_ref": sketch.Name, "fully_constrained": bool(sketch.FullyConstrained),
            "degrees_of_freedom": int(sketch.DoF), "conflicting_constraints": list(sketch.ConflictingConstraints),
            "redundant_constraints": list(sketch.RedundantConstraints), "valid": bool(sketch.isValid()),
            "status": "conflicting" if sketch.ConflictingConstraints else "redundant" if sketch.RedundantConstraints else
                      "invalid" if not sketch.isValid() else "fully_constrained" if sketch.FullyConstrained else "under_constrained"}


def _editable(ob):
    expressions = {path for path, _ in getattr(ob, "ExpressionEngine", [])}
    if ob.isDerivedFrom("Sketcher::SketchObject"):
        return [{"name": c.Name, "value": c.Value*(1 if c.Type == "Angle" else .001),
                 "unit": "rad" if c.Type == "Angle" else "m"}
                for i, c in enumerate(ob.Constraints) if c.Name and c.Driving
                and not {"Constraints."+c.Name, f"Constraints[{i}]"} & expressions and c.Type in {"Angle", "Diameter", "Radius", "Distance", "DistanceX", "DistanceY"}]
    if ob.TypeId == "PartDesign::Pocket" and ob.Type != "Length":
        # ThroughAll 的 Length 是闲置属性，不能把它作为有效切深提供给 Agent。
        return []
    return [{"name": key, "unit": unit, "value": float(getattr(ob, key).Value if unit != "1" else getattr(ob, key))*(.001 if unit == "m" else math.pi/180 if unit == "rad" else 1)}
            for key, unit in PARAMETERS.get(ob.TypeId, {}).items() if key not in expressions]


def _rebuild(doc):
    doc.recompute()
    issues = []
    for ob in doc.Objects:
        if ob.isDerivedFrom("Sketcher::SketchObject"):
            solver = _sketch_status(ob)
            if solver["status"] in {"conflicting", "redundant", "invalid"}:
                issues.append(solver)
        if any(s in ob.State for s in ("Invalid", "Error")):
            issues.append({"native_ref": ob.Name, "state": list(ob.State), "message": ob.getStatusString()})
    if issues:
        raise ValueError(json.dumps(issues, ensure_ascii=False))
    return [_sketch_status(o) for o in doc.Objects if o.isDerivedFrom("Sketcher::SketchObject")]


def _constraint_specs(sketch, data):
    """先验证原生重载签名；错误不能进入会使 FreeCAD 1.1.4 abort 的构造器。"""
    kind, entities = data["kind"], data["entities"]
    names = {"horizontal": "Horizontal", "vertical": "Vertical", "coincident": "Coincident", "tangent": "Tangent",
             "parallel": "Parallel", "perpendicular": "Perpendicular", "equal": "Equal", "distance": "Distance",
             "distance_x": "DistanceX", "distance_y": "DistanceY", "diameter": "Diameter", "radius": "Radius", "angle": "Angle", "fixed": "Block"}
    refs, types = [], []
    for ent in entities:
        index, point = ent["geometry"], ent.get("point", "whole")
        if type(index) is not int or not 0 <= index < sketch.GeometryCount:
            raise ValueError("草图几何索引不属于当前草图")
        geometry = sketch.Geometry[index]
        geometry_type = geometry.TypeId
        valid_points = {"Part::GeomLineSegment": {"whole", "start", "end"},
                        "Part::GeomCircle": {"whole", "center"},
                        "Part::GeomArcOfCircle": {"whole", "start", "end", "center"}}
        if point not in valid_points.get(geometry_type, set()):
            raise ValueError(f"{geometry_type} 不支持草图点 {point}")
        point_id = {"whole": None, "start": 1, "end": 2, "center": 3}[point]
        # Sketcher 的点编号按逆时针排列；三点圆弧的 OCCT StartPoint/EndPoint 保留输入方向。
        # 负法向圆弧交换编号，让工具的 start/end 始终指向输入端点（追加约束也一致）。
        if geometry_type == "Part::GeomArcOfCircle" and point_id in {1, 2} and geometry.Circle.Axis.z < 0:
            point_id = 3 - point_id
        refs.append([index] if point_id is None else [index, point_id])
        types.append(geometry_type)
    shape = tuple(len(ref) for ref in refs)
    signatures = {
        "fixed": {(1,), (2,)}, "horizontal": {(1,), (2, 2)}, "vertical": {(1,), (2, 2)},
        "coincident": {(2, 2)}, "parallel": {(1, 1)}, "equal": {(1, 1)},
        "tangent": {(1, 1), (2, 1), (1, 2), (2, 2)},
        "perpendicular": {(1, 1), (2, 1), (1, 2), (2, 2)},
        "radius": {(1,)}, "diameter": {(1,)}, "angle": {(1, 1), (2, 2)},
        "distance": {(1,), (2, 2), (2, 1), (1, 2)},
        "distance_x": {(1,), (2,), (2, 2)}, "distance_y": {(1,), (2,), (2, 2)},
    }
    if shape not in signatures.get(kind, set()):
        raise ValueError(f"{kind} 不支持此实体/点组合；fixed 接受一个 whole 或点，coincident 接受两个点，数值约束须使用对应的几何或点")
    line = "Part::GeomLineSegment"
    if ((kind in {"horizontal", "vertical", "distance", "distance_x", "distance_y"} and shape == (1,) and types[0] != line)
            or (kind in {"parallel", "angle"} and any(t != line for t in types))
            or (kind in {"radius", "diameter"} and types[0] not in {"Part::GeomCircle", "Part::GeomArcOfCircle"})
            or (kind == "distance" and shape in {(1, 2), (2, 1)} and types[shape.index(1)] != line)
            or (kind == "equal" and (types[0] == line) != (types[1] == line))):
        raise ValueError(f"{kind} 的几何类型不匹配")
    name = data.get("name")
    if kind == "fixed" and shape == (2,):
        index, point = refs[0]
        position = sketch.getPoint(index, point)
        # 锁定点的位置，不锁住圆弧半径/端点；原点用重合，轴上用点在线上，避免零距离约束。
        if position.x == 0 and position.y == 0:
            return [(("Coincident", index, point, -1, 1), name)]
        return [(("PointOnObject", index, point, axis) if value == 0 else
                 (dimension, index, point, float(value)), name + suffix if name else None)
                for dimension, value, axis, suffix in (("DistanceX", position.x, -2, "_X"), ("DistanceY", position.y, -1, "_Y"))]
    if shape == (1, 2):
        refs.reverse()  # 原生点到曲线重载的点必须在前。
    args = [arg for ref in refs for arg in ref]
    if kind in {"distance", "distance_x", "distance_y", "diameter", "radius", "angle"}:
        value = float(data["value"]) * (1 if kind == "angle" else 1000)
        if not math.isfinite(value) or (kind in {"radius", "diameter"} and value <= 0):
            raise ValueError("约束尺寸必须有限，半径/直径必须为正")
        args.append(value)  # float 明确区分 C++ 的几何索引与数值重载。
    return [((names[kind], *args), name)]


def _constraints(sketch, data):
    specs = [spec for item in data for spec in _constraint_specs(sketch, item)]
    names = [c.Name for c in sketch.Constraints if c.Name]
    for _, name in specs:
        if name:
            if name in names:
                raise ValueError("草图约束名称重复：" + name)
            names.append(name)
    if not specs:
        return []
    indices = list(sketch.addConstraint([Sketcher.Constraint(*args) for args, _ in specs]))
    for index, (_, name) in zip(indices, specs):
        if name:
            sketch.renameConstraint(index, name)
    return indices


def _solved_geometry(sketch):
    """回传求解后的局部几何，让 Agent 在拉伸前发现欠约束漂移。"""
    rows = []
    def xy(point):
        return [point.x / 1000, point.y / 1000]
    for index, geometry in enumerate(sketch.Geometry):
        row = {"index": index, "native_ref": f"{sketch.Name}.Geometry{index}", "type": geometry.TypeId}
        if geometry.TypeId in {"Part::GeomLineSegment", "Part::GeomArcOfCircle"}:
            row.update(start=xy(geometry.StartPoint), end=xy(geometry.EndPoint))
        if geometry.TypeId in {"Part::GeomCircle", "Part::GeomArcOfCircle"}:
            circle = geometry.Circle if geometry.TypeId == "Part::GeomArcOfCircle" else geometry
            row.update(center=xy(circle.Center), radius=circle.Radius / 1000)
        rows.append(row)
    return rows


def _sketch(doc, p):
    body = _object(doc, p["body_ref"], "PartDesign::Body")
    if p.get("sketch_ref"):
        if "support" in p or "name" in p:
            raise ValueError("追加草图不接受 name/support")
        sketch = _member(body, p["sketch_ref"], "Sketcher::SketchObject")
    else:
        previous = body.Tip
        sketch = body.newObject("Sketcher::SketchObject", _name(doc, p["name"]))
        support = p["support"]
        if "face_ref" in support:
            name, face = support["face_ref"].rsplit(".", 1)
            parent = body if name == body.Name else _member(body, name)
            if not face.startswith("Face") or not isinstance(parent.Shape.getElement(face).Surface, Part.Plane):
                raise ValueError("草图支持面必须是当前 Body 的平面")
            # Body.FaceN 指向当前 Tip，不能把后续草图挂回整个 Body 形成循环依赖。
            parent = previous if parent == body else parent
            sketch.AttachmentSupport = (parent, [face])
            sketch.MapMode = "FlatFace"
        else:
            plane = support["plane"]
            sketch.AttachmentSupport = (_origin(body, plane+"_Plane"), [""])
            sketch.MapMode = "FlatFace"
            sketch.AttachmentOffset = App.Placement(App.Vector(0, 0, support.get("offset", 0)*1000), App.Rotation())
    added, constraints = [], []
    for g in p["geometry"]:
        kind = g["kind"]
        construction = g.get("construction", False)
        if kind == "rectangle":
            a, c = g["start"], g["end"]
            points = [a, [c[0], a[1]], c, [a[0], c[1]]]
            ids = [sketch.addGeometry(Part.LineSegment(_vector(points[i]), _vector(points[(i+1)%4])), construction) for i in range(4)]
            for i in range(4):
                constraints.append(sketch.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i+1)%4], 1)))
                constraints.append(sketch.addConstraint(Sketcher.Constraint("Horizontal" if i%2 == 0 else "Vertical", ids[i])))
        else:
            geometry = (Part.LineSegment(_vector(g["start"]), _vector(g["end"])) if kind == "line" else
                        Part.Circle(_vector(g["center"]), App.Vector(0, 0, 1), g["radius"]*1000) if kind == "circle" else
                        Part.Arc(_vector(g["start"]), _vector(g["mid"]), _vector(g["end"])))
            ids = [sketch.addGeometry(geometry, construction)]
        added.append(ids)
    constraints.extend(_constraints(sketch, p["constraints"]))
    code = sketch.solve()
    if code != 0:
        raise ValueError(json.dumps({"solve_code": code, **_sketch_status(sketch)}, ensure_ascii=False))
    return {"native_ref": sketch.Name, "sketch_ref": sketch.Name, "body_ref": body.Name, "added_geometry": added,
            "geometry": _solved_geometry(sketch),
            "added_constraints": constraints, "solver": _sketch_status(sketch), "editable_parameters": _editable(sketch)}


def _origin(body, kind):
    return next(o for o in body.Origin.OriginFeatures if o.Role == kind)


def _feature(doc, p):
    body = _object(doc, p["body_ref"], "PartDesign::Body")
    data, previous = p["feature"], body.Tip
    kind = data["kind"]
    sketch = _member(body, data["sketch_ref"], "Sketcher::SketchObject") if "sketch_ref" in data else None
    ob = body.newObject(FEATURE_TYPES[kind], _name(doc, p["name"]))
    if sketch:
        ob.Profile = sketch
        ob.Reversed = data.get("reversed", False)
    if kind == "pocket" and data.get("through_all"):
        ob.Type = "ThroughAll"
    elif kind in {"pad", "pocket"}:
        ob.Length = data["length"]*1000
    elif kind == "hole":
        ob.Diameter = data["diameter"]*1000
        ob.Depth = data["length"]*1000
        ob.DepthType = 0  # 有限深度，官方 PartDesign TestHole 的枚举
        ob.DrillPoint = 0  # 平底
        ob.Threaded = False
    elif kind == "revolve":
        ob.ReferenceAxis = (sketch, ["H_Axis" if data["axis"] == "horizontal" else "V_Axis"])
        ob.Angle = math.degrees(data["angle"])
    elif kind in {"fillet", "chamfer"}:
        if previous is None:
            raise ValueError("修饰特征需要实体")
        edges = []
        for ref in data["edges"]:
            name, edge = ref.rsplit(".", 1)
            if name not in {body.Name, previous.Name} or not edge.startswith("Edge"):
                raise ValueError("必须使用当前 Body/Tip 的实际边引用")
            previous.Shape.getElement(edge)
            edges.append(edge)
        ob.Base = (previous, edges)
        setattr(ob, "Radius" if kind == "fillet" else "Size", data["radius" if kind == "fillet" else "size"]*1000)
    else:
        originals = [_member(body, name) for name in data["features"]]
        if any(o == ob for o in originals):
            raise ValueError("特征不能引用自身")
        ob.Originals = originals
        if kind == "mirror":
            ob.MirrorPlane = (_origin(body, data["plane"]+"_Plane"), [""])
        elif kind == "linear_pattern":
            ob.Direction = (_origin(body, data["axis"]+"_Axis"), [""])
            ob.Length = data["spacing"]*(data["count"]-1)*1000
            ob.Occurrences = data["count"]
        else:
            ob.Axis = (_origin(body, data["axis"]+"_Axis"), [""])
            ob.Angle = math.degrees(data["angle"])
            ob.Occurrences = data["count"]
    if "Refine" in ob.PropertiesList:
        ob.Refine = True
    _rebuild(doc)
    if ob.Shape.isNull() or not ob.Shape.isValid() or len(ob.Shape.Solids) != 1:
        raise ValueError("特征未生成有效单实体：" + ob.getStatusString())
    body.Tip = ob
    if previous:
        previous.Visibility = False
    if sketch:
        sketch.Visibility = False
    ob.Visibility = True
    import FreeCADGui as Gui
    Gui.getDocument(doc.Name).activeView().fitAll()
    return {"native_ref": ob.Name, "feature_ref": ob.Name, "body_ref": body.Name, "object_ref": body.Name,
            "editable_parameters": _editable(ob)}


def _mutate(doc, method, p):
    if method == "model.body":
        ob = doc.addObject("PartDesign::Body", _name(doc, p["name"]))
        return {"native_ref": ob.Name, "body_ref": ob.Name}
    if method == "model.sketch":
        return _sketch(doc, p)
    if method == "model.feature":
        return _feature(doc, p)
    if method in {"model.feature_edit", "model.feature_delete"}:
        ob = _object(doc, p["feature_ref"])
        if method == "model.feature_delete":
            if ob.TypeId not in PARAMETERS and ob.TypeId != "PartDesign::Mirrored" and not ob.isDerivedFrom("Sketcher::SketchObject"):
                raise ValueError("只能删除建模特征或草图，不能删除 Body/基准对象")
            dependents = [o.Name for o in ob.InList if o.TypeId != "PartDesign::Body"]
            if dependents:
                raise ValueError("特征有下游依赖：" + ", ".join(dependents))
            body = ob.getParentGeoFeatureGroup()
            previous = [o for o in body.Group if o != ob and o.isDerivedFrom("PartDesign::Feature")] if body else []
            doc.removeObject(ob.Name)
            if body:
                body.Tip = previous[-1] if previous else None
            return {"deleted_ref": p["feature_ref"]}
        parameter = p["parameter"]
        allowed = {row["name"]: row for row in _editable(ob)}
        if parameter not in allowed:
            raise ValueError("只允许修改 editable_parameters 中的尺寸")
        value = p["value"]
        unit = allowed[parameter]["unit"]
        if unit == "1" and (value < 2 or int(value) != value):
            raise ValueError("阵列数量须为至少2的整数")
        if ob.isDerivedFrom("Sketcher::SketchObject"):
            index = next(i for i, c in enumerate(ob.Constraints) if c.Name == parameter)
            ob.setDatum(index, App.Units.Quantity(value*1000, App.Units.Length) if unit == "m" else App.Units.Quantity(math.degrees(value), App.Units.Angle))
            if ob.solve() != 0:
                raise ValueError(json.dumps(_sketch_status(ob), ensure_ascii=False))
        else:
            setattr(ob, parameter, int(value) if unit == "1" else value*(1000 if unit == "m" else 180/math.pi))
        return {"native_ref": ob.Name, "feature_ref": ob.Name, "editable_parameters": _editable(ob)}
    if method == "model.rebuild":
        return {}
    raise ValueError("未知建模写操作")


def dispatch(state, method, p):
    if method not in METHODS:
        raise ValueError("未知建模命令")
    path = _journal_path(state, p["operation_id"])
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if method == "model.operation":
        return old or {"state": "not_found", "outcome": "unknown", "operation_id": p["operation_id"], "host_instance": state.host_instance}
    fingerprint = _fingerprint(method, p)
    if old:
        if old["fingerprint"] != fingerprint:
            raise ValueError("operation_id 已用于另一请求")
        return old.get("result", {"error": {"code": "operation_incomplete", "message": "查询原操作并读回，禁止重发", "outcome": "unknown"}})
    record = {"operation_id": p["operation_id"], "host_instance": state.host_instance, "fingerprint": fingerprint,
              "method": method, "state": "started", "outcome": "unknown"}
    _put(path, record)
    doc, transaction, changed = None, False, False
    try:
        if method in {"model.new", "model.copy"}:
            target = _new_path(p["path"])
            if method == "model.new":
                if p["host_instance"] != state.host_instance:
                    raise ValueError("宿主实例已改变")
                changed = True
                doc = App.newDocument("NativePart")
                doc.UndoMode = 1
                state._session_for_document(doc)
                body = doc.addObject("PartDesign::Body", _name(doc, p["name"]))
                doc.recompute()
                doc.saveAs(str(target))
                result = {"body_ref": body.Name, "native_ref": body.Name}
            else:
                source = _bound(state, p["document"], writable=False)
                changed = True
                source.saveCopy(str(target))
                doc = App.openDocument(str(target))
                state._session_for_document(doc)
                doc.UndoMode = 1
                result = {"bodies": [o.Name for o in doc.Objects if o.TypeId == "PartDesign::Body"]}
            if not target.is_file():
                raise ValueError("宿主未生成文件")
            if not hasattr(state, "modeling_copies"):
                state.modeling_copies = {}
            state.modeling_copies[state._session_for_document(doc)] = doc.FileName
            result.update(path=doc.FileName, file_exists=True)
        else:
            doc = _bound(state, p["document"])
            if method == "model.save":
                changed = True
                doc.save()
                result = {"path": doc.FileName, "file_exists": Path(doc.FileName).is_file()}
            else:
                doc.UndoMode = 1
                doc.openTransaction("构想引擎原生建模")
                transaction = changed = True
                result = _mutate(doc, method, p)
                result["sketches"] = _rebuild(doc)
                if method == "model.sketch":
                    result["frame"] = _frame(doc.getObject(result["sketch_ref"]))
                doc.commitTransaction()
                transaction = False
                state._edited(doc)
        result.update(outcome="committed", document=read.document_ref(state, doc), operation_id=p["operation_id"])
    except Exception as exc:
        outcome = "unknown" if changed else "not_applied"
        if transaction:
            try:
                doc.abortTransaction()
                doc.recompute()
                outcome = "rolled_back"
            except Exception as rollback:
                exc = RuntimeError(str(exc) + "; 回滚失败：" + str(rollback))
        result = {"operation_id": p["operation_id"], "error": {"code": "modeling_failed", "message": str(exc), "outcome": outcome}}
        if doc:
            result["document"] = read.document_ref(state, doc)
    record.update(state="finished", outcome=result.get("outcome", result.get("error", {}).get("outcome")), result=result)
    try:
        _put(path, record)
    except OSError as exc:
        return {"error": {"code": "receipt_write_failed", "message": str(exc), "outcome": "unknown"}, "operation_id": p["operation_id"]}
    return result
