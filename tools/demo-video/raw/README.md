# 应用内原始录屏

产品基线 `b339f7b`，深色主题；Logo 单独提交 `02dfe45`。不运行付费 dsh，不添加字幕、角标、光标或其他设计叠层。

## 采集和复现

- `session.cjs <工作目录>` 启动专属用户目录的 Electron 和 FreeCAD，接收 stdin JSON：`start` 为镜头目录，`mark` 为关键事件，`code` 为真实界面操作，`end:true` 停止采集，`stop:true` 结束自有进程。`recorded-actions.json` 保留本次 Electron 实际操作脚本。`GONGKE_EXISTING_HOST` 可绑定本次自己启动的原生宿主。
- `app-recorder.cjs` 连续抓取 Electron 实际页面帧，按采集时间戳保持原帧补足 60 fps。鼠标移动、按下/抬起、滚轮、键入及按键位置全部转换到 2560×1440。前后各保留一秒。原页面为 1440×810 逻辑像素、2 倍渲染，等比缩到交付规格。
- `replay-read.cjs` 仅重放第一份成功会话的原始事件 0–15，顺序和内容不变，停止在读图完成；`read_drawing.json` 包含产品附加的原始 0–199 项及 Agent 补读的 200–229 项，文字和坐标未经改写。
- `growth.cjs` 配合原有 `reexecute_session.py` 在新宿主执行原 MCP 调用；仅重绑定新实例/文档身份，不改工程参数。
- `qt-session.FCMacro` 在自己的 FreeCAD 进程接收工作目录内的 `action-*.json`。`fix-sketch.py` 通过元素列表、删除键、直线工具和端点点击完成真实修正。`save-reopen.py` 点击原生保存按钮、关闭标签，再通过打开文件对话框重开。
- `qt-frame.py` 解决 macOS 的 QWidget 抓取遗漏 Coin/OpenGL 子表面的问题：使用同一视口的 `saveImage` 读取当前画面，与 QWidget 控件、当前自有模态窗口按原位置组成完整应用帧。没有重建几何或替换视角；视口按逻辑分辨率采集，精细程度低于 Electron 的 2 倍渲染。
- FreeCAD 需设置 `FREECAD_USER_HOME` 到已创建的独立目录。只指定 `--user-cfg` 或 TMPDIR 不会隔离历史恢复缓存。依据：[官方路径实现](https://github.com/FreeCAD/FreeCAD/blob/main/src/App/Application.cpp)、[恢复目录扫描](https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/DocumentRecovery.cpp)。不清理用户的缓存或历史文档。
- `finalize.cjs` 只按叙事顺序接合第 07 段的四次应用采集并验证所有 MP4 规格，生成索引和 ffprobe 记录。07 的四份原片也保存在 `parts/`，可以自行重新剪辑。

## 本次交付边界

输出在 `out/demo-video/raw/`；保留 MP4 和操作日志，成功编码后立即删除帧序列及编码清单。模型修正后的截面积为 828.5 mm²，独立检查为 pass；重开后保留 40 条草图几何及 Profile、Plate。

- 第二轮 03 已预置本镜头需要的 robot4.pdf：全貌 2 秒后点击打开；实际点击为 2.758 秒、(269.81, 284)。
- 第二轮 04 真实连接 DeepSeek Harness，仅输入、不发送。展开原始返回中的标注 17，保留同一对话衔接 05。回放入口不进入产品界面，禁止发送 ACP prompt。
- 第二轮 05 结束已保存；06 正视定位只亮两条错边；07 两次选中至 Delete 分别停留 1.126 秒、1.156 秒。
- 08 本机实际已安装 DeepSeek Harness 和 WorkBuddy，录下的是实际安装与连接引导、Key 设置说明与 WorkBuddy 接入说明，未伪造“未安装”检测结果，**未交付未安装状态专属画面**。没有打开客户端或写用户级 WorkBuddy 配置。
- 07 为原生草图修正、工作台复查、原生保存/重开的顺序接合，无加速或转场。保存/重开段使用经 GUI 修正并保存的同一模型文件内容，在独立缓存目录的同一宿主中采集；没有将脚本修改模型冒充人工修改。

本轮验证：桌面 build 成功；npm test 73 通过、1 跳过；最终规格与事件范围由 finalize.cjs 校验。产品提交 70468a8、4ccb1b8、a0bcddd。

第 07 段补录了 Qt 鼠标轨迹和文件对话框键入事件；实际顺序为修正、保存重开、复查，交付 clip 按修正、复查、保存重开排列。原片和时间点均保留。

## 第二轮复现记录

`r2/actions.json` 保存本轮成功镜头的实际操作；`r2/setup-*.js` 在 session.cjs 提供的 async 上下文执行。每条 stdin JSON 控制在 900 字节内，长操作读取脚本文件，避免终端行长截断。

Qt 启动前运行 `python tools/demo-video/raw/r2/prepare-qt.py <工作目录>`，用其独立 apphome 设置 FREECAD_USER_HOME，并用 --user-cfg 指定生成的 user.cfg；随后沿用 qt-session.FCMacro 启动方式。源模型用 paid-robot4-02 的工作副本，操作日志中工作目录需替换成本次路径。prepare-qt 仅配置颜色，不修改模型。Qt 的原始键盘事件包含控件传播，剪辑绘制按键时可合并同一毫秒的同键事件。

Electron 的 04/05 必须在同一 session 连续采集；先真实连接且确认 ready，再使用只读回放，不调用 dsh prompt。Qt 07 四部分保留独立 MP4，finalize 只接合，不加视觉元素。
