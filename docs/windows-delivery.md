# Windows 安装交付

构想引擎使用已有 Agent：dsh 在窗口内通过 ACP 连接，WorkBuddy 使用工程 MCP。工作台不提供内置 Key 助手，不保存模型服务密钥。dsh 的登录、账户与密钥配置由原厂应用完成。

## 构建与安装

`.github/workflows/desktop.yml` 在 Windows x64 构建 PyInstaller 服务、.NET 自包含窗口 helper、AutoCAD 两个目标版本插件，再构建 NSIS。下载产物 `gongke-windows-installer-<commit>`，校验 `.sha256` 后运行 `gongke-0.2.0-windows-x64-setup.exe`。安装向导可选目录，普通使用无需 Python、Node 或 .NET SDK。

随包 FreeCAD 固定为 **1.0.2 / Windows x86_64 / Python 3.11**，保持官方 portable 发行包完整，不裁剪第三方许可证。构建下载固定 URL，并要求 SHA-256 `e89afe0433063c7f2484326b8b9a64e3027dc29d145ddb438a44046c960827a6`。它作为独立进程启动，默认使用 `resources/freecad/bin/FreeCAD.exe`；可以在 CAD 选择器切换已安装的 SOLIDWORKS，文件格式不自动转换。

安装内容：

| 路径 | 内容 |
|---|---|
| `resources/service` | 冻结 Python 工程服务及其依赖 |
| `resources/embed` | 自包含 Windows 窗口组件 |
| `resources/freecad` | FreeCAD 官方完整发行包；`gongke-distribution.json` 记录版本、摘要、源码链接和许可证清单 |
| `resources/host-module` | FreeCAD 桥接及共享 Python 核心 |
| `resources/plugins/autocad` | SDK 编译的 net8/net10 插件、安装/诊断脚本；不含 Autodesk SDK DLL |
| `resources/adapters/solidworks` | 当前仍是源代码及安装/构建脚本，**尚不等于可安装插件** |
| `resources/app.asar` | 桌面、ACP/MCP 接入和 dsh 官方安装引导（固定版本、完整摘要、签名校验、检测与配置） |
| `resources/licenses` | 本项目 LGPL 许可证；FreeCAD 和依赖许可证保留在其原目录 |

**尚缺 SOLIDWORKS 插件二进制的构建输入**：官方 `api/redist` 的 `SolidWorks.Interop.sldworks.dll`、`SolidWorks.Interop.swconst.dll`、`SolidWorks.Interop.swpublished.dll`。仓库要求真实官方 SDK，不生成替身引用，也不采用来源不明的 NuGet 替代品。提供可用于 CI 的官方引用文件后，还需构建并将输出纳入安装包。这是完整交付的阻塞项，不能将当前安装包称为已包含可用 SW 插件。

dsh 引导已编入桌面，按现有流程经用户同意下载原厂安装器；首版没有把 dsh 账户或凭据打进包，也不自动注册、付费。此安装包没有离线分发 dsh 本体。

## CI 验收证据

只有本次 run 的 `windows-installer-validation-<commit>/result.json` 中 `ok=true` 才算下列流程通过，脚本存在不代表验收成功：

1. 运行真实 NSIS，安装到中文且含空格的目录。
2. 创建真实本地账户“学生验收”，加载 Windows 用户配置，从其中文用户目录首次启动已安装 Electron。
3. 通过 renderer 原有 IPC 完成冻结服务握手、创建中文路径工程；再次运行 EXE 必须自行退出。
4. 通过真实 helper 发现随包 FreeCAD；冻结服务启动桥接，重复连接复用同一 PID。
5. 经绑定工程的公开命令创建新 `.FCStd`，矩形草图、Pad、保存；使用回执的文档身份和修订，不跳过工作副本保护。
6. 正常退出工作台，核对先前采集的 Electron、服务、helper、FreeCAD PID 全部退出。失败清理不计作通过。

安装验收产生日志、截图和进程清单，失败也上传。已有桌面计算/导出测试继续保留。Windows GUI 在新账户会话下能否正常启动，需要第一次推送实跑确认；不能用环境变量伪造用户目录来代替此项。

## 三处 CI 失败的处理与证据边界

