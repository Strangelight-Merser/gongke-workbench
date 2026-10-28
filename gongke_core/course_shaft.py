"""课程减速器输出轴的当前快照、校核与受控圆角修改。

保留设计对象的完整输入，不从展示摘要反推。按快照声明的映射状态复算当前几何，
分别呈现数值、接口冲突和来源缺口；轴径锁定，仅开放右轴承邻接轴肩的受限增圆角。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import math
from uuid import uuid4

from gongke_core import bearing_reference
from gongke_core.calc import fatigue, key as key_calc, shaft, shaft_stiffness


def _source(reference, status="unverified"):
    return {"reference": reference, "status": status}


def _fatigue_method_sources():
    # 扭转只核对到期刊对原图表的转引；不得把局部公式一致升级为完整方法域核实。
    return {
        "status": "unverified",
        "references": [
            {"method": "torsion_shoulder", "status": "verified_secondary_formula_reproduction",
             "url": "https://rdj.journals.ac.za/index.php/pub/article/download/57/58/141",
             "reference": "J. P. Jordaan (2025), Fig. 3；转引 Peterson 第二版 Chart 3.12",
             "note": "已核对扭转系数和 0.25 ≤ t/r ≤ 4；D=145、d=120、r=6 的系数约 1.56547，与图中 1.57 一致。"},
            {"method": "bending_shoulder", "status": "unverified_formula_page",
             "url": "https://doi.org/10.1002/9780470211106.ch3",
             "reference": "Peterson's Stress Concentration Factors，Wiley Chapter 3",
             "note": "仅确认书目信息；公式页访问返回 403，弯曲公式和实现中 0.1 ≤ t/r ≤ 20 尚未独立核实。"},
        ],
        "limitations": [
            "D/d、r/d 的完整适用域尚未核实；满足 t/r 条件不等于完整方法域已确认。",
            "相邻键槽、轴肩等缺口的相互作用尚未核实；当前按孤立缺口近似，不能据此认定整轴疲劳合格。",
        ],
    }


def from_design(design_result, shaft_index=2):
    """从 coupling 设计结果初始化低速输出轴快照；shaft_index 为零基索引。"""
    if design_result.task.scheme != "coupling" or shaft_index != 2 or len(design_result.shafts) != 3:
        raise ValueError("当前只支持 coupling 二级减速器的低速输出轴（shaft_index=2）")
    result = design_result.shafts[shaft_index]
    layout = result.layout
    if not layout.segments:
        raise ValueError("输出轴没有分段")
    entity_id = str(uuid4())
    origin = layout.segments[0].z0
    segments = []
    for i, segment in enumerate(layout.segments):
        keyway = None
        if segment.keyway:
            b, t1, length = segment.keyway
            keyway = {"width_m": b, "depth_m": t1, "length_m": length,
                      "center_z_m": segment.z0 + segment.length / 2,
                      "source": _source("当前 design.ShaftResult 的平键选择结果；位置按轴段居中", "computed")}
        segments.append({
            "segment_id": f"{entity_id}/segment/{i + 1}", "design_segment_index": i,
            "role": segment.role, "z0_m": segment.z0, "length_m": segment.length,
            "diameter_m": segment.d, "root_diameter_m": segment.root_d,
            "keyway": keyway, "editable": False,
        })
    fillets = []
    for i, (left, right) in enumerate(zip(layout.segments, layout.segments[1:])):
        if abs((left.root_d or left.d) - (right.root_d or right.d)) < 1e-6:
            continue
        small, large = (left, right) if (left.root_d or left.d) < (right.root_d or right.d) else (right, left)
        fillets.append({
            "left_segment_id": segments[i]["segment_id"], "right_segment_id": segments[i + 1]["segment_id"],
            "z_m": right.z0, "assumed_radius_m": fatigue.fillet_radius(small, large),
            "cad_radius_m": None,
            "source": _source("calc.fatigue.fillet_radius：轴承邻接处 1 mm，其余约 0.04d 并限制于 1–2.5 mm", "assumed"),
            "status": "not_mapped_to_cad",
        })
    bearing = layout.bearing
    fat = result.fatigue
    task = design_result.task
    # 这是原布局使用的近似，不是厂商安装尺寸。保留该规则是为了阻止无依据地突破现有定位约束。
    abutment = max(bearing.d + 0.2 * (bearing.D - bearing.d), bearing.d + 0.002)
    bearing_interfaces = []
    for side, z in zip(("left", "right"), layout.bearing_z):
        bearing_interfaces.append({
            "side": side, "center_z_m": z, "seat_start_z_m": z - bearing.B / 2,
            "seat_length_m": bearing.B, "designation": bearing.designation, "manufacturer": None,
            "bore_m": bearing.d, "outside_diameter_m": bearing.D, "width_m": bearing.B,
            "dynamic_load_rating_n": bearing.Cr, "static_load_rating_n": bearing.C0r,
            "dimensions_source": _source("data/standards/GB-T_276-2013_deep_groove_ball_bearings.yaml；当前设计选中的尺寸", "recorded"),
            "ratings_source": _source("现有常用手册数值，未指定厂商产品原页"),
            "abutment_minimum_m": abutment,
            "abutment_source": _source("layout.reducer.diameters：max(d+0.2(D-d), d+2 mm)", "project_approximation"),
            "manufacturer_abutment_source": None,
        })
    loads = [{"z_m": p.z, "fx_n": p.fx, "fy_n": p.fy, "fz_n": p.fz,
              "x0_m": p.x0, "y0_m": p.y0, "label": p.label,
              "couple_xz_nm": p.couple_xz, "couple_yz_nm": p.couple_yz}
             for p in result.load_case.loads]
    coupling = design_result.couplings[-1]
    end = next(segment for segment in layout.segments if segment.role == "端部")
    return {
        "schema_version": 1, "scope": "course_shaft_review", "read_only": False,
        "editable_parameters": ["right_bearing_shoulder_radius_m"],
        "entity_id": entity_id, "name": layout.name, "design_shaft_index": shaft_index,
        "z_origin_m": origin, "coordinate_convention": "所有 z_m/z0_m/supports_m 均为原设计坐标；局部轴坐标 = 原坐标 - z_origin_m。",
        "segments": segments, "supports_m": list(result.load_case.supports), "loads": loads,
        "torque_points": [{"z_m": z, "torque_nm": value} for z, value in result.load_case.torque_points],
        "load_source": _source("当前 design.gear_loads 与传动任务计算；包含斜齿轮轴向力及偏心力偶，非实测", "computed"),
        "power_w": result.power, "speed_rpm": result.speed_rpm, "torque_nm": result.torque,
        "material": {
            "name": fat.material.name, "young_modulus_pa": shaft_stiffness.E_STEEL,
            "ultimate_strength_pa": fat.material.sigma_b, "bending_fatigue_limit_pa": fat.material.sigma_m1,
            "torsion_fatigue_limit_pa": fat.material.tau_m1, "psi_sigma": fat.material.psi_sigma,
            "psi_tau": fat.material.psi_tau,
            "source": _source("calc.fatigue.MATERIALS 声明《机械设计》第八版表 15-1；原页和适用性尚未独立核实；弹性模量来自 shaft_stiffness.E_STEEL"),
        },
        "analysis_parameters": {
            "allowable_nominal_stress_pa": result.strength.sigma_allow, "alpha": result.strength.alpha,
            "required_fatigue_safety_factor": fat.S_required, "fit_k_sigma": task.shaft_fit_k,
            "key_allowable_pressure_pa": task.key_sigma_allow,
            "source": _source("ReducerTask 与 calc 默认条件；许用值、材料与疲劳近似尚未独立核实"),
        },
        "stiffness_limits": [{"label": item.label, "kind": item.kind, "z_m": item.z,
                              "limit": item.allow, "unit": "m" if item.kind == "y" else "rad",
                              "source": _source("shaft_stiffness.check 声明《机械设计》第九版表 15-5；原表未独立核实")}
                             for item in (result.stiffness.items if result.stiffness else [])],
        "bearing_interfaces": bearing_interfaces,
        "gear_interfaces": [{"pair": g.pair, "member": g.member, "center_z_m": g.z,
                             "width_m": g.width, "seat_diameter_m": g.seat_d,
                             "mount_direction": g.mount, "integral": g.integral,
                             "root_diameter_m": g.root_d, "tip_diameter_m": g.tip_d}
                            for g in layout.gears],
        "key_connections": [{"location": key.location, "shaft_diameter_m": key.d,
                             "segment_id": next(segment["segment_id"] for segment in segments
                                                if segment["keyway"] is not None
                                                and segment["diameter_m"] == key.d
                                                and segment["keyway"]["width_m"] == key.size.b),
                             "torque_nm": result.torque,
                             "width_m": key.size.b, "height_m": key.size.h,
                             "shaft_slot_depth_m": key.size.t1, "hub_slot_depth_m": key.size.t2,
                             "length_m": key.length, "count": key.count,
                             "allowable_pressure_pa": key.sigma_allow,
                             "source": _source("design._shaft 选择结果；许用挤压应力和连接适用条件尚未独立核实")}
                            for key in result.keys],
        "coupling_interface": {"extension": layout.extension, "hub_length_m": layout.coupling_hub,
                               "center_z_m": end.z0 + end.length / 2, "shaft_bore_index": 0,
                               "location": coupling.location, "required_torque_nm": coupling.torque,
                               "required_bores_m": list(coupling.bores),
                               "model": None, "source": _source("当前设计仅给出所需孔径/轮毂长度，未闭合具体联轴器型号")},
        "fillet_assumptions": fillets,
        "limitations": [
            "快照初始化自完整设计对象；当前 CAD 参数及特征的对应状态见 cad_geometry_state。",
            "无键槽不等于无结构约束；轴环定位齿轮，轴肩定位轴承。",
            "轴径保持锁定；右轴承邻接轴肩仅可在声明范围内增大圆角，几何写入不代表安装、配合或整轴疲劳认证。",
        ],
    }


def _number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not positive or value > 0))


def _current_inputs(snapshot):
    """重建固定尺寸和完整集中载荷，力偶由 fz 与偏心重新计算。"""
    if snapshot.get("scope") != "course_shaft_review" or snapshot.get("schema_version") != 1:
        raise ValueError("需要 course_shaft_review 版本 1 的完整快照")
    segments = []
    for item in snapshot["segments"]:
        if not all(_number(item[k], positive=k != "z0_m") for k in ("z0_m", "length_m", "diameter_m")):
            raise ValueError("轴段位置、长度或直径无效")
        if segments and not math.isclose(item["z0_m"], segments[-1].z1, abs_tol=1e-9):
            raise ValueError("当前轴段不连续")
        kw = item["keyway"]
        keyway = None
        if kw:
            if not all(_number(kw[k], True) for k in ("width_m", "depth_m", "length_m")):
                raise ValueError("键槽尺寸无效")
            if kw["length_m"] > item["length_m"] + 1e-9 or kw["depth_m"] >= item["diameter_m"] / 2:
                raise ValueError("键槽超出当前轴段范围")
            if not math.isclose(kw["center_z_m"], item["z0_m"] + item["length_m"] / 2, abs_tol=1e-9):
                raise ValueError("当前计算仅支持已绑定的轴段居中键槽")
            keyway = (kw["width_m"], kw["depth_m"], kw["length_m"])
        segments.append(shaft.Segment(item["z0_m"], item["length_m"], item["diameter_m"],
                                      item["role"], keyway, item["root_diameter_m"]))
        if shaft.section_modulus(segments[-1].d, keyway) <= 0:
            raise ValueError("当前截面的有效截面系数非正")
    if not segments:
        raise ValueError("缺少轴段")
    supports = snapshot["supports_m"]
    if len(supports) != 2 or not all(_number(z) for z in supports) or not segments[0].z0 <= supports[0] < supports[1] <= segments[-1].z1:
        raise ValueError("支点必须位于轴范围内且顺序正确")
    loads = []
    for p in snapshot["loads"]:
        if not all(_number(p[k]) for k in ("z_m", "fx_n", "fy_n", "fz_n", "x0_m", "y0_m")):
            raise ValueError("缺少完整且有限的集中载荷及偏心位置")
        if not segments[0].z0 <= p["z_m"] <= segments[-1].z1:
            raise ValueError("集中载荷不在当前轴范围内")
        loads.append(shaft.PointLoad(p["z_m"], p["fx_n"], p["fy_n"], p["fz_n"],
                                    p["x0_m"], p["y0_m"], p["label"]))
    torques = []
    for p in snapshot["torque_points"]:
        if not _number(p["z_m"]) or not _number(p["torque_nm"]) or not segments[0].z0 <= p["z_m"] <= segments[-1].z1:
            raise ValueError("转矩位置或数值无效")
        torques.append((p["z_m"], p["torque_nm"]))
    if abs(sum(t for _, t in torques)) > 1e-9 * max(1.0, sum(abs(t) for _, t in torques)):
        raise ValueError("输入输出转矩不平衡")
    return segments, shaft.ShaftLoadCase(tuple(supports), loads, torques)


def _geometry_gaps(snapshot):
    """CAD 读取层只填写事实；派生计算不改变几何映射状态。"""
    state = snapshot.get("cad_geometry_state")
    if state is None:
        return ["当前数值基于声明的轴快照，尚未绑定当前 CAD 参数和特征。"]
    gaps = []
    if state.get("parameters_current") is not True:
        gaps.append("当前 CAD 参数映射缺失或已过期，不能把旧快照计算称为当前轴计算。")
    if state.get("keyways_current") is not True:
        gaps.append("当前 CAD 键槽尚未与计算截面对应。")
    if state.get("fillets_current") is not True:
        gaps.append("当前 CAD 圆角尚未与疲劳计算对应。")
    if state.get("load_binding_current") is False:
        gaps.append("轴段长度改变后，原设计载荷、支点和配合位置尚未重新绑定。")
    if state.get("unsupported_features"):
        gaps.append("存在尚未覆盖的 CAD 特征：" + ", ".join(state["unsupported_features"]))
    return gaps


def _finite_sections(sections):
    # 无该应力分量时疲劳安全系数为无穷；JSON 用 null，并保留 unbounded_fields 说明。
    rows = []
    for section in sections:
        row = asdict(section)
        unbounded = [key for key, value in row.items() if isinstance(value, float) and math.isinf(value)]
        for key in unbounded:
            row[key] = None
        row["unbounded_fields"] = unbounded
        rows.append(row)
    return rows


def _right_shoulder_comparisons(snapshot):
    """只比较与右轴承实际邻接的轴肩，不把通用型号指定为某一厂家产品。"""
    bearings = [item for item in snapshot["bearing_interfaces"] if item["side"] == "right"]
    if len(bearings) != 1:
        return [], "右轴承接口未唯一绑定，未作厂商尺寸比较。"
    bearing = bearings[0]
    if str(bearing["designation"]) != "6211":
        return [], "当前右轴承型号不是已核对的开式 6211，未套用引用。"
    expected = bearing_reference.lookup("SKF")["dimensions"]
    for field, reference_field in (("bore_m", "bore_m"), ("outside_diameter_m", "outside_m"), ("width_m", "width_m")):
        if not math.isclose(bearing[field], expected[reference_field], rel_tol=0, abs_tol=1e-9):
            return [], "当前右轴承外形尺寸与已核对的 55×100×21 mm 不一致，未套用引用。"
    seat_z = bearing["seat_start_z_m"]
    shoulders = [s for s in snapshot["segments"] if s["role"] == "轴肩"
                 and math.isclose(s["z0_m"] + s["length_m"], seat_z, rel_tol=0, abs_tol=1e-9)]
    seats = [s for s in snapshot["segments"] if s["role"] == "轴承"
             and math.isclose(s["z0_m"], seat_z, rel_tol=0, abs_tol=1e-9)
             and math.isclose(s["diameter_m"], bearing["bore_m"], rel_tol=0, abs_tol=1e-9)
             and s["length_m"] >= bearing["seat_length_m"] - 1e-9]
    if len(shoulders) != 1 or len(seats) != 1:
        return [], "当前右轴承与轴肩的位置或轴径关联不一致，未作厂商尺寸比较。"
    shoulder, seat = shoulders[0], seats[0]
    fillets = [f for f in snapshot["fillet_assumptions"]
               if f["left_segment_id"] == shoulder["segment_id"] and f["right_segment_id"] == seat["segment_id"]]
    radius = fillets[0]["cad_radius_m"] if len(fillets) == 1 else None
    rows = []
    for name in ("SKF", "NSK", "Koyo"):
        reference = bearing_reference.lookup(name)
        result = bearing_reference.check_abutment(reference, shoulder["diameter_m"], radius)
        rows.append({"label": f"与 {name} 开式 6211 安装尺寸比较，未选定该厂商",
                     "segment_id": shoulder["segment_id"], "bearing_side": "right",
                     "selected_manufacturer": None, "reference": result["reference"],
                     "dimension_checks": result["checks"], "status": result["status"],
                     "limitations": result["limitations"]})
    return rows, "仅比较右侧相邻轴肩；不改变通用轴承型号、容量或供应商选择。"


def _interface_checks(snapshot):
    """比较现有对象与固定接口的名义尺寸；不推断未声明的制造公差或密封标准。"""
    checks = []
    segments = snapshot["segments"]
    source = _source("完整 design 结果初始化的固定接口条件；名义尺寸一致性不代表制造配合公差合格", "initial_design_interface")

    def seat(name, title, center, required, role):
        candidates = [s for s in segments if s["role"] == role and s["z0_m"] <= center <= s["z0_m"] + s["length_m"]]
        if len(candidates) != 1:
            checks.append({"name": name, "title": title, "status": "blocked", "z_m": center,
                           "reason": f"{title}的固定中心位置未唯一对应当前{role}段。", "source": deepcopy(source)})
            return
        target = candidates[0]
        matched = math.isclose(target["diameter_m"], required, rel_tol=0, abs_tol=1e-9)
        checks.append({"name": name, "title": title, "status": "pass" if matched else "fail",
                       "segment_id": target["segment_id"], "z_m": center,
                       "value": target["diameter_m"], "required_diameter_m": required,
                       "unit": "m", "comparison": "nominal_match",
                       "reason": (f"{title}与固定接口名义尺寸一致；未校核制造配合公差。" if matched
                                  else f"{title}当前直径 {target['diameter_m'] * 1000:g} mm 与固定接口 {required * 1000:g} mm 不一致。"),
                       "source": deepcopy(source)})

    for bearing in snapshot["bearing_interfaces"]:
        side = bearing["side"]
        seat(f"bearing_seat_{side}", ("左" if side == "left" else "右") + "轴承座", bearing["center_z_m"], bearing["bore_m"], "轴承")
        for segment in segments:
            if segment["role"] != "轴肩":
                continue
            adjacent = (math.isclose(segment["z0_m"] + segment["length_m"], bearing["seat_start_z_m"], rel_tol=0, abs_tol=1e-9)
                        or math.isclose(segment["z0_m"], bearing["seat_start_z_m"] + bearing["seat_length_m"], rel_tol=0, abs_tol=1e-9))
            if adjacent:
                minimum = bearing["abutment_minimum_m"]
                checks.append({"name": "project_layout_abutment_minimum", "title": ("左" if side == "left" else "右") + "轴承定位布局约束",
                               "segment_id": segment["segment_id"], "bearing_side": side,
                               "status": "fail" if segment["diameter_m"] < minimum - 1e-12 else "pass",
                               "value_m": segment["diameter_m"], "minimum_m": minimum,
                               "reason": "保持项目既有布局近似下限；低于它表示既有接口约束冲突，不表示违反所有 6211 厂商的通用安装下限。",
                               "source_status": "project_approximation", "source": deepcopy(bearing["abutment_source"])})
    for i, gear in enumerate(snapshot["gear_interfaces"]):
        if not gear["integral"]:
            seat(f"gear_seat_{i}", "齿轮安装座", gear["center_z_m"], gear["seat_diameter_m"], "齿轮")
    coupling = snapshot["coupling_interface"]
    if "center_z_m" not in coupling or "shaft_bore_index" not in coupling:
        checks.append({"name": "coupling_seat", "status": "blocked", "reason": "联轴器固定中心或本轴孔径映射未提供。", "source": deepcopy(source)})
    else:
        seat("coupling_seat", "输出联轴器轴伸", coupling["center_z_m"], coupling["required_bores_m"][coupling["shaft_bore_index"]], "端部")
    by_id = {s["segment_id"]: s for s in segments}
    for i, connection in enumerate(snapshot["key_connections"]):
        segment = by_id.get(connection["segment_id"])
        keyway = segment["keyway"] if segment is not None else None
        if keyway is None:
            checks.append({"name": f"key_geometry_{i}", "title": connection["location"] + "键槽对应关系",
                           "status": "fail", "segment_id": connection["segment_id"],
                           "reason": "当前轴段没有与选定键连接对应的键槽，不能沿用原挤压校核。",
                           "source": deepcopy(source)})
            continue
        dimensions = []
        for field, expected_field, label in (("width_m", "width_m", "槽宽"),
                                              ("length_m", "length_m", "槽长"),
                                              ("depth_m", "shaft_slot_depth_m", "轴槽深")):
            expected = connection[expected_field]
            matched = math.isclose(keyway[field], expected, rel_tol=0, abs_tol=1e-9)
            dimensions.append({"field": field, "label": label, "value_m": keyway[field],
                               "required_m": expected, "status": "pass" if matched else "fail"})
        differences = [d for d in dimensions if d["status"] == "fail"]
        reason = ("当前槽形与选定连接的声明尺寸一致；未据此确认加工公差。" if not differences else
                  "；".join(f"{d['label']}当前 {d['value_m'] * 1000:g} mm，声明 {d['required_m'] * 1000:g} mm" for d in differences)
                  + "。槽形改变后不能沿用原键挤压假设，需重新核对连接；此差异不是完整制造合格判定。")
        checks.append({"name": f"key_geometry_{i}", "title": connection["location"] + "键槽对应关系",
                       "status": "fail" if differences else "pass", "segment_id": connection["segment_id"],
                       "dimension_checks": dimensions, "reason": reason, "source": deepcopy(source)})
    return checks


def review(snapshot):
    """复算声明快照的当前尺寸；数值结论与材料来源、CAD 覆盖分别返回。"""
    checks = []
    gaps = _geometry_gaps(snapshot)
    state = snapshot.get("cad_geometry_state")
    out = {"status": "blocked", "can_apply": False, "scope": "course_shaft_review",
           "entity_id": snapshot.get("entity_id"), "checks": checks, "blocked_reasons": gaps,
           "geometry_basis": "current_parameters_declared_features" if state and state.get("parameters_current") else "declared_snapshot",
           "fatigue_method_sources": _fatigue_method_sources(),
           "limitations": deepcopy(snapshot.get("limitations", [])), "errors": []}
    if snapshot.get("analysis_basis") == "hypothetical_dimensions":
        out["geometry_basis"] = "hypothetical_snapshot"
    if state and (state.get("parameters_current") is not True or state.get("unsupported_features")
                  or state.get("load_binding_current") is False):
        return out
    try:
        segments, case = _current_inputs(snapshot)
        interface_checks = _interface_checks(snapshot)
        checks.extend(interface_checks)
        gaps.extend(item["reason"] for item in interface_checks if item["status"] in ("fail", "blocked"))
        comparisons, comparison_note = _right_shoulder_comparisons(snapshot)
        out["manufacturer_comparisons"] = comparisons
        out["manufacturer_comparison_note"] = comparison_note
        material = snapshot["material"]
        params = snapshot["analysis_parameters"]
        for key in ("young_modulus_pa", "ultimate_strength_pa", "bending_fatigue_limit_pa", "torsion_fatigue_limit_pa"):
            if not _number(material[key], True):
                raise ValueError(f"材料参数 {key} 必须为有限正数")
        for key in ("allowable_nominal_stress_pa", "alpha", "required_fatigue_safety_factor"):
            if not _number(params[key], True):
                raise ValueError(f"分析参数 {key} 必须为有限正数")
        nominal = shaft.check(segments, case, params["allowable_nominal_stress_pa"], params["alpha"])
        checks.append({"name": "nominal_combined_stress", "title": "声明截面的名义弯扭应力",
                       "status": "pass" if nominal.ok else "fail", "value": nominal.critical.sigma_ca,
                       "limit": nominal.sigma_allow, "unit": "Pa", "z_m": nominal.critical.z,
                       "source": deepcopy(params["source"]),
                       "assumptions": ["保留轴向力偏心产生的弯矩；此公式不计轴向直接正应力。"]})
        out["reactions"] = asdict(nominal.reactions)
        out["load_couples"] = [{"z_m": p.z, "couple_xz_nm": p.couple_xz, "couple_yz_nm": p.couple_yz} for p in case.loads]
        curve = shaft_stiffness.solve(segments, case, E=material["young_modulus_pa"])
        for i, item in enumerate(snapshot["stiffness_limits"]):
            if item["kind"] not in ("y", "θ") or not _number(item["limit"], True):
                raise ValueError("刚度限值不完整")
            value = curve.deflection(item["z_m"]) if item["kind"] == "y" else curve.slope(item["z_m"])
            checks.append({"name": f"stiffness_{i}", "title": item["label"], "kind": item["kind"],
                           "status": "pass" if value <= item["limit"] else "fail", "value": value,
                           "limit": item["limit"], "unit": item["unit"], "z_m": item["z_m"],
                           "source": deepcopy(item["source"])})
        if not snapshot["stiffness_limits"]:
            gaps.append("缺少刚度控制位置或限值，未形成刚度通过结论。")

        by_id = {s["segment_id"]: s for s in snapshot["segments"]}
        for i, connection in enumerate(snapshot["key_connections"]):
            geometry = next(c for c in interface_checks if c["name"] == f"key_geometry_{i}")
            if geometry["status"] != "pass":
                checks.append({"name": f"key_{i}", "title": connection["location"] + "键挤压",
                               "status": "blocked", "segment_id": connection["segment_id"],
                               "reason": geometry["reason"], "source": deepcopy(connection["source"])})
                continue
            segment = by_id[connection["segment_id"]]
            if connection["count"] != 1:
                checks.append({"name": f"key_{i}", "status": "blocked", "reason": "当前几何映射仅覆盖单键连接。"})
                gaps.append("双键承载与当前单槽几何不一致，未计算该连接。")
                continue
            working_length = connection["length_m"] - connection["width_m"]
            if not _number(working_length, True) or not _number(connection["height_m"], True):
                raise ValueError("键的工作长度或高度非正")
            value = key_calc.crush_stress(abs(connection["torque_nm"]), segment["diameter_m"],
                                          connection["height_m"], working_length, connection["count"])
            checks.append({"name": f"key_{i}", "title": connection["location"] + "键挤压",
                           "status": "pass" if value <= connection["allowable_pressure_pa"] else "fail",
                           "value": value, "limit": connection["allowable_pressure_pa"], "unit": "Pa",
                           "segment_id": segment["segment_id"], "source": deepcopy(connection["source"])})

        # 完整原生映射优先用实际 Radius；声明快照仍可提供明确标注的推定圆角条件值。
        declared_fillets = {(f["left_segment_id"], f["right_segment_id"]): f for f in snapshot["fillet_assumptions"]}
        fillet_consistent = True
        actual_fillets = bool(state and state.get("fillets_current") is True)
        actual_radii = {}
        for i, (left, right) in enumerate(zip(segments, segments[1:])):
            if math.isclose(left.d, right.d, abs_tol=1e-6):
                continue
            small, large = (left, right) if left.d < right.d else (right, left)
            item = declared_fillets.get((snapshot["segments"][i]["segment_id"], snapshot["segments"][i + 1]["segment_id"]))
            if actual_fillets:
                if item is None or not _number(item["cad_radius_m"], True):
                    fillet_consistent = False
                else:
                    actual_radii[i + 1] = item["cad_radius_m"]
            else:
                if item is None or not math.isclose(item["assumed_radius_m"], fatigue.fillet_radius(small, large), abs_tol=1e-9):
                    fillet_consistent = False
                if item is not None and item["cad_radius_m"] is not None and not math.isclose(item["cad_radius_m"], item["assumed_radius_m"], abs_tol=1e-9):
                    fillet_consistent = False
        if fillet_consistent:
            mat = fatigue.ShaftMaterial(material["name"], material["ultimate_strength_pa"], material["bending_fatigue_limit_pa"],
                                        material["torsion_fatigue_limit_pa"], material["psi_sigma"], material["psi_tau"])
            fat = fatigue.check(segments, case, mat, params["required_fatigue_safety_factor"], params["fit_k_sigma"],
                                shoulder_radii=actual_radii if actual_fillets else None)
            basis = "cad_shoulder_fillets" if actual_fillets else "assumed_fillets"
            out["fatigue_sections"] = _finite_sections(fat.sections)
            for row in out["fatigue_sections"]:
                row["status"] = "pass" if row["S_ca"] is not None and row["S_ca"] >= fat.S_required else "fail" if row["S_ca"] is not None else "not_applicable"
                if row["feature"] == "轴肩圆角":
                    row["geometry_basis"] = basis
                    joint = next(f for f in snapshot["fillet_assumptions"] if math.isclose(f["z_m"], row["z"], rel_tol=0, abs_tol=1e-9))
                    row["left_segment_id"] = joint["left_segment_id"]
                    row["right_segment_id"] = joint["right_segment_id"]
                elif row["feature"] == "键槽":
                    row["geometry_basis"] = "assumed_keyway_root"
                    row["conditional_status"] = row["status"]
                    row["status"] = "blocked"
                    row["radius_source"] = _source("calc.fatigue._section：r=0.02d，用于缺口敏感性估算", "assumed")
                    row["reason"] = "槽根实体圆角尚未绑定；此处 r 是推定值，不能用槽的平面圆头半径替代，也不能据此认定当前键槽疲劳通过。"
                else:
                    row["geometry_basis"] = "declared_fit_coefficient"
            assumed_keyway_roots = any(row["geometry_basis"] == "assumed_keyway_root" for row in out["fatigue_sections"])
            if assumed_keyway_roots:
                gaps.append("键槽疲劳仍以 r=0.02d 估计槽根缺口敏感性，尚未绑定实体槽根圆角；保留条件值，不形成当前几何疲劳通过结论。")
            aggregate_basis = "cad_shoulders_assumed_keyway_roots" if actual_fillets and assumed_keyway_roots else basis
            out["fatigue_unsupported_sections"] = deepcopy(fat.unsupported_sections)
            for item in out["fatigue_unsupported_sections"]:
                index = item["right_segment_index"]
                item["left_segment_id"] = snapshot["segments"][index - 1]["segment_id"]
                item["right_segment_id"] = snapshot["segments"][index]["segment_id"]
                gaps.append(f"轴向 z={item['z'] * 1000:g} mm 的实际圆角 t/r={item['t_over_r']:g} 超出当前模型范围：{item['reason']}。未使用夹紧值计算该截面。")
            if fat.critical is not None and math.isfinite(fat.critical.S_ca):
                checks.append({"name": "fatigue_current_geometry" if actual_fillets else "fatigue_assumed_geometry",
                               "title": "当前轴肩与推定键槽根部条件下的疲劳安全系数" if actual_fillets and assumed_keyway_roots else "当前轴肩圆角条件下的疲劳安全系数" if actual_fillets else "推定圆角条件下的疲劳安全系数",
                               "status": "blocked" if fat.unsupported_sections or assumed_keyway_roots else "pass" if fat.ok else "fail", "value": fat.critical.S_ca,
                               "limit": fat.S_required, "comparison": ">=", "unit": "1", "z_m": fat.critical.z,
                               "value_scope": "minimum_of_evaluated_sections",
                               "source": deepcopy(material["source"]), "geometry_basis": aggregate_basis,
                               "assumptions": ["轴肩圆角按标明的几何来源计算；键槽应力集中仍采用原有近似。"]})
            else:
                gaps.append("疲劳模型没有有限的危险截面结果，不能生成疲劳通过结论。")
        else:
            gaps.append("实际圆角读取不完整，未计算疲劳结论。" if actual_fillets else "当前圆角声明与现有疲劳模型的角色近似不一致，未计算疲劳结论。")
        if params["fit_k_sigma"] is None:
            gaps.append("齿轮过盈配合疲劳系数未提供，轮毂端截面尚未覆盖。")
        if any(p.fz != 0 for p in case.loads):
            gaps.append("已保留轴向力偏心弯矩，但名义弯扭和疲劳公式未计轴向直接应力。")
        if material["source"]["status"] != "verified" or params["source"]["status"] != "verified":
            gaps.append("材料疲劳参数或许用条件尚未独立核实；数值通过只对声明输入和近似成立。")
        if any(b["manufacturer_abutment_source"] is None for b in snapshot["bearing_interfaces"]):
            gaps.append("未绑定选定厂商和具体轴承产品的安装尺寸；项目布局近似不是通用 6211 的厂商下限。")
        out["numeric_conclusion"] = ("fail" if any(c["status"] == "fail" for c in checks)
                                     else "partial" if any(c["status"] == "blocked" for c in checks)
                                     else "pass_on_declared_assumptions")
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        out["errors"].append(str(exc))
        gaps.append("当前快照存在缺失或不适用输入，未形成完整数值校核。")
        out["numeric_conclusion"] = "blocked"
    return out


def assess_diameter_change(snapshot, segment_id, diameter_m):
    """解释候选违反或缺少哪些条件；不修改输入、不将局部数值结果升级为放行。"""
    if not isinstance(snapshot, dict) or snapshot.get("scope") != "course_shaft_review" or snapshot.get("schema_version") != 1:
        raise ValueError("需要 course_shaft_review 版本 1 的完整快照")
    target = next((s for s in snapshot["segments"] if s["segment_id"] == segment_id), None)
    if target is None:
        raise ValueError("快照中不存在该轴段")
    checks = []
    if isinstance(diameter_m, bool) or not isinstance(diameter_m, (int, float)) or not math.isfinite(diameter_m) or diameter_m <= 0:
        checks.append({"name": "positive_diameter", "status": "fail", "reason": "候选直径必须是以 m 为单位的有限正数。"})
    else:
        role = target["role"]
        candidate = deepcopy(snapshot)
        next(s for s in candidate["segments"] if s["segment_id"] == segment_id)["diameter_m"] = diameter_m
        interface_checks = [c for c in _interface_checks(candidate) if c.get("segment_id") == segment_id]
        checks.extend(interface_checks)
        if role in ("轴承", "齿轮", "密封", "端部") or target["keyway"] is not None:
            required = [c["required_diameter_m"] for c in interface_checks if "required_diameter_m" in c]
            if required:
                matched = all(math.isclose(diameter_m, d, rel_tol=0, abs_tol=1e-9) for d in required)
                checks.append({"name": "fixed_interface", "status": "pass" if matched else "fail",
                               "reason": f"{role}段按初始化时固定的接口名义尺寸检查；不以已手改的当前直径代替要求，也不代表制造公差合格。",
                               "required_diameter_m": required[0], "candidate_diameter_m": diameter_m,
                               "source_status": "initial_design_interface"})
            else:
                checks.append({"name": "fixed_interface", "status": "fail" if diameter_m != target["diameter_m"] else "blocked",
                               "reason": f"本阶段未开放{role}段自动改径；尚无独立接口尺寸依据，不能把当前值解释为已验证的配合标准。",
                               "candidate_diameter_m": diameter_m, "source_status": "editing_scope"})
        if role == "轴环":
            checks.append({"name": "gear_axial_location", "status": "blocked",
                           "reason": "轴环承担齿轮轴向定位；缺少轮毂倒角及有效接触尺寸依据，不能按无配合段开放减径。"})
        checks.extend([
            {"name": "manufacturer_installation_evidence", "status": "blocked",
             "reason": "未取得并绑定所选产品的轴承安装尺寸、倒角与相关接口依据。"},
            {"name": "cad_feature_mapping", "status": "blocked" if _geometry_gaps(snapshot) else "pass",
             "reason": "；".join(_geometry_gaps(snapshot)) or "当前 CAD 参数、键槽和圆角已读取；候选尺寸尚未应用。"},
            {"name": "material_and_method_sources", "status": "blocked",
             "reason": "材料疲劳参数及许用条件尚未独立核实，现有近似数值不能充当完整设计验收。"},
        ])
    out = {
        "status": "blocked", "can_apply": False, "entity_id": snapshot["entity_id"],
        "segment_id": segment_id, "current_diameter_m": target["diameter_m"],
        "candidate_diameter_m": diameter_m if isinstance(diameter_m, (int, float)) and not isinstance(diameter_m, bool) and math.isfinite(diameter_m) else None,
        "constraint_checks": checks,
        "blocked_reasons": [c["reason"] for c in checks if c["status"] in ("fail", "blocked")],
        "engineering_conclusion": "not_evaluated", "limitations": deepcopy(snapshot["limitations"]),
    }
    if _number(diameter_m, True):
        candidate = deepcopy(snapshot)
        next(s for s in candidate["segments"] if s["segment_id"] == segment_id)["diameter_m"] = diameter_m
        # 候选是计算副本；保留载荷/拓扑失效信息，不把假想尺寸标为已落实到 CAD。
        candidate["analysis_basis"] = "hypothetical_dimensions"
        out.update(candidate_snapshot=candidate,
                   change={"segment_id": segment_id, "parameter": "diameter_m", "old_value": target["diameter_m"],
                           "new_value": diameter_m, "unit": "m"}, review=review(candidate))
    return out


def preview(snapshot, segment_id, diameter_m):
    """与原生桥接的候选预览形状一致；本阶段所有候选均不可应用。"""
    return assess_diameter_change(snapshot, segment_id, diameter_m)


def preview_fillet_change(snapshot, left_segment_id, right_segment_id, radius_m):
    """预览右轴承邻接轴肩的单个圆角增大；可写条件与整轴工程结论分开。"""
    if not isinstance(snapshot, dict) or snapshot.get("scope") != "course_shaft_review" or snapshot.get("schema_version") != 1:
        raise ValueError("需要 course_shaft_review 版本 1 的完整快照")
    checks = []
    out = {
        "status": "blocked", "can_apply": False, "validation_scope": "right_bearing_shoulder_fillet_edit",
        "entity_id": snapshot.get("entity_id"), "constraint_checks": checks, "blocked_reasons": [],
        "change": {"parameter": "fillet_radius_m", "left_segment_id": left_segment_id,
                   "right_segment_id": right_segment_id, "old_value": None,
                   "new_value": radius_m if _number(radius_m) else None, "unit": "m"},
        "engineering_conclusion": "blocked", "review": review(snapshot),
        "limitations": [
            "can_apply 仅表示可尝试本阶段的可回滚几何事务；写入后仍须验证真实实体和完整快照。",
            "仅开放右轴承邻接轴肩的单个圆角增大，轴径、长度、键槽、载荷和配合声明保持不变。",
            "三家安装尺寸仅作编辑范围比较，未选定厂商；未公布的上限保留 unknown，不是通用 6211 安装认证。",
            "材料、完整疲劳方法域、键槽槽根、过盈与轴向直接应力等缺口仍保留，几何可写不表示整轴合格。",
        ],
    }

    def add(name, passed, reason, **values):
        checks.append({"name": name, "status": "pass" if passed else "fail", "reason": reason, **values})

    try:
        _current_inputs(snapshot)
        state = snapshot.get("cad_geometry_state", {})
        mapped = (all(state.get(key) is True for key in ("parameters_current", "keyways_current", "fillets_current", "load_binding_current"))
                  and not state.get("unsupported_features"))
        ids = [s["segment_id"] for s in snapshot["segments"]]
        fillets = snapshot["fillet_assumptions"]
        mapped = (mapped and len(set(ids)) == len(ids)
                  and [(f["left_segment_id"], f["right_segment_id"]) for f in fillets] == list(zip(ids, ids[1:]))
                  and all(f["status"] == "mapped_to_native_cad" and _number(f["cad_radius_m"], True) for f in fillets))
        add("current_geometry_binding", mapped, "须读取完整当前轴段、键槽、六处圆角及有效载荷关联，不能采用声明或失效映射。")
        interface_checks = _interface_checks(snapshot)
        checks.extend(interface_checks)
        comparisons, note = _right_shoulder_comparisons(snapshot)
        reference_ready = (len(comparisons) == 3
                           and {row["reference"]["manufacturer"] for row in comparisons} == {"SKF", "NSK", "Koyo"})
        add("right_bearing_references", reference_ready, note)
        lefts = [s for s in snapshot["segments"] if s["segment_id"] == left_segment_id]
        rights = [s for s in snapshot["segments"] if s["segment_id"] == right_segment_id]
        joints = [f for f in fillets if f["left_segment_id"] == left_segment_id and f["right_segment_id"] == right_segment_id]
        bearings = [b for b in snapshot["bearing_interfaces"] if b["side"] == "right"]
        target_matches = (len(lefts) == len(rights) == len(joints) == len(bearings) == 1
                          and reference_ready and lefts[0]["role"] == "轴肩" and rights[0]["role"] == "轴承"
                          and all(row["segment_id"] == left_segment_id for row in comparisons)
                          and math.isclose(rights[0]["z0_m"], bearings[0]["seat_start_z_m"], rel_tol=0, abs_tol=1e-9)
                          and math.isclose(lefts[0]["z0_m"] + lefts[0]["length_m"], rights[0]["z0_m"], rel_tol=0, abs_tol=1e-9))
        add("right_bearing_shoulder_target", target_matches, "仅允许唯一对应右轴承接口起点的相邻轴肩与轴承座圆角。")
        add("finite_positive_radius", _number(radius_m, True), "圆角半径必须为以 m 为单位的有限正数。")
        if target_matches and _number(radius_m, True):
            left, right, joint = lefts[0], rights[0], joints[0]
            old_radius = joint["cad_radius_m"]
            out["change"]["old_value"] = old_radius
            add("radius_increase_only", _number(old_radius, True) and radius_m > old_radius,
                "本阶段只允许增大已绑定的实际圆角；相等或减小不属于本次编辑范围。")
            radial_step = abs(left["diameter_m"] - right["diameter_m"]) / 2
            add("local_geometric_bounds", radius_m < min(radial_step, left["length_m"], right["length_m"]),
                "候选圆角须严格小于径差的一半及相邻两段长度；该初筛不替代实体重算。",
                radial_step_m=radial_step, adjacent_lengths_m=[left["length_m"], right["length_m"]])
            limits = [row["dimension_checks"]["fillet"]["limit_m"] for row in comparisons]
            add("reference_radius_edit_bound", all(_number(limit, True) and radius_m <= limit for limit in limits),
                "仅按三家已核对引用共同约束本阶段编辑半径，不据此选定厂家或认证实际安装。",
                reference_limits_m=limits, source_status="manufacturer_dimension_comparison_only")
            candidate = deepcopy(snapshot)
            next(f for f in candidate["fillet_assumptions"]
                 if f["left_segment_id"] == left_segment_id and f["right_segment_id"] == right_segment_id)["cad_radius_m"] = radius_m
            out["candidate_snapshot"] = candidate
            out["manufacturer_comparisons"], _ = _right_shoulder_comparisons(candidate)
            add("candidate_manufacturer_dimensions", not any(row["status"] == "fail" for row in out["manufacturer_comparisons"]),
                "候选不得与已知厂商尺寸冲突；未给出的上限仍为 unknown，不将其视作安装通过。")
            # 比较用快照只改一个实形参数；假想分析标记不能进入随后需整快照比对的候选。
            analysis_snapshot = deepcopy(candidate)
            analysis_snapshot["analysis_basis"] = "hypothetical_dimensions"
            out["review"] = review(analysis_snapshot)
            add("candidate_numeric_checks", not out["review"]["errors"] and not any(c["status"] == "fail" for c in out["review"]["checks"]),
                "声明输入下已计算项不得有明确数值失败；来源或模型缺口继续保留，不把整体 blocked 当作几何写入禁令。")
        out["blocked_reasons"] = [c["reason"] for c in checks if c["status"] != "pass"]
        out["can_apply"] = not out["blocked_reasons"] and "candidate_snapshot" in out
        out["status"] = "ready" if out["can_apply"] else "blocked"
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        out["blocked_reasons"] = [c["reason"] for c in checks if c["status"] != "pass"] + [f"当前快照无法形成受控圆角候选：{exc}"]
    return out
