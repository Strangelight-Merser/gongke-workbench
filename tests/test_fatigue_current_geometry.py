"""实际轴肩圆角输入与模型范围测试；不改既有教材算例或材料数据。

范围来自当前实现声明：弯曲 0.1≤t/r≤20、扭转 0.25≤t/r≤4。
这些测试验证输入被消费、越界不夹紧放行，不证明拟合或材料已获专业认可。
"""

from copy import deepcopy
import math

import pytest

from gongke_core import api
from gongke_core.calc import fatigue
from gongke_core.course_shaft import from_design, review, _current_inputs


@pytest.fixture
def snapshot():
    snapshot = from_design(api._run(api.example_task("coupling")))
    # 这里声明映射状态以隔离核心计算测试；真实 FreeCAD 的几何验收由端到端测试负责。
    snapshot["cad_geometry_state"] = {"parameters_current": True, "keyways_current": True,
                                      "fillets_current": True, "load_binding_current": True,
                                      "unsupported_features": []}
    for item in snapshot["fillet_assumptions"]:
        item["cad_radius_m"] = item["assumed_radius_m"]
        item["status"] = "mapped_to_native_cad"
    return snapshot


def right_bearing_fillet(snapshot):
    return next(f for f in snapshot["fillet_assumptions"] if math.isclose(f["z_m"], 0.164))


def test_default_actual_radius_exposes_torsion_model_gap(snapshot):
    result = review(snapshot)
    assert result["errors"] == []
    unknown = next(s for s in result["fatigue_unsupported_sections"] if math.isclose(s["z"], 0.164))
    assert unknown["r"] == 0.001
    assert unknown["t_over_r"] == pytest.approx(4.5)
    assert unknown["status"] == "blocked"
    assert not any(math.isclose(s["z"], 0.164) for s in result["fatigue_sections"])
    check = next(c for c in result["checks"] if c["name"] == "fatigue_current_geometry")
    assert check["status"] == "blocked"
    assert check["value_scope"] == "minimum_of_evaluated_sections"
    assert any("未使用夹紧值" in reason for reason in result["blocked_reasons"])


def test_actual_radius_change_is_consumed_without_replacing_assumption(snapshot):
    joint = right_bearing_fillet(snapshot)
    joint["cad_radius_m"] = 0.0015
    first = review(snapshot)
    first_section = next(s for s in first["fatigue_sections"] if math.isclose(s["z"], 0.164))
    assert first_section["r"] == 0.0015
    assert first_section["left_segment_id"] == joint["left_segment_id"]
    assert first_section["right_segment_id"] == joint["right_segment_id"]
    assert first_section["geometry_basis"] == "cad_shoulder_fillets"
    assert first["fatigue_unsupported_sections"] == []
    assert joint["assumed_radius_m"] == 0.001
    joint["cad_radius_m"] = 0.0012
    second = review(snapshot)
    second_section = next(s for s in second["fatigue_sections"] if math.isclose(s["z"], 0.164))
    assert second_section["r"] == 0.0012
    assert second_section["S_ca"] != pytest.approx(first_section["S_ca"])
    assert first["status"] == second["status"] == "blocked"
    assert first["can_apply"] is False
    assert any("过盈配合" in text for text in first["blocked_reasons"])
    assert any("轴向直接" in text for text in first["blocked_reasons"])


def test_explicit_radius_must_be_complete_not_replaced_by_role_rule(snapshot):
    segments, case = _current_inputs(snapshot)
    with pytest.raises(ValueError, match="实际圆角"):
        fatigue.check(segments, case, fatigue.MATERIALS["45"], shoulder_radii={1: 0.001})


@pytest.mark.parametrize("invalid", [None, 0, -0.001, float("nan"), float("inf"), True])
def test_bad_actual_radius_does_not_use_old_assumption(snapshot, invalid):
    right_bearing_fillet(snapshot)["cad_radius_m"] = invalid
    result = review(snapshot)
    assert not any(c["name"] == "fatigue_current_geometry" for c in result["checks"])
    # 非法半径也可能先被厂商尺寸比较拒绝；两条路径均不得退回角色推定圆角。
    assert result["errors"] or any("实际圆角读取不完整" in text for text in result["blocked_reasons"])


