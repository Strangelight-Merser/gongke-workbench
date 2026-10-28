"""可由学生继续编辑的原生回转轴；尺寸只保存在原生草图约束中。

此模块由 FreeCAD 主线程调用。事务边界由调用者管理，不导入外部几何内核。
支持三段教学轴和七段课程输出轴；后者带两个原生键槽和六处圆角，仍禁止 agent 改径。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid


class UnsupportedShaft(ValueError):
    """当前模型超出已绑定的原生轴范围，保留模型并停止自动修改。"""


def _constraint_signature(sketch):
    """只记录约束结构；数值由学生与 agent 共同编辑，不参加此签名。"""
    return [
        {
            "type": constraint.Type,
            "name": constraint.Name,
            "active": constraint.IsActive,
            "driving": constraint.Driving,
            **{field: getattr(constraint, field) for field in
               ("First", "FirstPos", "Second", "SecondPos", "Third", "ThirdPos")},
        }
        for constraint in sketch.Constraints
    ]


def _index(sketch, name):
    matches = [i for i, constraint in enumerate(sketch.Constraints) if constraint.Name == name]
    if len(matches) != 1:
        raise UnsupportedShaft(f"命名尺寸 {name} 已删除或不唯一，需要重新绑定")
    return matches[0]


def _describe_simple_parts(body):
    """验证当前三段剖面和尺寸含义，不依赖对象名、线编号或已有工程元数据。"""
    if body is None or body.TypeId != "PartDesign::Body":
        raise UnsupportedShaft("只支持原生 PartDesign Body")
    sketches = [obj for obj in body.Group if obj.TypeId == "Sketcher::SketchObject"]
    revolutions = [obj for obj in body.Group if obj.TypeId == "PartDesign::Revolution"]
    if len(body.Group) != 2 or len(sketches) != 1 or len(revolutions) != 1:
        raise UnsupportedShaft("三段轴 Body 只能包含一个草图和一个回转，不能含隐藏或后续特征")
    sketch, revolution = sketches[0], revolutions[0]
    if body.Tip != revolution or revolution.Profile[0] != sketch or revolution.Profile[1]:
        raise UnsupportedShaft("回转必须使用该草图的完整剖面，并作为当前 Body Tip")
    if any(set(obj.State) & {"Touched", "Invalid"} for obj in (body, sketch, revolution)):
        raise UnsupportedShaft("原生对象尚未成功重算")
    if sketch.ExpressionEngine or revolution.ExpressionEngine or sketch.ExternalGeometry:
        raise UnsupportedShaft("首版三段绑定不支持表达式或外部几何引用")
    if (not sketch.Placement.isIdentity() or str(sketch.MapMode) != "Deactivated"):
        raise UnsupportedShaft("草图须使用 Body 局部坐标，不能平移、旋转或附着到其他对象")
    if sketch.DoF != 0 or not sketch.FullyConstrained:
        raise UnsupportedShaft("草图必须完全约束后才能绑定")
    axis = revolution.ReferenceAxis
    if (axis[0] != sketch or list(axis[1]) != ["H_Axis"]
            or not math.isclose(revolution.Angle.Value, 360.0) or revolution.Suppressed):
        raise UnsupportedShaft("只支持绕草图水平轴的完整 360 度回转")
    if sketch.GeometryCount != 8:
        raise UnsupportedShaft("三段轴剖面必须由八条直线组成")
    tolerance = 1e-6  # CAD 使用 mm；用于原生求解后的坐标比较。
    horizontal, vertical = [], []
    for index, geometry in enumerate(sketch.Geometry):
        if geometry.TypeId != "Part::GeomLineSegment" or sketch.getConstruction(index):
            raise UnsupportedShaft("剖面只允许八条非构造直线")
        a, b = geometry.StartPoint, geometry.EndPoint
        if (not all(math.isfinite(value) for point in (a, b) for value in point)
                or abs(a.z) > tolerance or abs(b.z) > tolerance
                or min(a.x, b.x, a.y, b.y) < -tolerance):
            raise UnsupportedShaft("剖面必须位于局部 XY 平面的第一象限")
        if abs(a.y - b.y) <= tolerance and abs(a.x - b.x) > tolerance:
            horizontal.append((index, min(a.x, b.x), max(a.x, b.x), a.y))
        elif abs(a.x - b.x) <= tolerance and abs(a.y - b.y) > tolerance:
            vertical.append((a.x, min(a.y, b.y), max(a.y, b.y)))
        else:
            raise UnsupportedShaft("剖面仅支持水平轴段和垂直台阶")
    top = sorted((line for line in horizontal if line[3] > tolerance), key=lambda line: line[1])
    bottom = [line for line in horizontal if abs(line[3]) <= tolerance]
    if len(top) != 3 or len(bottom) != 1 or len(vertical) != 4:
        raise UnsupportedShaft("当前轮廓不是闭合的三段实心台阶轴")
    close = lambda a, b: math.isclose(a, b, rel_tol=1e-10, abs_tol=tolerance)
    if (not close(top[0][1], 0.0) or not close(bottom[0][1], 0.0)
            or not close(bottom[0][2], top[-1][2])
            or any(not close(a[2], b[1]) or close(a[3], b[3]) for a, b in zip(top, top[1:]))):
        raise UnsupportedShaft("三段轮廓须从局部 X=0 连续排列，且保留两个轴肩")
    expected = [(0.0, 0.0, top[0][3]),
                (top[0][2], min(top[0][3], top[1][3]), max(top[0][3], top[1][3])),
                (top[1][2], min(top[1][3], top[2][3]), max(top[1][3], top[2][3])),
                (top[2][2], 0.0, top[2][3])]
    if any(not all(close(a, b) for a, b in zip(actual, target))
           for actual, target in zip(sorted(vertical), expected)):
        raise UnsupportedShaft("剖面端面或轴肩未与三条轴段边正确闭合")
    segments = []
    for line, start, end, radius in top:
        lengths = [c for c in sketch.Constraints if c.Name and c.IsActive and c.Driving
                   and c.Type == "Distance" and c.First == line and c.FirstPos == 0
                   and c.Second == -2000 and c.Third == -2000]
        radii = [c for c in sketch.Constraints if c.Name and c.IsActive and c.Driving
                 and c.Type == "DistanceY" and c.First == line and c.FirstPos in (1, 2)
                 and c.Second == -2000 and c.Third == -2000]
        if len(lengths) != 1 or len(radii) != 1:
            raise UnsupportedShaft("每段须有唯一具名驱动线长 Distance 和绝对半径 DistanceY 约束")
        length_name, radius_name = lengths[0].Name, radii[0].Name
        length_value = sketch.getDatum(_index(sketch, length_name)).Value
        radius_value = sketch.getDatum(_index(sketch, radius_name)).Value
        if not close(length_value, end - start) or not close(radius_value, radius):
            raise UnsupportedShaft("命名尺寸与当前剖面的真实长度或半径不一致")
        # 几何验证后沿用约束这一尺寸来源，避免坐标相减的求解浮差混入绑定输入。
        segments.append({"length_m": length_value / 1000.0, "diameter_m": radius_value / 500.0,
                         "length_constraint": length_name, "radius_constraint": radius_name})
    expected_volume = sum(math.pi * (segment["diameter_m"] * 500) ** 2
                          * segment["length_m"] * 1000 for segment in segments)
    for obj in (body, revolution):
        if (obj.Shape.isNull() or not obj.Shape.isValid() or len(obj.Shape.Solids) != 1
                or not math.isclose(obj.Shape.Volume, expected_volume, rel_tol=1e-8, abs_tol=1e-6)):
            raise UnsupportedShaft("当前回转实体与三段实心轴剖面不一致")
    return {"body_name": body.Name, "label": body.Label, "sketch": sketch.Name,
            "revolution": revolution.Name, "segments": segments}


def describe_unbound(body):
    """只读列出可接管的原生三段轴；不改名、求解或重建任何学生对象。"""
    try:
        description = _describe_simple_parts(body)
        if {"GkEntityId", "GkMetadata", "GkSketch", "GkRevolution"} & set(body.PropertiesList):
            raise UnsupportedShaft("对象已有工程绑定属性，不能覆盖或重新绑定")
    except (UnsupportedShaft, ValueError, AttributeError, TypeError) as exc:
        return {"can_bind": False, "reason": str(exc)}
    return {"can_bind": True, "reason": None, **description}


def bind_existing(body, snapshot):
    """只附加工程条件和身份；调用者负责事务提交或失败回滚。"""
    from gongke_core.shaft_review import validate_snapshot

    errors = validate_snapshot(snapshot)
    if errors:
        raise ValueError("；".join(errors))
    source_info = snapshot.get("conditions_source", {})
    if (snapshot.get("coordinate_system") != "body_local_x"
            or not isinstance(source_info, dict) or source_info.get("status") != "declared"
            or not isinstance(source_info.get("reference"), str) or not source_info["reference"].strip()):
        raise ValueError("绑定必须声明 Body 局部 X 坐标及完整工程条件来源")
    description = describe_unbound(body)
    if not description["can_bind"]:
        raise UnsupportedShaft(description["reason"])
    for current, supplied in zip(description["segments"], snapshot["segments"]):
        if any(not math.isclose(current[field], supplied[field], rel_tol=1e-10, abs_tol=1e-9)
               for field in ("length_m", "diameter_m")):
            raise ValueError("工程输入与当前原生尺寸不一致，请重新读取待绑定对象")
    if any(getattr(obj, "GkEntityId", None) == snapshot["entity_id"] for obj in body.Document.Objects):
        raise ValueError("工程身份已用于其他对象")
    sketch = body.Document.getObject(description["sketch"])
    revolution = body.Document.getObject(description["revolution"])
    source = copy.deepcopy(snapshot)
    source.pop("entity_id")
    dimensions = []
    for segment, current in zip(source["segments"], description["segments"]):
        segment.pop("length_m")
        segment.pop("diameter_m")
        dimensions.append({"segment_id": segment["segment_id"], "length": current["length_constraint"],
                           "radius": current["radius_constraint"]})
    meta = {"engineering": source, "dimensions": dimensions,
            "constraint_signature": _constraint_signature(sketch), "binding_origin": "existing_native_shaft"}
    body.addProperty("App::PropertyString", "GkEntityId", "工程")
    body.GkEntityId = snapshot["entity_id"]
    body.setEditorMode("GkEntityId", 1)
    body.addProperty("App::PropertyString", "GkMetadata", "工程")
    body.GkMetadata = json.dumps(meta, ensure_ascii=False)
    body.setEditorMode("GkMetadata", 2)
    for name, obj in (("GkSketch", sketch), ("GkRevolution", revolution)):
        body.addProperty("App::PropertyLinkChild", name, "工程")
        setattr(body, name, obj)
        body.setEditorMode(name, 2)
    body.Document.recompute()
    return read_snapshot(body)


def _lengths_hash(segments):
    # 仅用于判断载荷绑定是否仍成立，不是另一份可写尺寸。
    lengths = [round(segment["length_m"], 12) for segment in segments]
    return hashlib.sha256(json.dumps(lengths, separators=(",", ":")).encode()).hexdigest()


def _validate_course_input(source):
    position = source["z_origin_m"]
    slots = []
    for segment in source["segments"]:
        if not math.isclose(segment["z0_m"], position, abs_tol=1e-10):
            raise ValueError("课程轴轴段起点与 z_origin_m 不连续")
        if segment["root_diameter_m"] is not None:
            raise ValueError("当前课程输出轴不支持整体齿轮轴")
        if segment["editable"]:
            raise ValueError("课程轴暂不允许 agent 改径")
        slot = segment["keyway"]
        if slot:
            slots.append(slot)
            if not (0 < slot["width_m"] < slot["length_m"] <= segment["length_m"]
                    and 0 < slot["depth_m"] < segment["diameter_m"] / 2):
                raise ValueError("键槽宽度、长度或深度超出受支持范围")
            if not math.isclose(slot["center_z_m"], position + segment["length_m"] / 2, abs_tol=1e-10):
                raise ValueError("课程轴初始化要求键槽在轴段居中")
        position += segment["length_m"]
    if len(slots) != 2 or any(connection["count"] != 1 for connection in source["key_connections"]):
        raise ValueError("课程输出轴仅支持两个已明确的单键连接")


def _create_keyways(body, source, profile, dimensions):
    """两个圆头槽均为原生草图加 Pocket；平面位置随对应轴段半径变化。"""
    import FreeCAD as App
    import Part
    import Sketcher

    doc = body.Document
    mappings, sketches, pockets = [], [], []
    for segment, shaft_names in zip(source["segments"], dimensions):
        slot = segment["keyway"]
        if slot is None:
            continue
        suffix = hashlib.sha256(segment["segment_id"].encode()).hexdigest()[:12]
        names = {"straight": f"slot_straight_{suffix}", "radius": f"slot_radius_{suffix}",
                 "right_center": f"slot_center_{suffix}"}
        center = (slot["center_z_m"] - source["z_origin_m"]) * 1000.0
        radius = slot["width_m"] * 500.0
        straight = (slot["length_m"] - slot["width_m"]) * 1000.0
        left, right = center - straight / 2, center + straight / 2
        sketch = body.newObject("Sketcher::SketchObject", "KeywayProfile")
        sketch.Label = f"{segment['role']}段键槽剖面"
        sketch.addGeometry([
            Part.LineSegment(App.Vector(left, -radius, 0), App.Vector(right, -radius, 0)),
            Part.Arc(App.Vector(right, -radius, 0), App.Vector(right + radius, 0, 0), App.Vector(right, radius, 0)),
            Part.LineSegment(App.Vector(right, radius, 0), App.Vector(left, radius, 0)),
            Part.Arc(App.Vector(left, radius, 0), App.Vector(left - radius, 0, 0), App.Vector(left, -radius, 0)),
        ], False)
        for i in range(4):
            # 端点相切同时约束接触位置，不能再叠加重合与整条曲线相切。
            sketch.addConstraint(Sketcher.Constraint("Tangent", i, 2, (i + 1) % 4, 1))
        sketch.addConstraint(Sketcher.Constraint("Equal", 1, 3))
        sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        index = sketch.addConstraint(Sketcher.Constraint("Radius", 1, radius))
        sketch.renameConstraint(index, names["radius"])
        index = sketch.addConstraint(Sketcher.Constraint("Distance", 0, straight))
        sketch.renameConstraint(index, names["straight"])
        index = sketch.addConstraint(Sketcher.Constraint("DistanceX", 1, 3, right))
        sketch.renameConstraint(index, names["right_center"])
        sketch.addConstraint(Sketcher.Constraint("PointOnObject", 1, 3, -1))
        solve_code = sketch.solve()
        if solve_code != 0 or sketch.DoF != 0:
            raise ValueError(f"原生圆头键槽约束求解失败：code={solve_code}, DoF={sketch.DoF}, "
                             f"redundant={sketch.RedundantConstraints}, conflicting={sketch.ConflictingConstraints}, "
                             f"malformed={sketch.MalformedConstraints}")
        sketch.setExpression("Placement.Base.z", f"{profile.Name}.Constraints.{shaft_names['radius']}")
        doc.recompute()
        pocket = body.newObject("PartDesign::Pocket", "KeywayPocket")
        pocket.Label = f"{segment['role']}段键槽"
        pocket.Profile = sketch
        pocket.Type = "Length"
        pocket.Length = slot["depth_m"] * 1000.0
        pocket.AlongSketchNormal = True
        pocket.Reversed = False
        body.Tip = pocket
        doc.recompute()
        if pocket.Shape.isNull() or not pocket.Shape.isValid() or len(pocket.Shape.Solids) != 1:
            raise ValueError("原生键槽 Pocket 未产生有效单实体")
        mappings.append({"segment_id": segment["segment_id"], "dimensions": names,
                         "constraint_signature": _constraint_signature(sketch),
                         "geometry_types": [geometry.TypeId for geometry in sketch.Geometry],
                         "expressions": [list(expression) for expression in sketch.ExpressionEngine],
                         "side_type": str(pocket.SideType),
                         "map_mode": str(sketch.MapMode)})
        sketches.append(sketch)
        pockets.append(pocket)
    for name, objects in (("GkKeySketches", sketches), ("GkKeyPockets", pockets)):
        body.addProperty("App::PropertyLinkListChild", name, "工程")
        setattr(body, name, objects)
        body.setEditorMode(name, 2)
    return mappings


def _check_keyways(body, meta):
    sketches, pockets = body.GkKeySketches, body.GkKeyPockets
    if len(sketches) != 2 or len(pockets) != 2 or len(meta["keyways"]) != 2:
        raise UnsupportedShaft("两个已绑定的原生键槽特征不完整")
    previous = body.GkRevolution
    for sketch, pocket, mapping in zip(sketches, pockets, meta["keyways"]):
        if sketch is None or pocket is None or pocket.TypeId != "PartDesign::Pocket":
            raise UnsupportedShaft("键槽草图或 Pocket 已删除或改变类型")
        if pocket.Profile[0] != sketch or pocket.BaseFeature != previous:
            raise UnsupportedShaft("键槽特征顺序或剖面关联已改变")
        if _constraint_signature(sketch) != mapping["constraint_signature"]:
            raise UnsupportedShaft("键槽约束结构已改变，需要重新绑定")
        if [geometry.TypeId for geometry in sketch.Geometry] != mapping["geometry_types"]:
            raise UnsupportedShaft("键槽剖面拓扑已改变")
        if any(sketch.getConstruction(i) for i in range(sketch.GeometryCount)):
            raise UnsupportedShaft("键槽剖面中含新增构造几何")
        if [list(expression) for expression in sketch.ExpressionEngine] != mapping["expressions"]:
            raise UnsupportedShaft("键槽平面与轴段半径的表达式关联已改变")
        if str(sketch.MapMode) != mapping["map_mode"]:
            raise UnsupportedShaft("键槽草图的附着方式已改变")
        if (sketch.Placement.Base.x != 0 or sketch.Placement.Base.y != 0
                or not math.isclose(sketch.Placement.Rotation.Angle, 0.0, abs_tol=1e-10)):
            raise UnsupportedShaft("键槽局部坐标发生改变")
        if (pocket.ExpressionEngine or str(pocket.Type) != "Length" or pocket.Reversed or pocket.Suppressed
                or not pocket.AlongSketchNormal or str(pocket.SideType) != mapping["side_type"]
                or pocket.UseCustomVector
                or not math.isclose(pocket.TaperAngle.Value, 0.0, abs_tol=1e-10)):
            raise UnsupportedShaft("键槽 Pocket 的方向或深度驱动方式改变")
        if any(set(obj.State) & {"Invalid", "Touched"} for obj in (sketch, pocket)):
            raise UnsupportedShaft("键槽原生特征重算失败")
        previous = pocket


def _shoulder_edges(feature, x_mm, small_radius_mm):
    """按当前几何识别肩部小圆凹边；Edge 名称仅用于本次原生特征创建。"""
    edges = []
    for i, edge in enumerate(feature.Shape.Edges, 1):
        curve = edge.Curve
        if curve.TypeId != "Part::GeomCircle":
            continue
        if (math.isclose(curve.Center.x, x_mm, abs_tol=1e-6)
                and abs(curve.Center.y) < 1e-6 and abs(curve.Center.z) < 1e-6
                and math.isclose(curve.Radius, small_radius_mm, abs_tol=1e-6)
                and math.isclose(abs(curve.Axis.x), 1.0, abs_tol=1e-8)
                and math.isclose(edge.Length, 2 * math.pi * small_radius_mm, rel_tol=1e-7)):
            edges.append(f"Edge{i}")
    return edges


def _create_fillets(body, source):
    """只使用已声明的六个半径，不替换不适用的半径，也不自动减小失败圆角。"""
    doc = body.Document
    segments = {segment["segment_id"]: segment for segment in source["segments"]}
    assumptions = source["fillet_assumptions"]
    if len(assumptions) != 6:
        raise ValueError("课程输出轴须明确六处相邻轴段的圆角")
    features, mappings = [], []
    for number, assumption in enumerate(assumptions, 1):
        left = segments[assumption["left_segment_id"]]
        right = segments[assumption["right_segment_id"]]
        radius_m = assumption["assumed_radius_m"]
        if isinstance(radius_m, bool) or not isinstance(radius_m, (int, float)) or not math.isfinite(radius_m) or radius_m <= 0:
            raise ValueError("已声明的圆角半径必须是有限正数")
        base = body.Tip
        x_mm = (right["z0_m"] - source["z_origin_m"]) * 1000
        edges = _shoulder_edges(base, x_mm, min(left["diameter_m"], right["diameter_m"]) * 500)
        if len(edges) != 1:
            raise ValueError(f"第 {number} 处轴肩没有唯一可识别的小圆凹边")
        fillet = body.newObject("PartDesign::Fillet", "ShaftFillet")
        fillet.Label = f"轴肩圆角 {number}"
        fillet.Base = (base, edges)
        fillet.Radius = radius_m * 1000
        body.Tip = fillet
        doc.recompute()
        if (set(fillet.State) & {"Invalid", "Touched"} or fillet.Shape.isNull()
                or not fillet.Shape.isValid() or len(fillet.Shape.Solids) != 1):
            raise ValueError(f"第 {number} 处声明圆角无法建立：{fillet.getStatusString()}")
        features.append(fillet)
        mappings.append({"left_segment_id": left["segment_id"], "right_segment_id": right["segment_id"]})
    body.addProperty("App::PropertyLinkListChild", "GkFillets", "工程")
    body.GkFillets = features
    body.setEditorMode("GkFillets", 2)
    return mappings


def _check_fillets(body, meta):
    """检查整个原生特征链及实际环面，不能让末端缓存 Shape 掩盖中途失败。"""
    if "GkFillets" not in body.PropertiesList or "fillets" not in meta:
        raise UnsupportedShaft("课程工程缺少当前原生圆角映射；原文件仍可编辑，请新建当前课程轴工程")
    if len(body.GkFillets) != 6 or len(meta["fillets"]) != 6:
        raise UnsupportedShaft("六处原生圆角映射不完整")
    ids = [item["segment_id"] for item in meta["dimensions"]]
    pairs = [(item["left_segment_id"], item["right_segment_id"]) for item in meta["fillets"]]
    if pairs != list(zip(ids, ids[1:])):
        raise UnsupportedShaft("原生圆角与相邻轴段身份不匹配")
    geometry = {}
    x = 0.0
    for item in meta["dimensions"]:
        length = body.GkSketch.getDatum(_index(body.GkSketch, item["length"])).Value
        radius = body.GkSketch.getDatum(_index(body.GkSketch, item["radius"])).Value
        geometry[item["segment_id"]] = {"x": x, "radius": radius}
        x += length
    previous = body.GkKeyPockets[-1]
    for number, (fillet, mapping) in enumerate(zip(body.GkFillets, meta["fillets"]), 1):
        if fillet is None or fillet.TypeId != "PartDesign::Fillet":
            raise UnsupportedShaft(f"第 {number} 处原生圆角已删除或类型改变")
        if set(fillet.State) & {"Invalid", "Touched"}:
            raise UnsupportedShaft(f"第 {number} 处原生圆角未成功重算：{fillet.getStatusString()}")
        if (fillet.Base[0] != previous or fillet.BaseFeature != previous or len(fillet.Base[1]) != 1
                or fillet.UseAllEdges or fillet.Suppressed or fillet.ExpressionEngine):
            raise UnsupportedShaft(f"第 {number} 处圆角的特征链或驱动方式改变")
        if fillet.Shape.isNull() or not fillet.Shape.isValid() or len(fillet.Shape.Solids) != 1:
            raise UnsupportedShaft(f"第 {number} 处圆角没有有效单实体")
        left, right = geometry[mapping["left_segment_id"]], geometry[mapping["right_segment_id"]]
        radius = fillet.Radius.Value
        if not math.isfinite(radius) or radius <= 0:
            raise UnsupportedShaft("实际圆角半径无效")
        center_x = right["x"] + (-radius if left["radius"] < right["radius"] else radius)
        major_radius = min(left["radius"], right["radius"]) + radius
        mapped = False
        for face in fillet.Shape.Faces:
            surface = face.Surface
            if surface.TypeId == "Part::GeomToroid" and (
                    math.isclose(surface.Center.x, center_x, abs_tol=1e-6)
                    and abs(surface.Center.y) < 1e-6 and abs(surface.Center.z) < 1e-6
                    and math.isclose(abs(surface.Axis.x), 1.0, abs_tol=1e-8)
                    and math.isclose(surface.MajorRadius, major_radius, abs_tol=1e-6)
                    and math.isclose(surface.MinorRadius, radius, abs_tol=1e-6)):
                mapped = True
                break
        if not mapped:
            raise UnsupportedShaft(f"第 {number} 处圆角实际几何未对应指定肩部和 Radius")
        previous = fillet
    cavities = body.GkRevolution.Shape.cut(body.GkKeyPockets[-1].Shape)
    if body.Shape.common(cavities).Volume > max(1e-5, cavities.Volume * 1e-9):
        raise UnsupportedShaft("当前圆角侵入已绑定的键槽空腔")


def _read_course_geometry(body, meta, result):
    """几何尺寸读当前原生对象；载荷/接口条件不因手改尺寸而偷偷平移。"""
    origin = result["z_origin_m"]
    z = origin
    by_id = {}
    for segment in result["segments"]:
        segment["z0_m"] = z
        z += segment["length_m"]
        by_id[segment["segment_id"]] = segment
    for sketch, pocket, mapping in zip(body.GkKeySketches, body.GkKeyPockets, meta["keyways"]):
        names = mapping["dimensions"]
        radius = sketch.getDatum(_index(sketch, names["radius"])).Value / 1000.0
        straight = sketch.getDatum(_index(sketch, names["straight"])).Value / 1000.0
        right_center = sketch.getDatum(_index(sketch, names["right_center"])).Value / 1000.0
        slot = by_id[mapping["segment_id"]]["keyway"]
        slot.update(width_m=2 * radius, length_m=straight + 2 * radius,
                    depth_m=pocket.Length.Value / 1000.0, center_z_m=origin + right_center - straight / 2)
    radii = {(mapping["left_segment_id"], mapping["right_segment_id"]): feature.Radius.Value / 1000.0
             for feature, mapping in zip(body.GkFillets, meta["fillets"])}
    for fillet in result["fillet_assumptions"]:
        fillet["z_m"] = by_id[fillet["right_segment_id"]]["z0_m"]
        fillet["cad_radius_m"] = radii[(fillet["left_segment_id"], fillet["right_segment_id"])]
        fillet["status"] = "mapped_to_native_cad"
    load_current = _lengths_hash(result["segments"]) == meta["load_binding_lengths_hash"]
    result["cad_geometry_state"] = {
        "parameters_current": True, "keyways_current": True, "fillets_current": True,
        "unsupported_features": [], "load_binding_current": load_current,
        "blocked_reasons": [] if load_current else ["轴段长度改变，原固定载荷、支承和接口位置必须重新绑定。"],
    }
    result["read_only"] = False
    result["editable_parameters"] = ["right_bearing_shoulder_radius_m"]
    result["limitations"][0] = "轴段、两个圆头键槽及六处圆角均读取当前原生特征；圆角初始化沿用声明设计假设，实际几何建立不等于材料、疲劳方法或制造条件获验证。"


def _parts(body):
    if body is None or body.TypeId != "PartDesign::Body" or "GkMetadata" not in body.PropertiesList:
        raise UnsupportedShaft("请选择工科工作台支持的原生轴 Body")
    meta = json.loads(body.GkMetadata)
    sketch, revolution = body.GkSketch, body.GkRevolution
    if sketch is None or revolution is None:
        raise UnsupportedShaft("绑定的草图或回转特征已删除")
    if sketch.TypeId != "Sketcher::SketchObject" or revolution.TypeId != "PartDesign::Revolution":
        raise UnsupportedShaft("绑定的原生特征类型已改变")
    course = meta["engineering"]["scope"] == "course_shaft_review"
    if course and body.Document.UseHasher:
        raise UnsupportedShaft("课程圆角工程要求文档保留完整原生拓扑名称")
    if course and ("GkFillets" not in body.PropertiesList or "fillets" not in meta or len(body.GkFillets) != 6):
        raise UnsupportedShaft("课程工程缺少当前原生圆角映射；原文件仍可编辑，请新建当前课程轴工程")
    tip = body.GkFillets[-1] if course else revolution
    if body.Tip != tip or revolution.Profile[0] != sketch:
        raise UnsupportedShaft("轴含未支持的后续特征或回转剖面已改变；保留当前模型")
    if sketch.ExpressionEngine or revolution.ExpressionEngine:
        raise UnsupportedShaft("尺寸或回转由表达式驱动，首版只允许读取工程状态，不自动改写")
    if sketch.GeometryCount != 2 * len(meta["dimensions"]) + 2 or _constraint_signature(sketch) != meta["constraint_signature"]:
        raise UnsupportedShaft("草图几何或约束结构已改变，需要重新绑定")
    if any(geometry.TypeId != "Part::GeomLineSegment" for geometry in sketch.Geometry):
        raise UnsupportedShaft("固定剖面只支持直线台阶，当前几何类型已改变")
    if any(sketch.getConstruction(i) for i in range(sketch.GeometryCount)):
        raise UnsupportedShaft("剖面中存在新增构造几何")
    for item in meta["dimensions"]:
        for name in (item["length"], item["radius"]):
            if not sketch.getDriving(_index(sketch, name)):
                raise UnsupportedShaft("已绑定尺寸变为参考尺寸，需要重新绑定")
    if not sketch.Placement.isIdentity():
        raise UnsupportedShaft("剖面局部坐标发生改变，需要重新绑定载荷轴线")
    axis = revolution.ReferenceAxis
    if axis[0] != sketch or list(axis[1]) != ["H_Axis"] or not math.isclose(revolution.Angle.Value, 360.0):
        raise UnsupportedShaft("回转轴或角度已改变")
    if revolution.Shape.isNull() or not revolution.Shape.isValid() or len(revolution.Shape.Solids) != 1:
        raise UnsupportedShaft("当前轴未形成有效单实体，请先修复原生模型")
    if any(set(obj.State) & {"Invalid", "Touched"} for obj in (sketch, revolution)):
        raise UnsupportedShaft("原生对象重算失败")
    if course:
        _check_keyways(body, meta)
        _check_fillets(body, meta)
        if body.Shape.isNull() or not body.Shape.isValid() or len(body.Shape.Solids) != 1:
            raise UnsupportedShaft("带键槽的当前轴未形成有效单实体")
    else:
        description = _describe_simple_parts(body)
        if description["sketch"] != sketch.Name or description["revolution"] != revolution.Name:
            raise UnsupportedShaft("三段轴原生对象与绑定映射不一致")
        if any(item["length"] != current["length_constraint"] or item["radius"] != current["radius_constraint"]
               for item, current in zip(meta["dimensions"], description["segments"])):
            raise UnsupportedShaft("绑定尺寸不再对应当前三段剖面的长度和半径")
    if set(body.State) & {"Invalid", "Touched"}:
        raise UnsupportedShaft("原生 Body 尚未成功重算")
    return meta, sketch, revolution


def inspect(body):
    """检查模型是否仍可按原绑定自动操作，不删除或重建任何学生特征。"""
    try:
        meta, _, _ = _parts(body)
    except (UnsupportedShaft, ValueError, AttributeError, KeyError, TypeError) as exc:
        return {"supported": False, "reason": str(exc)}
    result = {"supported": True, "reason": None}
    if meta["engineering"]["scope"] == "course_shaft_review":
        snapshot = read_snapshot(body)
        result["read_only"] = snapshot["read_only"]
        result["editable_parameters"] = snapshot["editable_parameters"]
        result["cad_geometry_state"] = snapshot["cad_geometry_state"]
        if not snapshot["cad_geometry_state"]["load_binding_current"]:
            result["analysis_status"] = "blocked"
            result["reason"] = "轴段长度已改变，固定载荷和接口位置必须重新绑定"
    return result


def supported(body):
    return inspect(body)["supported"]


def read_snapshot(body):
    """从当前原生命名尺寸读取 SI 快照，不读取初次创建时的旧直径。"""
    meta, sketch, _ = _parts(body)
    result = copy.deepcopy(meta["engineering"])
    result["entity_id"] = body.GkEntityId
    for segment, names in zip(result["segments"], meta["dimensions"]):
        if segment["segment_id"] != names["segment_id"]:
            raise UnsupportedShaft("轴段语义映射不一致")
        segment["length_m"] = sketch.getDatum(_index(sketch, names["length"])).Value / 1000.0
        segment["diameter_m"] = sketch.getDatum(_index(sketch, names["radius"])).Value / 500.0
    if result["scope"] == "course_shaft_review":
        _read_course_geometry(body, meta, result)
    return result


def create_shaft(doc, snapshot):
    """建立固定拓扑原生轴。创建失败由调用者中止原生事务。"""
    import FreeCAD as App
    import Part
    import Sketcher

    source = copy.deepcopy(snapshot)
    segments = source["segments"]
    course = source["scope"] == "course_shaft_review"
    if source["scope"] not in ("course_shaft_review", "simplified_shaft"):
        raise ValueError("不支持的原生轴范围")
    if len(segments) != (7 if course else 3):
        raise ValueError("课程输出轴要求七段，教学轴要求三段")
    if len({segment["segment_id"] for segment in segments}) != len(segments):
        raise ValueError("轴段身份必须唯一")
    for segment in segments:
        for field in ("length_m", "diameter_m"):
            value = segment[field]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field} 必须是有限正数")
    if course:
        _validate_course_input(source)
        if doc.Objects:
            raise ValueError("课程轴必须创建在新空文档中，不能改变已有工程的拓扑名称配置")
        # 小型课程工程保留完整拓扑名，避免 1.1.4 哈希压缩令圆角边引用漂移。
        doc.UseHasher = False
    radii = [segment["diameter_m"] * 500.0 for segment in segments]
    if any(math.isclose(a, b, abs_tol=1e-8) for a, b in zip(radii, radii[1:])):
        raise ValueError("固定台阶拓扑要求相邻轴段直径不同")
    lengths = [segment["length_m"] * 1000.0 for segment in segments]
    points = [(0, 0), (0, radii[0])]
    x = 0.0
    for i, (length, radius) in enumerate(zip(lengths, radii)):
        x += length
        points.append((x, radius))
        if i + 1 < len(lengths):
            points.append((x, radii[i + 1]))
    points.append((x, 0))

    body = doc.addObject("PartDesign::Body", "GongKeShaft")
    body.Label = source.get("name", "台阶轴")
    body.addProperty("App::PropertyString", "GkEntityId", "工程")
    body.GkEntityId = source.get("entity_id") or str(uuid.uuid4())
    body.setEditorMode("GkEntityId", 1)
    sketch = body.newObject("Sketcher::SketchObject", "ShaftProfile")
    sketch.Label = "轴剖面"
    sketch.addGeometry([
        Part.LineSegment(App.Vector(*a, 0), App.Vector(*b, 0))
        for a, b in zip(points, points[1:] + points[:1])
    ], False)
    edge_count = len(points)
    for i in range(edge_count):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % edge_count, 1))
        sketch.addConstraint(Sketcher.Constraint("Vertical" if i % 2 == 0 else "Horizontal", i))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
    dimensions = []
    for segment, line, length, radius in zip(segments, range(1, edge_count - 2, 2), lengths, radii):
        suffix = hashlib.sha256(segment["segment_id"].encode("utf-8")).hexdigest()[:12]
        names = {"segment_id": segment["segment_id"], "length": f"length_{suffix}", "radius": f"radius_{suffix}"}
        length_id = sketch.addConstraint(Sketcher.Constraint("Distance", line, length))
        sketch.renameConstraint(length_id, names["length"])
        radius_id = sketch.addConstraint(Sketcher.Constraint("DistanceY", line, 1, radius))
        sketch.renameConstraint(radius_id, names["radius"])
        dimensions.append(names)
    if sketch.solve() != 0:
        raise ValueError("原生剖面约束求解失败")
    doc.recompute()
    revolution = body.newObject("PartDesign::Revolution", "ShaftRevolution")
    revolution.Label = "轴回转"
    revolution.Profile = sketch
    revolution.ReferenceAxis = (sketch, ["H_Axis"])
    revolution.Angle = 360.0
    body.Tip = revolution
    doc.recompute()

    keyways = _create_keyways(body, source, sketch, dimensions) if course else None
    fillets = _create_fillets(body, source) if course else None

    # 元数据保留物理条件和语义映射，长度、直径只有原生约束这一处可写来源。
    for segment in source["segments"]:
        del segment["length_m"]
        del segment["diameter_m"]
    source.pop("entity_id", None)
    meta = {"engineering": source, "dimensions": dimensions,
            "constraint_signature": _constraint_signature(sketch)}
    if course:
        meta["keyways"] = keyways
        meta["fillets"] = fillets
        meta["load_binding_lengths_hash"] = _lengths_hash(snapshot["segments"])
        for segment in source["segments"]:
            segment.pop("z0_m")
            if segment["keyway"]:
                for name in ("width_m", "length_m", "depth_m", "center_z_m"):
                    segment["keyway"].pop(name)
        for assumption in source["fillet_assumptions"]:
            assumption.pop("cad_radius_m", None)
    body.addProperty("App::PropertyString", "GkMetadata", "工程")
    body.GkMetadata = json.dumps(meta, ensure_ascii=False)
    body.setEditorMode("GkMetadata", 2)
    for name, obj in (("GkSketch", sketch), ("GkRevolution", revolution)):
        body.addProperty("App::PropertyLinkChild", name, "工程")
        setattr(body, name, obj)
        body.setEditorMode(name, 2)
    doc.recompute()
    _parts(body)
    if App.GuiUp:
        sketch.Visibility = False
        revolution.Visibility = not course
        if course:
            for key_sketch in body.GkKeySketches:
                key_sketch.Visibility = False
            for pocket in body.GkKeyPockets:
                pocket.Visibility = False
            for fillet in body.GkFillets:
                fillet.Visibility = fillet == body.Tip
        body.Visibility = True
    return body


def set_diameter(body, segment_id, diameter_m):
    """只改指定原生半径约束；失败后调用者须 abortTransaction。"""
    import FreeCAD as App

    snapshot = read_snapshot(body)
    if snapshot["scope"] == "course_shaft_review":
        raise ValueError("课程输出轴的接口、材料和圆角依据尚未闭合，agent 改径已禁用；学生可继续原生编辑")
    matches = [segment for segment in snapshot["segments"] if segment["segment_id"] == segment_id]
    if len(matches) != 1:
        raise ValueError("轴段不存在")
    segment = matches[0]
    if not segment["editable"]:
        raise ValueError("该轴段尺寸已锁定")
    if (isinstance(diameter_m, bool) or not isinstance(diameter_m, (int, float))
            or not math.isfinite(diameter_m) or diameter_m <= 0):
        raise ValueError("直径必须是有限正数，单位 m")
    if not segment["min_diameter_m"] <= diameter_m <= segment["max_diameter_m"]:
        raise ValueError("直径超出当前轴段允许范围")
    i = snapshot["segments"].index(segment)
    neighbors = snapshot["segments"][max(0, i - 1):i] + snapshot["segments"][i + 1:i + 2]
    if any(math.isclose(diameter_m, neighbor["diameter_m"], abs_tol=1e-10) for neighbor in neighbors):
        raise ValueError("候选直径会消除轴肩，超出固定剖面拓扑")
    meta, sketch, _ = _parts(body)
    names = next(item for item in meta["dimensions"] if item["segment_id"] == segment_id)
    sketch.setDatum(_index(sketch, names["radius"]), App.Units.Quantity(f"{diameter_m * 500.0:.15g} mm"))
    body.Document.recompute()
    result = read_snapshot(body)
    actual = next(item["diameter_m"] for item in result["segments"] if item["segment_id"] == segment_id)
    if not math.isclose(actual, diameter_m, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("原生约束没有接受候选直径")
    return result


def set_fillet_radius(body, left_segment_id, right_segment_id, radius_m):
    """只写获准圆角的原生 Radius；事务由调用者提交，异常时须中止事务。"""
    from gongke_core import course_shaft

    snapshot = read_snapshot(body)
    preview = course_shaft.preview_fillet_change(snapshot, left_segment_id, right_segment_id, radius_m)
    if not preview["can_apply"]:
        raise ValueError("当前圆角修改不允许应用：" + "；".join(preview["blocked_reasons"]))
    meta = json.loads(body.GkMetadata)
    matches = [feature for feature, mapping in zip(body.GkFillets, meta["fillets"])
               if mapping["left_segment_id"] == left_segment_id
               and mapping["right_segment_id"] == right_segment_id]
    if len(matches) != 1:
        raise UnsupportedShaft("相邻轴段未唯一对应一个原生圆角")
    matches[0].Radius = radius_m * 1000.0
    body.Document.recompute()
    result = read_snapshot(body)
    actual = next(item["cad_radius_m"] for item in result["fillet_assumptions"]
                  if item["left_segment_id"] == left_segment_id and item["right_segment_id"] == right_segment_id)
    if not math.isclose(actual, radius_m, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("原生圆角没有接受候选半径")
    return result
