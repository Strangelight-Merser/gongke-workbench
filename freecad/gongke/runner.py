"""在独立进程中运行 gongke_core（不 import FreeCAD，可单独测试）。

FreeCAD 内置的 OCCT 与 build123d 依赖的 OCP 可能冲突，所以几何生成放在外部 Python 进程里：
工作台把任务书写成 JSON（YAML 的子集）文件，调用 ``python -m gongke_core design``，再读取输出。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FormValues:
    belt_pull_N: float = 2500
    belt_speed_m_s: float = 1.4
    drum_diameter_mm: float = 400
    years: float = 10
    shifts: int = 2
    days_per_year: int = 300
    bearing_life_years: float = 3
    sync_speed_rpm: int = 1500
    ratio_split: float = 1.3
    pinion_material: str = "40Cr_QT"
    gear_material: str = "45_QT"
    grade: int = 8
    title: str = "带式输送机传动装置设计"


def task_dict(v: FormValues) -> dict:
    gear = {"material1": v.pinion_material, "material2": v.gear_material, "grade": v.grade}
    return {
        "title": v.title,
        "conveyor": {"belt_pull_N": v.belt_pull_N, "belt_speed_m_s": v.belt_speed_m_s,
                     "drum_diameter_mm": v.drum_diameter_mm},
        "life": {"years": v.years, "days_per_year": v.days_per_year, "shifts": v.shifts},
        "bearing_life_years": v.bearing_life_years,
        "motor_sync_speed_rpm": v.sync_speed_rpm,
        "ratio_split": v.ratio_split,
        "gears": {"high": dict(gear), "low": dict(gear)},
    }


def find_python(preferred: str = "") -> str:
    """优先使用设置中指定的解释器，其次 PATH 中的 python3 / python。"""
    if preferred and Path(preferred).exists():
        return preferred
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            return p
    raise FileNotFoundError("找不到 Python 解释器，请在工科工作台设置中指定（需安装 build123d、pyyaml、python-docx）")


def write_task(v: FormValues, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "task.yaml"
    path.write_text(json.dumps(task_dict(v), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def command(python: str, task: Path, out_dir: Path, step: bool = True, full_teeth: bool = False,
            drawings: bool = True) -> tuple[str, list[str], str]:
    """返回 (程序, 参数, 工作目录)，供 QProcess 或 subprocess 使用。"""
    args = ["-m", "gongke_core", "design", str(task), "-o", str(out_dir)]
    if not step:
        args.append("--no-step")
    if full_teeth:
        args.append("--full-teeth")
    if not drawings:
        args.append("--no-drawings")
    return python, args, str(REPO_ROOT)


def environment() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def read_outputs(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    files = {name: out_dir / name for name in ("reducer_assembly.step", "report.docx", "report.md")}
    index = out_dir / "drawings" / "index.json"
    drawings = []
    if index.exists():
        for d in json.loads(index.read_text(encoding="utf-8")):
            d["dxf"] = out_dir / "drawings" / d["dxf"]
            d["svg"] = out_dir / "drawings" / d["svg"] if d.get("svg") else None
            drawings.append(d)
    return {"summary": summary, "files": {k: v for k, v in files.items() if v.exists()}, "drawings": drawings}
