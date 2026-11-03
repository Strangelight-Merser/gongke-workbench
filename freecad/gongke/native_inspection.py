"""FreeCAD 主线程的通用只读采集。只复制形体，不绑定、求解、重算或保存文档。"""
from __future__ import annotations

import math
import FreeCAD as App
import Part


METHODS = ["host.info", "model.context", "model.inspect", "model.section"]


def direction(values):
    axis = App.Vector(*values)
    if axis.Length == 0:
        raise ValueError("方向向量不能为零")
    axis.normalize()
    return vector(axis)


def dot(a, b):
    return App.Vector(*a).dot(App.Vector(*b))


def line_point(point, axis):
    p, n = App.Vector(*point), App.Vector(*axis)
    n.normalize()
    return vector(p-n*p.dot(n))


def vector(value, scale=1):
    return [float(v)*scale for v in (value.x, value.y, value.z)]


def document_ref(state, doc):
    sid = state._session_for_document(doc)
    return {"host_instance": state.host_instance, "document_id": sid,
            "revision": state.sessions[sid]["revision"], "configuration": ""}


def context(state):
    def describe(doc):
        objects = []
        for item in doc.Objects:
            if not hasattr(item, "Shape") or item.Shape.isNull():
                continue
            parent = item.getParentGeoFeatureGroup()
            if item.TypeId != "PartDesign::Body" and parent is not None and parent.TypeId == "PartDesign::Body":
                continue
            objects.append({"native_ref": item.Name, "label": item.Label, "kind": item.TypeId})
        return {"document": document_ref(state, doc), "name": doc.Name, "path": doc.FileName, "objects": objects}
    docs = [describe(doc) for doc in App.listDocuments().values()]
    return {"host_instance": state.host_instance, "kind": "freecad", "capabilities": METHODS,
            "active_document": document_ref(state, App.ActiveDocument) if App.ActiveDocument else None, "documents": docs}


def bound(state, reference, object_ref):
    if reference["host_instance"] != state.host_instance or reference["configuration"] != "":
        raise ValueError("宿主实例或配置已改变，请重新读取上下文")
    session = state._session(reference["document_id"])
    if session["revision"] != reference["revision"]:
        raise ValueError("模型修订已改变，请重新读取上下文")
    obj = session["doc"].getObject(object_ref)
    if obj is None or not hasattr(obj, "Shape") or obj.Shape.isNull():
        raise ValueError("对象已删除或没有 B-rep 形体")
    return obj


def world_shape(obj):
    shape = obj.Shape.copy()
    # Shape 自带对象 Placement；仅左乘父级变换，不能重复乘对象 Placement。
    shape.Placement = obj.getGlobalPlacement().multiply(obj.Placement.inverse()).multiply(shape.Placement)
    return shape


def parameters(obj):
    result = []
    quantity_types = {"App::PropertyLength": ("m", .001), "App::PropertyDistance": ("m", .001),
                      "App::PropertyAngle": ("rad", math.pi/180), "App::PropertyArea": ("m^2", 1e-6),
                      "App::PropertyVolume": ("m^3", 1e-9)}
    for name in obj.PropertiesList:
        typ = obj.getTypeIdOfProperty(name)
        if typ in quantity_types:
            unit, scale = quantity_types[typ]
            result.append({"name": name, "value": float(getattr(obj, name).Value)*scale, "unit": unit})
        elif typ in {"App::PropertyFloat", "App::PropertyInteger", "App::PropertyBool", "App::PropertyEnumeration", "App::PropertyString"}:
            result.append({"name": name, "value": getattr(obj, name), "unit": "1" if typ in {"App::PropertyFloat", "App::PropertyInteger"} else None})
    return result


def feature_tree(obj):
    seen, result = set(), []
    def visit(item, parent=None):
        if item.Document != obj.Document or item.Name in seen:
            return
        seen.add(item.Name)
        row = {"native_ref": item.Name, "parent": parent, "label": item.Label, "type": item.TypeId,
               "state": list(item.State), "parameters": parameters(item),
               "dependencies": [x.Name for x in item.OutList],
               "expressions": [[p, e] for p, e in getattr(item, "ExpressionEngine", [])]}
        if item.isDerivedFrom("Sketcher::SketchObject"):
            constraints = []
            for i, c in enumerate(item.Constraints):
                typ = c.Type
                unit = "rad" if typ in {"Angle", "AngleViaPoint"} else "m" if typ in {"Distance", "DistanceX", "DistanceY", "Radius", "Diameter"} else None
                constraints.append({"index": i, "name": c.Name, "type": typ,
                                    "value": float(c.Value)*(.001 if unit == "m" else 1) if unit else None,
                                    "unit": unit, "first": c.First, "second": c.Second,
                                    "driving": bool(c.Driving) if unit else None})
            row["sketch"] = {"fully_constrained": bool(item.FullyConstrained),
                             "degrees_of_freedom": int(item.DoF), "valid": bool(item.isValid()),
                             "geometry_count": item.GeometryCount, "constraints": constraints,
                             "conflicting_constraints": list(item.ConflictingConstraints),
                             "redundant_constraints": list(item.RedundantConstraints),
                             "status": "conflicting" if item.ConflictingConstraints else "redundant" if item.RedundantConstraints else "invalid" if not item.isValid() else "fully_constrained" if item.FullyConstrained else "under_constrained"}
        result.append(row)
        for child in getattr(item, "Group", []):
            visit(child, item.Name)
        for child in item.OutList:
            visit(child, item.Name)
    visit(obj)
    return result


