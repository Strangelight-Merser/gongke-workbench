"""简化轴载荷输入不降级、转矩间断采样不漏算的回归测试。

解析基准：实心圆轴 W=pi*d^3/32，纯扭矩名义合成应力 sigma=alpha*abs(T)/W。
集中转矩之间内力保持常数；转矩施加点左右极限及轴径突变两侧分别判断。
这些人工构造工况只验证计算覆盖，不是材料或实际设计的专业认可。
"""

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from gongke_core.shaft_review import _inputs, review, validate_snapshot
from gongke_core.calc import shaft


@pytest.fixture
def snapshot():
    return json.loads((Path(__file__).parents[1] / "examples/native_shaft.json").read_text())


@pytest.mark.parametrize("extra", [
    {"fz_n": 1e6, "x0_m": 0.1, "y0_m": 0.0},
    {"fz_n": 0.0},
    {"mx_nm": 1000.0},
    {"couple_xz_nm": 1000.0},
    {"distributed_load_n_m": 1000.0},
])
def test_unsupported_load_components_are_rejected_not_silently_zeroed(snapshot, extra):
    snapshot["loads"] = [{"z_m": 0.25, "fx_n": 0.0, "fy_n": 0.0, **extra}]
    snapshot["torque_points"] = []
    result = review(snapshot)
    # 原缺陷会对 fz=1e6 N、x0=0.1 m 返回零应力 pass；现在停止在输入边界。
    assert result["status"] == "blocked" and result["checks"] == []
    assert any("不支持的字段" in error for error in result["errors"])


def test_unsupported_torque_axis_is_not_discarded(snapshot):
    snapshot["torque_points"][0]["torque_x_nm"] = 1000.0
    assert any("torque_points[0]" in error and "不支持" in error for error in validate_snapshot(snapshot))


@pytest.mark.parametrize("end", [0.10002, 0.1000100001])
def test_narrow_balanced_torque_interval_matches_analytic_stress(snapshot, end):
    snapshot["loads"] = []
    snapshot["torque_points"] = [{"z_m": 0.10001, "torque_nm": 1000.0}, {"z_m": end, "torque_nm": -1000.0}]
    before = deepcopy(snapshot)
    assert validate_snapshot(snapshot) == []
    result = review(snapshot)
    expected = snapshot["constraints"]["alpha"] * 1000.0 / (math.pi * 0.04**3 / 32)
    assert result["checks"][0]["value"] == pytest.approx(expected, rel=1e-12)
    assert result["checks"][0]["value"] > snapshot["material"]["allowable_stress_pa"]
    assert result["status"] == "fail"  # 原实现漏掉整个区间，误报零应力 pass。
    assert snapshot == before


@pytest.mark.parametrize("start,end,expected_diameter", [
    (0.09999, 0.10001, 0.03),  # 跨越 30→40 mm 台阶，小截面侧控制。
    (0.1, 0.10001, 0.04),     # 台阶上施加正转矩，不得误算在左侧小截面。
    (0.09999, 0.1, 0.03),     # 台阶上施加负转矩，左侧小截面仍承受转矩。
    (0.39999, 0.40001, 0.03),  # 跨越 40→30 mm 台阶，右侧小截面控制。
])
def test_torque_events_preserve_both_sides_of_section_change(snapshot, start, end, expected_diameter):
    snapshot["loads"] = []
    snapshot["torque_points"] = [{"z_m": start, "torque_nm": 1000.0}, {"z_m": end, "torque_nm": -1000.0}]
    segments, case = _inputs(snapshot)
    result = shaft.check(segments, case, snapshot["material"]["allowable_stress_pa"], snapshot["constraints"]["alpha"])
    expected = snapshot["constraints"]["alpha"] * 1000.0 / (math.pi * expected_diameter**3 / 32)
    assert result.critical.d == expected_diameter
    assert result.critical.sigma_ca == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("container,field", [
    ("material", "source"), ("material", "young_modulus_pa"), ("material", "allowable_stress_pa"),
    ("constraints", "alpha"), ("constraints", "max_deflection_m"),
    ("loads", "fx_n"), ("loads", "fy_n"), ("torque_points", "torque_nm"),
])
def test_required_engineering_values_remain_required(snapshot, container, field):
    target = snapshot[container][0] if isinstance(snapshot[container], list) else snapshot[container]
    del target[field]
    assert review(snapshot)["status"] == "blocked"


def test_external_transverse_loads_need_not_balance_without_support_reactions(snapshot):
    snapshot["loads"] = [{"z_m": 0.25, "fx_n": 100.0, "fy_n": -1000.0}]
    assert validate_snapshot(snapshot) == []
    segments, case = _inputs(snapshot)
    reactions = shaft.reactions(case)
    assert reactions.ax + reactions.bx + 100.0 == pytest.approx(0.0)
    assert reactions.ay + reactions.by - 1000.0 == pytest.approx(0.0)
