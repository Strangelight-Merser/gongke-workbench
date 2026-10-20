"""查找并运行 CalculiX 求解器 ccx。

查找顺序：环境变量 GONGKE_CCX；PATH 中的 ccx；FreeCAD 安装目录自带的 ccx（FreeCAD 的 FEM 工作台随安装包提供）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


class CcxNotFound(RuntimeError):
    pass


def _freecad_candidates() -> list[Path]:
    out = []
    if sys.platform.startswith("win"):
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if root:
                out += sorted(Path(root).glob("FreeCAD*/bin/ccx.exe"), reverse=True)
    elif sys.platform == "darwin":
        out += [Path("/Applications/FreeCAD.app/Contents/Resources/bin/ccx")]
    else:
        out += [Path("/usr/lib/freecad/bin/ccx"), Path("/usr/bin/ccx")]
    return out


def find() -> Path:
    env = os.environ.get("GONGKE_CCX")
    if env and Path(env).is_file():
        return Path(env)
    for name in ("ccx", "ccx_2.22", "ccx_2.21"):
        p = shutil.which(name)
        if p:
            return Path(p)
    for p in _freecad_candidates():
        if p.is_file():
            return p
    raise CcxNotFound("没有找到 CalculiX 求解器 ccx：请安装 FreeCAD（自带 ccx）或 calculix-ccx，"
                      "也可以用环境变量 GONGKE_CCX 指定 ccx 的路径。")


MIN_VERSION = (2, 21)  # U1 梁单元在 2.21 修正了横向载荷的错误


def version(exe: Path | None = None) -> tuple[int, int]:
    """ccx 版本号，如 (2, 22)；读不出来时返回 (0, 0)。"""
    try:
        r = subprocess.run([str(exe or find()), "-v"], capture_output=True, text=True, errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return (0, 0)
    m = re.search(r"Version\s+(\d+)\.(\d+)", r.stdout + r.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def check_version(exe: Path | None = None) -> None:
    v = version(exe)
    if v < MIN_VERSION:
        raise CcxNotFound(f"CalculiX 版本 {v[0]}.{v[1]} 过旧，需要 {MIN_VERSION[0]}.{MIN_VERSION[1]} 或更新版本"
                          "（FreeCAD 1.0 自带 2.22）。")


def run(inp: Path, timeout: float = 300) -> Path:
    """运行 ccx：inp 为 *.inp 文件，返回 *.dat 结果文件路径。"""
    exe = find()
    job = inp.with_suffix("")
    env = dict(os.environ, OMP_NUM_THREADS="1")
    r = subprocess.run([str(exe), "-i", job.name], cwd=inp.parent, capture_output=True, text=True, errors="replace",
                       timeout=timeout, env=env)
    dat = job.with_suffix(".dat")
    if r.returncode != 0 or not dat.exists() or "*ERROR" in r.stdout:
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-15:])
        raise RuntimeError(f"ccx 计算失败（返回码 {r.returncode}）：\n{tail}")
    for ext in (".12d", ".cvg", ".sta"):  # 求解过程文件，保留 .inp/.dat/.frd
        job.with_suffix(ext).unlink(missing_ok=True)
    (inp.parent / "spooles.out").unlink(missing_ok=True)
    return dat
