"""减速器设计任务面板。计算和建模在独立进程中进行，界面不会卡住。"""

import tempfile
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.gongke import runner
from freecad.gongke.commands import params

MATERIALS = [("40Cr_QT", "40Cr 调质 280HBW"), ("45_QT", "45 钢 调质 240HBW"), ("42CrMo_QT", "42CrMo 调质 300HBW"),
             ("35SiMn_QT", "35SiMn 调质 260HBW"), ("45_N", "45 钢 正火 200HBW")]


class ReducerTaskPanel:
    def __init__(self):
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("带式输送机传动装置设计")
        lay = QtGui.QVBoxLayout(self.form)

        box = QtGui.QGroupBox("设计任务（带式输送机）")
        fl = QtGui.QFormLayout(box)
        self.pull = self._spin(100, 50000, 2500, 0, " N")
        self.speed = self._spin(0.1, 5, 1.4, 2, " m/s")
        self.drum = self._spin(100, 1500, 400, 0, " mm")
        self.years = self._spin(1, 30, 10, 0, " 年")
        self.shifts = QtGui.QComboBox()
        self.shifts.addItems(["单班制", "两班制", "三班制"])
        self.shifts.setCurrentIndex(1)
        self.sync = QtGui.QComboBox()
        self.sync.addItems(["1500 r/min（4 极）", "1000 r/min（6 极）"])
        self.scheme = QtGui.QComboBox()
        self.scheme.addItems(["电动机 → 联轴器 → 展开式二级圆柱齿轮减速器", "电动机 → V 带 → 展开式二级圆柱齿轮减速器",
                              "电动机 → 联轴器 → 圆锥-圆柱齿轮减速器", "电动机 → 联轴器 → 单级蜗杆减速器",
                              "电动机 → V 带 → 一级圆柱齿轮减速器"])
        self.belt_ratio = self._spin(1.4, 4, 2.5, 1, "")
        self.belt_ratio.setSpecialValueText("自动")  # 最小值 1.4 显示为“自动”
        self.belt_ratio.setEnabled(False)
        self.scheme.currentIndexChanged.connect(self._scheme_changed)
        fl.addRow("传动方案", self.scheme)
        fl.addRow("V 带传动比", self.belt_ratio)
        fl.addRow("输送带拉力 F", self.pull)
        fl.addRow("输送带速度 v", self.speed)
        fl.addRow("卷筒直径 D", self.drum)
        fl.addRow("使用年限", self.years)
        fl.addRow("工作制度", self.shifts)
        fl.addRow("电动机同步转速", self.sync)
        lay.addWidget(box)

        box2 = QtGui.QGroupBox("齿轮")
        fl2 = QtGui.QFormLayout(box2)
        self.mat1 = QtGui.QComboBox()
        self.mat2 = QtGui.QComboBox()
        for key, label in MATERIALS:
            self.mat1.addItem(label, key)
            self.mat2.addItem(label, key)
        self.mat2.setCurrentIndex(1)
        self.grade = QtGui.QComboBox()
        self.grade.addItems(["7", "8", "9"])
        self.grade.setCurrentIndex(1)
        fl2.addRow("小齿轮材料", self.mat1)
        fl2.addRow("大齿轮材料", self.mat2)
        fl2.addRow("精度等级", self.grade)
        lay.addWidget(box2)
        self.gear_box = box2

        self.with_model = QtGui.QCheckBox("生成三维装配体并导入当前文档")
        self.with_model.setChecked(True)
        lay.addWidget(self.with_model)
        self.full_teeth = QtGui.QCheckBox("齿轮建出完整齿形（模型大、生成慢）")
        lay.addWidget(self.full_teeth)
        self.with_drawings = QtGui.QCheckBox("生成二维工程图（装配图和零件图，DXF）")
        self.with_drawings.setChecked(True)
        lay.addWidget(self.with_drawings)
        self.with_fem = QtGui.QCheckBox("用 CalculiX 有限元复核轴的刚度（FreeCAD 自带求解器）")
        lay.addWidget(self.with_fem)
        self.run_btn = QtGui.QPushButton("开始设计")
        self.run_btn.clicked.connect(self.run)
        lay.addWidget(self.run_btn)
        self.install_btn = QtGui.QPushButton("安装所需 Python 包（首次使用，需联网，安装后约 1 GB）")
        self.install_btn.clicked.connect(self.install)
        self.install_btn.setVisible(False)
        lay.addWidget(self.install_btn)

        self.result = QtGui.QTextBrowser()
        self.result.setOpenExternalLinks(True)
        self.result.setMinimumHeight(260)
        lay.addWidget(self.result)
        self.proc = None
        self.out_dir = None

    def _scheme_changed(self, i):
        scheme = runner.SCHEMES[i]
        self.belt_ratio.setEnabled(scheme in ("vbelt", "single"))
        # 一级减速器默认自动分配 V 带传动比（使齿轮传动比约为 4）
        self.belt_ratio.setValue(self.belt_ratio.minimum() if scheme == "single" else 2.5)
        # 蜗杆传动的材料按默认（45 钢淬火蜗杆、铸锡青铜蜗轮），齿轮材料选项不适用
        self.gear_box.setEnabled(runner.SCHEMES[i] != "worm")

    @staticmethod
    def _spin(lo, hi, val, dec, suffix):
        s = QtGui.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setValue(val)
        s.setSuffix(suffix)
        return s

    def values(self) -> runner.FormValues:
        return runner.FormValues(
            belt_pull_N=self.pull.value(), belt_speed_m_s=self.speed.value(), drum_diameter_mm=self.drum.value(),
            years=self.years.value(), shifts=self.shifts.currentIndex() + 1,
            sync_speed_rpm=1500 if self.sync.currentIndex() == 0 else 1000,
            pinion_material=self.mat1.currentData(), gear_material=self.mat2.currentData(),
            grade=int(self.grade.currentText()),
            scheme=runner.SCHEMES[self.scheme.currentIndex()],
            belt_ratio=None if self.belt_ratio.value() <= self.belt_ratio.minimum() else self.belt_ratio.value(),
        )

    @staticmethod
    def _freecad_python() -> str:
        try:
            from freecad.utils import get_python_exe

            return get_python_exe()
        except ImportError:
            home = Path(App.getHomePath()) / "bin"
            return next((str(home / n) for n in ("python3", "python", "python.exe") if (home / n).exists()), "")

    def _python(self) -> str:
        return runner.find_python(params().GetString("PythonExe", ""), self._freecad_python())

    def _env(self, python: str) -> "QtCore.QProcessEnvironment":
        env = QtCore.QProcessEnvironment.systemEnvironment()
        for k, v in runner.environment(self._ccx(), runner.package_dir(App.getUserAppDataDir(), python)).items():
            env.insert(k, v)
        return env

    def install(self):
        """用所选 Python 的 pip 把依赖包装到工作台自己的目录。"""
        try:
            python = self._python()
        except FileNotFoundError as e:
            self.result.setPlainText(str(e))
            return
        target = runner.package_dir(App.getUserAppDataDir(), python)
        target.mkdir(parents=True, exist_ok=True)
        prog, args = runner.pip_command(python, target)
        self.proc = QtCore.QProcess()
        self.proc.setProcessEnvironment(self._env(python))
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._install_output)
        self.proc.finished.connect(self._install_done)
        self.run_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.result.setPlainText(f"正在安装到 {target}（使用 {python}）…\n")
        self.proc.start(prog, args)

    def _install_output(self):
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.result.moveCursor(QtGui.QTextCursor.End)
        self.result.insertPlainText(text)
        self.result.moveCursor(QtGui.QTextCursor.End)

    def _install_done(self, code, _status=None):
        self.run_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        if code == 0:
            self.install_btn.setVisible(False)
            self.result.append("\n安装完成，可以点“开始设计”了。")
        else:
            self.result.append(f"\n安装失败（退出码 {code}），请检查网络，或在设置中改用已装好依赖的 Python。")

    def run(self):
        try:
            python = self._python()
        except FileNotFoundError as e:
            self.result.setPlainText(str(e))
            return
        doc_dir = Path(App.ActiveDocument.FileName).parent if App.ActiveDocument and App.ActiveDocument.FileName else None
        self.out_dir = (doc_dir or Path(tempfile.mkdtemp(prefix="gongke_"))) / "gongke_reducer"
        task = runner.write_task(self.values(), self.out_dir)
        prog, args, cwd = runner.command(python, task, self.out_dir, step=self.with_model.isChecked(),
                                         full_teeth=self.full_teeth.isChecked(), drawings=self.with_drawings.isChecked(),
                                         fem=self.with_fem.isChecked())
        self.proc = QtCore.QProcess()
        self.proc.setProcessEnvironment(self._env(python))
        self.proc.setWorkingDirectory(cwd)
        self.proc.finished.connect(self.done)
        self.run_btn.setEnabled(False)
        extra = [t for t, on in (("三维模型", self.with_model.isChecked()), ("工程图", self.with_drawings.isChecked())) if on]
        self.result.setPlainText("正在计算" + (f"并生成{'和'.join(extra)}…" if extra else "…"))
        self.proc.start(prog, args)

    @staticmethod
    def _ccx() -> str:
        fem = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx")
        return runner.freecad_ccx(App.getHomePath(), fem.GetString("ccxBinaryPath", ""),
                                  fem.GetBool("UseStandardCcxLocation", True))

    def done(self, code, _status=None):
        self.run_btn.setEnabled(True)
        log = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        err = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        try:
            out = runner.read_outputs(self.out_dir)
        except FileNotFoundError:
            mod = runner.missing_module(err)
            if mod:
                self.install_btn.setVisible(True)
                self.result.setPlainText(f"缺少 Python 包 {mod}。请点下面的按钮安装所需的包（只需一次），"
                                         "或在“设置 Python 解释器”中改用已装好依赖的 Python。")
            else:
                self.result.setPlainText(f"运行失败（退出码 {code}）：\n{err or log}")
            return
        s = out["summary"]
        rows = "".join(
            f"<tr><td>{c['item']}</td><td style='color:{'green' if c['ok'] else 'red'}'>{'满足' if c['ok'] else '不满足'}</td>"
            f"<td>{c['detail']}</td></tr>" for c in s["checks"])
        g = s["gears"]
        html = (
            f"<p><b>电动机</b> {s['motor']['model']}（{s['motor']['power_kw']} kW，{s['motor']['speed_rpm']:.0f} r/min）</p>"
            f"<p>{runner.gears_html(g)}</p>"
            f"<table border='1' cellspacing='0' cellpadding='2'>{rows}</table>"
        )
        labels = {"reducer_assembly.step": "三维装配体（STEP）", "report.docx": "计算说明书（Word）",
                  "report.md": "计算说明书（Markdown）", "drawings/drawings.pdf": "整套图纸（PDF，可直接打印）",
                  "fem/comparison.md": "有限元复核对照表"}
        for name, path in out["files"].items():
            html += f"<p><a href='{QtCore.QUrl.fromLocalFile(str(path)).toString()}'>{labels.get(name, name)}</a></p>"
        if out["drawings"]:
            url = lambda p: QtCore.QUrl.fromLocalFile(str(p)).toString()
            html += "<p><b>工程图</b>（DXF 可用 FreeCAD、AutoCAD、中望 CAD 等打开编辑；SVG 可直接在浏览器预览）</p><ul>"
            for d in out["drawings"]:
                svg = f"，<a href='{url(d['svg'])}'>预览</a>" if d.get("svg") else ""
                html += f"<li>{d['number']} {d['name']}（{d['size']}）：<a href='{url(d['dxf'])}'>DXF</a>{svg}</li>"
            html += "</ul>"
        self.result.setHtml(html)
        step = out["files"].get("reducer_assembly.step")
        if step and self.with_model.isChecked():
            import Import

            doc = App.ActiveDocument or App.newDocument("减速器")
            Import.insert(str(step), doc.Name)
            doc.recompute()
            Gui.SendMsgToActiveView("ViewFit")
            Gui.activeDocument().activeView().viewIsometric()

    def getStandardButtons(self):
        return int(QtGui.QDialogButtonBox.Close)

    def reject(self):
        Gui.Control.closeDialog()
