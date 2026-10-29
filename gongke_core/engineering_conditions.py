"""只读修订所需的工程单位与来源确认，不补材料或载荷默认值。"""

from __future__ import annotations

from copy import deepcopy
import math


_UNITS = {
    "length": {"m": 1.0, "mm": 1e-3},
    "force": {"N": 1.0, "kN": 1e3},
    "torque": {"N*m": 1.0, "N·m": 1.0, "N*mm": 1e-3, "N·mm": 1e-3},
    "stress": {"Pa": 1.0, "MPa": 1e6, "GPa": 1e9},
    "ratio": {"1": 1.0},
}
_SI_UNITS = {"length": "m", "force": "N", "torque": "N·m", "stress": "Pa", "ratio": "1"}
_LABELS = {
    "coordinate_system": "坐标与位置声明", "supports": "两个简支点",
    "loads": "横向集中力", "torque_points": "输入与输出转矩", "material_name": "材料说明",
    "young_modulus": "弹性模量", "allowable_stress": "名义许用应力",
    "alpha": "弯扭折合系数", "max_deflection": "最大挠度限值",
}
_REQUIRED = tuple(name for name in _LABELS if name != "material_name")


def _quantity(item, dimension, *, positive=False):
    if not isinstance(item, dict) or set(item) != {"value", "unit"}:
        raise ValueError("数值必须明确给出 value 和 unit")
    value, unit = item["value"], item["unit"]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("数值必须是有限实数，不能用文字、布尔值或空值代替")
    if not isinstance(unit, str) or unit not in _UNITS[dimension]:
        raise ValueError("单位必须为 " + "、".join(_UNITS[dimension]))
    converted = value * _UNITS[dimension][unit]
    if not math.isfinite(converted) or (positive and converted <= 0):
        raise ValueError("换算结果必须为有限正数" if positive else "换算结果必须有限")
    return converted


