"""面向程序和 AI agent 的接口：输入、输出都是可 JSON 序列化的 dict，单位与任务书一致（mm、N、MPa、kW、r/min）。

MCP 服务器调用本接口；命令行与 FreeCAD 进程入口共享任务书校验和 delivery 导出流程。

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

from gongke_core import design as design_mod
from gongke_core import standards, summary

from gongke_core.task_input import (SCHEMES, GEAR_MATERIALS, WHEEL_MATERIALS,
                                    TaskError, task_schema, validate)


def clean(v, digits: int = 6):
    """把结果中的浮点数保留 digits 位有效数字（去掉 18.000000000000004 这类噪声，也让输出更短）。"""
    if isinstance(v, float):
        return float(f"{v:.{digits}g}")
    if isinstance(v, dict):
        return {k: clean(x, digits) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x, digits) for x in v]
    return v


def example_task(scheme: str = "coupling") -> dict:
    """示例任务书（examples/ 中对应方案的文件内容）。"""
    import yaml

    name = {"coupling": "basic"}.get(scheme, scheme)
    path = Path(__file__).resolve().parents[1] / "examples" / f"conveyor_{name}.yaml"
    if not path.exists():
        raise TaskError(f"没有 {scheme} 方案的示例")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run(task: dict):
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
    required = {"bearing": ("bore_mm", "轴承内径，mm，例如 40"),
                "key": ("shaft_d_mm", "轴径，mm，例如 45"),
                "form_factors": ("zv", "当量齿数，例如 34")}
    if kind in required:
        field, description = required[kind]
        if field not in q:
            raise TaskError(f"缺少参数 {field}（数值，{description}）")
    if kind == "motor":
        sync = float(q.get("sync_rpm", 1500))
        # 列表查询和按功率选型共享同一数据范围检查。
        standards.select_motor(0, sync)
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
    """在新目录中生成产物及 manifest.json；ok 同时要求计算、导出和自动图检通过。"""
    from gongke_core.delivery import generate as deliver
    return deliver(task, out_dir, report_docx, drawings, step, full_teeth, fem)


def check_drawings(path: str | Path) -> dict:
    """检查 DXF 图纸中文字与文字重叠、图线穿过文字（GB/T 4458.4 要求图线遇尺寸数字断开）。
    path 为单个 DXF 或图纸目录。返回每张图的问题（类型、文字、图纸坐标 mm）和总数。"""
    from gongke_core.drawing import lint

    p = Path(path)
    if not p.exists():
        raise ValueError(f"找不到 {p}")
    results = [lint.check(p)] if p.is_file() else lint.check_dir(p)
    if not results:
        raise TaskError(f"未找到可检查的 DXF 图纸：{p}")
    sheets = [{"file": Path(r.file).name, "issues": [i.as_dict() for i in r.issues]} for r in results]
    return {"checked": len(sheets), "total": sum(len(s["issues"]) for s in sheets),
            "sheets": [s for s in sheets if s["issues"]]}
