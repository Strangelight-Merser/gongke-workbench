"""原生图纸快照检查：单位、覆盖、引用和未知项；不作为真实 TechDraw 运行证据。"""

from copy import deepcopy

import pytest

from gongke_core.drawing_review import review
from gongke_core.revision_mapping import map_capture


@pytest.fixture
def inputs():
    path = "/工程 原件/shaft.FCStd"
    signature = [{"name": "middle_radius", "type": "DistanceY", "driving": True}]
    case = {
        "schema_version": 1, "case_id": "drawing-test",
        "document": {"path": path, "body": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": signature},
        "target": {"radius_constraint": "middle_radius", "segment_index": 1}, "pages": ["Sheet"],
        "annotations": [{"page": "Sheet", "view": view, "dimension": name, "target": "diameter"}
                        for view, name in (("Front", "DFront"), ("Back", "DBack"))],
    }
    geometry = {"supported": True, "body_name": "Rotor", "sketch": "Outline", "revolution": "Turned",
                "structure_signature": deepcopy(signature), "segments": [
                    {"length_m": .05, "diameter_m": .03, "radius_constraint": "left_radius"},
                    {"length_m": .1, "diameter_m": .038, "radius_constraint": "middle_radius"},
                    {"length_m": .05, "diameter_m": .03, "radius_constraint": "right_radius"}]}
    views = []
    for view, name in (("Front", "DFront"), ("Back", "DBack")):
        views.append({"name": view, "state": [], "sources": [{"path": path, "object": "Rotor"}],
                      "dimensions": [{"name": name, "type": "Diameter", "measurement_m": .038,
                                      "raw_value": 38.0, "raw_unit": "mm", "measure_type": "Projected",
                                      "display_text": "⌀38.00 mm", "format_spec": "⌀%.2w",
                                      "display_unit": "mm", "precision": 2, "arbitrary": False, "valid": True,
                                      "references2d": [{"object": view, "subelements": ["Edge5"]}],
                                      "references3d": [], "reference_status": "valid", "state": [], "issues": [],
                                      "over_tolerance_m": 0, "under_tolerance_m": 0}]})
    capture = {"host": "freecad", "session_id": "session-a", "document": {"path": path}, "geometry": geometry,
               "drawing": {"coverage": {"status": "complete", "scope": "selected_pages"}, "issues": [],
                           "pages": [{"name": "Sheet", "state": [], "unknown_objects": [], "views": views}]}}
    return case, capture


def checked(inputs):
    case, capture = inputs
    return review(capture, map_capture(case, capture))


def dimension(inputs, view=0):
    return inputs[1]["drawing"]["pages"][0]["views"][view]["dimensions"][0]


def codes(result):
    return {row["code"] for row in result["issues"]}


def test_checks_both_explicit_instances_without_modifying_input(inputs):
    original = deepcopy(inputs)
    result = checked(inputs)
    assert result["status"] == "pass" and result["issues"] == []
    assert result["coverage"] == {"scope": "selected_pages", "status": "checked", "declared": 2, "checked": 2}
    assert inputs == original


@pytest.mark.parametrize("source", [
    {"path": "/other/shaft.FCStd", "object": "Rotor"},
    {"path": "/工程 原件/shaft.FCStd", "object": "OtherBody"},
])
def test_wrong_model_reference_fails_with_native_location(inputs, source):
    inputs[1]["drawing"]["pages"][0]["views"][1]["sources"] = [source]
    result = checked(inputs)
    assert result["status"] == "fail" and "view_source_mismatch" in codes(result)
    issue = next(i for i in result["issues"] if i["code"] == "view_source_mismatch")
    assert issue["location"] == {"page": "Sheet", "view": "Back", "dimension": None}
    assert issue["next_action"]


def test_override_is_error_even_when_visible_number_matches_model(inputs):
    dimension(inputs)["arbitrary"] = True
    result = checked(inputs)
    assert result["status"] == "fail" and "display_override" in codes(result)


def test_dangling_reference_ignores_zero_cached_measurement(inputs):
    dimension(inputs).update(reference_status="dangling", raw_value=0.0, measurement_m=0.0)
    result = checked(inputs)
    assert result["status"] == "fail"
    assert "dangling_reference" in codes(result) and "measurement_mismatch" not in codes(result)


def test_missing_projection_cannot_pass_by_isvalid_alone(inputs):
    dimension(inputs).update(reference_status="unknown", valid=True, raw_value=0.0, measurement_m=0.0)
    result = checked(inputs)
    assert result["status"] == "unknown" and "reference_unknown" in codes(result)
    assert "measurement_mismatch" not in codes(result)
    assert result["coverage"]["checked"] == 1


@pytest.mark.parametrize("object_kind", ["page", "view", "dimension"])
def test_pending_update_does_not_compare_stale_measurement(inputs, object_kind):
    page = inputs[1]["drawing"]["pages"][0]
    obj = {"page": page, "view": page["views"][0], "dimension": dimension(inputs)}[object_kind]
    obj["state"] = ["Touched"]
    dimension(inputs).update(raw_value=40.0, measurement_m=.04)
    result = checked(inputs)
    assert result["status"] == "unknown" and "needs_rebuild" in codes(result)
    assert "measurement_mismatch" not in codes(result)


@pytest.mark.parametrize("flag", ["pending_transaction", "needs_rebuild"])
def test_document_edit_state_blocks_all_cached_dimension_comparisons(inputs, flag):
    inputs[1]["document"][flag] = True
    for index in (0, 1):
        dimension(inputs, index).update(raw_value=40.0, measurement_m=.04, display_text="⌀40.00 mm")
    before = deepcopy(inputs)
    result = checked(inputs)
    assert result["status"] == "unknown" and flag in codes(result)
    assert result["coverage"]["checked"] == 0
    assert "measurement_mismatch" not in codes(result)
    assert "display_value_mismatch" not in codes(result)
    issue = next(row for row in result["issues"] if row["code"] == flag)
    assert issue["location"] == {"page": None, "view": None, "dimension": None}
    assert issue["next_action"]
    assert inputs == before


def test_actual_and_formatted_measurements_have_distinct_checks(inputs):
    dimension(inputs).update(raw_value=40, measurement_m=.04, display_text="⌀40.00 mm")
    result = checked(inputs)
    assert result["status"] == "fail" and "measurement_mismatch" in codes(result)
    assert "display_value_mismatch" not in codes(result)
    dimension(inputs).update(raw_value=38, measurement_m=.038, display_text="⌀40.00 mm")
    result = checked(inputs)
    assert "display_value_mismatch" in codes(result) and "measurement_mismatch" not in codes(result)


def test_display_comparison_respects_precision_in_mm_not_string_equality(inputs):
    inputs[1]["geometry"]["segments"][1]["diameter_m"] = .038003
    for index in (0, 1):
        dimension(inputs, index).update(raw_value=38.003, measurement_m=.038003, display_text="⌀38.00 mm")
    assert checked(inputs)["status"] == "pass"
    # 同一数值的省略尾零显示不应被字符串比较误报。
    dimension(inputs)["display_text"] = "⌀38.0 mm"
    assert checked(inputs)["status"] == "pass"


@pytest.mark.parametrize("values", [
    {"format_spec": "38 mm"}, {"format_spec": "⌀%.2f"},
    {"display_unit": "unknown"}, {"display_text": "⌀1.496 in"}, {"precision": None},
])
def test_unverified_display_format_never_becomes_green(inputs, values):
    dimension(inputs).update(values)
    result = checked(inputs)
    assert result["status"] == "unknown" and "display_format_unknown" in codes(result)


def test_unmapped_objects_and_incomplete_enumeration_remain_unknown(inputs):
    capture = inputs[1]
    capture["drawing"]["coverage"]["status"] = "partial"
    capture["drawing"]["pages"][0]["unknown_objects"] = [{"name": "ManualAnnotation", "type": "TechDraw::DrawViewAnnotation"}]
    result = checked(inputs)
    assert result["status"] == "unknown"
    assert {"incomplete_capture", "unmapped_page_object"} <= codes(result)


def test_unmapped_dimension_and_other_type_are_not_ignored(inputs):
    extra = deepcopy(dimension(inputs))
    extra["name"] = "ExtraDimension"
    inputs[1]["drawing"]["pages"][0]["views"][0]["dimensions"].append(extra)
    dimension(inputs, 1)["type"] = "Radius"
    result = checked(inputs)
    assert result["status"] == "unknown"
    assert {"annotation_unmapped", "dimension_type_unknown"} <= codes(result)


def test_missing_geometry_or_mismatching_document_does_not_pass(inputs):
    inputs[1]["geometry"] = {"supported": False, "reason": "草图尚未重算"}
    assert checked(inputs)["status"] == "unknown"
    inputs[1]["document"]["path"] = "/different/shaft.FCStd"
    assert checked(inputs)["status"] == "fail"


def test_capture_read_failure_is_preserved_as_actionable_unknown(inputs):
    dimension(inputs)["issues"] = [{"code": "tolerance_unreadable", "message": "公差属性未读到"}]
    result = checked(inputs)
    assert result["status"] == "unknown"
    issue = next(i for i in result["issues"] if i["code"] == "tolerance_unreadable")
    assert issue["location"] == {"page": "Sheet", "view": "Front", "dimension": "DFront"}
    assert issue["next_action"]


def test_declared_dimension_missing_is_not_counted_as_complete(inputs):
    inputs[1]["drawing"]["pages"][0]["views"][1]["dimensions"] = []
    result = checked(inputs)
    assert result["status"] == "unknown" and "annotation_unavailable" in codes(result)
    assert result["coverage"]["declared"] == 2 and result["coverage"]["checked"] == 1


def test_missing_source_does_not_compare_cached_value(inputs):
    inputs[1]["drawing"]["pages"][0]["views"][0]["sources"] = []
    dimension(inputs).update(raw_value=10, measurement_m=.01)
    result = checked(inputs)
    assert result["status"] == "unknown" and "view_source_unknown" in codes(result)
    assert "measurement_mismatch" not in codes(result)


def test_multiple_even_identical_sources_are_outside_single_body_scope(inputs):
    sources = inputs[1]["drawing"]["pages"][0]["views"][0]["sources"]
    sources.append(deepcopy(sources[0]))
    result = checked(inputs)
    assert result["status"] == "unknown" and "view_source_ambiguous" in codes(result)


def test_unknown_native_state_and_foreign_2d_reference_cannot_pass(inputs):
    dimension(inputs)["state"] = ["Restoring"]
    result = checked(inputs)
    assert result["status"] == "unknown" and "object_state_unknown" in codes(result)
    dimension(inputs)["state"] = ["Up-to-date"]
    dimension(inputs)["references2d"][0]["path"] = "/other/same-name.FCStd"
    result = checked(inputs)
    assert result["status"] == "fail" and "dimension_view_mismatch" in codes(result)


@pytest.mark.parametrize("object_kind", ["page", "view", "dimension"])
def test_expanded_tree_node_is_ready_but_does_not_hide_unknown_state(inputs, object_kind):
    page = inputs[1]["drawing"]["pages"][0]
    obj = {"page": page, "view": page["views"][0], "dimension": dimension(inputs)}[object_kind]
    obj["state"] = ["Expanded", "Up-to-date"]
    assert checked(inputs)["status"] == "pass"
    obj["state"].append("Restoring")
    dimension(inputs).update(raw_value=40.0, measurement_m=.04)
    result = checked(inputs)
    assert result["status"] == "unknown" and "object_state_unknown" in codes(result)
    assert "measurement_mismatch" not in codes(result)


def test_page_with_updates_disabled_does_not_claim_current_measurements(inputs):
    inputs[1]["drawing"]["pages"][0]["keep_updated"] = False
    result = checked(inputs)
    assert result["status"] == "unknown" and "page_update_disabled" in codes(result)
    assert result["coverage"]["checked"] == 0


@pytest.mark.parametrize("field,value", [("raw_unit", "in"), ("measure_type", "True"),
                                          ("arbitrary_tolerances", True)])
def test_unverified_measurement_or_tolerance_display_is_unknown(inputs, field, value):
    dimension(inputs)[field] = value
    assert checked(inputs)["status"] == "unknown"