def edge_record(edge, ref):
    curve = edge.Curve
    record = {"native_ref": ref, "kind": "other", "length": edge.Length*.001,
              "start": vector(edge.valueAt(edge.FirstParameter), .001),
              "end": vector(edge.valueAt(edge.LastParameter), .001),
              "samples": [vector(edge.valueAt(edge.FirstParameter+(edge.LastParameter-edge.FirstParameter)*i/16), .001) for i in range(17)],
              "sampling": "parameter_uniform_16_segments_display_only"}
    if isinstance(curve, Part.Circle):
        record.update(kind="circle", radius=curve.Radius*.001, point=vector(curve.Center, .001), direction=vector(curve.Axis), angular_span=edge.Length/curve.Radius)
    elif isinstance(curve, Part.Line):
        record.update(kind="line", point=record["start"], direction=vector(curve.Direction))
    return record


def model_issues(obj, shape, features):
    issues = [{"native_ref": f["native_ref"], "state": f["state"]} for f in features
              if any(s in f["state"] for s in ("Touched", "Invalid", "Error"))
              or f.get("sketch", {}).get("status") in {"conflicting", "redundant", "invalid"}]
    if not shape.isValid():
        issues.append({"native_ref": obj.Name, "state": ["invalid_shape"]})
    return issues


def inspect(obj, reference):
    shape = world_shape(obj)
    features = feature_tree(obj)
    issues = model_issues(obj, shape, features)
    faces = []
    for i, face in enumerate(shape.Faces, 1):
        surface = face.Surface
        row = {"native_ref": f"{obj.Name}.Face{i}", "kind": "other", "area": face.Area*1e-6}
        if isinstance(surface, Part.Cylinder):
            axis, center = vector(surface.Axis), vector(surface.Center, .001)
            u0, u1, v0, v1 = face.ParameterRange
            pt = face.valueAt((u0+u1)/2, (v0+v1)/2)
            radial = pt-surface.Center
            radial -= surface.Axis*radial.dot(surface.Axis)
            row.update(kind="cylinder", radius=surface.Radius*.001, direction=axis,
                       point=line_point(center, axis), inward=face.normalAt((u0+u1)/2, (v0+v1)/2).dot(radial) < 0,
                       angular_span=abs(u1-u0))
        elif isinstance(surface, Part.Plane):
            axis = direction(vector(surface.Axis))
            point = vector(face.CenterOfMass, .001)
            row.update(kind="plane", point=[v*dot(point, axis) for v in axis], direction=axis)
        faces.append(row)
    # 显示网格可能在打开文档后才生成；工程尺寸不依赖三角网格的采样极值。
    bb = shape.optimalBoundingBox(False, False)
    return {"document": reference, "object_ref": obj.Name, "coordinate_system": "document", "length_unit": "m",
            "angle_unit": "rad", "state": "needs_rebuild" if issues else "ready", "issues": issues,
            "features": features, "faces": faces,
            "edges": [edge_record(edge, f"{obj.Name}.Edge{i}") for i, edge in enumerate(shape.Edges, 1)],
            "volume": shape.Volume*1e-9, "volume_unit": "m^3", "solid_count": len(shape.Solids),
            "bounds": {"min": [bb.XMin*.001, bb.YMin*.001, bb.ZMin*.001], "max": [bb.XMax*.001, bb.YMax*.001, bb.ZMax*.001]}}


def section(obj, reference, plane):
    normal = direction(plane["normal"])
    n = App.Vector(*normal)
    origin = App.Vector(*[v*1000 for v in plane["origin"]])
    shape = world_shape(obj)
    result = {"document": reference, "object_ref": obj.Name, "coordinate_system": "document", "length_unit": "m",
              "plane": {"origin": plane["origin"], "normal": normal}, "area_unit": "m^2"}
    if model_issues(obj, shape, feature_tree(obj)):
        return {**result, "status": "unknown", "reason": "model_not_ready", "edges": []}
    wires = shape.slice(n, n.dot(origin))
    edges = [edge_record(edge, f"section.Edge{i}") for i, edge in enumerate([e for w in wires for e in w.Edges], 1)]
    closed = all(w.isClosed() for w in wires)
    if not closed:
        return {**result, "status": "unknown", "reason": "open_section", "edges": edges}
    area = Part.makeFace(wires, "Part::FaceMakerBullseye").Area*1e-6 if wires else 0.0
    return {**result, "status": "ok", "area": area, "edges": edges, "wire_count": len(wires)}


def dispatch(state, method, params):
    if method == "host.info":
        return {"kind": "freecad", "host_instance": state.host_instance, "version": ".".join(App.Version()[:3]),
                "capabilities": METHODS}
    if method == "model.context":
        return context(state)
    if method not in {"model.inspect", "model.section"}:
        raise ValueError("未知只读模型命令")
    reference = params["document"]
    obj = bound(state, reference, params["object_ref"])
    result = inspect(obj, reference) if method == "model.inspect" else section(obj, reference, params["plane"])
    bound(state, reference, params["object_ref"])
    return result