def test_explicit_radius_change_preserves_all_other_inputs(snapshot):
    before = deepcopy(snapshot)
    review(snapshot)
    assert snapshot == before


def test_torsion_upper_endpoint_accepts_only_numeric_roundoff(snapshot):
    joint = right_bearing_fillet(snapshot)
    joint["cad_radius_m"] = 0.001125
    raw_ratio = (0.064 - 0.055) / (2 * joint["cad_radius_m"])
    assert raw_ratio > 4.0 and math.isclose(raw_ratio, 4.0, rel_tol=1e-12)
    result = review(snapshot)
    assert result["fatigue_unsupported_sections"] == []
    section = next(s for s in result["fatigue_sections"] if math.isclose(s["z"], 0.164))
    assert section["r"] == 0.001125
    assert joint["cad_radius_m"] == 0.001125


@pytest.mark.parametrize("ratio", [0.249, 4.01])
def test_actual_torsion_domain_violation_is_not_clamped(snapshot, ratio):
    joint = right_bearing_fillet(snapshot)
    joint["cad_radius_m"] = (0.064 - 0.055) / (2 * ratio)
    result = review(snapshot)
    section = next(s for s in result["fatigue_unsupported_sections"] if math.isclose(s["z"], 0.164))
    assert section["t_over_r"] == pytest.approx(ratio)
    assert section["r"] == joint["cad_radius_m"]
    assert not any(math.isclose(s["z"], 0.164) for s in result["fatigue_sections"])


def test_torsion_lower_endpoint_accepts_numeric_roundoff(snapshot):
    joint = right_bearing_fillet(snapshot)
    radius_at_boundary = (0.064 - 0.055) / (2 * 0.25)
    # 直接核心输入检查模型边界，不声称该大半径能在真实 CAD 上建成。
    joint["cad_radius_m"] = math.nextafter(radius_at_boundary, math.inf)
    result = review(snapshot)
    assert result["fatigue_unsupported_sections"] == []
    assert any(math.isclose(s["z"], 0.164) for s in result["fatigue_sections"])


def test_partial_formula_source_verification_does_not_promote_fatigue_method(snapshot):
    right_bearing_fillet(snapshot)["cad_radius_m"] = 0.0015
    result = review(snapshot)
    sources = result["fatigue_method_sources"]
    assert sources["status"] == "unverified"
    by_method = {entry["method"]: entry for entry in sources["references"]}
    assert by_method["torsion_shoulder"]["status"] == "verified_secondary_formula_reproduction"
    assert by_method["bending_shoulder"]["status"] == "unverified_formula_page"
    assert any("D/d、r/d" in text for text in sources["limitations"])
    assert any("相互作用" in text for text in sources["limitations"])
    assert result["fatigue_unsupported_sections"] == []
    assert result["status"] == "blocked"
    check = next(c for c in result["checks"] if c["name"] == "fatigue_current_geometry")
    assert check["source"]["status"] == "unverified"


def test_bound_shoulder_radius_does_not_claim_an_actual_keyway_root(snapshot):
    right_bearing_fillet(snapshot)["cad_radius_m"] = 0.0015
    result = review(snapshot)
    key_sections = [row for row in result["fatigue_sections"] if row["feature"] == "键槽"]
    assert len(key_sections) == 2
    for row in key_sections:
        assert row["geometry_basis"] == "assumed_keyway_root"
        assert row["r"] == pytest.approx(0.02 * row["d"])
        assert row["radius_source"]["status"] == "assumed"
        assert row["status"] == "blocked"
        assert row["conditional_status"] == "pass"
        assert row["S_ca"] > 1.5
    shoulders = [row for row in result["fatigue_sections"] if row["feature"] == "轴肩圆角"]
    assert shoulders and all(row["geometry_basis"] == "cad_shoulder_fillets" for row in shoulders)
    assert result["fatigue_unsupported_sections"] == []
    check = next(c for c in result["checks"] if c["name"] == "fatigue_current_geometry")
    assert check["geometry_basis"] == "cad_shoulders_assumed_keyway_roots"
    assert check["status"] == "blocked"
    assert any("实体槽根圆角" in text for text in result["blocked_reasons"])
