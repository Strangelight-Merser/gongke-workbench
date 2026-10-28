"""在独立进程中运行 gongke_core（不 import FreeCAD，可单独测试）。

FreeCAD 内置的 OCCT 与 build123d 依赖的 OCP 可能冲突，所以几何生成放在外部 Python 进程里：
工作台把任务书写成 JSON（YAML 的子集）文件，调用 ``python -m gongke_core design``，再读取输出。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# gongke_core 运行所需的第三方包。由工作台用所选 Python 的 pip 安装到单独的目录（见 package_dir），
# 只加进子进程的 PYTHONPATH：不装进 FreeCAD 的 AdditionalPythonPackages，以免 numpy 等包的其他版本
# 进入 FreeCAD 自身进程。
REQUIREMENTS = ["pyyaml>=6", "python-docx>=1.1", "pillow>=10.1", "ezdxf>=1.3", "build123d>=0.9"]
CHECK_IMPORTS = "import yaml, docx, PIL, ezdxf, build123d"


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
    scheme: str = "coupling"  # SCHEMES 之一
    belt_ratio: float | None = 2.5  # None：按方案自动确定（single 方案使齿轮传动比约为 4）


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
        "gears": {"worm": {"grade": v.grade}} if v.scheme == "worm" else
                 {"high": dict(gear)} if v.scheme == "single" else {"high": dict(gear), "low": dict(gear)},
        "scheme": v.scheme,
        "vbelt": {"ratio": v.belt_ratio} if v.belt_ratio else {},
    }


def find_python(preferred: str = "", freecad_python: str = "") -> str:
    """优先使用设置中指定的解释器，其次 FreeCAD 自带的 Python，再次 PATH 中的 python3 / python。"""
    for p in (preferred, freecad_python):
        if p and Path(p).exists():
            return p
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            return p
    raise FileNotFoundError("找不到 Python 解释器，请在工科工作台设置中指定")


def package_dir(user_data_dir: str, python: str) -> Path:
    """为某个 Python 解释器安装依赖包的目录（不同解释器分开，避免二进制包版本不匹配）。"""
    tag = hashlib.sha1(str(Path(python).resolve()).encode()).hexdigest()[:8]
    return Path(user_data_dir) / "GongKe" / f"pylibs-{tag}"


def pip_command(python: str, target: Path) -> tuple[str, list[str]]:
    """安装依赖包的命令（pip install --target）。"""
    return python, ["-m", "pip", "install", "--upgrade", "--target", str(target), *REQUIREMENTS]


def check_command(python: str) -> tuple[str, list[str]]:
    """检查依赖包是否都能导入的命令。"""
    return python, ["-c", CHECK_IMPORTS]


def missing_module(stderr: str) -> str:
    """从子进程的错误输出中找出缺少的模块名，没有则返回空串。"""
    for line in stderr.splitlines():
        if "No module named" in line:
            return line.split("No module named", 1)[1].strip().strip("'\"")
    return ""


def write_task(v: FormValues, out_dir: Path) -> Path:
    # 工作台重复运行时保留整次旧产物，不在原目录里覆盖报告或混用旧模型。
    # 仅归档本程序有 manifest 标识的运行目录；其他非空目录仍由导出器拒绝。
    if (out_dir / "manifest.json").is_file():
        from uuid import uuid4
        archive = out_dir.with_name(out_dir.name + "-" + uuid4().hex[:12])
        out_dir.rename(archive)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "task.yaml"
    path.write_text(json.dumps(task_dict(v), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def command(python: str, task: Path, out_dir: Path, step: bool = True, full_teeth: bool = False,
            drawings: bool = True, fem: bool = False) -> tuple[str, list[str], str]:
    """返回 (程序, 参数, 工作目录)，供 QProcess 或 subprocess 使用。"""
    args = ["-m", "gongke_core", "design", str(task), "-o", str(out_dir)]
    if not step:
        args.append("--no-step")
    if full_teeth:
        args.append("--full-teeth")
    if not drawings:
        args.append("--no-drawings")
    if fem:
        args.append("--fem")
    return python, args, str(REPO_ROOT)


def freecad_ccx(home: str, user_path: str = "", use_standard: bool = True) -> str:
    """FreeCAD 有限元工作台使用的 ccx：首选项里指定的路径，否则安装目录 bin/ 下自带的。找不到返回空串。"""
    if not use_standard and user_path and Path(user_path).is_file():
        return user_path
    for name in ("ccx.exe", "ccx"):
        p = Path(home) / "bin" / name
        if p.is_file():
            return str(p)
    return ""


def environment(ccx: str = "", packages: Path | None = None) -> dict:
    env = dict(os.environ)
    if ccx:
        env["GONGKE_CCX"] = ccx
    paths = [str(REPO_ROOT)] + ([str(packages)] if packages and packages.is_dir() else [])
    env["PYTHONPATH"] = os.pathsep.join(paths + [env.get("PYTHONPATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def gear_line(g: dict) -> str:
    """面板上一级齿轮的简要参数。"""
    if g.get("type") == "worm":
        return (f"m={g['m']:.2f} z={g['z1']}/{g['z2']} a={g['a']:.0f} mm，η={g['eta']:.2f}，"
                f"油温 {g['oil_temp']:.0f} ℃")
    if g.get("type") == "bevel":
        return f"直齿锥齿轮 m={g['m']:.2f} z={g['z1']}/{g['z2']} R={g['R']:.0f} mm"
    return f"mn={g['mn']:.2f} z={g['z1']}/{g['z2']} a={g['a']:.0f} mm"


def gears_html(gears: dict) -> str:
    """面板上的传动件一行。"""
    if "worm" in gears:
        return f"<b>蜗杆传动</b> {gear_line(gears['worm'])}"
    if "low" not in gears:
        return f"<b>齿轮传动</b> {gear_line(gears['high'])}"
    return f"<b>高速级</b> {gear_line(gears['high'])}；<b>低速级</b> {gear_line(gears['low'])}"


SCHEMES = ("coupling", "vbelt", "bevel", "worm", "single")


def read_outputs(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] in ("running", "failed"):
        raise RuntimeError("本次运行未完成：" + "；".join(manifest["notes"]))
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    delivered = set(manifest["files"])
    files = {name: out_dir / name for name in ("reducer_assembly.step", "report.docx", "report.md", "drawings/drawings.pdf",
                                                "fem/comparison.md") if name in delivered}
    drawings = []
    for row in manifest["drawings"]:
        d = dict(row)
        d["dxf"] = out_dir / "drawings" / d["dxf"]
        d["svg"] = out_dir / "drawings" / d["svg"] if d.get("svg") else None
        drawings.append(d)
    return {"summary": summary, "files": files, "drawings": drawings, "delivery": manifest}
