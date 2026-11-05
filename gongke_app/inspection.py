"""跨宿主的只读量测和条件检查；不加载 CAD 内核，不推断设计意图。"""
from __future__ import annotations

import math


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties if required is None else required), "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
NUMBER = {"type": "number"}
VECTOR = {"type": "array", "items": NUMBER, "minItems": 3, "maxItems": 3}
DOCUMENT = obj({"host_instance": TEXT, "document_id": TEXT, "revision": {"type": "integer", "minimum": 0},
                "configuration": {"type": "string"}})
SELECTOR = obj({"native_ref": TEXT, "kind": {"enum": ["plane", "cylinder", "circle", "line", "other"]},
                "radius": {"type": "number", "exclusiveMinimum": 0}, "direction": VECTOR,
                "point": VECTOR, "near": VECTOR, "within": {"type": "number", "minimum": 0},
                "offset": NUMBER, "inward": {"type": "boolean"}}, [])
PLANE = obj({"origin": VECTOR, "normal": VECTOR})
METRICS = {"diameter": "m", "axis_distance": "m", "plane_distance": "m", "coordinate": "m",
           "edge_length": "m", "count": "1", "section_area": "m^2", "parameter": None}
MEASUREMENT = obj({"kind": {"enum": list(METRICS)}, "selectors": {"type": "array", "items": SELECTOR, "maxItems": 2},
                   "axis": {"enum": [0, 1, 2]}, "plane": PLANE, "feature": TEXT, "parameter": TEXT}, ["kind"])
EVIDENCE = obj({"path": TEXT, "sha256": TEXT, "page": {"type": "integer", "minimum": 1}, "item": TEXT})
DRAWING = obj({"path": TEXT, "sha256": TEXT, "page": {"type": "integer", "minimum": 1},
               "outline_seed": TEXT, "plane": PLANE,
               "axes": {"type": "array", "items": {"enum": [-3, -2, -1, 1, 2, 3]}, "minItems": 2, "maxItems": 2}})
CONDITION = obj({"id": TEXT, "source": TEXT, "measurement": MEASUREMENT, "expected": NUMBER,
                 "tolerance": {"type": "number", "minimum": 0}, "unit": {"enum": ["m", "mm", "m^2", "mm^2", "rad", "deg", "1"]}, "evidence": EVIDENCE},
                ["id", "source", "measurement", "expected", "tolerance", "unit"])
COMMON = {"host_id": TEXT, "document": DOCUMENT, "object_ref": TEXT}
NATIVE_METHODS = {"model.context", "model.inspect", "model.section"}


def definitions():
    return {
        "host.context": ("读取 FreeCAD/SOLIDWORKS 文档与对象身份、能力。支持未保存零件；后续读取须原样传回 document 和 object_ref。", obj({"host_id": TEXT}), False),
        "host.inspect": ("只读特征树、参数、草图约束及最终 B-rep 面/边；任意零件，不绑定、不重算。几何为 m/rad、document 坐标。圆柱面不等于通孔。", obj(COMMON), False),
        "host.section": ("按文档坐标的平面读取精确截面；origin 为 m，normal 为非零方向。只在临时几何上计算，不创建文档特征。", obj({**COMMON, "plane": PLANE}), False),
        "host.measure": ("从当前 B-rep 测尺寸；selectors 用实际 native_ref 或几何筛选，多个匹配返回歧义。优先使用 inspect 返回的 native_ref；near 比较返回实体的 point（默认容差 1e-8 m），不是到面上任意点的距离，不能随意取面内坐标。平面可用 kind=plane、direction 和 offset 筛选。plane_distance 是平行面的支撑平面距离，不自动等于局部壁厚；axis_distance 是平行轴距。", obj({**COMMON, "measurement": MEASUREMENT}), False),
        "host.check": ("对照检查。自填 expected/source 仅作 Agent 自检，匹配也返回 unverified（未经独立核对）。图纸标注须 evidence 引用 read_drawing 的 path/sha256/page/item，服务端复读纯数值标注（mm）。drawing 可独立比对矢量 PDF 完整直线轮廓：outline_seed 为外轮廓边 source，axes 为页面向右/向上的模型轴 ±1/±2/±3，plane 为对应截面。未知不猜，pass 仅限返回 scope。", obj({**COMMON, "conditions": {"type": "array", "items": CONDITION, "maxItems": 100}, "drawing": DRAWING}, [*COMMON, "conditions"]), False),
    }


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def direction(a):
    n = norm(a)
    if not n:
        raise ValueError("方向向量不能为零")
    return [v/n for v in a]