- run `41769254323` 的实际失败是 `test_connection_auth_and_config_preview:258` 的 `assert not Path(result['path']).exists()`；403 断言已经通过。测试只设置 HOME，而 Windows `Path.home()` 使用 USERPROFILE，导致不同测试共用 runneradmin 配置。测试现在同时隔离两者，不改变鉴权协议。
- macOS 启动超时已由 run `41773061261` 的诊断产物定位：`tests/service-16190.log`、`service-16498.log`、`service-18263.log` 在 0.138 / 0.226 / 0.178 秒进入 `connection.start.begin`，第 5、10 秒都停在 `socket.getfqdn → HTTPServer.server_bind → ConnectionServer.__init__`；独立 probe 在 0.141 秒进入同一位置。前轮 NumPy 预加载归因错误。现在本机 HTTP 服务器直接调用 TCPServer 的 bind，并把数字地址、实际端口写入 HTTPServer 属性，不做反向 DNS。[CPython 3.11 源码](https://github.com/python/cpython/blob/3.11/Lib/http/server.py) 显示原 bind 额外调用 getfqdn，仅用于 server_name。回归测试禁止 getfqdn/gethostbyaddr，经过真实服务子进程握手与 EOF 退出；旧实现失败，新实现通过，原 15 秒时限不变。
- 本轮临时 startup_trace、diagnose 脚本、workflow 诊断步骤及诊断说明已删除。保留原有安装/桌面验收使用的 `GONGKE_TEST_DIAGNOSTICS_DIR`：它为长期运行的打包应用测试提供线程栈，未参与本轮 15 秒启动定位。无数值扩展预加载的行为和测试仍保留，验证握手及机械计算不加载无关宿主依赖，不再将它描述为超时根因。
- AutoCAD `OperationStore.Get` 原来把文件存在时的所有 IOException 当成活跃锁。Windows `FileShare.None` 与普通文件读者也冲突，不能据此断言操作仍在执行。改为 Windows 字节范围锁，只有 `ERROR_LOCK_VIOLATION` 表示活跃操作；其他 I/O 错误传播。保留永久 ID 占位、崩溃回读和禁止重放。恢复测试增加普通读者持有锁文件的情形，并输出实际恢复状态。原 CI 仅记录断言名，未记录 HResult，不能证明那一次具体由扫描器触发；run `41774064329` 仍在 running 恢复断言失败，说明这一修改没有解决失败，不能视为根因已确认；后续 run `41775603833` 已证明 running 锁在退出后约 12 ms 自动释放，queued 立即恢复。错误是测试把进程退出通知当成解锁屏障；现按实际恢复条件有界等待，产品保持保守状态与禁止重放。临时诊断已删除，具体时序与真实宿主边界见 [AutoCAD 回执契约](../adapters/autocad/README.md)。

冻结服务启动 FreeCAD 前暂时恢复标准 DLL 搜索路径，随后恢复服务的原路径，并从子进程 PATH 移除 `_MEIPASS` 内条目。FreeCAD 不继承服务携带的 Qt/Python/OCCT。

另一个实机发现：FreeCAD 的 App 层 save/saveAs 不清除 GUI Modified 标志，原流程保存成功后仍阻止正常退出。现在仅在保存成功后清除当前文档 GUI 标志，失败仍保留；不调用会顺带保存外部依赖文档的 GUI 保存向导。依据 [FreeCAD 1.0.2 Gui::Document::save 源码](https://github.com/FreeCAD/FreeCAD/blob/1.0.2/src/Gui/Document.cpp#L1388)。本机 FreeCAD 1.1.4 已经通过同一工程服务建矩形/Pad、B-rep 单实体及体积 `1e-6 m³` 检查、保存、正常关闭且 PID 消失；这不替代 Windows 1.0.2 安装验收。

## 本次本机验证

- 完整 `python -m pytest -q tests`：866 passed（95.44 秒）。
- `npm run build` 通过；桌面测试 65 passed、1 skipped（Windows 专属 cmd 测试）。
- AutoCAD：70 项协议/崩溃恢复检查通过；SOLIDWORKS：51 项协议/回执检查通过。
- helper `dotnet publish -r win-x64 --self-contained true -p:PublishSingleFile=true` 成功；只证明可编译，不冒充 Windows 运行结果。
- 独立 FreeCAD 1.1.4 原生零件与正常退出验证见上节；Windows 固定版/冻结服务/安装器必须等 CI 实跑。

## Windows 真机验收表

每项记录 Windows/显卡/缩放比例/宿主版本、安装包 SHA-256、操作、实际结果与截图。未执行标“未验”，不得用协议或 SDK 编译结果代替。

| 场景 | 操作与通过条件 |
|---|---|
| 普通学生安装 | 干净 Windows 10/11 x64，无 Python/Node/.NET SDK，普通账户安装/启动/卸载；工程和用户资料不被卸载删除 |
| 窗口焦点 | FreeCAD 嵌入后键盘输入、鼠标拖动、快捷键、原生菜单、弹窗、Alt-Tab 和返回工作台均可用 |
| DPI/多屏 | 100%/150%/200%，跨屏拖动、最大化/还原、侧栏伸缩，画布无错位或截断 |
| 保存与退出 | 未保存零件退出出现原生保存流程；取消退出继续编辑；保存后正常退出无子进程残留 |
| 已有 FreeCAD | 保留已有用户文档，重复连接不生成多实例；工作副本之外文件不覆盖 |
| SOLIDWORKS | 用官方 SDK 构建插件并安装注册，在真实已授权宿主切换/嵌入、创建或复制零件、修改、重建、保存、回读；不可把源码目录当成已安装插件 |
| AutoCAD | 匹配版本插件安装/加载，DXF→DWG、工作副本编辑、保存、崩溃后同 operation_id 查询，不重放未知写入 |
| dsh | 原厂安装器签名通过；中文用户目录定位；学生自行完成账户配置；ACP 连接后真实读取当前工程并核对任务回执 |
| 联网边界 | 无网仍可使用随包 FreeCAD 和计算；dsh 未安装时明确需要联网下载；取消下载/安装可恢复 |

## 依据

- [FreeCAD 1.0.2 官方发行包及摘要](https://github.com/FreeCAD/FreeCAD/releases/tag/1.0.2)、[对应源代码](https://github.com/FreeCAD/FreeCAD/releases/download/1.0.2/freecad_source.tar.gz)。本项目不修改 FreeCAD 二进制，保留发行包许可证及可替换独立程序目录。
- [PyInstaller：冻结应用启动外部程序](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)：Windows SetDllDirectory 与 PATH 清理要求。
- [electron-builder NSIS](https://www.electron.build/docs/nsis/)：安装目录、安装范围与产物配置。
- [SOLIDWORKS 官方 API 入门](https://help.solidworks.com/2023/english/api/sldworksapiprogguide/Welcome.htm)：官方安装提供 primary interop assemblies。
- [dsh 引导来源和同类实现参考](../desktop/ACP.md)：固定官方安装器、签名验证及账号边界。


## 新布局下的打包流程验收

run `41775603833` 的课程设计节点已经被定位，但日志持续显示 element is not visible。`fitLayout` 在中心剩余宽度小于 640 时折叠工程树；这与示例数据、虚拟化无关。流程先从开始页创建工程，需要工程树时读取“资源管理器”的 aria-pressed，通过活动栏展开，再等待工程树可见；不使用强制点击。CI 使用 `GONGKE_TEST_WINDOW_WIDTH=1100` 固定覆盖这一条件。

所有支持 `GONGKE_TEST_EXECUTABLE` 的脚本已清点：

| 脚本 | macOS 打包应用、每次全新用户目录，1100×768 / 1440×768 |
|---|---|
| desktop-flow | 两种宽度完整通过：教学计算、生成、成果清单与图纸、断连 Agent、packaged 断言 |
| workflow-flow | 两种宽度完整通过：空白任务、实际计算和导出、成果过期、重启打开、工程隔离 |
| freecad-flow | 两种宽度完整通过：独立真实 FreeCAD 的合成教学轴和 TechDraw 页、工作副本、40→38 mm 修改及读回、校核、图纸更新、DXF、源文件哈希不变 |
| windows-installed | 依赖 Windows、中文账户、NSIS、helper、随包 FreeCAD；本机无法运行，仍由 Windows runner 完整验收 |

FreeCAD 流程现在先通过“连接 FreeCAD”完成生命周期连接，等界面操作完成，再选择特征树对象；切换工作副本和刷新几何后重新选择对象。它不再假定读取工程或切换文档会自动选中教学轴。额外的 workbench-live 源码流程也通过窄窗口进入和后续宽度/主题切换。

本机复跑：设置 `GONGKE_TEST_EXECUTABLE` 为打包可执行文件路径，分别以 `GONGKE_TEST_WINDOW_WIDTH=1100` 和 `1440` 运行 `node desktop/tests/desktop-flow.cjs`、`workflow-flow.cjs`。`freecad-flow.cjs` 还需要 `GONGKE_FREECAD_SESSION` 指向独立测试宿主，里面打开已保存的合成教学轴及关联 TechDraw 页；不要指向用户工程。输出分别在 `out/desktop-validation`、`out/workflow-validation`、`out/freecad-app-validation`，result.json 必须同时包含 ok 和 packaged 为 true。
