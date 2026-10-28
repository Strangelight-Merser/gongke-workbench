"""接管既有轴时只使用原生实测尺寸和明确给出的局部工况。"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from gongke_core.shaft_binding import prepare_snapshot


@pytest.fixture
def inputs():
    sample = json.loads((Path(__file__).resolve().parents[1] / "examples/native_shaft.json").read_text())
    measured = {"segments": [{"length_m": row["length_m"], "diameter_m": row["diameter_m"]}
                              for row in sample["segments"]]}
    # 学生已有个人修改：38 mm 是接管的事实，不回填示例的 40 mm。
    measured["segments"][1]["diameter_m"] = .038
    conditions = {key: deepcopy(sample[key]) for key in
                  ("material", "supports_m", "loads", "torque_points", "constraints")}
    conditions.update(coordinate_system="body_local_x", source="解析教学算例，明确采用所列支承与工况及编辑范围。",
                      middle_diameter_bounds_m=[.032, .05])
    return measured, conditions


def test_keeps_student_dimensions_declared_sources_and_fresh_identity(inputs):
    geometry, conditions = inputs
    before = deepcopy(inputs)
    snapshot = prepare_snapshot(geometry, conditions)
    another = prepare_snapshot(geometry, conditions)
    assert snapshot["segments"][1]["diameter_m"] == .038
    assert snapshot["segments"][0]["min_diameter_m"] == snapshot["segments"][0]["max_diameter_m"] == .03
    assert snapshot["conditions_source"]["status"] == "declared"
    assert snapshot["loads"] == conditions["loads"]
    assert snapshot["entity_id"] != another["entity_id"]
    assert inputs == before


@pytest.mark.parametrize("missing", ["material", "loads", "supports_m", "torque_points", "constraints", "source"])
def test_missing_conditions_never_receive_teaching_defaults(inputs, missing):
    geometry, conditions = inputs
    del conditions[missing]
    with pytest.raises(ValueError):
        prepare_snapshot(geometry, conditions)


@pytest.mark.parametrize("field,value", [("entity_id", "old-identity"), ("diameter_m", .04), ("fz_n", 1e6)])
def test_does_not_accept_identity_geometry_or_unsupported_load_override(inputs, field, value):
    geometry, conditions = inputs
    conditions[field] = value
    with pytest.raises(ValueError):
        prepare_snapshot(geometry, conditions)


@pytest.mark.parametrize("change", [
    {"coordinate_system": "world"}, {"source": " "},
    {"supports_m": [-.1, .45]}, {"middle_diameter_bounds_m": [.04, .05]},
    {"torque_points": [{"z_m": .1, "torque_nm": 100}]},
    {"loads": [{"z_m": .25, "fx_n": 0, "fy_n": 0, "fz_n": 1e6}]},
])
def test_invalid_frame_or_conditions_block_binding(inputs, change):
    geometry, conditions = inputs
    conditions.update(change)
    with pytest.raises(ValueError):
        prepare_snapshot(geometry, conditions)


def test_explicit_unloaded_case_is_preserved(inputs):
    geometry, conditions = inputs
    conditions.update(loads=[], torque_points=[])
    snapshot = prepare_snapshot(geometry, conditions)
    assert snapshot["loads"] == [] and snapshot["torque_points"] == []