def line_point(point, axis):
    axis = direction(axis)
    return sub(point, [v*dot(point, axis) for v in axis])


def parallel(a, b):
    return abs(abs(dot(direction(a), direction(b)))-1) < 1e-10


def matches(entity, selector):
    for key in ("native_ref", "kind", "inward"):
        if key in selector and entity.get(key) != selector[key]:
            return False
    if "radius" in selector and abs(entity.get("radius", math.inf)-selector["radius"]) > 1e-8:
        return False
    if "direction" in selector and ("direction" not in entity or not parallel(entity["direction"], selector["direction"])):
        return False
    if "offset" in selector:
        if "direction" not in selector:
            raise ValueError("offset 筛选必须提供 direction")
        if entity["kind"] != "plane":
            return False
        if abs(dot(entity["point"], direction(selector["direction"]))-selector["offset"]) > 1e-8:
            return False
    for key in ("point", "near"):
        if key in selector:
            if "point" not in entity:
                return False
            # 圆柱轴线上任意参数原点先投影到离文档原点最近的位置。
            target = line_point(selector[key], entity["direction"]) if entity["kind"] == "cylinder" else selector[key]
            if norm(sub(entity["point"], target)) > (selector.get("within", 1e-8) if key == "near" else 1e-8):
                return False
    return True


def measure(snapshot, request, section=None):
    kind = request["kind"]
    result = {"document": snapshot["document"], "object_ref": snapshot["object_ref"],
              "coordinate_system": "document", "unit": METRICS[kind], "status": "unknown", "locations": []}
    if snapshot["state"] != "ready":
        return {**result, "reason": "model_not_ready", "details": snapshot.get("issues", [])}
    if kind == "section_area":
        if "plane" not in request:
            raise ValueError("section_area 需要 plane")
        cut = section(request["plane"])
        if cut["document"] != snapshot["document"]:
            raise ValueError("截面与模型修订不一致")
        return {**result, "status": cut["status"], "value": cut.get("area"), "reason": cut.get("reason"),
                "locations": [{"object_ref": snapshot["object_ref"], "plane": cut["plane"], "edges": cut.get("edges", [])}]}
    if kind == "parameter":
        found = [p for f in snapshot["features"] if f["native_ref"] == request.get("feature")
                 for p in f["parameters"] if p["name"] == request.get("parameter")]
        if len(found) != 1 or type(found[0].get("value")) not in (int, float) or found[0].get("unit") not in {"m", "rad", "1"}:
            return {**result, "reason": "parameter_unavailable"}
        return {**result, "status": "ok", "value": found[0]["value"], "unit": found[0]["unit"],
                "locations": [{"native_ref": request["feature"], "parameter": request["parameter"]}]}
    selectors = request.get("selectors", [])
    required = 2 if kind in {"axis_distance", "plane_distance"} else 1
    if len(selectors) != required:
        raise ValueError(f"{kind} 需要 {required} 个 selectors")
    entities = snapshot["faces"] + snapshot["edges"]
    groups = [[e for e in entities if matches(e, selector)] for selector in selectors]
    result["locations"] = [{"native_ref": e["native_ref"], "kind": e["kind"], "point": e.get("point")}
                           for group in groups for e in group]
    if kind == "count":
        return {**result, "status": "ok", "value": len(groups[0])}
    if any(len(group) != 1 for group in groups):
        return {**result, "reason": "missing_entity" if any(not group for group in groups) else "ambiguous_entity",
                "match_counts": [len(group) for group in groups]}
    a = groups[0][0]
    if kind == "diameter" and a["kind"] in {"cylinder", "circle"}:
        value = a["radius"]*2
    elif kind in {"axis_distance", "plane_distance"}:
        b = groups[1][0]
        expected = "cylinder" if kind == "axis_distance" else "plane"
        if a["kind"] != expected or b["kind"] != expected or not parallel(a["direction"], b["direction"]):
            return {**result, "reason": "requires_parallel_" + expected}
        delta, axis = sub(a["point"], b["point"]), direction(a["direction"])
        value = norm(sub(delta, [v*dot(delta, axis) for v in axis])) if kind == "axis_distance" else abs(dot(delta, axis))
    elif kind == "coordinate" and "point" in a and "axis" in request:
        value = a["point"][request["axis"]]
    elif kind == "edge_length" and "length" in a:
        value = a["length"]
    else:
        return {**result, "reason": "incompatible_measurement"}
    return {**result, "status": "ok", "value": value}


