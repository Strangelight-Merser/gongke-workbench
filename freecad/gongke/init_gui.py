"""FreeCAD 加载工作台时执行。"""

import os

import FreeCADGui as Gui

from freecad.gongke import ICONPATH


class GongKeWorkbench(Gui.Workbench):
    MenuText = "工科工作台"
    ToolTip = "机械类课程设计：减速器设计计算、三维建模、计算说明书"
    Icon = os.path.join(ICONPATH, "gongke.svg")

    def Initialize(self):
        from freecad.gongke import commands

        commands.register()
        self.appendToolbar("工科", commands.TOOLBAR)
        self.appendMenu("工科", commands.MENU)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(GongKeWorkbench())
