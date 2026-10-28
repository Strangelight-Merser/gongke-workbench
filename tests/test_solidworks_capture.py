"""完全合成的采集文件契约测试；不是 Windows、VBA 或 SOLIDWORKS 运行证据。"""

import copy
import json

import pytest

from tools.solidworks.read_capture import load_capture, matching_views, validate_capture


@pytest.fixture
def capture():
    """字段形状来自原型；名称、尺寸值和图纸关联均为人为构造。"""
    return {
        "schema_version": 1,
        "capture_kind": "solidworks_readonly_inventory",
        "prototype_validation": "unverified",
        "status": "collected",
        "captured_at_local": "2026-10-28T12:34:56",
        "document": {"path": r"C:\课程设计\轴.SLDPRT", "title": "轴", "type": 1, "configuration": "教学"},
        "enumeration_completeness": "not_established",
        "engineering_semantics": "unmapped",
        "dimensions": [{
            "full_name": "D1@草图1@轴.SLDPRT", "feature_name": "草图1", "value_si": 0.038,
            "parameter_type": 0, "unit": "m", "driven_state": 0, "read_only": False, "status": "read",
        }],
        "open_drawings": [{
            "path": r"C:\课程设计\轴.SLDDRW", "title": "轴图纸", "status": "read",
            "views": [{"sheet_name": "图纸1", "view_name": "前视图", "referenced_model": r"c:\课程设计\轴.sldprt",
                       "referenced_configuration": "教学", "status": "read"}],
        }],
        "issues": [],
    }


def test_load_unicode_raw_identity_without_engineering_defaults(tmp_path, capture):
    path = tmp_path / "synthetic_capture.json"
    path.write_text(json.dumps(capture, ensure_ascii=True), encoding="ascii")
    data = load_capture(path)
    assert data == capture
    assert data["dimensions"][0]["value_si"] == 0.038
    assert "shaft" not in data and "material" not in data and "loads" not in data


@pytest.mark.parametrize(("kind", "unit", "value"), [(0, "m", 0.038), (1, "rad", 1.570796), (2, "integer", 3)])
def test_dimension_type_units(capture, kind, unit, value):
    capture["dimensions"][0].update(parameter_type=kind, unit=unit, value_si=value)
    assert validate_capture(capture) is capture


def test_partial_and_unknown_remain_visible(capture):
    capture["status"] = "partial"
    capture["issues"] = ["dimension.unit: unknown_parameter_type", "view.referenced_configuration: empty_value"]
    capture["dimensions"][0].update(parameter_type=-1, unit=None, read_only=None, status="partial")
    capture["open_drawings"][0]["status"] = "partial"
    capture["open_drawings"][0]["views"][0].update(referenced_configuration=None, status="partial")
    assert validate_capture(capture) is capture
    assert matching_views(capture) == []


@pytest.mark.parametrize("document", [None, {"path": r"C:\Assembly.SLDASM", "title": "Assembly", "type": 2, "configuration": None}])
def test_unsupported_active_document_is_not_a_part(capture, document):
    capture.update(document=document, status="unsupported", dimensions=[], issues=["active_document: unsupported"])
    assert validate_capture(capture) is capture
    assert matching_views(capture) == []
    capture["status"] = "collected"
    with pytest.raises(ValueError, match="活动零件"):
        validate_capture(capture)


def test_drawing_association_requires_full_path_and_configuration(capture):
    drawing = capture["open_drawings"][0]
    base = copy.deepcopy(drawing["views"][0])
    drawing["views"] += [
        {**base, "view_name": "同名另一目录", "referenced_model": r"D:\其他项目\轴.SLDPRT"},
        {**base, "view_name": "另一配置", "referenced_configuration": "生产"},
        {**base, "view_name": "只有文件名", "referenced_model": "轴.SLDPRT"},
    ]
    assert [view["view_name"] for view in matching_views(capture)] == ["前视图"]


@pytest.mark.parametrize("changes", [
    {"unit": "mm"}, {"value_si": True}, {"value_si": float("inf")},
    {"parameter_type": 2, "unit": "integer", "value_si": 2.5},
    {"full_name": None}, {"read_only": 0},
])
def test_reject_wrong_units_invalid_values_and_false_complete_records(capture, changes):
    capture["dimensions"][0].update(changes)
    with pytest.raises(ValueError):
        validate_capture(capture)


def test_reject_duplicate_dimension_identity(capture):
    capture["dimensions"].append(copy.deepcopy(capture["dimensions"][0]))
    with pytest.raises(ValueError, match="FullName 重复"):
        validate_capture(capture)


def test_reject_false_completeness_and_mapping(capture):
    capture["enumeration_completeness"] = "complete"
    with pytest.raises(ValueError, match="不能证明"):
        validate_capture(capture)
    capture["enumeration_completeness"] = "not_established"
    capture["engineering_semantics"] = "shaft"
    with pytest.raises(ValueError, match="工程语义"):
        validate_capture(capture)


def test_empty_dimensions_do_not_claim_success(capture):
    capture["dimensions"] = []
    with pytest.raises(ValueError, match="未枚举出尺寸"):
        validate_capture(capture)
    capture.update(status="partial", issues=["dimensions: none_enumerated_not_proof_of_no_dimensions"])
    assert validate_capture(capture) is capture


def test_child_partial_propagates(capture):
    capture["open_drawings"][0]["views"][0].update(referenced_model=None, status="partial")
    with pytest.raises(ValueError, match="不完整视图"):
        validate_capture(capture)


@pytest.mark.parametrize("text", ['{"schema_version":1,"schema_version":1}', '{"value":NaN}'])
def test_reject_ambiguous_json(tmp_path, text):
    path = tmp_path / "invalid_synthetic.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_capture(path)
