"""复制独立工作台到指定 FreeCAD Mod 目录，不链接源码、不修改用户配置。

用法：python tools/install_freecad_workbench.py --mod-dir /绝对路径/FreeCAD/Mod
目标 GongKeWorkbench 必须不存在；更新时先由用户保留原安装，不覆盖已有数据。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def install(mod_dir: Path) -> Path:
    source = Path(__file__).resolve().parents[1]
    mod_dir = mod_dir.expanduser()
    if not mod_dir.is_absolute():
        raise ValueError("--mod-dir 必须是 FreeCAD 用户 Mod 目录的绝对路径")
    target = mod_dir / "GongKeWorkbench"
    # 不覆盖已有工作台，安装目录中的用户工程也不会被自动清理。
    target.mkdir(parents=True, exist_ok=False)
    for name in ("gongke_core", "freecad", "data", "examples"):
        shutil.copytree(source / name, target / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    for name in ("package.xml", "LICENSE", "pyproject.toml", "README.md"):
        shutil.copy2(source / name, target / name)
    (target / "docs").mkdir()
    for name in ("agent-api.md", "assistant-workflow.md", "architecture.md", "drawing-checklist.md"):
        shutil.copy2(source / "docs" / name, target / "docs" / name)
    shutil.copytree(source / "docs/images", target / "docs/images",
                    ignore=shutil.ignore_patterns(".DS_Store"))
    # FreeCAD 将 Mod 子目录加入 sys.path，再发现 freecad.* 命名空间中的 init_gui。
    # 沿用该原生机制，不增加重复注册工作台的 InitGui.py。
    return target


def main():
    parser = argparse.ArgumentParser(description="安装独立的工科工作台副本")
    parser.add_argument("--mod-dir", type=Path, required=True, help="FreeCAD 用户 Mod 目录的绝对路径")
    args = parser.parse_args()
    target = install(args.mod_dir)
    print(f"工作台已复制到：{target}")
    print("重新启动 FreeCAD 后选择工科工作台。原生轴编辑无需安装 build123d。")
    print(f"外部 MCP 进程可将工作目录设为：{target}")


if __name__ == "__main__":
    main()
