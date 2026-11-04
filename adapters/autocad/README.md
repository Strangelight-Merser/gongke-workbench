# AutoCAD 原生连接

Windows 完整版 AutoCAD 2026 的 Managed .NET 插件。工作台通过本机命名管道读取活动工程，操作真实实体；CAD API 只在 AutoCAD UI 线程执行。本文是安装集成和开发接口说明。

插件以 Autodesk 官方 NuGet 程序集编译；协议测试不加载 Autodesk 运行时。Windows AutoCAD 内的安装、编辑、Undo 和保存重开由下方现场脚本及清单检查，协议通过不代替原生宿主结果。

## 版本与安装

| 宿主 | 构建 | 真实编译引用 |
|---|---|---|
| AutoCAD 2026 至 Update 1.1 | net8.0-windows | AutoCAD.NET 25.1.0 |
| AutoCAD 2026 Update 1.2 及后续 | net10.0-windows | AutoCAD.NET 25.1.1 |

Autodesk 官方兼容表明确列出了 2026.1.2 的运行时切换。安装器只读检查宿主 `AcMgd.dll` 的 `TargetFrameworkAttribute` 标记选择包，不仅判断产品年份。首版 bundle 仅声明 R25.1；未声明 AutoCAD LT、Mac、2025、2027 或专业垂直产品支持。

产品安装器应提升权限运行生成包中的 `Install.ps1`，关闭 AutoCAD 后将匹配的 `.bundle` 安装到 `%PROGRAMFILES%\Autodesk\ApplicationPlugins`。下一次启动自动加载，无需 NETLOAD、宏、手动复制 DLL 或修改 SECURELOAD/TRUSTEDPATHS。脚本校验插件身份、宿主运行时、程序集 SHA-256；不会启动或关闭用户 CAD。AutoCAD 如果由管理员设定 `APPAUTOLOAD=0`，仍需由管理员处理该设置，本插件不静默绕过。用户升级 AutoCAD 运行时后应重新运行产品的连接安装。

```sh
python adapters/autocad/scripts/build.py --dotnet dotnet
```

构建需要 .NET 10 SDK（同时可构建 net8），通过 `packages.lock.json` 锁定官方引用；首次生成锁文件后，正式构建使用 locked restore。输出为 `adapters/autocad/artifacts/` 的两组 bundle、安装/卸载脚本和摘要清单。包只含本项目程序集，不携带 Autodesk DLL 或固定宿主运行时的 runtimeconfig。

## 本机协议

发现文件：`%LOCALAPPDATA%\Gongke\hosts\autocad-{pid}.json`。

```json
{"host_id":"autocad-<session>","host":"autocad","instance_id":"<session>","pid":123,"transport":"named_pipe","pipe_name":"gongke-autocad-123","token":"<random>","protocol_version":1}
```

客户端以当前 Windows 用户访问 `\\.\pipe\gongke-autocad-{pid}`，每行一个 UTF-8 JSON，长度至多 1 MiB。所有请求带发现文件中的 token；文件仅限本地连接使用，不进入诊断包、模型上下文或远程日志。

```json
{"id":"request-1","token":"<random>","method":"documents.list","params":{}}
{"id":"request-1","result":{"documents":[]}}
```

错误结构为 `{id,error:{code,message,outcome}}`，`outcome` 为 `unchanged` 或 `unknown`。写入成功结果含 `outcome:"committed"`。不向客户端暴露任意命令、AutoLISP、脚本或 shell。

