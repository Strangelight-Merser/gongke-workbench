# FreeCAD 单实例与退出

产品入口为模型页的“连接 FreeCAD”和 Windows 的 FreeCAD 启动按钮。二者都调用应用服务 `freecad.connect`，不允许窗口辅助程序另启 FreeCAD。安装包携带 `host-module/` 中的桥接源码；FreeCAD 本体从安装路径或 `GONGKE_FREECAD_EXE` 取得。

默认会话为用户目录 `~/.local/share/gongke/freecad-session.json`，不随工程或 Electron userData 改变。`GONGKE_FREECAD_SESSION` 仅在隔离验收时指定独立命名空间。多个工程仍使用原有文档身份、修订与工作副本约束，不以新开 FreeCAD 隔离工程。

## 生命周期契约

- 会话记录回环端口、令牌、PID、进程启动身份和随机实例 ID。发布使用权限为 0600 的临时文件并原子替换；退出仅移除令牌仍匹配的会话。
- `*.launch.lock` 串行化发现和启动；`*.bridge.lock` 在桥接存活期间持有。会话丢失但桥接锁仍被占用时，也禁止再启动。
- 发现依次核对进程身份、带令牌的 `lifecycle.identity` 回执及实例 ID。死亡进程或 PID 身份变化只清理残留会话，不向对应 PID 发信号。
- 活进程但桥接无响应时报告错误，保留会话和实例，不以重启制造第二个实例。损坏的身份文件也不能据此强关活进程。旧桥接缺少身份字段时要求该实例正常退出后重新连接，不做协议兼容。
- `lifecycle.acquire` 登记服务的随机连接 ID 和进程身份。`lifecycle.release` 清除已退出服务的登记，只有最后一个连接能请求关闭由应用启动的宿主。手动打开并加载桥接的 FreeCAD 可以借用，但不会随应用退出而关闭；没有桥接的实例既不连接也不关闭。
- 退出检查在 FreeCAD 主线程读取所有文档的 `FileName` 和 `Gui.Document.Modified`。新文档或已修改文档使退出暂停，Electron 提示具体文档名；用户在 FreeCAD 保存或关闭文档后再次退出。没有未保存文档时调用原生窗口 close，不发送强杀信号。
- `App.Document.saveAs()` 不一定清除 GUI Modified，本轮真实测试确认这一点。退出检查保留 GUI 标志，不自动保存、不清标志，也不用 `isTouched()` 代替保存状态。
- Electron 的 `before-quit` 先请求 `system.prepare_close`；工程任务未结束时拒绝退出。Windows 窗口辅助程序完成释放后，`will-quit` 通过 stdin EOF 结束 Python 服务。原生关闭取消后可继续操作，并重新检查下一次退出。

这是新增的应用内部协议，不向 Agent 暴露任意执行能力。Windows 嵌入只接受管理器返回的 FreeCAD PID；独立嵌入原型仅用于 SOLIDWORKS/合成窗口实验，真实 FreeCAD 使用完整应用路径。

## 验收进程

- `agent_modeling_trial.py` 直接启动可执行文件，保留真实 Popen 句柄；不再通过 macOS `open -W` 持有启动器 PID，也不在非 background 模式保留宿主。
- `native_modeling_freecad.py` 省略 `--endpoint` 时自行启动和回收隔离 FreeCAD。显式 `--endpoint` 是借用，不能回收借来的进程。
- `scripts/run_desktop_acceptance.py --output <新目录> --timeout <秒>` 用于 WorkBuddy 人工验收：创建隔离 FreeCAD/Electron，关闭桌面、Ctrl-C、异常或超时均按本轮句柄回收。先保存本轮需要交付的文档；本轮临时未保存文档在测试收尾中丢弃。
- Playwright 验收共享 `owned-electron.cjs`，正常关闭有超时，失败则仅终止本次启动的 ChildProcess；SIGINT/SIGTERM 走同一收尾。没有按进程名扫描/批量终止的路径。

## 本轮证据（macOS，2026-11-03）

- Python 相关回归：79 passed。包含已有桥接复用、残留会话、PID 身份改变、桥接无响应、实例锁、未保存/已保存文档、多个连接、借用宿主、脚本异常/SIGINT/SIGTERM 清理。
- 桌面构建通过；桌面测试 61 passed、1 skipped；嵌入协议测试 2 passed。构建保留原有大 chunk 提示。
- 真实 FreeCAD PID 76810：两个管理器复用同一实例；第一次 release 不关闭，最后一次 release 正常退出，exit 0。
- `tests/e2e/freecad_lifecycle_saved.py`：真实 GUI 保存后，PID 80056 按生命周期协议正常退出，exit 0。证据目录 `/var/folders/qh/smby8tjs56s7zrmf7_0klzhc0000gn/T/gongke-lifecycle-saved-5gmljyuc`。
- `desktop/tests/freecad-lifecycle-live.cjs`：从真实模型页点击“连接 FreeCAD”，再次连接返回同一 PID 83441；新文档使退出提示出现，工作台继续响应；验收结束回收自己创建的宿主和桌面。提示通过 Electron dialog 接口记录，未将替身对话框当作真实系统弹窗截图。证据目录 `/var/folders/qh/smby8tjs56s7zrmf7_0klzhc0000gn/T/gongke-lifecycle-live-xRdv09`。
- WorkBuddy 启动器 3 秒超时注入：FreeCAD 80446、Electron 80476 均回收，记录 `/tmp/gongke-3171-supervisor/processes.json`。
- 原生建模入口以缺失 study 注入异常：本轮 FreeCAD 81921 回收；错误与过程记录在 `/tmp/gongke-3171-native-failure*`。这验证启动与异常清理，不代表本轮重新验收了 P7/P8 几何。
- 完整 visual-review：14/16 场景通过，两种尺寸的 modeling 场景在点击“新建模型”时超时；交互检查通过，Electron 全部收尾。保留原断言，未把这两个失败改成通过；证据 `/tmp/gongke-3171-visual/review.json`。
- 用户指定保留的 FreeCAD 986、9285、12228、54681、55018 和 Electron 14097、51587 均保持原启动身份；未向它们发送关闭信号。

仍需 Windows 实机执行 `desktop/native/embed/test-windows.ps1` 和完整应用的 FreeCAD 连接、嵌入、未保存提示、保存后退出流程。本机没有 dotnet/Windows 宿主，未声称通过 C# 编译或 HWND 实测。没有运行付费 Agent 建模或真实 WorkBuddy 账号交互。

## 依据

- [Electron app 生命周期](https://www.electronjs.org/docs/latest/api/app)：before-quit 可阻止退出；app.quit 路径可能不触发 window-all-closed，因此服务收尾放在 will-quit。
- [FreeCAD GUI Document API](https://freecad.github.io/SourceDoc/de/d4e/classGui_1_1Document.html) 与 [Python GUI 保存接口源码](https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/DocumentPyImp.cpp)：文档保存状态属于 GUI 文档；本机进一步核对了实际 Python 属性 Modified 和 GUI 保存行为。
- [同类 FreeCAD MCP 的文档状态说明](https://github.com/hram/freecad-mcp#какие-документы-не-сохранены)：区分 Modified、isSaved 和 isTouched，并记录 App.saveAs 可能保留 GUI Modified。采用这一区分，不引入该项目的兼容模式或任意代码执行接口。
