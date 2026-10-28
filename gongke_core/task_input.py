"""所有任务书入口共用的字段定义与校验。"""
from __future__ import annotations

import copy
import math
from typing import Any
from gongke_core import standards

SCHEMES = {
    "coupling": "电动机 → 联轴器 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒",
    "vbelt": "电动机 → V 带 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒",
    "bevel": "电动机 → 联轴器 → 圆锥-圆柱齿轮减速器 → 联轴器 → 卷筒",
    "worm": "电动机 → 联轴器 → 单级蜗杆减速器（蜗杆下置） → 联轴器 → 卷筒",
    "single": "电动机 → V 带 → 一级圆柱齿轮减速器 → 联轴器 → 卷筒（齿轮参数写在 gears.high）",
}

GEAR_MATERIALS = [r[0] for r in standards.load("textbook/gear_materials.yaml")["materials"]]
WHEEL_MATERIALS = list(standards.load("textbook/worm_gearing.yaml")["wheel_materials"])

_OVERRIDES = {
    "type": "object",
    "description": "用教材图表查得的系数覆盖程序的近似值",
    "properties": {
        "k_v": {"type": "number", "exclusiveMinimum": 0, "description": "动载系数 Kv"},
        "k_alpha": {"type": "number", "exclusiveMinimum": 0, "description": "齿间载荷分配系数 Kα"},
        "k_hbeta": {"type": "number", "exclusiveMinimum": 0, "description": "接触齿向载荷分布系数 KHβ"},
        "k_fbeta": {"type": "number", "exclusiveMinimum": 0, "description": "弯曲齿向载荷分布系数 KFβ"},
        "k_hn1": {"type": "number", "exclusiveMinimum": 0, "description": "小齿轮接触疲劳寿命系数 KHN1"},
        "k_hn2": {"type": "number", "exclusiveMinimum": 0, "description": "大齿轮接触疲劳寿命系数 KHN2"},
        "k_fn1": {"type": "number", "exclusiveMinimum": 0, "description": "小齿轮弯曲疲劳寿命系数 KFN1"},
        "k_fn2": {"type": "number", "exclusiveMinimum": 0, "description": "大齿轮弯曲疲劳寿命系数 KFN2"},
    },
    "additionalProperties": False,
}

_CYL_GEAR = {
    "type": "object",
    "description": "圆柱齿轮（斜齿轮）参数，未给出的取默认值",
    "properties": {
        "material1": {"enum": GEAR_MATERIALS, "default": "40Cr_QT", "description": "小齿轮材料与热处理"},
        "material2": {"enum": GEAR_MATERIALS, "default": "45_QT", "description": "大齿轮材料与热处理"},
        "grade": {"type": "integer", "minimum": 6, "maximum": 9, "default": 8, "description": "精度等级（GB/T 10095）"},
        "z1": {"type": "integer", "minimum": 17, "maximum": 40, "default": 24, "description": "小齿轮齿数"},
        "beta_deg": {"type": "number", "minimum": 8, "maximum": 20, "default": 14, "description": "初选螺旋角，8°～20°；当前不支持圆柱直齿"},
        "phi_d": {"type": "number", "minimum": 0.4, "maximum": 1.4, "default": 1.0, "description": "齿宽系数 φd = b/d1"},
        "k_a": {"type": "number", "minimum": 1, "maximum": 2.5, "default": 1.0, "description": "使用系数 KA"},
        "s_h": {"type": "number", "exclusiveMinimum": 0, "default": 1.0, "description": "接触疲劳安全系数 SH"},
        "s_f": {"type": "number", "exclusiveMinimum": 0, "default": 1.4, "description": "弯曲疲劳安全系数 SF"},
        "overrides": _OVERRIDES,
    },
    "additionalProperties": False,
}