| method | params | 结果 |
|---|---|---|
| `host.describe` | `{}` | 版本、运行时、能力、验证边界 |
| `documents.list` | `{}` | 文档会话、revision、路径、活动状态、单位；非活动文档 dirty 为 null |
| `document.snapshot` | `document_id, offset?, limit?` | 直接模型空间/图纸空间实体，分页、类型计数、真实几何/文字/测量值；后续分页必须带 `expected_revision` |
| `document.select` | `operation_id, document_id, expected_revision, handle` | 选中真实实体并切换其所属布局 |
| `drawing.edit_text` | `operation_id, document_id, expected_revision, handle, text` | 仅 TEXT/MTEXT 普通文字；原生事务、重生成、读回 |
| `drawing.move_dimension_text` | `operation_id, document_id, expected_revision, handle, position:[x,y,z]` | 仅原生 DIMENSION 文字位置；保持测量值、显示覆盖文本不变 |
| `drawing.import_dxf` | `operation_id, source_path, target_path` | 用全新空 Database 导入 DXF，新 DWG 保存及磁盘重开 |
| `document.save_copy` | `operation_id, document_id, expected_revision, target_path` | 复制当前内存数据库（包括未保存修改），保存新 DWG，磁盘重开；原窗口保持打开 |
| `document.open` | `operation_id, path` | 打开或激活现有 DWG；返回新文档会话 |
| `operation.status` | `operation_id` | 原会话、方法、参数、指纹、request_id、状态、outcome 和原始响应；跨插件重启可查 |
| `operation.cancel` | `operation_id` | 仅取消尚未开始的操作；运行中的原生事务不会被强杀 |

文件路径必须为 Windows 绝对路径；目标 DWG 必须不存在。先写同目录唯一暂存文件，再原子移动且禁止覆盖，避免检查后文件出现的竞态。`save_copy` 不修改原文档名称，也不会自动切换活动文档。因此工作台应先 `save_copy` 创建工作副本，再 `open` 副本，之后才编辑；不能把用户原工程的活动内存当作新修订。

文档身份是进程会话＋原生 Document 实例，实体以 handle 定位。对象增加、修改、删除事件推进 revision，包括宿主内的人工修改；旧 revision 的写入会拒绝。DocumentToBeDestroyed 中解除数据库事件并移除身份，避免下次请求访问已释放的数据库。快照包含 WCS 坐标、图层、实体类型、样式和支持的几何信息。LWPOLYLINE/POLYLINE 保留 bulge；圆弧保留法向；DIMENSION 保留 subtype、真实 measurement、text_override、Dimlfac、Dimscale。不能把导出的 LINE/TEXT 片段当作尺寸。嵌套块/Xref只显示其原生类型，不展开、不允许写入；锁定图层及字段驱动文字拒绝编辑。

管道线程只收发消息；Idle UI 回调调度原生操作。文字、标注和选择通过 `ExecuteInCommandContextAsync` 进入活动文档的命令上下文，使用宿主提供的命令锁，不重复 LockDocument；异常在回调内部捕获。快照与 save_copy 在 Idle 应用上下文中显式 LockDocument；写入用 StartTransaction，读取用 StartOpenCloseTransaction，事务在返回前释放。打开文档和离线 DXF 导入留在应用上下文，因此零文档时也能开始导入。普通文字不接受字段表达式；MTEXT 输入为纯文本并转义格式控制；标注仅移动文字，不修改测量或伪造显示数值。

## 操作恢复与保存语义

所有改变原生状态的请求（包括 open/select）必须携带非空 `operation_id`，客户端宜生成 UUID。cancel 使用待取消操作的 ID，不创建另一个操作。相同 ID、方法和规范化参数只返回原状态，JSON 属性顺序不影响去重；相同 ID 不同参数报 `operation_id_conflict`，绝不重放。

操作保存在 `%LOCALAPPDATA%\Gongke\hosts\autocad-operations`，同一用户的各 AutoCAD 实例共用：

- `<SHA256(operation_id)>.lock` 是永久 ID 占位；Windows 执行者持有字节范围锁（共享打开，不设置 Inheritable），其他平台独占打开，直至完成或退出。另一进程不能再次执行，也不能把活跃的 queued/running 误判为崩溃。
- 同名 `.json` 保存原会话、方法、原始参数、参数 SHA-256、原请求 ID、状态和响应。先写同目录唯一临时文件并 `Flush(true)`，再原子替换状态。`queued` 在入队前落盘，`running` 在任何原生 API 前落盘，完成回执在回复前落盘。
- 初始记录或 running 屏障写入失败不调用宿主；完成记录失败返回 `operation_store_unavailable/unknown`，不假报成功。状态文件缺失、损坏或存储不可读时不推断未执行；占位仍禁止该 ID 重放。不要把此目录作为缓存删除。

