**可以实现部分嵌入，但没有一条成熟路线，能把三家 CAD 的完整编辑界面统一塞进 Electron，并同时覆盖 macOS、Windows。** Windows 有控件和窗口重挂方案；跨平台完整编辑最值得考虑的是 **FreeCAD 作为原生宿主，构想引擎融入其窗口**。这需要调整桌面架构，但远小于重新开发完整 CAD。

**SOLIDWORKS：官方可嵌的是查看控件，未找到完整编辑器的受支持嵌入接口。**

- **eDrawings ActiveX** 支持查看、测量、剖切、批注等，部分能力需要 Professional 授权；不能编辑 SOLIDWORKS 草图、尺寸驱动特征和装配约束。保存批注不等于修改原生模型。[官方 API](https://www.edrawingsviewer.com/edrawings-api)
- SOLIDWORKS API 提供 `IFrame.GetHWndx64()`，可以取得主窗口句柄，但文档没有承诺把主窗口改成外部应用子窗口的运行方式。**取得 HWND 不等于厂商支持嵌入。**[IFrame 接口](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFrame_members.html?format=P&value=)
- OLE 支持把 SOLIDWORKS 文档嵌入 Word，但官方描述的编辑行为是启动 SOLIDWORKS，不能据此认定完整 UI 可作为控件托管。[官方 OLE 说明](https://help.solidworks.com/2025/english/solidworks/sldworks/c_object_linking_vs_embedding.htm)
- `SetParent` 可以尝试重挂窗口，但本次没有找到完整主窗口长期稳定工作的充分证据。开发者确实尝试过把 FeatureManager 重挂到 WinForms，报告选择数次后崩溃、退出后残留进程；这是局部窗口案例，不能直接推断所有主窗口方案都会失败。[开发者原帖](https://3dswym.3dexperience.3ds.com/question/solidworks-user-forum/help-on-getfeaturemgrviewhwndx64-dested-vb-net_3y19QAdmTJCsKciNnOM3Ww)

**AutoCAD：存在真正的官方编辑嵌入路线，但要区分四种产品。**

| 方案 | 能做到什么 | 对构想引擎的意义 |
|---|---|---|
| **AutoCAD OEM** | 官方支持宿主子窗口、.NET Form、in-place activation；可提供定制命令和编辑 UI | Windows 上最正规的商业嵌入路线，需要另行取得 OEM 授权；不是直接使用学生已有 AutoCAD 许可证 |
| **普通 AutoCAD AcCtrl** | 官方文档提供 `Src` 和 `PostCommand`，示例可执行画线命令 | 确实能编辑，不只是看图；但主要提供嵌入绘图区，不自动带来完整 Ribbon、命令行和面板 |
| **RealDWG** | 读写 DWG/DXF 数据库 | 不包含 AutoCAD 编辑 UI，官方明确也不提供查看支持；界面仍需自己实现 |
| **APS Viewer** | Web 模型查看、选择、测量、批注及自定义场景交互 | 适合 Electron 内预览；场景几何修改不等于原生 DWG 编辑和保存 |

依据：[OEM 官方说明](https://forge.autodesk.com/developer/overview/autocad-oem)、[AcCtrl 官方示例](https://help.autodesk.com/cloudhelp/2025/ENU/OARX-DevGuide/files/GUID-D2D6F91A-DC86-43F3-8637-AAF6AF2254F6.htm)、[RealDWG 官方 FAQ](https://aps.autodesk.com/developer/overview/realdwg-api)、[APS 场景 API](https://aps.autodesk.com/blog/introducing-scene-api-aps-viewer)。

AcCtrl 不能简单当成可靠的完整编辑器组件：Autodesk 工程师的示例及评论记录了对话框出现时完整 AutoCAD 窗口弹出、复杂交互难以衔接；2023 年开发者仍报告切换图纸后卡死。[原始示例与讨论](https://keanw.com/2008/03/embedding-autoc.html)、[较新使用反馈](https://forums.autodesk.com/t5/net-forum/how-to-use-dwgviewracctrl-dll-in-the-client-machine-without/td-p/12148035)

普通 AutoCAD 的 `SetParent + MoveWindow` 也有公开实现，说明重挂具有实践基础；该案例同时卡在文档切换事件处理，不能作为完整工作流稳定性的证明。[实现原帖](https://dobon.net/cgi-bin/vbbbs/cbbs.cgi?mode=res&namber=35623&no=0&page=)

**AutoCAD for Mac 可以做真正的插件联动**：支持 AutoLISP、ObjectARX；不支持 Windows 那套 ActiveX、VBA、Managed .NET。因此 Windows 插件不能原样搬过去，AcCtrl/OEM 也不是 Mac 的统一答案。[2026 官方能力表](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-MAC-Customization/files/GUID-E6429154-36DF-4D84-8ABC-9FCA15B66158.htm)

**FreeCAD：可以作为组件复用，但“开源可嵌”不代表“Electron 即插即用”。**

官方支持导入 `FreeCAD`、`FreeCADGui`，并说明同版本 Qt 宿主可以承载 GUI；源码还保留 PySide、Win32 等嵌入示例。Windows 有 Qt/Win32 接入基础，macOS 更适合在**同一进程的 Qt 宿主**内整合，需要统一 Python、Qt 和原生库版本。[官方嵌入文档](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Embedding_FreeCAD.md)、[源码示例目录](https://github.com/FreeCAD/FreeCAD/tree/main/src/Tools/embedded)

不过，官方旧示例明确警告：直接拆出 FreeCAD 3D widget 会遇到事件处理问题、右键菜单崩溃；复制场景到自己的 viewer 又不会自动获得完整选择系统、草图编辑和工作台操作。**更稳妥的路线是保留 FreeCAD 的文档与 GUI 生命周期，在里面加入工程管理和 Agent 面板。**这些示例证明有复用基础，并非现代 Electron 双平台完整嵌入的验收结果。[FreeCADGui 嵌入说明](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Embedding_FreeCADGui.md)

另外，FreeCAD 用 OCCT 做几何，原生视图主要使用 Coin/Open Inventor；单独嵌入一个 OCCT 视图，不会同时获得 FreeCAD 编辑器。[架构说明](https://freecad.github.io/DevelopersHandbook/gettingstarted/dependencies.html)

**Electron 的限制集中在窗口体系，而不是缺一个 npm 包。**

Windows 下可以用原生模块取得 Electron 的 HWND，再创建容器、调用 `SetParent`。真实项目 [electron-native-windows](https://github.com/sweetwisdom/electron-native-windows) 已演示嵌入其他应用，但示例通过关闭 GPU、DirectComposition，甚至部分沙箱设置来处理冲突，不能直接当 CAD 产品基础。

重挂后仍需处理：

| 问题 | 证据与实际含义 |
|---|---|
| 菜单、焦点、快捷键 | 重挂不会自动合并菜单和命令路由；跨线程父子关系会连接输入队列，一个窗口阻塞可能影响另一个 |
| 对话框、浮动面板 | 它们未必属于被重挂的子树，可能继续作为顶层窗口弹出；模态关系需要单独处理 |
| DPI、多显示器 | Microsoft 明确警告不同 DPI awareness 会产生异常，跨进程重挂可能强制重置子进程 DPI；跨不同缩放屏幕因此是主要风险 |
| 许可 | 重挂只改变窗口关系，不替代 CAD 安装与使用授权，也不产生再分发权 |

前两项的机制依据来自 [Microsoft 工程师解释](https://devblogs.microsoft.com/oldnewthing/20130412-00/?p=4683%2F)，DPI 行为见 [SetParent 官方文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent)。菜单、弹窗和多屏全部稳定，不能仅凭“窗口成功显示”推断。

macOS 则没有面向任意现有应用、类似跨进程 `SetParent` 的公开通用机制。Electron 返回的是 `NSView*`，它是进程内对象指针，不能拿另一个进程的窗口编号直接挂进自己的视图树。Qt 的 native embedding 同样使用 `NSView*`，不意味着支持跨进程搬窗口。共享画面、捕获串流可以另做，但那成为远程显示与输入转发系统。[Electron 文档](https://www.electronjs.org/docs/latest/api/browser-window#wingetnativewindowhandle)、[Qt 官方说明](https://doc.qt.io/qt-6/mixing-qt-with-other-ui-toolkits.html)

三条替代路线中，工作量以下均为**复用现有工程和 Agent 链路的工程估计**，不是厂商报价：

| 路线 | 跨平台覆盖 | 工作量量级 | 学生体验与主要风险 | 推荐 |
|---|---|---|---|---|
| **a. 强联动**：自动并排、选择同步、Agent 操作即时更新 | FreeCAD 双平台；SW 仅 Win；AutoCAD 两端分别适配 | 首个宿主约 **1–3 人月**；其余各增加适配工作 | 保留完整原生编辑能力；仍有两个窗口，小屏受限；Mac 自动布局通常需要辅助功能权限 | **近期交付推荐**，但不能完全满足单窗口诉求 |
| **b. 受限编辑器**：build123d/OCCT＋自有 Web 视图 | 核心体验可统一覆盖 Win/Mac | 参数化模板编辑约 **3–6 人月**；加入通用草图约束、特征历史、装配后进入 **一年以上持续研发** | 常见课程任务体验最好；必须严格限制编辑范围，导入模型也不会自然恢复原始特征树 | **保留 Electron 时最推荐** |
| **c. FreeCAD 核心**：完整原生编辑＋构想引擎面板，商业 CAD 外部联动 | FreeCAD 编辑统一覆盖 Win/Mac；商业功能依各自平台 | 保留原生工作台的产品化首版约 **4–8 人月** | 能获得完整编辑且单窗口；代价是接受 FreeCAD 交互、维护打包和升级，并调整 Electron 主壳 | **完整编辑与单窗口优先时最推荐** |

路线 b 已有可借鉴的真实项目，但各自覆盖不同层次：

- [CQ-editor](https://github.com/CadQuery/CQ-editor) 提供跨平台 PyQt 编辑、调试和 OCCT 视图；[OCP CAD Viewer](https://github.com/bernhard-42/vscode-ocp-cad-viewer) 展示了 build123d/CadQuery 与 Web 视图联动。它们能节省视图和代码工作流开发，不能直接提供完整鼠标建模系统。
- [Zoo Design Studio](https://zoo.dev/docs/zoo-design-studio) 展示了点选、代码和自然语言共享模型的产品体验；前端开源，几何引擎是专有云服务，不能直接作为本地 OCCT 编辑器搬用。[官方 FAQ](https://zoo.dev/docs/faq)
- [Onshape 的架构](https://www.onshape.com/de/blog/how-does-onshape-really-work) 证明浏览器可以承载专业 CAD 交互，但背后还有几何服务器、约束求解器和特征系统。WebGL 视图只是其中一层。

**按你“仍然希望嵌入，又不想自研完整 CAD”的优先级，我推荐 c：让 FreeCAD 承担完整编辑，构想引擎承担工程、计算、结果和已有 Agent 的组织；SolidWorks、AutoCAD 保留文件互通与插件联动。** 具体应优先做 FreeCAD 工作台/Qt 宿主整合，避免从拆分它的内部 GUI 开始。

如果保留现有 Electron 主窗口是硬约束，则选 **b＋a**：常用课程参数、标准件和简单特征在窗口内完成，深度编辑进入联动 CAD。**单纯把商业 CAD 窗口塞进去，并不会减少适配工作，反而增加一层窗口兼容维护。**

真正需要决定的产品取舍只有三项：

1. 首版要支持**完整自由建模**，还是先覆盖**明确的课程设计与参数化任务**？
2. 是否接受 **FreeCAD 为默认编辑环境**，商业 CAD 作为可选扩展？
3. 是否必须交付**保留商业 CAD 原生特征树的可编辑文件**？若必须，相应商业宿主和适配就仍需保留。

