"""校核当前简化轴，不选型、不修改 CAD，也不重新运行整机设计。

首版范围是三个同轴实心圆柱段的名义弯扭应力和 Euler–Bernoulli 梁挠度。
轴肩应力集中、疲劳、配合、键槽及装配定位不在该校核的结论范围内。
"""

from __future__ import annotations

from copy import deepcopy
import math
from uuid import UUID

from gongke_core.calc import shaft, shaft_stiffness


LIMITATIONS = [
    "教学用简化三段实心圆轴；结果不是完整减速器或实际轴的设计验收。",
    "只计算名义弯扭应力及线弹性小挠度；未校核轴肩应力集中、疲劳、配合和装配定位。",
    "支承抽象为两个简支点，不包含轴承和连接件的实际刚度。",
    "材料、许用应力、折合系数和挠度限值均使用输入条件，不自动补齐或重新选型。",
]


def _number(value, *, positive=False) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not positive or value > 0))


def validate_snapshot(snapshot: dict) -> list[str]:
    """返回阻止校核的输入问题；缺失条件不会使用材料或载荷默认值。"""
    if not isinstance(snapshot, dict):
        return ["snapshot 必须是对象"]
    errors = []
    if snapshot.get("schema_version") != 1 or isinstance(snapshot.get("schema_version"), bool):
        errors.append("schema_version 必须为 1")
    if snapshot.get("scope") != "simplified_shaft":
        errors.append("仅支持 scope=simplified_shaft")
    try:
        UUID(snapshot.get("entity_id", ""))
    except (ValueError, TypeError, AttributeError):
        errors.append("entity_id 必须是 UUID")

    segments = snapshot.get("segments")
    if not isinstance(segments, list) or len(segments) != 3:
        errors.append("首版必须有三个轴段")
        segments = []
    ids = []
    total = 0.0
    for i, segment in enumerate(segments):
        path = f"segments[{i}]"
        if not isinstance(segment, dict):
            errors.append(f"{path} 必须是对象")
            continue
        sid = segment.get("segment_id")
        if not isinstance(sid, str) or not sid.strip() or sid in ids:
            errors.append(f"{path}.segment_id 必须是非空且唯一的字符串")
        ids.append(sid)
        for field in ("length_m", "diameter_m", "min_diameter_m", "max_diameter_m"):
            if not _number(segment.get(field), positive=True):
                errors.append(f"{path}.{field} 必须为有限正数")
        if _number(segment.get("length_m"), positive=True):
            total += segment["length_m"]
        if all(_number(segment.get(k), positive=True)
               for k in ("diameter_m", "min_diameter_m", "max_diameter_m")):
            if not segment["min_diameter_m"] <= segment["diameter_m"] <= segment["max_diameter_m"]:
                errors.append(f"{path} 当前直径必须在给定区间内")
        if segment.get("editable") is not (i == 1):
            errors.append(f"{path}.editable 必须为 {i == 1}；仅开放中间段直径")

    material = snapshot.get("material")
    if not isinstance(material, dict):
        errors.append("缺少 material")
    else:
        for key in ("name", "source"):
            if not isinstance(material.get(key), str) or not material[key].strip():
                errors.append(f"material.{key} 必须是非空字符串")
        for key in ("young_modulus_pa", "allowable_stress_pa"):
            if not _number(material.get(key), positive=True):
                errors.append(f"material.{key} 必须为有限正数")

    supports = snapshot.get("supports_m")
    if not (isinstance(supports, list) and len(supports) == 2
            and all(_number(v) for v in supports)):
        errors.append("supports_m 必须给出两个有限的支点位置")
    elif not 0 <= supports[0] < supports[1] <= total:
        errors.append("支点必须在轴范围内，且左支点小于右支点")

    for name, fields in (("loads", ("fx_n", "fy_n")), ("torque_points", ("torque_nm",))):
        items = snapshot.get(name)
        if not isinstance(items, list):
            errors.append(f"必须显式提供 {name} 列表，无该载荷时用空列表")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{name}[{i}] 必须是对象")
                continue
            unsupported = item.keys() - {"z_m", *fields}
            if unsupported:
                errors.append(f"{name}[{i}] 含不支持的字段：{', '.join(sorted(unsupported))}；简化模型不能忽略额外载荷分量")
            if not _number(item.get("z_m")) or not 0 <= item["z_m"] <= total:
                errors.append(f"{name}[{i}].z_m 必须在轴范围内")
            for field in fields:
                if not _number(item.get(field)):
                    errors.append(f"{name}[{i}].{field} 必须是有限数")
    torque_points = snapshot.get("torque_points")
    if isinstance(torque_points, list) and all(
            isinstance(p, dict) and _number(p.get("torque_nm")) for p in torque_points):
        torques = [p["torque_nm"] for p in torque_points]
        if abs(sum(torques)) > 1e-9 * max(1.0, sum(abs(t) for t in torques)):
            errors.append("输入与输出转矩必须平衡")

    constraints = snapshot.get("constraints")
    if not isinstance(constraints, dict):
        errors.append("缺少 constraints")
    else:
        for key in ("alpha", "max_deflection_m"):
            if not _number(constraints.get(key), positive=True):
                errors.append(f"constraints.{key} 必须为有限正数")
    return errors


