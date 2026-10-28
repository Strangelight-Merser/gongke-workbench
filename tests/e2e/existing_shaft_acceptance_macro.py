"""从独立安装副本启动已有学生轴的真实 GUI/MCP 接管验收。"""

import importlib.util
import os
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[2]
Gui.activateWorkbench("GongKeWorkbench")
from freecad.gongke import bridge, native_shaft

installed = Path(App.getUserAppDataDir()) / "Mod/GongKeWorkbench"
assert Path(native_shaft.__file__).is_relative_to(installed)
assert Path(bridge.__file__).is_relative_to(installed)
os.environ.setdefault("GONGKE_MCP_ROOT", str(installed))
assert Path(os.environ["GONGKE_MCP_ROOT"]).resolve() == installed.resolve(), "MCP 必须使用独立安装副本"
Gui.runCommand("GongKe_NativeShaft")
spec = importlib.util.spec_from_file_location("existing_shaft_flow", ROOT / "tests/e2e/existing_shaft_session_flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
session = flow.start(os.environ["GONGKE_NATIVE_OUT"], os.environ["GONGKE_EXTERNAL_PYTHON"])
