"""在已安装工作台中验证加载、包资源与原生工程，不把源码目录加入路径。"""

import json
from pathlib import Path
import traceback

import FreeCAD as App
import FreeCADGui as Gui

OUT = Path.home() / "Documents" / "gongke-workbench" / "out" / "installed-native"
OUT.mkdir(parents=True, exist_ok=True)
try:
    assert "GongKeWorkbench" in Gui.listWorkbenches(), "独立安装未被 FreeCAD 发现"
    Gui.activateWorkbench("GongKeWorkbench")
    from freecad.gongke import native_shaft, bridge
    import gongke_core
    installed = Path(App.getUserAppDataDir()) / "Mod" / "GongKeWorkbench"
    assert Path(native_shaft.__file__).is_relative_to(installed)
    assert Path(gongke_core.__file__).is_relative_to(installed)
    Gui.runCommand("GongKe_NativeShaft")
    doc = App.ActiveDocument
    body = next(obj for obj in doc.Objects if hasattr(obj, "GkEntityId"))
    assert native_shaft.supported(body)
    doc.saveAs(str(OUT / "installed_shaft.FCStd"))
    result = {"ok": True, "installed_path": str(installed), "module_path": native_shaft.__file__,
              "context": bridge.start().state.get_project_context(), "version": App.Version()}
    (OUT / "installation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
except Exception:
    (OUT / "error.txt").write_text(traceback.format_exc())
    App.Console.PrintError(traceback.format_exc())
