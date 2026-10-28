"""使用独立安装的工作台，顺序运行真实原生几何与 MCP 会话验收。"""

import importlib.util
import json
import os
from pathlib import Path
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ["GONGKE_NATIVE_OUT"])


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/e2e" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    Gui.activateWorkbench("GongKeWorkbench")
    from freecad.gongke import native_shaft, bridge
    installed = Path(App.getUserAppDataDir()) / "Mod/GongKeWorkbench"
    assert Path(native_shaft.__file__).is_relative_to(installed)
    assert Path(bridge.__file__).is_relative_to(installed)
    Gui.runCommand("GongKe_NativeShaft")
    load("course_shaft_smoke").run(OUT / "geometry", OUT / "course_snapshot.json")
    teaching = load("native_session_flow").start(OUT / "teaching", os.environ["GONGKE_EXTERNAL_PYTHON"])
    course = None
    timer = QtCore.QTimer()

    def advance():
        global course
        if not teaching.done:
            return
        if not (OUT / "teaching/native_session.json").exists():
            timer.stop()
            return
        if course is None:
            course = load("course_session_flow").start(OUT / "course", os.environ["GONGKE_EXTERNAL_PYTHON"])
        elif course.done:
            timer.stop()
            if (OUT / "course/course_session.json").exists():
                (OUT / "acceptance.json").write_text(json.dumps({
                    "ok": True, "installed_module": native_shaft.__file__, "freecad_version": App.Version(),
                    "geometry": str(OUT / "geometry/course_shaft_smoke.json"),
                    "teaching": str(OUT / "teaching/native_session.json"),
                    "course": str(OUT / "course/course_session.json")}, ensure_ascii=False, indent=2))

    timer.timeout.connect(advance)
    timer.start(100)
except Exception:
    (OUT / "macro_error.txt").write_text(traceback.format_exc())
    App.Console.PrintError(traceback.format_exc())
