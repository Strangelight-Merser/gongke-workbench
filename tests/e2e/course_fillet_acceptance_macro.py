"""独立安装副本：真实 stdio MCP 圆角闭环，并留下可继续编辑的工程。"""

import importlib.util
import os
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[2]
Gui.activateWorkbench("GongKeWorkbench")
from freecad.gongke import native_shaft, bridge
installed = Path(App.getUserAppDataDir()) / "Mod/GongKeWorkbench"
assert Path(native_shaft.__file__).is_relative_to(installed)
assert Path(bridge.__file__).is_relative_to(installed)
Gui.runCommand("GongKe_NativeShaft")
spec = importlib.util.spec_from_file_location("course_fillet_flow", ROOT / "tests/e2e/course_fillet_session_flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
session = flow.start(os.environ["GONGKE_NATIVE_OUT"], os.environ["GONGKE_EXTERNAL_PYTHON"])
