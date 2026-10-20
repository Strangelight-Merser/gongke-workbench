"""面向程序和 AI agent 的接口：输入、输出都是可 JSON 序列化的 dict，单位与任务书一致（mm、N、MPa、kW、r/min）。

FreeCAD 工作台、命令行和 MCP 服务器（`gongke_core.mcp_server`）都调用这里的函数，三者功能一致。

- `task_schema()`：任务书各字段的 JSON Schema（含说明、单位、默认值、可选值）。
- `validate(task)`：检查任务书，返回错误列表。
- `design(task)`：完成全部设计计算，返回结果摘要和各项校核结论。
- `report(task, chapter)`：计算说明书（Markdown 文本），可只取某一章。
- `explore(task, param, values)`：改变一个参数做多方案对比。
- `lookup(kind, ...)`：查标准件和材料数据（电动机、轴承、平键、模数、材料、齿形系数）。
- `generate(task, out_dir, ...)`：生成说明书、工程图（DXF/SVG/PDF）、三维模型和有限元复核文件。
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from gongke_core import design as design_mod
from gongke_core import standards, summary

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
        "k_v": {"type": "number", "description": "动载系数 Kv"},
        "k_alpha": {"type": "number", "description": "齿间载荷分配系数 Kα"},
        "k_hbeta": {"type": "number", "description": "接触齿向载荷分布系数 KHβ"},
        "k_fbeta": {"type": "number", "description": "弯曲齿向载荷分布系数 KFβ"},
        "k_hn1": {"type": "number", "description": "小齿轮接触疲劳寿命系数 KHN1"},
        "k_hn2": {"type": "number", "description": "大齿轮接触疲劳寿命系数 KHN2"},
        "k_fn1": {"type": "number", "description": "小齿轮弯曲疲劳寿命系数 KFN1"},
        "k_fn2": {"type": "number", "description": "大齿轮弯曲疲劳寿命系数 KFN2"},
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
        "beta_deg": {"type": "number", "minimum": 0, "maximum": 20, "default": 14, "description": "初选螺旋角，°（0 为直齿）"},
        "phi_d": {"type": "number", "minimum": 0.4, "maximum": 1.4, "default": 1.0, "description": "齿宽系数 φd = b/d1"},
        "k_a": {"type": "number", "minimum": 1, "maximum": 2.5, "default": 1.0, "description": "使用系数 KA"},
        "s_h": {"type": "number", "default": 1.0, "description": "接触疲劳安全系数 SH"},
        "s_f": {"type": "number", "default": 1.4, "description": "弯曲疲劳安全系数 SF"},
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
                "years": {"type": "number", "default": 10, "description": "使用年限"},
                "days_per_year": {"type": "number", "default": 300, "description": "每年工作天数"},
                "shifts": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2, "description": "每天班数（每班 8 小时）"},
            },
            "additionalProperties": False,
        },
        "bearing_life_years": {"type": "number", "default": 3, "description": "轴承预期寿命（检修期），年"},
        "motor_sync_speed_rpm": {"enum": [1000, 1500, 3000], "default": 1500, "description": "电动机同步转速，r/min"},
        "ratio_split": {"type": "number", "minimum": 1.1, "maximum": 1.6, "default": 1.3,
                        "description": "二级圆柱齿轮减速器高速级传动比 i1 = √(ratio_split·i)"},
        "vbelt": {
            "type": "object",
            "description": "V 带参数（vbelt、single 方案）",
            "properties": {
                "ratio": {"type": "number", "minimum": 1.5, "maximum": 4,
                          "description": "V 带传动比（不给出时 vbelt 取 2.5；single 取 i/4 并限制在 2～4，使齿轮传动比约为 4）"},
                "section": {"enum": ["A", "B"], "description": "带型（不给出时自动选）"},
                "dd1_mm": {"type": "number", "description": "小带轮基准直径，mm（不给出时自动选）"},
                "a0_mm": {"type": "number", "description": "初定中心距，mm"},
                "KA": {"type": "number", "description": "工况系数（不给出时按每天工作时间取）"},
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
                "S_required": {"type": "number", "default": 1.5, "description": "轴疲劳强度许用安全系数 [S]"},
                "k_sigma_fit": {"type": "number", "description": "齿轮过盈配合处 kσ/εσ（查教材附表，给出时才校核该截面）"},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


class TaskError(ValueError):
    """任务书有误。"""


def clean(v, digits: int = 6):
    """把结果中的浮点数保留 digits 位有效数字（去掉 18.000000000000004 这类噪声，也让输出更短）。"""
    if isinstance(v, float):
        return float(f"{v:.{digits}g}")
    if isinstance(v, dict):
        return {k: clean(x, digits) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x, digits) for x in v]
    return v


def task_schema() -> dict:
    return copy.deepcopy(TASK_SCHEMA)


def example_task(scheme: str = "coupling") -> dict:
    """示例任务书（examples/ 中对应方案的文件内容）。"""
    import yaml

    name = {"coupling": "basic"}.get(scheme, scheme)
    path = Path(__file__).resolve().parents[1] / "examples" / f"conveyor_{name}.yaml"
    if not path.exists():
        raise TaskError(f"没有 {scheme} 方案的示例")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (t == "integer" and int(value) != value):
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


def _run(task: dict):
    errors = validate(task)
    if errors:
        raise TaskError("任务书有误：\n" + "\n".join(errors))
    return design_mod.run(design_mod.ReducerTask.from_dict(task))


def design(task: dict) -> dict:
    """完成设计计算。返回 summary（电动机、传动比、各级传动件、各轴、校核项）以及未通过的项目。"""
    t0 = time.time()
    res = _run(task)
    s = summary.summarize(res)
    s["failed"] = [c for c in s["checks"] if not c["ok"]]
    s["elapsed_s"] = round(time.time() - t0, 2)
    return clean(s)


def report(task: dict, chapter: str | None = None) -> dict:
    """计算说明书 Markdown 文本。chapter 为章标题中的关键字（如“低速轴”“轴承”），不给出时返回全文和章目录。"""
    from gongke_core.report import content, markdown_writer

    text = markdown_writer.render(content.build(_run(task), with_diagrams=False))
    parts = text.split("\n## ")
    chapters = [p.splitlines()[0] for p in parts[1:]]
    if chapter is None:
        return {"chapters": chapters, "markdown": text}
    hits = [p for p in parts[1:] if chapter in p.splitlines()[0]]
    if not hits:
        raise TaskError(f"没有标题含“{chapter}”的章，可选：{'；'.join(chapters)}")
    return {"chapters": chapters, "markdown": "\n\n".join("## " + h for h in hits)}


def _set(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _metrics(s: dict) -> dict:
    gears = {}
    for k, g in s["gears"].items():
        m = g.get("mn", g.get("m"))
        row = {"module": m, "z": [g["z1"], g["z2"]], "sigma_h/allow": round(g["sigma_h"] / g["sigma_h_allow"], 3),
               "sigma_f/allow": round(max(a / b for a, b in zip(g["sigma_f"], g["sigma_f_allow"])), 3)}
        if "d1" in g:
            row["d_mm"] = [round(g["d1"], 2), round(g["d2"], 2)]  # 分度圆直径（锥齿轮为大端）
        if "a" in g:
            row["a_mm"] = round(g["a"], 1)
        gears[k] = row
    return {
        "ok": s["ok"],
        "motor": f"{s['motor']['model']} {s['motor']['power_kw']} kW",
        "total_ratio": round(s["ratios"]["total"], 3),
        "speed_error_pct": round(s["ratios"]["speed_error_pct"], 2),
        "gears": gears,
        "shaft_d_max_mm": [round(max(seg["d"] for seg in sh["segments"]), 1) for sh in s["shafts"]],
        "bearing_life_min_h": round(min(sh["bearing_life_h"] for sh in s["shafts"])),
        "failed": [c["item"] for c in s["checks"] if not c["ok"]],
    }


def explore(task: dict, param: str, values: list) -> dict:
    """多方案对比：把 param（点号路径，如 "ratio_split"、"gears.high.z1"、"scheme"）依次取 values 中的值做设计，
    返回每个方案的主要指标（电动机、模数、齿数、中心距、强度利用率 σ/[σ]、最大轴径、最短轴承寿命、未通过项）。"""
    rows = []
    for v in values:
        t = copy.deepcopy(task)
        _set(t, param, v)
        try:
            rows.append({"value": v, **_metrics(design(t))})
        except Exception as e:  # 某个取值不可行时记录原因，继续比较其他取值
            rows.append({"value": v, "error": str(e)})
    return {"param": param, "results": rows}


def lookup(kind: str, **q) -> dict:
    return clean(_lookup(kind, **q))


def _lookup(kind: str, **q) -> dict:
    """查标准件和材料数据。kind：
    motor（power_kw、sync_rpm：选型；不给 power_kw 时列出该转速全部型号）、
    bearing（bore_mm，type = deep_groove / tapered）、key（shaft_d_mm）、modules（series = 1/2，或 bevel / worm）、
    gear_materials、worm_wheel_materials、form_factors（zv）。"""
    if kind == "motor":
        sync = float(q.get("sync_rpm", 1500))
        if "power_kw" in q:
            m = standards.select_motor(float(q["power_kw"]) * 1e3, sync)
            return {"model": m.model, "power_kw": m.power / 1e3, "speed_rpm": m.speed_rpm, "shaft_d_mm": m.shaft_d * 1e3}
        return {"motors": [{"model": m.model, "power_kw": m.power / 1e3, "speed_rpm": m.speed_rpm}
                           for m in standards.motors() if m.sync_speed_rpm == sync]}
    if kind == "bearing":
        d = float(q["bore_mm"]) * 1e-3
        typ = q.get("type", "deep_groove")
        rows = standards.tapered_with_bore(d) if typ == "tapered" else standards.bearings_with_bore(d)
        return {"bearings": [{"designation": b.designation, "d_mm": b.d * 1e3, "D_mm": b.D * 1e3, "B_mm": b.B * 1e3,
                              "Cr_kN": b.Cr / 1e3, "C0r_kN": b.C0r / 1e3} for b in rows]}
    if kind == "key":
        k = standards.key_size(float(q["shaft_d_mm"]) * 1e-3)
        return {"b_mm": k.b * 1e3, "h_mm": k.h * 1e3, "t1_mm": k.t1 * 1e3, "t2_mm": k.t2 * 1e3,
                "lengths_mm": [round(v * 1e3) for v in standards.key_lengths()]}
    if kind == "modules":
        series = q.get("series", 1)
        if series == "bevel":
            vals = standards.bevel_modules()
        elif series == "worm":
            return {"m_d1_mm": [[m * 1e3, d1 * 1e3] for m, d1 in standards.worm_module_d1()]}
        else:
            vals = standards.standard_modules(int(series))
        return {"modules_mm": [round(v * 1e3, 3) for v in vals]}
    if kind == "gear_materials":
        return {"materials": [{"key": r[0], "name": r[1], "hardness_hb": r[2], "sigma_hlim_mpa": r[3], "sigma_fe_mpa": r[4]}
                              for r in standards.load("textbook/gear_materials.yaml")["materials"]]}
    if kind == "worm_wheel_materials":
        return {"materials": [{"key": k, "name": v[0], "casting": v[1]}
                              for k, v in standards.load("textbook/worm_gearing.yaml")["wheel_materials"].items()]}
    if kind == "form_factors":
        yfa, ysa = standards.form_factors(float(q["zv"]))
        return {"zv": float(q["zv"]), "YFa": round(yfa, 4), "YSa": round(ysa, 4)}
    raise TaskError(f"未知的查询类型 {kind}")


def generate(task: dict, out_dir: str | Path, report_docx: bool = True, drawings: bool = True, step: bool = False,
             full_teeth: bool = False, fem: bool = False) -> dict:
    """生成文件：summary.json、report.md（+ report.docx）、drawings/（DXF、SVG、drawings.pdf）、
    reducer_assembly.step（step=True，需要 build123d，较慢）、fem/（fem=True，需要 CalculiX 和 gmsh）。
    返回生成的文件列表和说明（某项因缺少依赖跳过时写在 notes 里）。"""
    from gongke_core.report import content, markdown_writer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = _run(task)
    (out / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    notes: list[str] = []
    fem_rep = None
    if fem:
        from gongke_core.fem import ccx, shaft_check
        try:
            fem_rep = shaft_check.run(res, out / "fem")
            (out / "fem" / "comparison.md").write_text(shaft_check.to_markdown(fem_rep), encoding="utf-8")
            if fem_rep.gear_note:
                notes.append(f"跳过齿根应力复核：{fem_rep.gear_note}")
        except ccx.CcxNotFound as e:
            notes.append(f"跳过有限元复核：{e}")
    (out / "summary.json").write_text(json.dumps(summary.summarize(res, fem_rep), ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    doc = content.build(res, fem=fem_rep)
    markdown_writer.write(doc, out / "report.md")
    if report_docx:
        try:
            from gongke_core.report import docx_writer
            docx_writer.write(doc, out / "report.docx")
        except ImportError:
            notes.append("未安装 python-docx，跳过 Word 说明书")
    sheets = []
    if drawings:
        try:
            from gongke_core import drawing
            from gongke_core.drawing import render  # noqa: F401  需要 ezdxf
        except ImportError:
            notes.append("未安装 ezdxf，跳过工程图")
        else:
            files = drawing.build_all(res, out / "drawings")
            sheets = [{"name": f.name, "number": f.number, "size": f.size, "dxf": f.dxf.name,
                       "svg": f.svg.name if f.svg else None} for f in files]
            (out / "drawings" / "index.json").write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding="utf-8")
            n = check_drawings(out / "drawings")["total"]
            if n:
                notes.append(f"图纸自查发现 {n} 处文字重叠或压线，详见 check_drawings")
    if step:
        try:
            from gongke_core.geometry import assembly
        except ImportError:
            notes.append("未安装 build123d，跳过三维模型")
        else:
            assembly.export(res, out / "reducer_assembly.step", teeth=full_teeth)
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    return {"out_dir": str(out.resolve()), "ok": res.ok, "drawings": sheets, "files": files, "notes": notes}


def check_drawings(path: str | Path) -> dict:
    """检查 DXF 图纸中文字与文字重叠、图线穿过文字（GB/T 4458.4 要求图线遇尺寸数字断开）。
    path 为单个 DXF 或图纸目录。返回每张图的问题（类型、文字、图纸坐标 mm）和总数。"""
    from gongke_core.drawing import lint

    p = Path(path)
    if not p.exists():
        raise ValueError(f"找不到 {p}")
    results = [lint.check(p)] if p.is_file() else lint.check_dir(p)
    sheets = [{"file": Path(r.file).name, "issues": [i.as_dict() for i in r.issues]} for r in results]
    return {"checked": len(sheets), "total": sum(len(s["issues"]) for s in sheets),
            "sheets": [s for s in sheets if s["issues"]]}
