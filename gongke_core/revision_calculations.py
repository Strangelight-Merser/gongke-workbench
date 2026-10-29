"""只读修订的按项计算：输入不足只阻断依赖该输入的检查，不授予修改资格。"""

from __future__ import annotations

import math

from gongke_core.calc import shaft, shaft_stiffness


_LIMITATIONS = ["三段实心圆截面与简支梁假定", "名义弯扭应力不覆盖局部应力集中和完整疲劳",
                "挠度使用 Euler–Bernoulli 梁模型", "不代表配合、公差、制造或整机认可"]


def _finite(value, *, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (not positive or value > 0)


def assess(geometry, normalized):
    """geometry 必须是当前 CAD 的三段 diameter_m/length_m；不接受条件覆盖几何。"""
    si = normalized.get("si", {})
    material, constraints = si.get("material", {}), si.get("constraints", {})
    geometry_errors, segments = [], []
    measured = geometry.get("segments") if isinstance(geometry, dict) else None
    if not isinstance(measured, list) or len(measured) != 3:
        geometry_errors.append("当前几何须包含三个已识别实心圆轴段")
    else:
        start = 0.0
        for index, item in enumerate(measured):
            if not isinstance(item, dict) or any(not _finite(item.get(k), positive=True)
                                                 for k in ("length_m", "diameter_m")):
                geometry_errors.append(f"轴段 {index + 1} 缺少有效长度或明确的直径；不能把半径当作直径")
                continue
            segments.append(shaft.Segment(start, item["length_m"], item["diameter_m"],
                                          item.get("segment_id", f"segment_{index + 1}")))
            start += item["length_m"]
    total = sum(s.length for s in segments)
    common = list(geometry_errors)
    if si.get("coordinate_system") != "body_local_x" or si.get("position_mode") != "fixed_body_coordinate":
        common.append("待确认 Body 局部坐标与固定位置声明")
    supports = si.get("supports_m")
    if not (isinstance(supports, list) and len(supports) == 2 and all(_finite(x) for x in supports)
            and 0 <= supports[0] < supports[1] <= total):
        common.append("待确认位于当前轴内的两个简支点")
    loads = si.get("loads")
    if not isinstance(loads, list):
        common.append("待确认横向载荷；未提供不等于零载")
    elif any(not isinstance(p, dict) or set(p) != {"z_m", "fx_n", "fy_n"}
             or not all(_finite(p[k]) for k in ("z_m", "fx_n", "fy_n"))
             or not 0 <= p["z_m"] <= total for p in loads):
        common.append("横向载荷包含未支持分量、无效值或轴外作用位置")

    checks = []

    def unavailable(name, title, unit, reasons):
        checks.append({"name": name, "title": title, "status": "unavailable", "value": None,
                       "unit": unit, "limit": None, "reasons": reasons})

    def numerical(name, title, unit, value, limit, limit_name, location, **extra):
        status = "unknown" if limit is None else ("pass" if value <= limit else "fail")
        checks.append({"name": name, "title": title, "status": status, "value": value,
                       "unit": unit, "limit": limit, "z_m": location,
                       "reasons": [f"{limit_name}未确认，只提供数值，不作合格判断"] if limit is None else [],
                       **extra})

    stress_reasons = list(common)
    torques = si.get("torque_points")
    if not isinstance(torques, list):
        stress_reasons.append("待确认输入与输出转矩；未提供不等于零转矩")
    elif any(not isinstance(p, dict) or set(p) != {"z_m", "torque_nm"}
             or not all(_finite(p[k]) for k in ("z_m", "torque_nm"))
             or not 0 <= p["z_m"] <= total for p in torques):
        stress_reasons.append("转矩包含无效值或轴外作用位置")
    elif abs(sum(p["torque_nm"] for p in torques)) > 1e-9 * max(1, sum(abs(p["torque_nm"]) for p in torques)):
        stress_reasons.append("输入与输出转矩不平衡")
    alpha = constraints.get("alpha")
    if not _finite(alpha, positive=True):
        stress_reasons.append("待确认弯扭折合系数")
    if stress_reasons:
        unavailable("nominal_combined_stress", "名义弯扭合成应力", "Pa", stress_reasons)
    else:
        case = shaft.ShaftLoadCase(tuple(supports), [shaft.PointLoad(p["z_m"], fx=p["fx_n"], fy=p["fy_n"]) for p in loads],
                                  [(p["z_m"], p["torque_nm"]) for p in torques])
        limit = material.get("allowable_stress_pa")
        # check 的数值求解不使用限值；缺限值显式传 None，仅取 critical，不访问其 ok 属性。
        # 这样复用相同采样与公式，也不会套用该底层函数的默认 60 MPa。
        result = shaft.check(segments, case, sigma_allow=limit, alpha=alpha)
        numerical("nominal_combined_stress", "名义弯扭合成应力", "Pa", result.critical.sigma_ca,
                  limit, "名义许用应力", result.critical.z, segment_id=result.critical.role)

    stiffness_reasons = list(common)
    elastic = material.get("young_modulus_pa")
    if not _finite(elastic, positive=True):
        stiffness_reasons.append("待确认弹性模量")
    if stiffness_reasons:
        unavailable("maximum_deflection", "梁模型最大挠度", "m", stiffness_reasons)
    else:
        # 横向梁挠度不依赖转矩及名义应力限值。
        case = shaft.ShaftLoadCase(tuple(supports), [shaft.PointLoad(p["z_m"], fx=p["fx_n"], fy=p["fy_n"]) for p in loads], [])
        curve = shaft_stiffness.solve(segments, case, E=elastic)
        i = max(range(len(curve.z)), key=lambda n: math.hypot(curve.yx[n], curve.yy[n]))
        numerical("maximum_deflection", "梁模型最大挠度", "m", math.hypot(curve.yx[i], curve.yy[i]),
                  constraints.get("max_deflection_m"), "最大挠度限值", curve.z[i])

    status = "fail" if any(c["status"] == "fail" for c in checks) else (
        "pass" if all(c["status"] == "pass" for c in checks) else "unknown")
    return {"checks": checks, "input_confirmation": normalized.get("status", "incomplete"),
            "input_issues": normalized.get("issues", []), "geometry_issues": geometry_errors,
            "method_coverage": {"scope": "simplified_shaft", "limitations": list(_LIMITATIONS)},
            "numerical_status": status,
            "modification_eligibility": {"allowed": False, "reason": "只读修订检查不授予原生修改资格"}}
