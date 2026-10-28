"""启动真实 FreeCAD 与本机命令桥，供外部 MCP 客户端验证原生操作。"""

import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import freecad
if str(ROOT / "freecad") not in freecad.__path__:
    freecad.__path__.append(str(ROOT / "freecad"))

import FreeCAD as App
import FreeCADGui as Gui

OUT = Path(os.environ.get("GONGKE_NATIVE_OUT", ROOT / "out" / "native-agent"))
OUT.mkdir(parents=True, exist_ok=True)

try:
    from freecad.gongke import init_gui
    Gui.activateWorkbench("GongKeWorkbench")
    Gui.runCommand("GongKe_NativeShaft")
    from freecad.gongke.bridge import start
    bridge = start()
    context = bridge.state.get_project_context()
    (OUT / "ready.json").write_text(json.dumps({"context": context, "version": App.Version(), "user_data": App.getUserAppDataDir(),
                                               "endpoint": str(bridge.endpoint)}, ensure_ascii=False, indent=2))
    if os.environ.get("GONGKE_NATIVE_SMOKE"):
        import importlib.util
        spec = importlib.util.spec_from_file_location("native_smoke", ROOT / "tests" / "e2e" / "native_shaft_smoke.py")
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        smoke.run(OUT)
        App.setActiveDocument(context["document"])
    if os.environ.get("GONGKE_NATIVE_SESSION"):
        import importlib.util
        from PySide import QtCore
        spec = importlib.util.spec_from_file_location("native_session", ROOT / "tests" / "e2e" / "native_session_flow.py")
        session = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(session)
        def begin_session():
            App.setActiveDocument(context["document"])
            session.start(OUT, os.environ["GONGKE_EXTERNAL_PYTHON"])
        QtCore.QTimer.singleShot(0, begin_session)
except Exception:
    (OUT / "error.txt").write_text(traceback.format_exc())
    App.Console.PrintError(traceback.format_exc())
