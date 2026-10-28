"""真实 coupling 输出轴的输入保真与约束拒绝；不将教学近似当成专业认可。"""

from copy import deepcopy
import json

import pytest

from gongke_core import api
from gongke_core.course_shaft import assess_diameter_change, from_design, review


@pytest.fixture(scope="module")
def design():
    return api._run(api.example_task("coupling"))


@pytest.fixture
def snapshot(design):
    return from_design(design)


def test_preserve_full_loads_and_coordinate_origin(design, snapshot):
    source = design.shafts[2]
    assert len(snapshot["segments"]) == len(source.layout.segments) == 7
    assert snapshot["z_origin_m"] == source.layout.segments[0].z0
    assert snapshot["segments"][0]["z0_m"] - snapshot["z_origin_m"] == 0
    for segment, original in zip(snapshot["segments"], source.layout.segments):
        assert segment["length_m"] == original.length
        assert segment["diameter_m"] == original.d
        assert segment["z0_m"] == original.z0
    load, original = snapshot["loads"][0], source.load_case.loads[0]
    assert load["fz_n"] == original.fz != 0
    assert load["x0_m"] == original.x0 != 0
    assert load["couple_xz_nm"] == pytest.approx(-load["x0_m"] * load["fz_n"])
    assert load["couple_xz_nm"] == original.couple_xz
    # 平移轴坐标时，力到支点的力臂和偏心力偶必须保持不变。
    shifted_load = load["z_m"] - snapshot["z_origin_m"]
    shifted_support = snapshot["supports_m"][0] - snapshot["z_origin_m"]
    assert shifted_load - shifted_support == pytest.approx(original.z - source.load_case.supports[0])
    assert snapshot["torque_points"] == [{"z_m": z, "torque_nm": t} for z, t in source.load_case.torque_points]
    json.dumps(snapshot, allow_nan=False)


def test_reject_64_to_63_mm_project_layout_conflict(snapshot):
    shoulder = snapshot["segments"][3]
    assert shoulder["diameter_m"] == pytest.approx(0.064)
    result = assess_diameter_change(snapshot, shoulder["segment_id"], 0.063)
    check = next(c for c in result["constraint_checks"] if c["name"] == "project_layout_abutment_minimum")
    assert check["status"] == "fail"
    assert check["minimum_m"] == pytest.approx(0.064)
    assert check["source"]["status"] == "project_approximation"
    assert check["source_status"] == "project_approximation"
    assert "不表示违反所有 6211" in check["reason"]
    assert result["status"] == "blocked" and not result["can_apply"]


@pytest.mark.parametrize("index", [0, 1, 4, 5, 6])
def test_fit_keyway_and_seal_diameters_are_locked(snapshot, index):
    segment = snapshot["segments"][index]
    result = assess_diameter_change(snapshot, segment["segment_id"], segment["diameter_m"] - 0.001)
    assert any(c["name"] == "fixed_interface" and c["status"] == "fail" for c in result["constraint_checks"])
    assert not result["can_apply"]


def test_no_free_collar_or_unverified_larger_shoulder(snapshot):
    collar = snapshot["segments"][2]
    result = assess_diameter_change(snapshot, collar["segment_id"], 0.069)
    assert any(c["name"] == "gear_axial_location" and c["status"] == "blocked" for c in result["constraint_checks"])
    shoulder = snapshot["segments"][3]
    result = assess_diameter_change(snapshot, shoulder["segment_id"], 0.065)
    assert next(c for c in result["constraint_checks"] if c["name"] == "project_layout_abutment_minimum")["status"] == "pass"
    assert result["status"] == "blocked" and result["engineering_conclusion"] == "not_evaluated"


def test_assessment_does_not_change_original(snapshot):
    before = deepcopy(snapshot)
    assess_diameter_change(snapshot, snapshot["segments"][3]["segment_id"], 0.063)
    assert snapshot == before


def test_source_and_fillet_gaps_are_explicit(snapshot):
    assert snapshot["material"]["source"]["status"] == "unverified"
    assert snapshot["analysis_parameters"]["fit_k_sigma"] is None
    assert all(f["cad_radius_m"] is None and f["status"] == "not_mapped_to_cad" for f in snapshot["fillet_assumptions"])
    assert all(b["manufacturer_abutment_source"] is None for b in snapshot["bearing_interfaces"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, True])
def test_invalid_candidate_is_blocked_and_json_safe(snapshot, value):
    result = assess_diameter_change(snapshot, snapshot["segments"][3]["segment_id"], value)
    assert result["constraint_checks"][0]["status"] == "fail"
    json.dumps(result, allow_nan=False)