| 查询状态 | outcome | 含义及后续 |
|---|---|---|
| `queued` / `running` | `unknown` | 尚不能取得锁；可能仍执行，也可能退出后的锁释放尚未完成。继续查询原操作，不重放 |
| `completed` | `committed` | 完成响应已持久化；原响应在 `response`，其 ID 是原请求 ID |
| `failed` | `unchanged` / `unknown` | 按原生错误返回；事务提交后的 Regen/读回失败为 unknown |
| `cancelled_before_start` | `unchanged` | 在本实例排队时取消，或插件正常退出前取消 |
| `interrupted_before_start` | `unchanged` | 执行者已退出，最后持久状态为 queued，确定未进入宿主 |
| `interrupted` | `unknown` | 执行者已退出，最后持久状态为 running，必须读回 |
| `unknown` | `unknown` | 没有可信记录；不能解释为“没执行” |

Windows 的进程退出通知不是文件锁释放屏障。[LockFileEx 官方契约](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex) 指出进程终止后 OS 会解锁，但释放时间取决于系统资源。真实 AutoCAD 进程崩溃后，其锁会由 OS 回收；不能承诺 WaitForExit 返回的瞬间已经可用。插件异常但 AutoCAD 进程仍存活不等同于宿主崩溃。状态查询在锁仍冲突时保留原状态/unknown，取得锁后才报告 interrupted，永久 ID 占位始终阻止重放。

契约测试要求被终止 PID 与子进程自报的持锁 PID 一致，再在 10 秒验收上限内等待 Get 的实际恢复状态；不固定 sleep 后假定解锁，不延长产品调用超时，不在产品内重试。run `41775603833` 的 queued 持锁 PID 5224、running 持锁 PID 6272 都与 Kill 目标一致。queued 在退出后首次探测成功；running 的 WaitForExit 返回于 `04:55:27.1680277`，首次 Lock 在 `.1682506` 返回 33，下一次在 `.1799538` 已取得锁（约 12 ms）。这时普通读者和父进程 Process 句柄仍打开；不是关闭它们才恢复。running 在父进程此前的探测中从未取得锁，子进程只有持锁/写回执/等待路径，不创建孙进程，文件共享标志也没有 Inheritable。证据支持退出后异步解锁，不支持启动器漏杀、父进程自持锁或 Defender 的归因。

跨进程事务提交和回执落盘不可能成为同一个事务；本实现不自动重试 interrupted/unknown。运行中退出的内存编辑可能未保存，也可能已被用户另存；使用保存的 params 查目标文件或重新打开图纸读快照。重新打开后必须重新获取 document_id/revision/handle，旧文档会话不能复用。completed 编辑回执证明当时内存操作成功，不保证崩溃后未保存的内存仍存在。旧版 JSONL 不作为恢复依据，无兼容重放路径。

工作副本资格同时在应用层和插件执行端检查。插件只接受成功持久化的 import/save_copy 回执所指向的 **路径 + 磁盘 DWG FingerprintGuid**，因此修改原件、同内容其他路径或被不同图纸替换的文件会被拒绝。`documents.list/open/snapshot` 的文档信息包含 `is_working_copy`。应用恢复副本登记时验证原 session_id、方法、参数指纹和原请求 ID；允许查询实例的 PID/session 与原实例不同。

完整流程为 `drawing.import_dxf → document.open → document.snapshot → drawing.edit_text / drawing.move_dimension_text → document.save_copy → document.open → document.snapshot`。编辑成功表示内存已提交，**持久保存使用 save_copy 写入新的版本 DWG**，不会隐式保存或改名当前窗口。仍可在 AutoCAD 内手工正常保存工作副本；协议不增加覆盖式 document.save。DXF 导入和 save_copy 均先写 staging、磁盘重开取指纹，再 no-overwrite 发布；只有完成回执落盘才获得副本写权限。发布后若回执落盘失败，文件保留供核对，不自动覆盖、删除或授予权限。

## 验证入口

```sh
dotnet run --project adapters/autocad/Gongke.AutoCAD.ContractTests -c Release
python adapters/autocad/scripts/make_fixture.py out/autocad-native-fixture.dxf
```

协议检查实际运行本机命名管道和独立子进程：验证 token、参数顺序/Unicode 指纹、去重、取消、跨进程排他、进程强制退出后 queued/running/completed 恢复、坏记录/缺失记录、写入屏障/完成落盘失败，以及不覆盖文件；不使用伪造 Autodesk SDK。应用层恢复检查为 `python -m pytest tests/test_autocad_recovery_contract.py`。由本项目生成的 DXF 包含 LINE、LWPOLYLINE、ARC、CIRCLE、TEXT、MTEXT 和真实 DIMENSION，仅为合成测试图，不是机械设计依据。

