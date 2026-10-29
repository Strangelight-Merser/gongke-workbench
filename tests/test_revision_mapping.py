"""外部任务映射不接触 CAD；样例仅是契约测试，不冒充原生宿主验收。"""

from copy import deepcopy

import pytest

from gongke_core.revision_mapping import applicability, map_capture, validate_case


@pytest.fixture
def revision():
    signature = [{"type": "DistanceY", "name": "radius_2", "driving": True, "first": 3}]
    case = {
        "schema_version": 1, "case_id": "course-revision-1",
        "document": {"path": "/courses/原生 工程/shaft.FCStd", "body": "Rotor",
                     "sketch": "Outline", "revolution": "Turned", "structure_signature": signature},
        "target": {"radius_constraint": "radius_2", "segment_index": 1},
        "pages": ["Drawing"],
        "annotations": [{"page": "Drawing", "view": view, "dimension": dim, "target": "diameter"}
                        for view, dim in (("Front", "DiameterFront"), ("Rear", "DiameterRear"))],
    }
    capture = {
        "host": "freecad", "session_id": "session-A", "document": {"path": case["document"]["path"], "name": "Shaft"},
        "geometry": {"supported": True, "body_name": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": deepcopy(signature),
                     "segments": [{"length_m": length, "diameter_m": diameter, "radius_constraint": name}
                                  for length, diameter, name in ((.05, .03, "radius_1"), (.1, .038, "radius_2"),
                                                               (.05, .03, "radius_3"))]},
        "drawing": {"pages": [{"name": "Drawing", "views": [
            {"name": view, "sources": [{"path": case["document"]["path"], "object": "Rotor"}],
             "dimensions": [{"name": dim, "measurement_m": .038, "arbitrary": False, "format_spec": "%.2f"}]}
            for view, dim in (("Front", "DiameterFront"), ("Rear", "DiameterRear"))]}]},
    }
    return case, capture


def test_reads_external_mapping_without_mutation_or_fresh_identity(revision):
    case, capture = revision
    before = deepcopy(revision)
    first, second = map_capture(case, capture), map_capture(case, capture)
    assert first == second
    assert revision == before
    assert first["status"] == "mapped" and first["can_apply"] is False
    assert first["mapping"]["target"]["diameter_m"] == .038
    assert len(first["mapping"]["annotations"]) == 2
    assert first["mapping"]["coverage"]["scope"] == "selected_pages"
    assert first["mapping"]["coverage"]["status"] == "declared_instances_matched"
    assert first["entity_id"].startswith("revision:")


def test_bound_identity_is_preserved_and_mismatch_is_rejected(revision):
    case, capture = revision
    case["document"]["entity_id"] = capture["geometry"]["entity_id"] = "existing-id"
    assert map_capture(case, capture)["entity_id"] == "existing-id"
    capture["geometry"]["entity_id"] = "other-id"
    result = map_capture(case, capture)
    assert result["status"] == "mismatch" and result["mapping"] is None
    assert result["issues"][0]["code"] == "entity_mismatch"


@pytest.mark.parametrize("path", ["/other/shaft.FCStd", "/courses/原生 工程/shaft-copy.FCStd"])
def test_same_name_in_other_directory_or_copy_never_substitutes_original(revision, path):
    case, capture = revision
    capture["document"]["path"] = path
    result = map_capture(case, capture)
    assert result["status"] == "mismatch" and result["mapping"] is None
    assert result["issues"][0]["location"] == "document.path"


@pytest.mark.parametrize("field", ["body_name", "sketch", "revolution"])
def test_internal_object_rename_requires_new_mapping(revision, field):
    case, capture = revision
    capture["geometry"][field] += "Renamed"
    result = map_capture(case, capture)
    assert result["status"] == "mismatch" and result["mapping"] is None


def test_structure_and_target_identity_not_inferred_from_equal_values(revision):
    case, capture = revision
    capture["geometry"]["structure_signature"][0]["driving"] = False
    assert map_capture(case, capture)["status"] == "mismatch"
    capture["geometry"]["structure_signature"] = deepcopy(case["document"]["structure_signature"])
    capture["geometry"]["segments"][1]["radius_constraint"] = "same_value_other_dimension"
    result = map_capture(case, capture)
    assert result["status"] == "mismatch"
    assert result["issues"][0]["code"] == "target_mismatch"


def test_unreadable_geometry_is_not_an_empty_success(revision):
    case, capture = revision
    capture["geometry"] = {"supported": False, "reason": "需要重算，读取未自动刷新"}
    result = map_capture(case, capture)
    assert result["status"] == "unsupported" and result["mapping"] is None
    assert result["issues"][0]["message"] == "需要重算，读取未自动刷新"


def test_missing_declared_instance_has_exact_locator_and_preserves_other_mapping(revision):
    case, capture = revision
    capture["drawing"]["pages"][0]["views"][1]["dimensions"] = []
    result = map_capture(case, capture)
    assert result["status"] == "incomplete"
    assert result["issues"][0]["location"] == "Drawing/Rear/DiameterRear"
    assert result["mapping"]["coverage"]["matched"] == 1


