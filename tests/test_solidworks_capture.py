"""完全合成的采集文件契约测试；不是 Windows、VBA 或 SOLIDWORKS 运行证据。"""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.solidworks.read_capture import inspection_summary, load_capture, matching_views, validate_capture
from tools.package_solidworks_probe import FILES, package


@pytest.fixture
def capture():
    """字段形状来自原型；名称、尺寸值和图纸关联均为人为构造。"""
    return {
        "schema_version": 2,
        "capture_kind": "solidworks_readonly_inventory",
        "prototype_validation": "unverified",
        "status": "collected",
        "captured_at_local": "2026-10-28T12:34:56",
        "host": {"revision_number": "34.0.0", "platform": "Windows"},
        "document": {"path": r"C:\课程设计\轴.SLDPRT", "title": "轴", "type": 1, "configuration": "教学"},
        "selected_target": {"full_name": "D1@草图1@轴.SLDPRT", "value_si": 0.038,
                            "parameter_type": 0, "unit": "m", "display_type": 6, "selection_type": 14},
        "state_before": [{"path": r"C:\课程设计\轴.SLDPRT", "title": "轴", "type": 1,
                          "configuration": "教学", "save_flag": True, "selection_count": 1}],
        "state_after": [{"path": r"C:\课程设计\轴.SLDPRT", "title": "轴", "type": 1,
                         "configuration": "教学", "save_flag": True, "selection_count": 1}],
        "state_preservation": "not_established",
        "enumeration_completeness": "not_established",
        "engineering_semantics": "unmapped",
        "dimensions": [{
            "full_name": "D1@草图1@轴.SLDPRT", "feature_name": "草图1", "value_si": 0.038,
            "parameter_type": 0, "unit": "m", "driven_state": 0, "read_only": False, "status": "read",
        }],
        "open_drawings": [{
            "path": r"C:\课程设计\轴.SLDDRW", "title": "轴图纸", "status": "read",
            "views": [{"sheet_name": "图纸1", "view_name": "前视图", "referenced_model": r"c:\课程设计\轴.sldprt",
                       "referenced_configuration": "教学", "status": "read",
                       "annotation_coverage": "not_established", "view_update_status": "not_checked",
                       "display_dimensions": [{"annotation_name": "D1@前视图", "dimension_full_names": ["D1@草图1@轴.SLDPRT"],
                                               "display_type": 6, "override": False, "override_value": None,
                                               "override_value_unit": "not_established", "dangling": False,
                                               "text_override_status": "not_checked", "status": "read"}]}],
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


def test_selected_target_can_be_outside_feature_enumeration(capture):
    """显式选中可提供隐藏尺寸线索，但绝不升级全部尺寸覆盖。"""
    capture["selected_target"]["full_name"] = "D2@草图2@轴.SLDPRT"
    summary = inspection_summary(capture)
    assert summary["matching_target_instances"] == []
    assert summary["engineering_semantics"] == "unmapped"
    assert summary["enumeration_completeness"] == "not_established"
    assert summary["drawing_review"] == "incomplete"


def test_all_target_display_instances_preserved_and_wrong_configuration_excluded(capture):
    drawing = capture["open_drawings"][0]
    side = copy.deepcopy(drawing["views"][0])
    side.update(view_name="侧视图")
    side["display_dimensions"][0]["annotation_name"] = "D1@侧视图"
    other_config = copy.deepcopy(side)
    other_config.update(view_name="另配置视图", referenced_configuration="生产")
    other_path = copy.deepcopy(side)
    other_path.update(view_name="同名另一目录", referenced_model=r"D:\课程设计\轴.SLDPRT")
    drawing["views"] += [side, other_config, other_path]
    assert [r["view_name"] for r in inspection_summary(capture)["matching_target_instances"]] == ["前视图", "侧视图"]


def test_numeric_override_and_dangling_keep_cad_location(capture):
    annotation = capture["open_drawings"][0]["views"][0]["display_dimensions"][0]
    annotation.update(override=True, override_value=40.0, dangling=True)
    summary = inspection_summary(capture)
    assert [r["kind"] for r in summary["findings"]] == ["numeric_override", "dangling_dimension"]
    assert all(r["annotation_name"] == "D1@前视图" and r["view_name"] == "前视图" for r in summary["findings"])
    assert summary["matching_target_instances"][0]["override_value_unit"] == "not_established"


def test_unread_dangling_is_unknown_not_false(capture):
    capture.update(status="partial", issues=["annotation.dangling: read_failed"])
    drawing = capture["open_drawings"][0]
    drawing["status"] = "partial"
    view = drawing["views"][0]
    view["status"] = "partial"
    view["display_dimensions"][0].update(dangling=None, status="partial")
    summary = inspection_summary(capture)
    assert summary["findings"][0]["kind"] == "annotation_read_incomplete"
    assert summary["drawing_review"] == "incomplete"


def test_state_change_is_reported_and_never_called_collected(capture):
    capture["state_after"][0]["save_flag"] = False
    with pytest.raises(ValueError, match="前后观察"):
        validate_capture(capture)
    capture.update(status="partial", issues=["state: observed_state_changed"])
    assert {"kind": "observed_state_changed"} in inspection_summary(capture)["findings"]
    capture["state_preservation"] = "verified"
    with pytest.raises(ValueError, match="原状态"):
        validate_capture(capture)


@pytest.mark.parametrize("changes", [
    {"override": True}, {"dangling": None}, {"dimension_full_names": []},
    {"override_value": float("nan")}, {"annotation_name": None},
    {"text_override_status": "clear"}, {"override_value_unit": "m"},
])
def test_reject_false_complete_annotation(capture, changes):
    capture["open_drawings"][0]["views"][0]["display_dimensions"][0].update(changes)
    with pytest.raises(ValueError):
        validate_capture(capture)


@pytest.mark.parametrize("changes", [
    {"selection_type": 1}, {"display_type": 10}, {"unit": "mm"}, {"value_si": True},
    {"parameter_type": 2, "unit": "integer", "value_si": 2.5},
])
def test_reject_ambiguous_selected_target(capture, changes):
    capture["selected_target"].update(changes)
    with pytest.raises(ValueError):
        validate_capture(capture)


def test_missing_selection_requires_partial_and_no_mapping(capture):
    capture["selected_target"] = None
    with pytest.raises(ValueError, match="选择的尺寸"):
        validate_capture(capture)
    capture.update(status="partial", issues=["selected_target: select_exactly_one_dimension"])
    assert inspection_summary(capture)["matching_target_instances"] == []


def test_old_schema_cannot_silently_gain_new_evidence(capture):
    capture["schema_version"] = 1
    with pytest.raises(ValueError, match="schema_version"):
        validate_capture(capture)


def test_unknown_state_observation_cannot_claim_collected(capture):
    for key in ("state_before", "state_after"):
        capture[key][0]["save_flag"] = None
    with pytest.raises(ValueError, match="未知观察字段"):
        validate_capture(capture)
    capture.update(status="partial", issues=["state.save_flag: read_failed"])
    assert inspection_summary(capture)["state_preservation"] == "not_established"


def test_probe_package_runs_without_repository_and_keeps_exact_source(tmp_path, capture):
    """仅验证源码包与 Python 检查器；不会执行或验证 VBA。"""
    output = tmp_path / "readonly-probe.zip"
    manifest = package(output)
    original_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        package(output)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == original_hash
    source = Path(__file__).resolve().parents[1] / "tools" / "solidworks"
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"gongke-solidworks-probe/" + name for name in (*FILES, "manifest.json")}
        assert json.loads(archive.read("gongke-solidworks-probe/manifest.json")) == manifest
        for name in FILES:
            data = archive.read("gongke-solidworks-probe/" + name)
            assert data == (source / name).read_bytes()
            assert manifest["files"][name] == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        archive.extractall(tmp_path / "consumer")
    consumer = tmp_path / "consumer" / "gongke-solidworks-probe"
    data_path = consumer / "synthetic.json"
    data_path.write_text(json.dumps(capture), encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(consumer / "read_capture.py"), str(data_path)],
                            cwd=consumer, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == inspection_summary(capture)
    assert manifest["prototype_validation"] == "unverified"
    data_path.write_text('{"schema_version": 1}', encoding="utf-8")
    invalid = subprocess.run([sys.executable, "-I", str(consumer / "read_capture.py"), str(data_path)],
                             cwd=consumer, capture_output=True, text=True)
    assert invalid.returncode == 1
    assert "采集文件不合格" in invalid.stderr
