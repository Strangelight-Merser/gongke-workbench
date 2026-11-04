"""WorkBuddy 人工验收的进程范围：桌面退出、Ctrl-C 或超时均回收本轮 CAD/Electron。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.acceptance_host import start_host
from scripts.owned_processes import OwnedProcesses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="全新运行目录")
    parser.add_argument("--freecad", default=os.environ.get("GONGKE_FREECAD_EXE", "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"))
    parser.add_argument("--timeout", type=float, default=7200, help="最长验收秒数")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    owned = OwnedProcesses()
    try:
        endpoint = start_host(owned, output / "host", args.freecad)
        executable = subprocess.check_output(["node", "-p", "require('electron')"], cwd=ROOT / "desktop", text=True).strip()
        env = {**os.environ, "GONGKE_FREECAD_SESSION": str(endpoint), "GONGKE_DESKTOP_USER_DATA": str(output / "desktop"), "GONGKE_PYTHON": sys.executable}
        env.pop("ELECTRON_RUN_AS_NODE", None)
        with (output / "electron.log").open("w") as log:
            app = owned.spawn([executable, str(ROOT / "desktop")], cwd=ROOT, env=env, stdout=log, stderr=log)
        (output / "processes.json").write_text(json.dumps({"freecad_pid": owned.children[0].pid, "electron_pid": app.pid}))
        print(f"本轮桌面状态目录：{output / 'desktop/state'}；退出桌面即回收本轮宿主。", flush=True)
        return app.wait(timeout=args.timeout)
    finally:
        owned.close()


if __name__ == "__main__":
    raise SystemExit(main())