def test_current_review_reuses_full_design_conditions_without_redesign(design, snapshot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("当前轴校核不得调用整机设计")
    monkeypatch.setattr(api.design_mod, "run", forbidden)
    result = review(snapshot)
    assert result["errors"] == []
    assert result["status"] == "blocked"
    checks = {item["name"]: item for item in result["checks"]}
    original = design.shafts[2]
    assert checks["nominal_combined_stress"]["value"] == pytest.approx(original.strength.critical.sigma_ca)
    assert checks["stiffness_0"]["value"] == pytest.approx(original.stiffness.items[0].value)
    assert checks["key_0"]["value"] == pytest.approx(original.keys[0].sigma_p)
    assert checks["key_1"]["value"] == pytest.approx(original.keys[1].sigma_p)
    assert checks["fatigue_assumed_geometry"]["value"] == pytest.approx(original.fatigue.critical.S_ca)
    assert result["reactions"]["ax"] == pytest.approx(original.strength.reactions.ax)
    assert result["load_couples"][0]["couple_xz_nm"] == pytest.approx(-168.61761132108208)
    assert any("轴向直接" in text for text in result["blocked_reasons"])
    json.dumps(result, allow_nan=False)


def test_candidate_snapshot_changes_only_requested_dimension_and_computes_values(snapshot):
    before = deepcopy(snapshot)
    target = snapshot["segments"][3]
    result = assess_diameter_change(snapshot, target["segment_id"], 0.063)
    candidate = deepcopy(snapshot)
    candidate["segments"][3]["diameter_m"] = 0.063
    candidate["analysis_basis"] = "hypothetical_dimensions"
    assert snapshot == before
    assert result["candidate_snapshot"] == candidate
    assert result["change"] == {"segment_id": target["segment_id"], "parameter": "diameter_m", "old_value": 0.064, "new_value": 0.063, "unit": "m"}
    checks = {item["name"]: item for item in result["review"]["checks"]}
    assert checks["nominal_combined_stress"]["value"] == pytest.approx(41983295.138393745)
    assert checks["stiffness_0"]["value"] == pytest.approx(3.5249053650119957e-6)
    assert result["review"]["geometry_basis"] == "hypothetical_snapshot"


def test_axial_eccentric_load_is_not_silently_ignored(snapshot):
    baseline = review(snapshot)
    changed = deepcopy(snapshot)
    changed["loads"][0]["fz_n"] = 0
    result = review(changed)
    assert result["load_couples"][0]["couple_xz_nm"] == 0
    assert result["reactions"]["ax"] != pytest.approx(baseline["reactions"]["ax"])


@pytest.mark.parametrize("extra", [{"parameters_current": False}, {"load_binding_current": False}, {"unsupported_features": ["Hole"]}])
def test_stale_parameters_load_binding_or_unknown_feature_blocks_current_and_candidate(snapshot, extra):
    snapshot["cad_geometry_state"] = {"parameters_current": True, "keyways_current": True,
                                      "fillets_current": False, "load_binding_current": True,
                                      "unsupported_features": [], **extra}
    result = review(snapshot)
    assert result["status"] == "blocked" and result["checks"] == []
    assert result["blocked_reasons"]
    candidate = assess_diameter_change(snapshot, snapshot["segments"][3]["segment_id"], 0.063)
    assert candidate["review"]["checks"] == []


def test_cad_with_no_fillet_cannot_claim_assumed_fatigue_result(snapshot):
    snapshot["cad_geometry_state"] = {"parameters_current": True, "keyways_current": True,
                                      "fillets_current": False, "load_binding_current": True,
                                      "unsupported_features": []}
    for fillet in snapshot["fillet_assumptions"]:
        fillet["cad_radius_m"] = 0.0
    result = review(snapshot)
    assert result["errors"] == []
    assert any(item["name"] == "nominal_combined_stress" for item in result["checks"])
    assert not any(item["name"] == "fatigue_assumed_geometry" for item in result["checks"])
    assert any("圆角声明" in text for text in result["blocked_reasons"])


def test_candidate_compares_manufacturers_without_selecting_one(snapshot):
    before = deepcopy(snapshot)
    result = assess_diameter_change(snapshot, snapshot["segments"][3]["segment_id"], 0.063)
    comparisons = result["review"]["manufacturer_comparisons"]
    assert len(comparisons) == 3
    rows = {row["reference"]["manufacturer"]: row for row in comparisons}
    assert rows["SKF"]["dimension_checks"]["lower_bound"]["status"] == "fail"
    assert rows["NSK"]["dimension_checks"]["lower_bound"]["status"] == "pass"
    assert rows["NSK"]["dimension_checks"]["upper_bound"]["status"] == "pass"
    assert all(row["dimension_checks"]["fillet"]["status"] == "unknown" for row in comparisons)
    assert all(row["selected_manufacturer"] is None and "未选定" in row["label"] for row in comparisons)
    assert all(b["manufacturer"] is None for b in snapshot["bearing_interfaces"])
    assert snapshot == before


def test_manufacturer_fillet_check_consumes_cad_radius_not_assumption(snapshot):
    shoulder, seat = snapshot["segments"][3:5]
    junction = next(f for f in snapshot["fillet_assumptions"]
                    if f["left_segment_id"] == shoulder["segment_id"] and f["right_segment_id"] == seat["segment_id"])
    junction["cad_radius_m"] = 0.002
    result = review(snapshot)
    assert len(result["manufacturer_comparisons"]) == 3
    assert all(row["dimension_checks"]["fillet"]["value_m"] == 0.002
               and row["dimension_checks"]["fillet"]["status"] == "fail"
               for row in result["manufacturer_comparisons"])


@pytest.mark.parametrize("field,value", [("designation", "6211-2Z"), ("outside_diameter_m", 0.11)])
def test_mismatched_bearing_reference_is_not_silently_used(snapshot, field, value):
    snapshot["bearing_interfaces"][1][field] = value
    result = review(snapshot)
    assert result["manufacturer_comparisons"] == []
    assert "未套用引用" in result["manufacturer_comparison_note"]


@pytest.mark.parametrize("index,diameter,check_name,required", [
    (0, 0.054, "bearing_seat_left", 0.055),
    (4, 0.054, "bearing_seat_right", 0.055),
    (1, 0.057, "gear_seat_0", 0.058),
    (6, 0.044, "coupling_seat", 0.045),
])
def test_manual_diameter_change_reports_fixed_interface_conflict(snapshot, monkeypatch, index, diameter, check_name, required):
    def forbidden(*args, **kwargs):
        raise AssertionError("接口检查不得重新设计或选型")
    monkeypatch.setattr(api.design_mod, "run", forbidden)
    snapshot["segments"][index]["diameter_m"] = diameter
    result = review(snapshot)
    check = next(item for item in result["checks"] if item["name"] == check_name)
    assert check["status"] == "fail"
    assert check["value"] == diameter
    assert check["required_diameter_m"] == required
    assert check["source"]["status"] == "initial_design_interface"
    assert check["reason"] in result["blocked_reasons"]
    assert result["numeric_conclusion"] == "fail"


def test_preview_restore_uses_interface_requirement_not_current_bad_diameter(snapshot):
    snapshot["segments"][4]["diameter_m"] = 0.054
    target = snapshot["segments"][4]
    kept = assess_diameter_change(snapshot, target["segment_id"], 0.054)
    restored = assess_diameter_change(snapshot, target["segment_id"], 0.055)
    for result, expected in ((kept, "fail"), (restored, "pass")):
        check = next(c for c in result["constraint_checks"] if c["name"] == "fixed_interface")
        assert check["required_diameter_m"] == 0.055
        assert check["status"] == expected
    assert restored["can_apply"] is False
    assert target["diameter_m"] == 0.054


def test_manual_63_mm_shoulder_has_project_conflict_and_separate_manufacturer_checks(snapshot):
    snapshot["segments"][3]["diameter_m"] = 0.063
    result = review(snapshot)
    check = next(c for c in result["checks"] if c["name"] == "project_layout_abutment_minimum")
    assert check["status"] == "fail" and check["source_status"] == "project_approximation"
    comparisons = {row["reference"]["manufacturer"]: row for row in result["manufacturer_comparisons"]}
    assert comparisons["SKF"]["dimension_checks"]["lower_bound"]["status"] == "fail"
    assert comparisons["NSK"]["dimension_checks"]["lower_bound"]["status"] == "pass"


def test_seal_has_no_invented_manufacturer_requirement(snapshot):
    target = snapshot["segments"][5]
    result = assess_diameter_change(snapshot, target["segment_id"], 0.051)
    check = next(c for c in result["constraint_checks"] if c["name"] == "fixed_interface")
    assert check["source_status"] == "editing_scope"
    assert "required_diameter_m" not in check


@pytest.mark.parametrize("field,delta,expected", [
    ("width_m", 0.001, 0.016),
    ("length_m", -0.001, 0.063),
    ("depth_m", 0.001, 0.006),
])
def test_changed_keyway_dimensions_do_not_reuse_original_key_approval(snapshot, field, delta, expected):
    snapshot["segments"][1]["keyway"][field] += delta
    result = review(snapshot)
    assert result["errors"] == []
    checks = {c["name"]: c for c in result["checks"]}
    geometry = checks["key_geometry_0"]
    assert geometry["status"] == "fail"
    changed = next(c for c in geometry["dimension_checks"] if c["field"] == field)
    assert changed["required_m"] == expected
    assert changed["value_m"] == pytest.approx(expected + delta)
    assert changed["status"] == "fail"
    assert checks["key_0"]["status"] == "blocked"
    assert "value" not in checks["key_0"]
    assert checks["key_1"]["status"] == "pass"
    assert result["numeric_conclusion"] == "fail"
    assert geometry["reason"] in result["blocked_reasons"]


def test_native_float_roundoff_does_not_create_keyway_conflict(snapshot):
    snapshot["segments"][1]["keyway"]["width_m"] += 1e-13
    snapshot["segments"][1]["keyway"]["depth_m"] -= 1e-13
    result = review(snapshot)
    checks = {c["name"]: c for c in result["checks"]}
    assert checks["key_geometry_0"]["status"] == "pass"
    assert checks["key_0"]["status"] == "pass"


def test_missing_current_keyway_does_not_reuse_selected_key_result(snapshot):
    snapshot["segments"][1]["keyway"] = None
    result = review(snapshot)
    checks = {c["name"]: c for c in result["checks"]}
    assert checks["key_geometry_0"]["status"] == "fail"
    assert checks["key_0"]["status"] == "blocked"
    assert "value" not in checks["key_0"]
