"""工作台命令：减速器设计向导、设置。"""

import os

import FreeCAD as App
import FreeCADGui as Gui

from freecad.gongke import ICONPATH

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/GongKe"


def params():
    return App.ParamGet(PARAM_PATH)


class ReducerDesignCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "gongke.svg"),
            "MenuText": "带式输送机传动装置设计",
            "ToolTip": "输入带式输送机参数，完成设计计算，生成三维装配体和计算说明书",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from freecad.gongke.panels import ReducerTaskPanel

        Gui.Control.showDialog(ReducerTaskPanel())


class SettingsCommand:
    def GetResources(self):
        return {"MenuText": "设置 Python 解释器…", "ToolTip": "指定运行 gongke_core 的 Python（需安装 build123d 等依赖）"}

    def IsActive(self):
        return True

    def Activated(self):
        from PySide import QtGui

        cur = params().GetString("PythonExe", "")
        path, _ = QtGui.QFileDialog.getOpenFileName(None, "选择 Python 解释器", cur or os.path.expanduser("~"))
        if path:
            params().SetString("PythonExe", path)
            App.Console.PrintMessage(f"工科工作台：Python 解释器设为 {path}\n")


TOOLBAR = ["GongKe_ReducerDesign"]
MENU = ["GongKe_ReducerDesign", "GongKe_Settings"]


def register():
    Gui.addCommand("GongKe_ReducerDesign", ReducerDesignCommand())
    Gui.addCommand("GongKe_Settings", SettingsCommand())
