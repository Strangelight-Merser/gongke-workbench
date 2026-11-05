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

输出在 `out/demo-video/raw/`；原帧和操作日志也保留。模型修正后的截面积为 828.5 mm²，独立检查为 pass；重开后保留 40 条草图几何及 Profile、Plate。

- 03 是空工程：图纸目录、空 CAD 视图、Agent 面板可见。没有为镜头添加示例文件；当前产品不能在无文件时显示真实 PDF 分栏。
- 04 使用真实“导入图纸”按钮，当前产品没有拖放导入入口。原始文件未修改，工作台 PDF 渲染没有显示斜向水印。
- 08 本机实际已安装 DeepSeek Harness 和 WorkBuddy，录下的是实际安装与连接引导、Key 设置说明与 WorkBuddy 接入说明，未伪造“未安装”检测结果，**未交付未安装状态专属画面**。没有打开客户端或写用户级 WorkBuddy 配置。
- 07 为原生草图修正、工作台复查、原生保存/重开的顺序接合，无加速或转场。保存/重开段使用经 GUI 修正并保存的同一模型文件内容，在独立缓存目录的同一宿主中采集；没有将脚本修改模型冒充人工修改。

本轮验证：桌面 build 成功；录屏脚本通过 Node 语法检查；最终规格与事件范围由 finalize.cjs 校验。产品代码未变更，不额外运行产品回归测试。

第 07 段补录了 Qt 鼠标轨迹和文件对话框键入事件；实际顺序为修正、保存重开、复查，交付 clip 按修正、复查、保存重开排列。原片和时间点均保留。