def test_unmapped_annotation_remains_unknown_even_when_numbers_agree(revision):
    case, capture = revision
    capture["drawing"]["pages"][0]["views"][0]["dimensions"].append(
        {"name": "ManualNote", "measurement_m": .038})
    result = map_capture(case, capture)
    assert result["status"] == "incomplete"
    assert result["mapping"]["coverage"]["status"] == "unknown"
    assert result["mapping"]["coverage"]["unmapped"] == [{"page": "Drawing", "view": "Front", "dimension": "ManualNote"}]


def test_missing_page_and_duplicate_dimension_cannot_complete_coverage(revision):
    case, capture = revision
    capture["drawing"]["pages"] = []
    result = map_capture(case, capture)
    assert {row["code"] for row in result["issues"]} == {"page_unavailable", "annotation_unavailable"}


def test_reopen_preserves_object_identity_but_invalidates_previous_session_result(revision):
    case, capture = revision
    previous = map_capture(case, capture)
    capture["session_id"] = "session-B"
    capture["document"]["name"] = "ShaftReloaded"
    current = map_capture(case, capture)
    assert previous["entity_id"] == current["entity_id"]
    assert applicability(previous, current) == {"status": "stale", "changed": ["session_id"]}


def test_separate_geometry_conditions_and_drawing_invalidation(revision):
    case, capture = revision
    conditions = {"load": {"value": 1000, "unit": "N", "source": "任务书第 1 页"}}
    first = map_capture(case, capture, conditions)
    conditions["load"]["source"] = "更正后的任务书第 2 页"
    assert applicability(first, map_capture(case, capture, conditions))["changed"] == ["conditions"]
    first = map_capture(case, capture, conditions)
    capture["drawing"]["pages"][0]["views"][0]["dimensions"][0]["arbitrary"] = True
    assert applicability(first, map_capture(case, capture, conditions))["changed"] == ["drawing"]
    first = map_capture(case, capture, conditions)
    capture["geometry"]["segments"][1]["diameter_m"] = .036
    assert applicability(first, map_capture(case, capture, conditions))["changed"] == ["geometry"]


def test_annotation_enumeration_order_is_not_a_change(revision):
    case, capture = revision
    first = map_capture(case, capture)
    capture["drawing"]["pages"][0]["views"].reverse()
    case["annotations"].reverse()
    assert applicability(first, map_capture(case, capture)) == {"status": "current", "changed": []}


@pytest.mark.parametrize("object_kind", ["page", "view", "dimension"])
def test_tree_expansion_does_not_expire_result_or_mutate_capture(revision, object_kind):
    case, capture = revision
    page = capture["drawing"]["pages"][0]
    obj = {"page": page, "view": page["views"][0],
           "dimension": page["views"][0]["dimensions"][0]}[object_kind]
    obj["state"] = ["Up-to-date"]
    previous = map_capture(case, capture)
    obj["state"].insert(0, "Expanded")
    before = deepcopy(capture)
    assert applicability(previous, map_capture(case, capture)) == {"status": "current", "changed": []}
    assert capture == before


@pytest.mark.parametrize("state", ["Restoring", "Touched", "Invalid", "Error"])
def test_only_tree_expansion_is_removed_from_drawing_fingerprint(revision, state):
    case, capture = revision
    page = capture["drawing"]["pages"][0]
    page["state"] = ["Expanded", "Up-to-date"]
    previous = map_capture(case, capture)
    page["state"].append(state)
    assert applicability(previous, map_capture(case, capture)) == {"status": "stale", "changed": ["drawing"]}


@pytest.mark.parametrize("flag", ["pending_transaction", "needs_rebuild"])
def test_edit_state_preserves_identity_but_invalidates_previous_result(revision, flag):
    case, capture = revision
    capture["document"].update(pending_transaction=False, needs_rebuild=False)
    previous = map_capture(case, capture)
    capture["document"][flag] = True
    current = map_capture(case, capture)
    assert current["status"] == "mapped" and current["entity_id"] == previous["entity_id"]
    assert current["mapping"] == previous["mapping"]
    assert applicability(previous, current) == {"status": "stale", "changed": ["document_state"]}
    assert applicability(current, previous) == {"status": "stale", "changed": ["document_state"]}


def test_non_edit_document_metadata_does_not_invalidate_result(revision):
    case, capture = revision
    previous = map_capture(case, capture)
    capture["document"].update(modified=True, name="DisplayName")
    assert applicability(previous, map_capture(case, capture)) == {"status": "current", "changed": []}


@pytest.mark.parametrize("mutation", [
    lambda c: c["document"].pop("structure_signature"),
    lambda c: c["document"].update(path="shaft.FCStd"),
    lambda c: c["target"].update(segment_index=True),
    lambda c: c["annotations"][0].update(target="radius"),
    lambda c: c["annotations"].append(deepcopy(c["annotations"][0])),
    lambda c: c["pages"].append(c["pages"][0]),
])
def test_incomplete_or_ambiguous_task_requires_explicit_mapping(revision, mutation):
    case, _ = revision
    mutation(case)
    with pytest.raises(ValueError):
        validate_case(case)
