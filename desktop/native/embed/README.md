# Windows CAD 编辑区

本模块托管 FreeCAD / SOLIDWORKS **完整原生主窗口**，包含特征树、工作台、原生建模工具。窗口控制使用独立的 x64 C# 辅助进程；工程读写继续使用 `freecad/gongke/bridge.py` 和 `adapters/solidworks`。Electron 不加载 CAD 内核，也不解释或重建原生特征树。

当前交付是共用实现的独立原型和桌面接线，**尚未取得 Windows CAD 的运行证据**。不能据本机编译把主窗口重挂认定为产品已验收。下面的真机实验决定具体 CAD 版本是否采用重挂，或切换为停靠。

## 实现选择与依据

| 选择 | 原因及边界 |
|---|---|
| 完整主窗口重挂 | 保留 CAD 自己的菜单、工具面板、文档管理与事件循环；不拆走三维视图或 FeatureManager。修改 `WS_CHILD/WS_POPUP` 和外框，再调用 `SetParent`，释放时恢复原值。 |
| 同一实现提供自动停靠 | 保留 CAD 顶层窗口和原生外框，将 owner 设为工作台并跟随中部区域。不会跨进程重设 parent/DPI，但仍是独立顶层窗口；有自己的标题栏，Alt+Tab、遮挡、激活体验与真子窗口不同。需要显式选择，不静默更改模式。 |
| 辅助进程与恢复守护分开 | 主进程不执行可能阻塞的 Win32 调用；辅助进程/工作台退出时守护尝试恢复 CAD 的 parent、owner、style、位置和已隐藏浮窗。跨进程队列耦合仍可能使挂起互相影响，必须用真机挂起实验确认。 |
| 原生保存提示决定关闭 | 正常退出对本应用启动的进程发送 `WM_CLOSE`，等保存/放弃完成再销毁 Electron HWND。借用的已有 CAD 仅释放。取消原生关闭后点击“取消退出”。不自动保存、不强杀 CAD。 |
| 窗口列表显式选主窗口 | 依据真实 HWND、PID、程序路径检查目标，而非凭 `MainWindowHandle` 或窗口标题猜实例。不修改现有桥协议。启动画面退出后再刷新选择主窗口；不要选欢迎/登录/文档浮窗。 |

依据：

