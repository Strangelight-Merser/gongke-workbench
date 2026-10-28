"""课程右肩圆角编辑边界；使用声明映射隔离核心测试，不冒称真实 CAD 验收。

尺寸引用来自 bearing_reference 中的三家开式 6211；只检查声明编辑范围。
本文件不改变原始教材测试，也不把材料与疲劳缺口补成通过。
"""

from copy import deepcopy
import json

import pytest

from gongke_core import api
from gongke_core.course_shaft import from_design, preview_fillet_change


@pytest.fixture(scope="module")
def initialized():
    return from_design(api._run(api.example_task("coupling")))


@pytest.fixture
def snapshot(initialized):
    result = deepcopy(initialized)
    result["cad_geometry_state"] = {
        "parameters_current": True, "keyways_current": True, "fillets_current": True,
        "load_binding_current": True, "unsupported_features": [],
    }
    for fillet in result["fillet_assumptions"]:
        fillet["cad_radius_m"] = fillet["assumed_radius_m"]
        fillet["status"] = "mapped_to_native_cad"
    return result


def preview(snapshot, radius=0.0015):
    left, right = snapshot["segments"][3:5]
    return preview_fillet_change(snapshot, left["segment_id"], right["segment_id"], radius)


@pytest.mark.parametrize("radius", [0.0012, 0.0015])
def test_geometry_edit_ready_while_engineering_remains_blocked(snapshot, radius):
    result = preview(snapshot, radius)
    assert result["status"] == "ready" and result["can_apply"] is True
    assert result["validation_scope"] == "right_bearing_shoulder_fillet_edit"
    assert result["change"] == {
        "parameter": "fillet_radius_m", "left_segment_id": snapshot["segments"][3]["segment_id"],
        "right_segment_id": snapshot["segments"][4]["segment_id"], "old_value": 0.001,
        "new_value": radius, "unit": "m",
    }
    assert result["engineering_conclusion"] == result["review"]["status"] == "blocked"
    assert result["review"]["geometry_basis"] == "hypothetical_snapshot"
    assert result["review"]["fatigue_unsupported_sections"] == []
    assert any("槽根" in gap for gap in result["review"]["blocked_reasons"])
    rows = {r["reference"]["manufacturer"]: r for r in result["manufacturer_comparisons"]}
    assert rows["SKF"]["dimension_checks"]["upper_bound"]["status"] == "unknown"
    assert rows["Koyo"]["dimension_checks"]["upper_bound"]["status"] == "unknown"
    assert all(r["selected_manufacturer"] is None for r in rows.values())


def test_candidate_changes_only_actual_radius_without_redesign(snapshot, monkeypatch):
    before = deepcopy(snapshot)
    monkeypatch.setattr(api, "_run", lambda *_: pytest.fail("预览不得重新设计或选径"))
    result = preview(snapshot)
    expected = deepcopy(snapshot)
    expected["fillet_assumptions"][3]["cad_radius_m"] = 0.0015
    assert result["candidate_snapshot"] == expected
    assert "analysis_basis" not in result["candidate_snapshot"]
    assert snapshot == before
    assert expected["fillet_assumptions"][3]["assumed_radius_m"] == 0.001
    assert result["candidate_snapshot"]["loads"][0]["fz_n"] == snapshot["loads"][0]["fz_n"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("radius", [None, True, float("nan"), float("inf"), 0, -0.001, 0.001, 0.0009, 0.002])
def test_invalid_decrease_or_over_catalog_edit_bound_rejected(snapshot, radius):
    result = preview(snapshot, radius)
    assert result["status"] == "blocked" and result["can_apply"] is False
    assert result["blocked_reasons"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field", ["parameters_current", "keyways_current", "fillets_current", "load_binding_current"])
def test_incomplete_geometry_or_changed_length_binding_rejected(snapshot, field):
    snapshot["cad_geometry_state"][field] = False
    result = preview(snapshot)
    assert not result["can_apply"]
    assert next(c for c in result["constraint_checks"] if c["name"] == "current_geometry_binding")["status"] == "fail"


def test_declared_unmapped_input_is_not_editable(initialized):
    assert preview(initialized)["can_apply"] is False
    assert initialized["read_only"] is False
    assert initialized["editable_parameters"] == ["right_bearing_shoulder_radius_m"]


@pytest.mark.parametrize("index, diameter", [(1, 0.057), (3, 0.063), (4, 0.054), (6, 0.044)])
def test_existing_interface_conflicts_block_edit(snapshot, index, diameter):
    snapshot["segments"][index]["diameter_m"] = diameter
    assert preview(snapshot)["can_apply"] is False


def test_actual_key_slot_conflict_blocks_edit(snapshot):
    snapshot["segments"][1]["keyway"]["depth_m"] += 0.001
    result = preview(snapshot)
    assert not result["can_apply"]
    assert next(c for c in result["constraint_checks"] if c["name"] == "key_geometry_0")["status"] == "fail"


@pytest.mark.parametrize("left_index,right_index", [(0, 1), (2, 3), (4, 3), (3, 5)])
def test_other_or_nonadjacent_joint_rejected(snapshot, left_index, right_index):
    result = preview_fillet_change(snapshot, snapshot["segments"][left_index]["segment_id"],
                                   snapshot["segments"][right_index]["segment_id"], 0.0015)
    assert not result["can_apply"]
    assert next(c for c in result["constraint_checks"] if c["name"] == "right_bearing_shoulder_target")["status"] == "fail"


def test_missing_or_duplicate_mapping_rejected(snapshot):
    snapshot["fillet_assumptions"].append(deepcopy(snapshot["fillet_assumptions"][3]))
    assert preview(snapshot)["can_apply"] is False
    snapshot["fillet_assumptions"].pop()
    snapshot["fillet_assumptions"].pop(0)
    assert preview(snapshot)["can_apply"] is False


def test_different_bearing_product_is_not_silently_compared(snapshot):
    snapshot["bearing_interfaces"][1]["designation"] = "6211-2Z"
    result = preview(snapshot)
    assert not result["can_apply"]
    assert next(c for c in result["constraint_checks"] if c["name"] == "right_bearing_references")["status"] == "fail"


def test_clear_numeric_failure_blocks_candidate(snapshot):
    snapshot["analysis_parameters"]["allowable_nominal_stress_pa"] = 1
    result = preview(snapshot)
    assert not result["can_apply"]
    assert next(c for c in result["constraint_checks"] if c["name"] == "candidate_numeric_checks")["status"] == "fail"
