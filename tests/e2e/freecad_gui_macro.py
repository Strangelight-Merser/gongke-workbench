"""FreeCAD 界面端到端测试宏：加载工作台 → 打开设计面板 → 运行计算和建模 → 检查导入的零件。

用法（需要 FreeCAD 1.0+ 与 Xvfb，见 tests/e2e/run_freecad_e2e.sh）：
    GONGKE_PYTHON=/path/to/python xvfb-run -a freecad tests/e2e/freecad_gui_macro.py
结果写入 $GONGKE_E2E_OUT（默认 /tmp/gongke_e2e），成功时生成 ok 文件。
"""
import os, sys, traceback
from pathlib import Path

OUT = Path(os.environ.get("GONGKE_E2E_OUT", "/tmp/gongke_e2e"))
OUT.mkdir(parents=True, exist_ok=True)
import FreeCAD as App, FreeCADGui as Gui
log = open(OUT / "log.txt", "w", encoding="utf-8")
def P(*a):
    print(*a, file=log, flush=True)
try:
    P("workbenches", [w for w in Gui.listWorkbenches() if "GongKe" in w])
    Gui.activateWorkbench("GongKeWorkbench")
    P("active", Gui.activeWorkbench().MenuText)
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/GongKe").SetString("PythonExe", os.environ.get("GONGKE_PYTHON", sys.executable))
    App.newDocument("减速器")
    Gui.runCommand("GongKe_ReducerDesign")
    from freecad.gongke.panels import ReducerTaskPanel
    dlg = Gui.Control.activeDialog()
    P("dialog open", dlg)
    p = ReducerTaskPanel()
    p.run()
    ok = p.proc.waitForFinished(600000)
    P("finished", ok, p.proc.exitCode())
    from PySide import QtGui
    QtGui.QApplication.processEvents()
    doc = App.ActiveDocument
    P("objects", len(doc.Objects), "solids", sum(1 for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Solids))
    P("result text", p.result.toPlainText()[:600])
    n_solids = sum(1 for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Solids)
    assert p.proc.exitCode() == 0 and n_solids >= 15, "装配体导入不完整"
    assert "GK-00" in p.result.toPlainText(), "工程图未生成"
    v = Gui.activeDocument().activeView()
    v.viewIsometric(); Gui.SendMsgToActiveView("ViewFit")
    QtGui.QApplication.processEvents()
    v.saveImage(str(OUT / "view.png"), 1400, 1000, "White")
    (OUT / "ok").write_text("ok")
    P("ok")
except Exception:
    P(traceback.format_exc())
finally:
    log.close()
    os._exit(0)
