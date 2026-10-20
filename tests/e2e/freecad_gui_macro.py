"""FreeCAD 界面端到端测试宏：加载工作台 → 打开设计面板 → 运行计算和建模 → 检查导入的零件。

用法（需要 FreeCAD 1.0+ 与 Xvfb，见 tests/e2e/run_freecad_e2e.sh）：
    xvfb-run -a freecad tests/e2e/freecad_gui_macro.py
默认用 FreeCAD 自带的 Python；GONGKE_PYTHON 可指定其他解释器。GONGKE_E2E_INSTALL=1 时先用面板上的按钮安装依赖包。
结果写入 $GONGKE_E2E_OUT（默认 /tmp/gongke_e2e），成功时生成 ok 文件。
"""
import os, traceback
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
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/GongKe").SetString("PythonExe", os.environ.get("GONGKE_PYTHON", ""))
    App.newDocument("减速器")
    Gui.runCommand("GongKe_ReducerDesign")
    from freecad.gongke.panels import ReducerTaskPanel
    dlg = Gui.Control.activeDialog()
    P("dialog open", dlg)
    p = ReducerTaskPanel()
    if os.environ.get("GONGKE_E2E_INSTALL"):
        p.install()
        ok = p.proc.waitForFinished(1800000)
        P("install", ok, p.proc.exitCode(), p.result.toPlainText()[-300:])
        assert ok and p.proc.exitCode() == 0, "依赖包安装失败"
    scheme = os.environ.get("GONGKE_E2E_SCHEME")
    if scheme in ("vbelt", "bevel", "worm", "single"):
        p.scheme.setCurrentIndex(("coupling", "vbelt", "bevel", "worm", "single").index(scheme))
    p.with_fem.setChecked(True)  # 用 FreeCAD 自带的 ccx
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
    assert "有限元复核" in p.result.toPlainText(), "未找到 FreeCAD 自带的 ccx 或有限元复核失败"
    if scheme != "worm":
        assert list((p.out_dir / "fem").glob("tooth_zv*.inp")), "未找到 FreeCAD 自带的 gmsh，齿根应力未复核"
    if os.environ.get("GONGKE_E2E_SCHEME") in ("vbelt", "single"):
        assert "GK-03-01" in p.result.toPlainText(), "大带轮零件图未生成"
    if os.environ.get("GONGKE_E2E_SCHEME") == "bevel":
        assert "锥齿轮" in p.result.toPlainText(), "锥齿轮零件图未生成"
    if os.environ.get("GONGKE_E2E_SCHEME") == "worm":
        assert "蜗轮零件图" in p.result.toPlainText(), "蜗轮零件图未生成"
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