_BEVEL_GEAR = {
    "type": "object",
    "description": "直齿锥齿轮参数（bevel 方案的高速级）",
    "properties": {
        "material1": _CYL_GEAR["properties"]["material1"],
        "material2": _CYL_GEAR["properties"]["material2"],
        "grade": {"type": "integer", "minimum": 6, "maximum": 9, "default": 8, "description": "精度等级（GB/T 11365）"},
        "z1": {"type": "integer", "minimum": 17, "maximum": 40, "default": 24, "description": "小锥齿轮齿数"},
        "phi_r": {"type": "number", "minimum": 0.25, "maximum": 0.35, "default": 0.3, "description": "齿宽系数 φR = b/R"},
        "k_a": _CYL_GEAR["properties"]["k_a"],
        "s_h": _CYL_GEAR["properties"]["s_h"],
        "s_f": _CYL_GEAR["properties"]["s_f"],
        "overrides": _OVERRIDES,
    },
    "additionalProperties": False,
}

_WORM_GEAR = {
    "type": "object",
    "description": "蜗杆传动参数（worm 方案）",
    "properties": {
        "wheel_material": {"enum": WHEEL_MATERIALS, "default": "ZCuSn10P1_metal", "description": "蜗轮齿圈材料"},
        "grade": {"type": "integer", "minimum": 7, "maximum": 9, "default": 8, "description": "精度等级（GB/T 10089）"},
        "z1": {"type": "integer", "enum": [1, 2, 4, 6], "description": "蜗杆头数（不给出时按传动比自动选）"},
        "worm_hardened": {"type": "boolean", "default": True, "description": "蜗杆齿面淬火（> 45HRC）；false 为调质（≤ 350HB）"},
        "two_sided": {"type": "boolean", "default": False, "description": "蜗轮齿双侧受载（正反转）"},
        "k_a": _CYL_GEAR["properties"]["k_a"],
    },
    "additionalProperties": False,
}

