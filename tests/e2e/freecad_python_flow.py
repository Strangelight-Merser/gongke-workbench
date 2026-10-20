"""不开图形界面，按工作台面板的同一套步骤走一遍：用指定的 Python（通常是 FreeCAD 自带的）
把依赖包装到用户数据目录，再在独立进程中完成设计、出图、建模和有限元复核。

用于没有显示器的 CI（如 Windows）：用户目录含中文、输出目录含中文和空格，检查路径和编码问题。

    python tests/e2e/freecad_python_flow.py <python> <工作目录> [ccx]
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gongke_runner", REPO / "freecad" / "gongke" / "runner.py")
runner = importlib.util.module_from_spec(spec)
sys.modules["gongke_runner"] = runner  # dataclass 需要在 sys.modules 中找到模块
spec.loader.exec_module(runner)


def main(python: str, work: Path, ccx: str = "") -> int:
    user_data = work / "用户 张三" / "FreeCAD"  # 模拟中文用户名下的 FreeCAD 用户数据目录
    target = runner.package_dir(str(user_data), python)
    target.mkdir(parents=True, exist_ok=True)
    prog, args = runner.pip_command(python, target)
    subprocess.run([prog, *args], check=True)
    env = runner.environment(ccx, target)
    prog, args = runner.check_command(python)
    subprocess.run([prog, *args], check=True, env=env)
    for scheme in runner.SCHEMES:
        out = work / "课程设计 输出" / scheme
        task = runner.write_task(runner.FormValues(scheme=scheme, belt_ratio=None if scheme == "single" else 2.5), out)
        prog, args, cwd = runner.command(python, task, out, step=True, drawings=True, fem=bool(ccx))
        r = subprocess.run([prog, *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        print(scheme, r.returncode, r.stdout.strip().splitlines()[-1:] if r.stdout else "", r.stderr[-2000:])
        res = runner.read_outputs(out)
        assert r.returncode in (0, 2), f"{scheme} 运行失败"
        assert "reducer_assembly.step" in res["files"] and "drawings/drawings.pdf" in res["files"], scheme
        if ccx:
            assert "fem/comparison.md" in res["files"], f"{scheme} 有限元复核未完成"
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else ""))