2026-11-03 本机 macOS 验证：

| 命令 | 实际结果 |
|---|---|
| `dotnet run --project adapters/autocad/Gongke.AutoCAD.ContractTests -c Release` | net8.0，70 项通过，包含强制终止子进程和真实文件系统故障 |
| `dotnet build adapters/autocad/Gongke.AutoCAD.Addin -c Release --no-restore` | net8.0-windows、net10.0-windows 均通过，0 警告、0 错误 |
| `python -m pytest tests/test_autocad_recovery_contract.py tests/test_app_service.py -k 'host or copy_registration or solidworks_pair' -q` | 16 passed，15 deselected |

本轮使用临时目录中的 .NET 8.0.427 / 10.0.403 SDK；NuGet 在线还原遇到本机证书错误后，使用现有官方包缓存完成 locked restore，没有关闭 TLS 校验。以下 Windows 脚本及清单尚未在真实 AutoCAD 执行。

`Test-Host.ps1` 是开发/现场验收入口：在已安装桥的 AutoCAD 中，通过同一管道导入合成 DXF、读取实体、修改文字、拒绝过期快照、移动尺寸文字、另存修订、重新打开并核对文字与源文件摘要。它只使用新路径，不覆盖图纸，不自动开 CAD。输出的 evidence 带实际通过状态；当前仓库没有声称执行过它。原生 Undo、人工修改后过期、复杂原生 DWG 的块/尺寸样式按下方清单复查。

### Windows AutoCAD 现场清单

使用独立的合成测试目录，保持用户工程关闭。两个目标运行时各执行一次，并保留宿主版本与脚本输出的 evidence：

```powershell
python adapters/autocad/scripts/make_fixture.py C:/gongke-check/fixture.dxf
powershell -ExecutionPolicy Bypass -File adapters/autocad/scripts/Test-Host.ps1 `
  -FixtureDxf C:/gongke-check/fixture.dxf -OutputDirectory C:/gongke-check/run-1