TASK_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "带式输送机传动装置设计任务书",
    "description": "与 examples/*.yaml 的结构相同。只有 conveyor 必填，其余都有默认值。",
    "type": "object",
    "required": ["conveyor"],
    "properties": {
        "title": {"type": "string", "default": "带式输送机传动装置设计"},
        "scheme": {"enum": list(SCHEMES), "default": "coupling",
                   "description": "传动方案：" + "；".join(f"{k}：{v}" for k, v in SCHEMES.items())},
        "conveyor": {
            "type": "object",
            "required": ["belt_pull_N", "belt_speed_m_s", "drum_diameter_mm"],
            "properties": {
                "belt_pull_N": {"type": "number", "exclusiveMinimum": 0, "description": "输送带工作拉力 F，N"},
                "belt_speed_m_s": {"type": "number", "exclusiveMinimum": 0, "description": "输送带速度 v，m/s"},
                "drum_diameter_mm": {"type": "number", "exclusiveMinimum": 0, "description": "卷筒直径 D，mm"},
            },
            "additionalProperties": False,
        },
        "life": {
            "type": "object",
            "properties": {
                "years": {"type": "number", "exclusiveMinimum": 0, "default": 10, "description": "使用年限"},
                "days_per_year": {"type": "number", "exclusiveMinimum": 0, "default": 300, "description": "每年工作天数"},
                "shifts": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2, "description": "每天班数（每班 8 小时）"},
            },
            "additionalProperties": False,
        },
        "bearing_life_years": {"type": "number", "exclusiveMinimum": 0, "default": 3, "description": "轴承预期寿命（检修期），年"},
        "motor_sync_speed_rpm": {"enum": sorted({m.sync_speed_rpm for m in standards.motors()}), "default": 1500, "description": "电动机同步转速，r/min"},
        "ratio_split": {"type": "number", "minimum": 1.1, "maximum": 1.6, "default": 1.3,
                        "description": "二级圆柱齿轮减速器高速级传动比 i1 = √(ratio_split·i)"},
        "vbelt": {
            "type": "object",
            "description": "V 带参数（vbelt、single 方案）",
            "properties": {
                "ratio": {"type": "number", "minimum": 1.5, "maximum": 4,
                          "description": "V 带传动比（不给出时 vbelt 取 2.5；single 取 i/4 并限制在 2～4，使齿轮传动比约为 4）"},
                "section": {"enum": ["A", "B"], "description": "带型（不给出时自动选）"},
                "dd1_mm": {"type": "number", "exclusiveMinimum": 0, "description": "小带轮基准直径，mm（不给出时自动选）"},
                "a0_mm": {"type": "number", "exclusiveMinimum": 0, "description": "初定中心距，mm"},
                "KA": {"type": "number", "exclusiveMinimum": 0, "description": "工况系数（不给出时按每天工作时间取）"},
            },
            "additionalProperties": False,
        },
        "gears": {
            "type": "object",
            "properties": {"high": {"anyOf": [_CYL_GEAR, _BEVEL_GEAR]}, "low": _CYL_GEAR, "worm": _WORM_GEAR},
            "additionalProperties": False,
        },
        "shaft": {
            "type": "object",
            "properties": {
                "S_required": {"type": "number", "exclusiveMinimum": 0, "default": 1.5, "description": "轴疲劳强度许用安全系数 [S]"},
                "k_sigma_fit": {"type": "number", "exclusiveMinimum": 0, "description": "齿轮过盈配合处 kσ/εσ（查教材附表，给出时才校核该截面）"},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


class TaskError(ValueError):
    """任务书有误。"""


def task_schema() -> dict:
    return copy.deepcopy(TASK_SCHEMA)


def _check(value, schema: dict, path: str, errors: list[str]) -> None:
    """按 TASK_SCHEMA 的子集（type/enum/required/min/max/additionalProperties/anyOf）检查，不依赖 jsonschema 库。"""
    if "anyOf" in schema:
        trials = []
        for sub in schema["anyOf"]:
            e: list[str] = []
            _check(value, sub, path, e)
            if not e:
                return
            trials.append(e)
        errors.extend(min(trials, key=len))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}：{value!r} 不是可选值 {schema['enum']}")
        return
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}：应为对象")
            return
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errors.append(f"{path}.{k}：必填")
        for k, v in value.items():
            if k in props:
                _check(v, props[k], f"{path}.{k}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{k}：未知字段（可用字段：{', '.join(props)}）")
        return
    if t in ("number", "integer"):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or (t == "integer" and int(value) != value)):
            errors.append(f"{path}：应为{'整数' if t == 'integer' else '数值'}")
            return
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}：{value} 小于下限 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}：{value} 大于上限 {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}：应大于 {schema['exclusiveMinimum']}")
    elif t == "string" and not isinstance(value, str):
        errors.append(f"{path}：应为字符串")
    elif t == "boolean" and not isinstance(value, bool):
        errors.append(f"{path}：应为 true/false")


def validate(task: dict) -> list[str]:
    """返回任务书中的错误（空列表表示无误）。"""
    errors: list[str] = []
    _check(task, TASK_SCHEMA, "task", errors)
    if errors:
        return errors
    scheme = task.get("scheme", "coupling") if isinstance(task, dict) else None
    gears = (task.get("gears") or {}) if isinstance(task, dict) else {}
    if scheme == "worm" and ("high" in gears or "low" in gears):
        errors.append("task.gears：worm 方案只用 gears.worm")
    if scheme != "worm" and "worm" in gears:
        errors.append("task.gears.worm：只用于 worm 方案")
    if scheme == "bevel" and "high" in gears and any(k in gears["high"] for k in ("beta_deg", "phi_d")):
        errors.append("task.gears.high：bevel 方案的高速级是直齿锥齿轮，没有 beta_deg、phi_d（用 phi_r）")
    if scheme == "single" and "low" in gears:
        errors.append("task.gears.low：single 方案只有一级齿轮，用 gears.high")
    if scheme in ("coupling", "vbelt", "single") and "high" in gears and "phi_r" in gears["high"]:
        errors.append("task.gears.high.phi_r：只用于 bevel 方案")
    return errors