def normalize_conditions(document):
    """把字段记录转为部分可用的 SI 条件，未确认或有冲突的值仅保留为证据。

    fields 中的数值记录包含 value、unit、status 和 source；source 为原文 text 与
    位置 reference。一条载荷用自己的 status/source 覆盖各分量。confirmed 是
    输入者确认的任务条件，verified 是输入者声明已核验，转换器不自动认证来源。
    """
    issues, evidence = [], []
    si = {"material": {}, "constraints": {}}

    def issue(field, kind, message):
        issues.append({"field": field, "kind": kind, "message": message})

    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1):
        issue("conditions", "invalid", "条件文档必须使用 schema_version=1")
        fields = {}
    elif not isinstance(document.get("fields"), dict):
        issue("conditions.fields", "invalid", "条件文档必须提供 fields 对象")
        fields = {}
    else:
        fields = document["fields"]
        for name in fields.keys() - _LABELS.keys():
            issue(name, "unsupported", f"不支持的条件字段 {name}；模型尺寸只能来自当前 CAD")

    def record(name, supplied, label):
        entry = {"field": name, "label": label, "input": deepcopy(supplied), "usable": False}
        evidence.append(entry)
        if not isinstance(supplied, dict):
            issue(name, "missing" if supplied is None else "invalid", f"{label}缺失或记录格式不正确")
            return None
        status, source = supplied.get("status"), supplied.get("source")
        entry["status"] = status
        if status not in ("confirmed", "verified", "pending", "conflict", "missing"):
            issue(name, "invalid", f"{label}必须明确来源确认状态")
            return None
        if status not in ("confirmed", "verified"):
            kind = "conflict" if status == "conflict" else "unconfirmed"
            issue(name, kind, f"{label}有冲突，请核对来源" if kind == "conflict" else f"{label}待确认，不作为正式计算输入")
            return None
        if not isinstance(source, dict) or any(
            not isinstance(source.get(k), str) or not source[k].strip() for k in ("text", "reference")
        ):
            issue(name, "missing_source", f"{label}缺少原始文本或来源位置")
            return None
        entry["source"] = deepcopy(source)
        return entry

    def converted(entry, value, unit=None):
        entry["usable"] = True
        entry["si_value"] = deepcopy(value)
        if unit is not None:
            entry["si_unit"] = unit

    for name in _REQUIRED:
        if name not in fields:
            record(name, None, _LABELS[name])

    coordinate = fields.get("coordinate_system")
    if "coordinate_system" in fields:
        entry = record("coordinate_system", coordinate, _LABELS["coordinate_system"])
        if entry is not None:
            if coordinate.get("value") != "body_local_x":
                issue("coordinate_system", "unsupported", "仅支持 Body 局部 X 为轴线，横向 fx/fy 分别沿局部 Y/Z")
            elif coordinate.get("position_mode") != "fixed_body_coordinate":
                issue("coordinate_system", "reconfirm", "位置必须明确为固定 Body 局部坐标；轴段锚点须先重新确认映射")
            else:
                si["coordinate_system"] = "body_local_x"
                si["position_mode"] = "fixed_body_coordinate"
                converted(entry, coordinate["value"])

    for name, dimension, section, key in (
        ("young_modulus", "stress", "material", "young_modulus_pa"),
        ("allowable_stress", "stress", "material", "allowable_stress_pa"),
        ("alpha", "ratio", "constraints", "alpha"),
        ("max_deflection", "length", "constraints", "max_deflection_m"),
    ):
        if name not in fields:
            continue
        supplied = fields[name]
        entry = record(name, supplied, _LABELS[name])
        if entry is None:
            continue
        try:
            value = _quantity({k: supplied.get(k) for k in ("value", "unit")}, dimension, positive=True)
        except ValueError as exc:
            issue(name, "invalid", f"{_LABELS[name]}：{exc}")
        else:
            si[section][key] = value
            converted(entry, value, _SI_UNITS[dimension])

    if "material_name" in fields:
        supplied = fields["material_name"]
        entry = record("material_name", supplied, _LABELS["material_name"])
        if entry is not None:
            if not isinstance(supplied.get("value"), str) or not supplied["value"].strip():
                issue("material_name", "invalid", "材料说明必须是非空文本")
            else:
                si["material"]["name"] = supplied["value"]
                converted(entry, supplied["value"])

    if "supports" in fields:
        supplied = fields["supports"]
        entry = record("supports", supplied, _LABELS["supports"])
        if entry is not None:
            try:
                values = supplied.get("value")
                if not isinstance(values, list) or len(values) != 2:
                    raise ValueError("必须提供两个支点位置")
                values = [_quantity({"value": v, "unit": supplied.get("unit")}, "length") for v in values]
                if not 0 <= values[0] < values[1]:
                    raise ValueError("两个位置须非负且按轴线方向递增")
            except ValueError as exc:
                issue("supports", "invalid", f"简支点：{exc}")
            else:
                si["supports_m"] = values
                converted(entry, values, "m")

    for name, components in (("loads", {"fx": ("force", "fx_n"), "fy": ("force", "fy_n")}),
                             ("torque_points", {"torque": ("torque", "torque_nm")})):
        if name not in fields:
            continue
        supplied = fields[name]
        entry = record(name, supplied, _LABELS[name])
        if entry is None:
            continue
        values = supplied.get("value")
        if not isinstance(values, list):
            issue(name, "invalid", f"{_LABELS[name]}必须提供列表，确认无该载荷时提供空列表")
            continue
        items, complete = [], True
        for index, item in enumerate(values):
            path = f"{name}[{index}]"
            row = record(path, item, f"{_LABELS[name]}第 {index + 1} 项")
            if row is None:
                complete = False
                continue
            try:
                extra = item.keys() - {"position", "status", "source", *components}
                if extra:
                    raise ValueError("含不支持的分量或位置语义：" + "、".join(sorted(extra)))
                value = {"z_m": _quantity(item.get("position"), "length")}
                if value["z_m"] < 0:
                    raise ValueError("作用位置不能为负数")
                for component, (dimension, key) in components.items():
                    value[key] = _quantity(item.get(component), dimension)
            except ValueError as exc:
                complete = False
                issue(path, "invalid", f"{_LABELS[name]}第 {index + 1} 项：{exc}")
            else:
                items.append(value)
                converted(row, value)
        if complete:
            si[name] = items
            converted(entry, items)

    return {"schema_version": 1, "si": si, "evidence": evidence, "issues": issues,
            "status": "confirmed" if not issues else "incomplete"}
