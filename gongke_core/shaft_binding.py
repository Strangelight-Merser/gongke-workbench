"""将现有原生三段轴的实测尺寸与明确声明的工况组成校核输入。"""

from copy import deepcopy
import math
from uuid import uuid4

from gongke_core.shaft_review import validate_snapshot


def _fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label} 必须且只能包含：" + ", ".join(required))


def prepare_snapshot(geometry, conditions):
    """不补材料/载荷默认值；尺寸来自 CAD，来宾不能指定对象身份。"""
    _fields(conditions, ("material", "supports_m", "loads", "torque_points", "constraints",
                         "middle_diameter_bounds_m", "coordinate_system", "source"), "engineering")
    if conditions["coordinate_system"] != "body_local_x":
        raise ValueError("coordinate_system 必须为 body_local_x：z_m 沿 Body 局部 X，fx_n 沿局部 Y，fy_n 沿局部 Z")
    if not isinstance(conditions["source"], str) or not conditions["source"].strip():
        raise ValueError("source 必须说明载荷、支承、转矩、许用条件和编辑区间的来源")
    _fields(conditions["material"], ("name", "young_modulus_pa", "allowable_stress_pa", "source"), "material")
    _fields(conditions["constraints"], ("alpha", "max_deflection_m"), "constraints")
    for name, fields in (("loads", ("z_m", "fx_n", "fy_n")),
                         ("torque_points", ("z_m", "torque_nm"))):
        if not isinstance(conditions[name], list):
            raise ValueError(f"{name} 必须显式提供列表，无该载荷时提供空列表")
        for item in conditions[name]:
            _fields(item, fields, name)
    bounds = conditions["middle_diameter_bounds_m"]
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0 for v in bounds)
            or bounds[0] >= bounds[1]):
        raise ValueError("middle_diameter_bounds_m 必须给出按升序排列的两个有限正数，单位 m")
    measured = geometry.get("segments")
    if not isinstance(measured, list) or len(measured) != 3:
        raise ValueError("当前原生几何必须包含三个已识别轴段")
    identity = str(uuid4())
    snapshot = {
        "schema_version": 1, "scope": "simplified_shaft", "entity_id": identity,
        "coordinate_system": "body_local_x",
        "conditions_source": {"reference": conditions["source"], "status": "declared"},
        "segments": [],
        **{key: deepcopy(conditions[key]) for key in
           ("material", "supports_m", "loads", "torque_points", "constraints")},
    }
    for i, measurement in enumerate(measured):
        diameter = measurement["diameter_m"]
        low, high = bounds if i == 1 else (diameter, diameter)
        snapshot["segments"].append({
            "segment_id": f"{identity}/segment/{i + 1}", "length_m": measurement["length_m"],
            "diameter_m": diameter, "editable": i == 1,
            "min_diameter_m": low, "max_diameter_m": high,
        })
    errors = validate_snapshot(snapshot)
    if errors:
        raise ValueError("；".join(errors))
    return snapshot