UNITS = {"m": ("m", 1), "mm": ("m", .001), "m^2": ("m^2", 1), "mm^2": ("m^2", 1e-6),
         "rad": ("rad", 1), "deg": ("rad", math.pi/180), "1": ("1", 1)}


def check(snapshot, conditions, section=None, project=None, drawing=None):
    results = []
    for condition in conditions:
        actual = measure(snapshot, condition["measurement"], section)
        unit, scale = UNITS[condition["unit"]]
        expected, tolerance = condition["expected"]*scale, condition["tolerance"]*scale
        status = "unknown"
        if actual["status"] == "ok":
            if actual["unit"] != unit:
                actual = {**actual, "status": "unknown", "reason": "unit_mismatch"}
            else:
                delta = abs(actual["value"]-expected)
                status = "pass" if delta <= tolerance or math.isclose(delta, tolerance, rel_tol=1e-12, abs_tol=1e-15) else "fail"
        source_kind, evidence = "agent_defined", None
        reason = None
        if "evidence" in condition:
            from gongke_app.drawing_check import annotation, UnknownDrawing
            try:
                value, evidence = annotation(project, condition["evidence"])
                source_kind = "drawing_annotation"
                # 当前仅支持直接引用长度标注；不把一个数字拿来给面积/参数推导背书。
                if unit != "m" or condition["measurement"]["kind"] not in {"diameter", "axis_distance", "plane_distance", "edge_length"}:
                    raise UnknownDrawing("引用标注仅支持直接长度量测，推导值属于 Agent 自定")
                if not math.isclose(expected, value*.001, abs_tol=1e-12):
                    raise UnknownDrawing("期望值与引用标注不一致")
            except (UnknownDrawing, ValueError, OSError) as exc:
                status, reason = "unknown", str(exc)
        elif status == "pass":
            status, reason = "unverified", "未经独立核对"
        results.append({"source_kind": source_kind, "evidence": evidence, "reason": reason, "id": condition["id"], "source": condition["source"], "measurement": condition["measurement"], "status": status,
                        "expected": expected, "tolerance": tolerance, "unit": unit, "actual": actual})
    if drawing is not None:
        from gongke_app.drawing_check import check_drawing
        results.append(check_drawing(project, snapshot, section, drawing))
    return {"document": snapshot["document"], "object_ref": snapshot["object_ref"], "checks": results,
            "scope": "仅核验已列出的条件及视图截面，不代表整张图纸或整个模型符合",
            "unverified": [r["id"] for r in results if r["source_kind"] == "agent_defined"],
            "status": "fail" if any(r["status"] == "fail" for r in results) else
                      "unknown" if not results or any(r["status"] == "unknown" for r in results) else
                      "unverified" if any(r["status"] == "unverified" for r in results) else "pass"}
