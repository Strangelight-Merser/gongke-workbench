"""单位与来源边界；教学假定仅用于检查输入，不作为机械设计依据。"""

from copy import deepcopy

import pytest

from gongke_core.engineering_conditions import normalize_conditions


def record(value, unit=None, **extra):
    return {"value": value, **({"unit": unit} if unit else {}), "status": "confirmed",
            "source": {"text": "教学假定，非实际设计依据", "reference": "本测试条件"}, **extra}


def example():
    return {"schema_version": 1, "fields": {
        "coordinate_system": record("body_local_x", position_mode="fixed_body_coordinate"),
        "supports": record([25, 175], "mm"),
        "loads": record([{
            "position": {"value": 100, "unit": "mm"},
            "fx": {"value": 0, "unit": "N"}, "fy": {"value": -1, "unit": "kN"},
            "status": "confirmed", "source": {"text": "轴中点向下1000 N", "reference": "教学受力图"},
        }]),
        "torque_points": record([]),
        "material_name": record("教学弹性材料"),
        "young_modulus": record(200, "GPa"),
        "allowable_stress": record(60, "MPa"),
        "alpha": record(0.6, "1"),
        "max_deflection": record(0.1, "mm"),
    }}


def test_engineering_units_and_original_evidence_survive_without_input_mutation():
    source = example()
    before = deepcopy(source)
    result = normalize_conditions(source)
    assert result["status"] == "confirmed"
    assert result["issues"] == []
    assert result["si"]["material"]["young_modulus_pa"] == 2e11
    assert result["si"]["material"]["allowable_stress_pa"] == 6e7
    assert result["si"]["supports_m"] == pytest.approx([0.025, 0.175])
    assert result["si"]["loads"] == [{"z_m": 0.1, "fx_n": 0.0, "fy_n": -1000.0}]
    assert result["si"]["constraints"]["max_deflection_m"] == pytest.approx(1e-4)
    entry = next(x for x in result["evidence"] if x["field"] == "young_modulus")
    assert entry["input"] == source["fields"]["young_modulus"]
    assert entry["source"]["reference"] == "本测试条件"
    assert source == before


@pytest.mark.parametrize("name", ["loads", "torque_points"])
def test_missing_loads_are_not_silently_zero(name):
    source = example()
    source["fields"].pop(name)
    result = normalize_conditions(source)
    assert name not in result["si"]
    assert any(i["field"] == name and i["kind"] == "missing" for i in result["issues"])
    source["fields"][name] = record([])
    assert normalize_conditions(source)["si"][name] == []
    source["fields"][name]["status"] = "pending"
    assert name not in normalize_conditions(source)["si"]


@pytest.mark.parametrize("value,unit", [(True, "GPa"), (float("nan"), "GPa"),
                                       (float("inf"), "GPa"), (0, "GPa"),
                                       (200, "MPa/mm"), (1e308, "GPa")])
def test_invalid_quantities_do_not_enter_si(value, unit):
    source = example()
    source["fields"]["young_modulus"] = record(value, unit)
    result = normalize_conditions(source)
    assert "young_modulus_pa" not in result["si"]["material"]
    assert result["si"]["material"]["allowable_stress_pa"] == 6e7
    assert any(i["field"] == "young_modulus" for i in result["issues"])


@pytest.mark.parametrize("status", ["pending", "conflict", "missing"])
def test_unconfirmed_value_keeps_its_evidence_but_is_not_computational_input(status):
    source = example()
    source["fields"]["allowable_stress"]["status"] = status
    result = normalize_conditions(source)
    assert "allowable_stress_pa" not in result["si"]["material"]
    evidence = next(e for e in result["evidence"] if e["field"] == "allowable_stress")
    assert evidence["status"] == status and not evidence["usable"]
    assert evidence["input"]["value"] == 60


def test_claimed_verified_does_not_invent_source_or_upgrade_confirmation():
    source = example()
    source["fields"]["young_modulus"]["status"] = "verified"
    source["fields"]["young_modulus"].pop("source")
    result = normalize_conditions(source)
    assert "young_modulus_pa" not in result["si"]["material"]
    assert any(i["kind"] == "missing_source" for i in result["issues"])
    assert source["fields"]["allowable_stress"]["status"] == "confirmed"


def test_unknown_anchor_requires_reconfirmation_instead_of_moving_loads():
    source = example()
    source["fields"]["coordinate_system"]["position_mode"] = "segment_anchor"
    result = normalize_conditions(source)
    assert "coordinate_system" not in result["si"]
    assert any(i["kind"] == "reconfirm" for i in result["issues"])


def test_one_unconfirmed_load_invalidates_the_load_set_without_discarding_other_fields():
    source = example()
    source["fields"]["loads"]["value"][0]["status"] = "pending"
    result = normalize_conditions(source)
    assert "loads" not in result["si"]
    assert result["si"]["supports_m"] == pytest.approx([0.025, 0.175])


def test_extra_axial_force_must_not_be_silently_ignored():
    source = example()
    source["fields"]["loads"]["value"][0]["fz"] = {"value": 500, "unit": "N"}
    result = normalize_conditions(source)
    assert "loads" not in result["si"]
    assert any("fz" in i["message"] for i in result["issues"])


def test_task_conditions_cannot_supply_radius_as_model_diameter():
    source = example()
    source["fields"]["radius"] = record(20, "mm")
    result = normalize_conditions(source)
    assert any(i["field"] == "radius" and i["kind"] == "unsupported" for i in result["issues"])
    assert "radius" not in result["si"]


def test_torque_conversion_and_source_per_point():
    source = example()
    source["fields"]["torque_points"] = record([
        {"position": {"value": position, "unit": "mm"}, "torque": {"value": value, "unit": "N·mm"},
         "status": "confirmed", "source": {"text": "输入输出相等反向", "reference": "教学转矩图"}}
        for position, value in ((25, 100000), (175, -100000))
    ])
    result = normalize_conditions(source)
    assert result["si"]["torque_points"] == [
        pytest.approx({"z_m": 0.025, "torque_nm": 100.0}),
        pytest.approx({"z_m": 0.175, "torque_nm": -100.0})]
