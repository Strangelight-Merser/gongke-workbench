"""独立解析解与现有完整输入基准，验证按项求解而非总状态包装。"""

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from gongke_core.engineering_conditions import normalize_conditions
from gongke_core.revision_calculations import assess
from gongke_core.shaft_review import review


def case():
    # 三段等径轴组成简支等截面梁。解析：Mmax=PL/4；σ=M/W；δmax=PL³/(48EI)。
    # 仅为静力学解析基准，P=1000 N、L=0.6 m、d=0.04 m、E=200 GPa。
    geometry = {"segments": [{"length_m": 0.2, "diameter_m": 0.04} for _ in range(3)]}
    conditions = {"status": "confirmed", "issues": [], "si": {
        "coordinate_system": "body_local_x", "position_mode": "fixed_body_coordinate",
        "supports_m": [0, 0.6], "loads": [{"z_m": 0.3, "fx_n": 0, "fy_n": -1000}],
        "torque_points": [], "material": {"young_modulus_pa": 2e11, "allowable_stress_pa": 6e7},
        "constraints": {"alpha": 0.6, "max_deflection_m": 1e-3},
    }}
    return geometry, conditions


def by_name(result):
    return {c["name"]: c for c in result["checks"]}


def test_center_load_matches_closed_form_and_never_grants_write_permission():
    geometry, normalized = case()
    original = deepcopy((geometry, normalized))
    result = assess(geometry, normalized)
    checks = by_name(result)
    inertia = math.pi * 0.04**4 / 64
    modulus = math.pi * 0.04**3 / 32
    assert checks["nominal_combined_stress"]["value"] == pytest.approx((1000 * 0.6 / 4) / modulus, rel=1e-12)
    assert checks["maximum_deflection"]["value"] == pytest.approx(1000 * 0.6**3 / (48 * 2e11 * inertia), rel=2e-6)
    assert result["numerical_status"] == "pass"
    assert result["modification_eligibility"]["allowed"] is False
    assert (geometry, normalized) == original


def test_missing_elastic_modulus_preserves_stress():
    geometry, normalized = case()
    normalized["si"]["material"].pop("young_modulus_pa")
    checks = by_name(assess(geometry, normalized))
    assert checks["nominal_combined_stress"]["status"] == "pass"
    assert checks["maximum_deflection"]["status"] == "unavailable"


def test_missing_limits_keep_values_without_fabricated_allowables():
    geometry, normalized = case()
    normalized["si"]["material"].pop("allowable_stress_pa")
    normalized["si"]["constraints"].pop("max_deflection_m")
    checks = assess(geometry, normalized)["checks"]
    assert all(c["status"] == "unknown" and c["limit"] is None and c["value"] > 0 for c in checks)


def test_missing_or_unbalanced_torque_does_not_hide_transverse_deflection():
    geometry, normalized = case()
    normalized["si"].pop("torque_points")
    checks = by_name(assess(geometry, normalized))
    assert checks["nominal_combined_stress"]["status"] == "unavailable"
    assert checks["maximum_deflection"]["status"] == "pass"
    normalized["si"]["torque_points"] = [{"z_m": 0.2, "torque_nm": 100}]
    checks = by_name(assess(geometry, normalized))
    assert "不平衡" in checks["nominal_combined_stress"]["reasons"][-1]
    assert checks["maximum_deflection"]["status"] == "pass"


def test_missing_loads_is_unavailable_but_confirmed_zero_load_is_zero():
    geometry, normalized = case()
    normalized["si"].pop("loads")
    assert all(c["status"] == "unavailable" for c in assess(geometry, normalized)["checks"])
    normalized["si"]["loads"] = []
    assert all(c["value"] == 0 for c in assess(geometry, normalized)["checks"])


def test_fail_is_not_hidden_by_an_independent_missing_input():
    geometry, normalized = case()
    normalized["si"]["material"].pop("young_modulus_pa")
    normalized["si"]["material"]["allowable_stress_pa"] = 1e5
    result = assess(geometry, normalized)
    assert result["numerical_status"] == "fail"
    assert by_name(result)["nominal_combined_stress"]["status"] == "fail"


@pytest.mark.parametrize("mutation", ["radius", "negative_length", "outside_support", "outside_load", "axial_force"])
def test_invalid_geometry_and_unsupported_loads_are_not_silently_interpreted(mutation):
    geometry, normalized = case()
    if mutation == "radius":
        geometry["segments"][0]["radius_m"] = geometry["segments"][0].pop("diameter_m") / 2
    elif mutation == "negative_length":
        geometry["segments"][0]["length_m"] = -0.2
    elif mutation == "outside_support":
        normalized["si"]["supports_m"] = [0, 1]
    elif mutation == "outside_load":
        normalized["si"]["loads"][0]["z_m"] = 1
    else:
        normalized["si"]["loads"][0]["fz_n"] = 100
    assert all(c["status"] == "unavailable" for c in assess(geometry, normalized)["checks"])


def test_full_existing_snapshot_has_identical_numbers_to_current_review():
    snapshot = json.loads((Path(__file__).parents[1] / "examples/native_shaft.json").read_text())
    normalized = {"status": "confirmed", "issues": [], "si": {
        **{k: deepcopy(snapshot[k]) for k in ("material", "supports_m", "loads", "torque_points", "constraints")},
        "coordinate_system": "body_local_x", "position_mode": "fixed_body_coordinate",
    }}
    actual, expected = by_name(assess(snapshot, normalized)), by_name(review(snapshot))
    for name in actual:
        assert actual[name]["value"] == expected[name]["value"]
        assert actual[name]["status"] == expected[name]["status"]


def test_normalizer_pending_limit_propagates_to_unknown_not_pass():
    geometry, _ = case()
    def source(value, **extra):
        return {"value": value, "status": "confirmed", "source": {"text": "解析条件", "reference": "测试解析式"}, **extra}
    inputs = {"schema_version": 1, "fields": {
        "coordinate_system": source("body_local_x", position_mode="fixed_body_coordinate"),
        "supports": source([0, 600], unit="mm"), "loads": source([]), "torque_points": source([]),
        "young_modulus": source(200, unit="GPa"), "allowable_stress": source(60, unit="MPa"),
        "alpha": source(0.6, unit="1"), "max_deflection": source(1, unit="mm"),
    }}
    inputs["fields"]["allowable_stress"]["status"] = "pending"
    result = assess(geometry, normalize_conditions(inputs))
    stress = by_name(result)["nominal_combined_stress"]
    assert stress["value"] == 0 and stress["limit"] is None and stress["status"] == "unknown"
    assert result["input_confirmation"] == "incomplete"