```

1. **零文档和完整保存链**：从无图纸窗口开始运行脚本。确认导入无挂起；同 ID 重发得到原回执；未登记 DWG 的编辑被执行端拒绝；工作副本文字和尺寸位置可改；保存新版本并重开后文字、尺寸测量、覆盖文字、位置正确；源 DXF 和原 DWG 摘要不变。脚本在发送前记录 request_id/params，超时后也保留可查 ID。
2. **上下文与 Undo**：打开两张图，A 激活时对 B 的编辑必须报 document_not_active；B 的快照/save_copy 可在应用上下文加锁完成。进入 LINE 等交互命令后提交编辑，应排队；Esc 后才执行。正常文字/标注编辑后执行一次 U，检查只撤销该次修改并刷新 revision；人工改动后用旧 revision 必须拒绝。关闭再打开同一文件，用旧 document_id 必须拒绝。
3. **原件和事务**：在合成副本中锁定目标图层、把 TEXT 改成字段驱动或提供 DIMENSION handle 给 edit_text，分别确认拒绝且内容未变。检查 MTEXT 的反斜线/花括号按纯文本显示；尺寸测量与覆盖不变。用含多个布局、块、样式的合成 DWG 做 save_copy，人工核对保存重开后的布局/样式与未保存修改。
4. **正常重启**：记录 evidence 中第一次 import/save_copy 的 operation_id、request_id、host.instance_id；关闭并重开 AutoCAD，用新发现文件查询 operation.status。应为 completed/committed，session_id 和 response.id 仍为原值。重启工作台后查询该 ID，确认副本登记可恢复。重发原请求只返回摘要，无第二份文件。重新 open 副本后 `is_working_copy=true`。
5. **强制退出窗口**：仅对测试 AutoCAD 进程操作。调试器在 `TryDequeue` 前（queued）、running 落盘后、`tx.Commit()`/`FilePolicy.Publish()` 后但 `Complete` 前暂停并终止进程。重启后分别期望 interrupted_before_start/unchanged、interrupted/unknown、interrupted/unknown；同 ID 不能重新入队。最后一种须人工核对磁盘或内存恢复图，不能声称未执行。操作记录里的 params 提供读回目标。
6. **双实例和断连**：两个 AutoCAD 实例对同 ID 同参数同时提交，最多一个执行；另一个只查状态。执行期间断开客户端，之后查询原 ID，应得到原结果或 unknown，不能另换 ID 重发。operation.cancel 只取消当前实例尚未开始的操作；运行中的操作 cancelled=false。
7. **记录不可写**：在隔离 Windows 用户/目录用 ACL 拒绝状态目录写入（不要改用户正式数据目录）。分别在提交前、queued 后、原生提交后施加：前两者不得进入原生写入，第三者返回 operation_store_unavailable/unknown。恢复 ACL 后查询原 ID；不得把回执失败解释成未执行。坏 JSON、删除单个 JSON 但保留 lock 也必须阻止重放。

步骤 4–7 使用本文的 JSON 行协议，通过新发现文件的 pipe/token 查询；不要把 token 放入 evidence。完成现场检查后记录各项结果及 DWG/evidence 路径，不能用协议测试数字替代这些结果。

### 本次实现取舍

- 保留 Idle + 静止判断；无活动文档时在切入命令上下文前拒绝编辑，导入/打开不依赖活动文档。
- 使用小型文件状态存储及系统文件锁，不引入数据库、后台补偿任务或自动重试。原生操作提交后丢失回执的窗口保留 unknown，保存的原参数用于读回。
- 保留 save_copy 的新版本保存语义，不扩大成原件覆盖接口。`hosts.py` 仅调整 AutoCAD 跨实例恢复身份校验和 status 契约描述，SOLIDWORKS 的会话约束保持不变。

## 官方依据

- [Managed .NET 兼容版本表](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Customization/files/GUID-A6C680F2-DE2E-418A-A182-E4884073338A.htm)
- [Autodesk .NET 10 更新说明](https://blog.autodesk.io/autodesk-desktop-products-2025-2026-net-10-updates/)
- [Autodesk 官方 AutoCAD.NET 25.1.0](https://www.nuget.org/packages/AutoCAD.NET/25.1.0) / [25.1.1](https://www.nuget.org/packages/AutoCAD.NET/25.1.1)
- [DocumentLock 与原生事务](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-DevGuide-Managed/files/GUID-A2CD7540-69C5-4085-BCE8-2A8ACE16BFDD.htm)
- [DxfIn 要求全新空数据库](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_Database_DxfIn_string_string.html)
- [.bundle 安装与受信任目录](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Customization/files/GUID-5E50A846-C80B-4FFD-8DD3-C20B22098008.htm)
- [PackageContents 格式](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Customization/files/GUID-BC76355D-682B-46ED-B9B7-66C95EEF2BD0.htm)
- [命令上下文的 Autodesk 示例](https://blog.autodesk.io/creating-a-sample-autocad-plugin-with-net-80-and-ccli-for-autocad-2025/)：modeless/UI 请求进入命令上下文，管道线程不调用 CAD API。
- [Commit/Abort/Dispose 语义](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-DevGuide-Managed/files/GUID-C3DE4301-EAC3-4745-A434-9F28EE87AB73.htm)：未 Commit 的事务在 Dispose 时回滚；Commit 后读回失败不能声称回滚。
- [Wblock() 完整数据库复制](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_Database_Wblock.html)：沿用完整内存数据库复制，保存未保存的修改。
- [DocumentCollection 上下文方法](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-__MEMBERTYPE_Methods_Autodesk_AutoCAD_ApplicationServices_DocumentCollection.html)：打开/新建属于应用上下文，实体命令使用命令上下文。
- [同类 Civil 3D 集成的零文档故障记录](https://github.com/Joshua8-AI/civil3d-automation/blob/main/docs/FINDINGS.md)：作为故障场景参考，保留进入命令上下文前的零文档检查；未采用其服务架构或把其现场结果当成本插件证据。
- [文档销毁事件](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-__MEMBERTYPE_Events_Autodesk_AutoCAD_ApplicationServices_DocumentCollection.html)：在 DocumentToBeDestroyed 清理监听器；DocumentDestroyed 时底层数据库已删除。