def _inputs(snapshot):
    segments = []
    z = 0.0
    for item in snapshot["segments"]:
        segments.append(shaft.Segment(z, item["length_m"], item["diameter_m"], item["segment_id"]))
        z += item["length_m"]
    case = shaft.ShaftLoadCase(
        tuple(snapshot["supports_m"]),
        [shaft.PointLoad(p["z_m"], fx=p["fx_n"], fy=p["fy_n"]) for p in snapshot["loads"]],
        [(p["z_m"], p["torque_nm"]) for p in snapshot["torque_points"]],
    )
    return segments, case


def review(snapshot: dict) -> dict:
    """校核指定尺寸；pass 仅指 checks 中列出的简化模型检查。"""
    errors = validate_snapshot(snapshot)
    if errors:
        return {"status": "blocked", "checks": [], "errors": errors, "limitations": list(LIMITATIONS)}
    segments, case = _inputs(snapshot)
    material = snapshot["material"]
    constraints = snapshot["constraints"]
    stress = shaft.check(segments, case, material["allowable_stress_pa"], constraints["alpha"])
    curve = shaft_stiffness.solve(segments, case, E=material["young_modulus_pa"])
    i = max(range(len(curve.z)), key=lambda n: math.hypot(curve.yx[n], curve.yy[n]))
    displacement = math.hypot(curve.yx[i], curve.yy[i])
    checks = [
        {"name": "nominal_combined_stress", "title": "名义弯扭合成应力",
         "status": "pass" if stress.ok else "fail", "value": stress.critical.sigma_ca,
         "limit": material["allowable_stress_pa"], "unit": "Pa",
         "utilization": stress.critical.sigma_ca / material["allowable_stress_pa"],
         "z_m": stress.critical.z, "segment_id": stress.critical.role,
         "formula": "sigma = sqrt(Mx^2 + My^2 + (alpha*T)^2)/(pi*d^3/32)",
         "source": "gongke_core.calc.shaft.check；实心圆截面名义弯扭合成应力公式",
         "limit_source": material["source"]},
        {"name": "maximum_deflection", "title": "梁模型最大挠度",
         "status": "pass" if displacement <= constraints["max_deflection_m"] else "fail",
         "value": displacement, "limit": constraints["max_deflection_m"], "unit": "m",
         "utilization": displacement / constraints["max_deflection_m"], "z_m": curve.z[i],
         "formula": "y'' = M/(E*I), I = pi*d^4/64; y(za)=y(zb)=0",
         "source": "Euler–Bernoulli 梁微分方程；gongke_core.calc.shaft_stiffness.solve",
         "limit_source": "当前工程 constraints.max_deflection_m 的输入限值"},
    ]
    return {"status": "pass" if all(c["status"] == "pass" for c in checks) else "fail",
            "scope": "simplified_shaft", "entity_id": snapshot["entity_id"],
            "checks": checks, "errors": [], "limitations": list(LIMITATIONS),
            "material_source": material["source"]}


def preview(snapshot: dict, segment_id: str, diameter_m: float) -> dict:
    """只改副本中的一个开放直径，返回候选校核和明确差异。"""
    errors = validate_snapshot(snapshot)
    if errors:
        return {"status": "blocked", "errors": errors, "limitations": list(LIMITATIONS)}
    target = next((s for s in snapshot["segments"] if s["segment_id"] == segment_id), None)
    if target is None or not target["editable"]:
        errors.append("目标轴段不存在或直径已锁定")
    elif not _number(diameter_m, positive=True):
        errors.append("diameter_m 必须为有限正数")
    elif not target["min_diameter_m"] <= diameter_m <= target["max_diameter_m"]:
        errors.append("候选直径超出当前工程允许的区间")
    if errors:
        return {"status": "blocked", "errors": errors, "limitations": list(LIMITATIONS)}
    candidate = deepcopy(snapshot)
    next(s for s in candidate["segments"] if s["segment_id"] == segment_id)["diameter_m"] = diameter_m
    result = review(candidate)
    return {"status": result["status"], "can_apply": result["status"] == "pass", "change": {"segment_id": segment_id,
            "parameter": "diameter_m", "old_value": target["diameter_m"],
            "new_value": diameter_m, "unit": "m"}, "candidate_snapshot": candidate,
            "review": result, "limitations": list(LIMITATIONS)}
