"""当前轴校核的解析基准与输入约束；不调用整机自动设计。

基准公式：简支等截面梁中央集中力，Mmax=P*L/4、ymax=P*L^3/(48*E*I)；
实心圆截面 I=pi*d^4/64、W=pi*d^3/32，纯扭矩合成应力=alpha*T/W。
这些是静力平衡及 Euler–Bernoulli 梁方程的解析解，不把假定材料限值当作标准数据。
"""

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from gongke_core.shaft_review import preview, review, validate_snapshot


@pytest.fixture
def snapshot():
    return json.loads((Path(__file__).parents[1] / "examples/native_shaft.json").read_text())


def uniform(snapshot):
    for segment in snapshot["segments"]:
        segment.update(length_m=0.2, diameter_m=0.02, min_diameter_m=0.01, max_diameter_m=0.06)
    snapshot["supports_m"] = [0.0, 0.6]
    snapshot["loads"] = [{"z_m": 0.3, "fx_n": 0.0, "fy_n": -1000.0}]
    snapshot["torque_points"] = []
    return snapshot


def test_central_load_matches_analytic_solution(snapshot):
    data = uniform(snapshot)
    result = review(data)
    stress, deflection = result["checks"]
    d, length, force = 0.02, 0.6, 1000.0
    assert stress["value"] == pytest.approx((force * length / 4) / (math.pi * d**3 / 32), rel=2e-6)
    expected = force * length**3 / (48 * data["material"]["young_modulus_pa"] * math.pi * d**4 / 64)
    assert deflection["value"] == pytest.approx(expected, rel=2e-6)
    assert stress["z_m"] == pytest.approx(0.3, abs=2e-6)
    assert result["status"] == "fail"


def test_pure_torque_matches_analytic_solution(snapshot):
    data = uniform(snapshot)
    data["loads"] = []
    data["torque_points"] = [{"z_m": 0.0, "torque_nm": 100.0}, {"z_m": 0.6, "torque_nm": -100.0}]
    result = review(data)
    stress, deflection = result["checks"]
    assert stress["value"] == pytest.approx(0.6 * 100 / (math.pi * 0.02**3 / 32))
    assert deflection["value"] == 0
    assert result["status"] == "fail"


def test_preview_keeps_fixed_conditions_and_original(snapshot):
    before = deepcopy(snapshot)
    candidate = preview(snapshot, "middle", 0.035)
    assert snapshot == before
    expected = deepcopy(before)
    expected["segments"][1]["diameter_m"] = 0.035
    assert candidate["candidate_snapshot"] == expected
    assert candidate["change"] == {"segment_id": "middle", "parameter": "diameter_m", "old_value": 0.04, "new_value": 0.035, "unit": "m"}
    assert candidate["review"]["scope"] == "simplified_shaft"


@pytest.mark.parametrize("segment,value", [("left", 0.035), ("missing", 0.035), ("middle", 0.019), ("middle", float("nan")), ("middle", True)])
def test_reject_locked_missing_outside_and_nonfinite_candidates(snapshot, segment, value):
    assert preview(snapshot, segment, value)["status"] == "blocked"


@pytest.mark.parametrize("field", ["material", "supports_m", "loads", "torque_points", "constraints", "entity_id"])
def test_missing_condition_never_passes(snapshot, field):
    del snapshot[field]
    assert validate_snapshot(snapshot)
    result = review(snapshot)
    assert result["status"] == "blocked" and result["checks"] == []


def test_bad_supports_unbalanced_torque_and_invalid_material_block(snapshot):
    snapshot["supports_m"] = [0.2, 0.2]
    snapshot["torque_points"][0]["torque_nm"] = 200
    snapshot["material"]["young_modulus_pa"] = float("inf")
    errors = validate_snapshot(snapshot)
    assert len(errors) == 3
    assert review(snapshot)["status"] == "blocked"


def test_larger_diameter_reduces_nominal_stress_and_deflection(snapshot):
    smaller = preview(snapshot, "middle", 0.025)["review"]
    larger = preview(snapshot, "middle", 0.045)["review"]
    assert smaller["checks"][0]["value"] > larger["checks"][0]["value"]
    assert smaller["checks"][1]["value"] > larger["checks"][1]["value"]
    assert all("status" in check and "limit_source" in check for check in larger["checks"])