- [Microsoft SetParent](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent)：调用不会自动更改 window styles；跨进程重挂可能强制改变子进程 DPI awareness。代码记录实际 DPI/context，而非把像素换算当作 DPI 风险已解决。
- [Microsoft 对跨进程窗口树的解释](https://devblogs.microsoft.com/oldnewthing/20130412-00/?p=4683)：窗口树跨线程/进程会耦合输入队列。辅助进程隔离不能消除窗口树自身的耦合。
- [Electron getNativeWindowHandle](https://www.electronjs.org/docs/latest/api/browser-window#wingetnativewindowhandle)：Windows 返回 HWND。这里读取 64 位值并按十进制字符串传递，避免 JavaScript 浮点截断。
- [SOLIDWORKS IFrame.GetHWndx64](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFrame~GetHWndx64.html)：提供主窗口句柄，不承诺完整编辑器可嵌入。当前不用 COM 启动或接管实例，避免与现有插件的 COM 生命周期混用。
- [FreeCAD 嵌入文档](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Embedding_FreeCAD.md)、[GUI 嵌入示例](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Embedding_FreeCADGui.md)：支持组件复用，但旧拆视图示例记录了事件和上下文菜单问题，因此本轮选择完整主窗口。
- [electron-native-windows](https://github.com/sweetwisdom/electron-native-windows)：有 Electron 托管外部窗口的开源实践；没有搬用其禁用 GPU/沙箱的设置。产品保持 Chromium sandbox/contextIsolation，未新增 npm 原生模块或 gRPC 依赖。

## 一键原型

Windows 10/11 x64，安装 Node.js（满足项目 Vite 版本要求）、.NET 8 或更新 SDK；CAD 正常安装并具备本机许可。工作台与 CAD 都用普通权限运行。

从仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File desktop/native/embed/run-prototype.ps1
```

若收到 `gongke-embed-prototype-win-x64.zip`，完整解压后双击 `start-prototype.cmd`，无需安装 Node.js、.NET 或 Python；它只包含独立原型与窗口组件，CAD 仍使用本机安装。

源码脚本发布自包含辅助进程、构建桌面代码，再打开独立 Electron 原型，不需要 Python 服务或 Agent。首次没有 `node_modules` 时执行 `npm ci`。发布目录 `publish/` 中的文件要整体携带；“单文件”主程序仍可能伴随 Windows Desktop 原生依赖，不能只拷贝 EXE。

1. FreeCAD 必须从完整构想引擎启动与嵌入，走桥接单实例管理；独立窗口原型只验证 SOLIDWORKS/合成窗口路径。完整应用中选择 FreeCAD 安装。检测随包 `resources/freecad/bin/FreeCAD.exe`、开发环境 `GONGKE_FREECAD_EXE`、注册表 App Paths/卸载项和常见安装目录。未检测到时点“选择程序”，只能选择 `FreeCAD.exe` 或 `SLDWORKS.exe`。
2. 点“启动”，等 CAD 启动完毕，点“刷新窗口”。也可直接选择已运行的 CAD 主窗口。窗口列表显示标题和 PID，供与桥的发现记录比对。
3. 选择“嵌入”或“自动停靠”，点“进入建模”。人工自由建模完全在原生 CAD 中进行。
4. `Ctrl+Alt+F6` 在 CAD 与工作台间切换；也可点击外围输入区或“返回 CAD”。快捷键仅在本工作流处于前台时注册；占用情况见 `shortcut` 状态。
5. “独立窗口”恢复原布局；切换软件前先释放或关闭当前 CAD。“关闭 CAD”走原生保存/取消。切换不会转换、重写或删除工程文件；`.FCStd` 不会自动变成 `.SLDPRT` 特征树。

合成窗口自动冒烟（不是 CAD 验收）：

```powershell
powershell -ExecutionPolicy Bypass -File desktop/native/embed/test-windows.ps1
# 人工观察替身的菜单、对话框、浮窗和未保存关闭
powershell -ExecutionPolicy Bypass -File desktop/native/embed/run-prototype.ps1 -Fixture
```

合成程序名为 `fixture/publish/SLDWORKS.exe`，标题明确写着 `synthetic fixture (not FreeCAD)`，不要安装到真实 CAD 目录。自动冒烟检查实际 HWND parent/style、窗口移动缩放、最小化隐藏、释放与进程退出，输出 `out/embed-fixture/result.json`；不把截图或协议替身写成 FreeCAD/SOLIDWORKS 通过。

## 窗口契约

- Renderer 仅暴露 `status/discover/chooseInstallation/launch/attach/layout/focus/detach/closeCad/diagnose/cancelClose`。不能发任意 shell、脚本、Win32 消息或工程命令。IPC 只接受主 frame；可执行路径来自系统扫描或主进程原生选择框。
- C# 在单独 STA 消息循环中执行窗口操作，stdin JSONL 按序派发，stdout 只发协议。超时不重发有副作用的调用；用 `status` 刷新状态。
- CSS 矩形经 zoom、客户区裁剪及 Electron `dipToScreenRect` 转成屏幕物理坐标；辅助进程在父 HWND 的 DPI context 下转为客户坐标。移动、缩放、最小化、显示器度量变化都重算。
- Native HWND 位于 Chromium 图层之上。切换视图、已有 `.modal-scrim`、原生程序选择框、页面 reload 时隐藏 CAD。新的 HTML 模态层应使用 `dialog[open]` 或 `[role=dialog][aria-modal=true]`；不得在 CAD 上方仅加 CSS z-index。
- CAD 自己的对话框保留原 owner，不改成 Electron 子窗口；CAD 主窗口禁用时同步禁用工作台，避免模态期间继续发起动作。拥有关系内的浮窗跟随父窗口移动并约束到当前屏幕工作区。没有 owner 的第三方插件窗口不擅自接管，真机记录其行为。
- 不合并菜单、不转发所有键盘消息、不模拟鼠标输入。原生菜单、快捷键及焦点保持 CAD 自己的路由，是否完整保留必须实测。`nativeMenu=true` 尤其需要检查 Win32 菜单在 child style 下的行为。
- 当前 HWND/PID 只用于窗口所有权。FreeCAD session 文件和 SOLIDWORKS discovery 文件均已有 PID；启用桥后核对二者一致，多实例时在原有工程接口选择对应宿主。嵌入层不把“窗口已出现”当作“工程桥已连接”。
- 窗口模块不读取或写入模型。Agent 修改仍走现有工作副本、对象身份、修订及 operation_id 规则。人工在原生菜单里打开和保存文件属于用户的直接编辑，不由嵌入模块截获。

## 真机实验与决策

每个 CAD 版本分别测试 `embed` 和 `dock`；用新建测试工程或原件副本，不用唯一未保存的重要工程。记录 Windows build、CAD 版本、显卡/驱动、两个屏幕的分辨率与缩放、连接方式。下表当前全部为**待运行**。

| 场景 | 操作及通过条件 |
|---|---|
| 完整编辑 | FreeCAD 创建草图约束→Pad→修改尺寸→Undo；SW 创建草图→拉伸→编辑草图→装配配合。特征树、PropertyManager、菜单与右键菜单全部可用。 |
| 文件保真 | 在 CAD 内另存原生文件，退出后独立重开。原生特征可继续编辑；原件哈希不变；不得用 STEP 预览代替。 |
| 菜单 | 菜单鼠标点击、Alt/F10、上下文菜单、工具栏溢出、SW CommandManager；发生不可达/错位即判 embed 失败，并用 dock 重测。 |
| 焦点 | CAD 中尺寸输入→Agent 输入中文→返回草图；Ctrl+C/V、Ctrl+Z、Ctrl+S、Esc、Tab、Ctrl+Alt+F6。快捷键不能误发给另一侧。 |
| 模态 | 打开、另存、选项、未保存关闭；检查原生对话框不在工作台后方，取消后恢复输入，工作台模态期间不能操作 CAD。 |
| 浮动面板 | 拖出面板后移动、最小化、恢复工作台；面板不留在屏幕外，不成为被隐藏的孤儿窗口。单独记录无 owner 插件窗口。 |
| 多屏 DPI | 100%/150%/200% 两屏，包含负坐标屏；拖动跨屏、最大化/还原、改变缩放、拔掉副屏。模型拾取与显示位置一致，菜单/弹窗正确，编辑区不覆盖 Agent。 |
| 图层 | 切换工程页/参数页、开工作台设置框、改变侧栏宽度、窗口缩放；CAD 隐藏/恢复正确，不挡 HTML 对话框。 |
| 多实例与桥 | 各开两个测试实例，按 PID 选择其中一个；原生桥 PID 与编辑区 PID 一致，另一实例未改 parent/未收到关闭；执行一次已有桥命令并在原生树确认。 |
| 退出与取消 | 从工作台启动 CAD，编辑不保存，关工作台→取消原生关闭→取消退出→继续编辑；再次关闭并保存，工作台与自启动的 CAD/辅助进程全部退出。借用实例只恢复独立窗口。 |
| renderer 崩溃 | 在测试原型的 Electron 调试会话中触发 renderer crash；CAD 应释放，原生文档仍可操作。重新加载不自动重放建模动作。 |
| helper / 工作台崩溃 | 在任务管理器只结束诊断记录里的 helper PID，另一次只结束工作台主 PID。检查 CAD 是否恢复可见、文档可编辑；检查 recovery 日志。不得把“守护启动了”当作恢复成功。 |
| CAD 崩溃/挂起 | 对测试实例结束/暂停 CAD，工作台应显示断开且不重发命令；测试跨进程输入队列是否让工作台同时挂起。CAD 自身崩溃的未保存恢复由其 autosave/recovery 决定。 |

若特定 CAD 在 `embed` 中出现菜单不可用、模态死锁、混合 DPI 拾取偏移或崩溃，记录复现与诊断，再在同版本 `dock` 重测。只在证据证明失败后决定该版本默认使用停靠；本轮没有虚构失败结论。停靠保留完整编辑器与原生文件，但有外框、独立顶层窗口和激活切换，不能宣传为真正嵌入。

“崩溃不残留进程”与“未保存文档不丢失”不能靠强杀同时满足：本实现将异常后的 CAD 恢复为**可见、由用户继续管理的原生窗口**，辅助进程退出；这不是隐藏残留。若 parent 销毁时 CAD 自行退出、窗口已销毁或 CAD 本身崩溃，窗口恢复无法保证数据恢复。真机实验必须确认这一边界，不能承诺尚不存在的跨 CAD 自动保存机制。

## 诊断与交付

免安装原型的运行文件名为 `GongkeEmbedPrototype.exe`。Electron 40 在 Windows 根据可执行文件名判断 `app.isPackaged`，因此不能保留 `electron.exe` 名称，否则辅助进程会误走开发目录。依据：[对应版本源码](https://github.com/electron/electron/blob/v40.10.6/shell/browser/api/electron_api_app.cc#L846-L855)。

点“保存诊断”，路径显示在界面。目录是 Electron userData 下的 `embed/`：

- `embed.jsonl`：窗口操作与错误，包含 PID、标题等本机信息；分享前核对标题中的文件名。
- `diagnostic-*.json`：实际 parent/style、DPI/context、物理矩形、浮窗和显示器信息。
- `recovery-*.json`：恢复快照，正常释放后删除；`recovery.jsonl` 记录守护恢复是否仍有有效窗口，`.error` 保留恢复失败原因。
- `helper-stderr.log`：辅助进程异常输出。

截图必须来自 Windows 桌面。Playwright 的网页截图可能不包含外进程子窗口；用下面脚本捕获真实虚拟屏幕与 PID 列表（会包含屏幕上的其他窗口，分享前检查）：

```powershell
powershell -ExecutionPolicy Bypass -File desktop/native/embed/capture.ps1
```

回传：每项 pass/fail/未测、两种模式的截图和诊断、测试原生文档、复现步骤。不要回传许可信息或桥 token 文件。

本机可重复检查：

```sh
cd desktop
npm run build
npm test
node --test native/embed/protocol.test.cjs
# macOS/Linux 可交叉编译，不能在本机执行 Win32 行为
# .NET SDK 的 EnableWindowsTargeting 已在工程文件设置
dotnet build native/embed/Gongke.Embed.csproj -c Release
```
